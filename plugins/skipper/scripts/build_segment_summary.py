#!/usr/bin/env python3
"""정리예시 시트 생성 — 연도별·분기별 부문 매출액과 비중 표.

원본 엑셀 '정리예시' 탭의 두 표를 그대로 만든다:
  1. 연도별 매출액 및 비중 (단위: 백만원)
  2. 분기별 매출액 및 비중 (단위: 백만원, 단일분기 기준)

부문 수치는 /api/v1/revenue-segments 에서 받는다. 서버가 연결/별도(fsDiv)·
표(roleKey)·기간을 하나로 좁혀 주므로 한 부문이 한 번만 나오고, 단일분기(Q2·Q4)도
서버가 누적에서 차감해 유도한다 — 여기서 다시 계산하지 않는다.

2단계로 쓴다.

  --draft  API 응답으로 초안 JSON을 만든다. 커버리지가 비면 null로 남긴다.
           (기업에 따라 XBRL 부문 매출이 없거나 연결 매출과 어긋난다. 초안은
           출발점일 뿐이고, 원문 '매출 및 수주상황' 표로 검증·보정해야 한다.)
  --data   보정된 JSON을 읽어 CSV를 만든다. 합계와 비중은 여기서 계산한다 —
           손으로 넣지 마라.

사용:
  python3 build_segment_summary.py "SK" --draft draft.json
  python3 build_segment_summary.py "SK" --data draft.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skipper_api import SkipperError, call, fail, resolve, segments, write_csv  # noqa: E402

UNIT_DIVISOR = 1_000_000  # 원 → 백만원
QUARTER_BY_MONTH = {"03": 1, "06": 2, "09": 3, "12": 4}


def is_total(name: str) -> bool:
    """합계 행은 부문이 아니다 — 합계는 스크립트가 다시 계산한다."""
    return re.sub(r"\s+", "", name or "") in {"합계", "부문합계", "총계", "소계"}


def quarter_labels(latest: tuple[int, int], count: int) -> list[str]:
    """(2026, 1)에서 5개 → ['25.1Q','25.2Q','25.3Q','25.4Q','26.1Q']."""
    year, quarter = latest
    labels: list[str] = []
    for _ in range(count):
        labels.append(f"{year % 100:02d}.{quarter}Q")
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    return list(reversed(labels))


def parse_quarter_label(label: str) -> tuple[int, int]:
    """'25.1Q' → (2025, 1). 두 자리 연도는 2000년대로 읽는다."""
    match = re.match(r"\s*(\d{2,4})\.(\d)Q\s*$", label)
    if not match:
        raise ValueError(f"분기 라벨 형식이 아닙니다: {label!r} (예: 25.1Q)")
    year = int(match.group(1))
    return (2000 + year if year < 100 else year, int(match.group(2)))


def latest_quarter(ticker: str) -> tuple[int, int]:
    """가장 최근 정기보고서에서 최신 분기를 읽는다. 실패하면 오늘 기준으로 추정한다."""
    try:
        listing = call("list_disclosures", ticker=ticker, category="정기공시", days=600, limit=10)
        for item in listing.get("kr_disclosures") or []:
            match = re.search(r"\((\d{4})\.(\d{2})\)", item.get("title", ""))
            if match and match.group(2) in QUARTER_BY_MONTH:
                return int(match.group(1)), QUARTER_BY_MONTH[match.group(2)]
    except SkipperError:
        pass
    today = date.today()
    return today.year, max(1, (today.month - 1) // 3)


def collect(ticker: str, period: str, limit: int) -> tuple[dict[tuple[str, int], dict], list[dict]]:
    """한 기간 토큰을 조회해 {(정규화부문명, 연도): item}과 연도별 메타를 돌려준다.

    조인 키는 name이 아니라 normalizedName이다 — 발행사가 해마다 표기를 바꾸므로
    ('카카오' ↔ '㈜카카오') name으로 이으면 한 부문이 두 줄로 갈린다.
    """
    store: dict[tuple[str, int], dict] = {}
    meta: list[dict] = []
    try:
        groups = segments(ticker, period=period, limit=limit)
    except SkipperError as exc:
        print(f"  {period} 조회 실패: {exc}", file=sys.stderr)
        return store, meta
    for group in groups:
        try:
            year = int(group.get("calendarYear") or 0)
        except (TypeError, ValueError):
            continue
        if not year:
            continue
        meta.append({
            "year": year,
            "period": group.get("period") or period,
            "roleKey": group.get("roleKey") or "",
            "fsDiv": group.get("fsDiv") or "",
        })
        for item in group.get("items") or []:
            name = item.get("name") or ""
            if is_total(name):
                continue
            store[(item.get("normalizedName") or name, year)] = item
    return store, meta


def to_mn(item: dict | None) -> int | None:
    """금액을 백만원으로. 서버가 유도에 실패하면 amount가 null이므로 그대로 비운다."""
    amount = (item or {}).get("amount")
    return round(amount / UNIT_DIVISOR) if isinstance(amount, (int, float)) else None


def display_names(stores: list[dict[tuple, dict]]) -> dict[str, str]:
    """정규화부문명 → 표시명 (가장 최근 연도의 공시 표기)."""
    best: dict[str, tuple[int, str]] = {}
    for store in stores:
        for key, item in store.items():
            norm, year = key[0], key[1]
            if norm not in best or year > best[norm][0]:
                best[norm] = (year, item.get("name") or norm)
    return {norm: label for norm, (_, label) in best.items()}


def build_draft(company: dict[str, str], years: int,
                quarters: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """API 응답으로 초안을 만든다. 커버 밖 칸은 null로 남겨 보정 대상임을 드러낸다."""
    ticker = company["ticker"]

    annual_store, metas = collect(ticker, "FY", years + 1)

    quarter_periods = quarter_labels(latest_quarter(ticker), quarters)
    parsed = [parse_quarter_label(label) for label in quarter_periods]
    span = max(y for y, _ in parsed) - min(y for y, _ in parsed) + 2
    quarter_store: dict[tuple[str, int, int], dict] = {}
    for slot in sorted({q for _, q in parsed}):
        store, meta = collect(ticker, f"Q{slot}", span)
        metas.extend(meta)
        for (norm, year), item in store.items():
            quarter_store[(norm, year, slot)] = item

    labels = display_names([annual_store, quarter_store])

    fact_years = sorted({year for _, year in annual_store})
    last_year = fact_years[-1] if fact_years else date.today().year - 1
    annual_periods = [str(last_year - i) for i in range(years - 1, -1, -1)]

    annual: dict[str, list[Any]] = {}
    quarterly: dict[str, list[Any]] = {}
    for norm in sorted(labels):
        label = labels[norm]
        annual[label] = [to_mn(annual_store.get((norm, int(y)))) for y in annual_periods]
        quarterly[label] = [to_mn(quarter_store.get((norm, y, q))) for y, q in parsed]

    derived = sum(1 for i in quarter_store.values() if i.get("derived"))
    rejected = sum(1 for i in quarter_store.values()
                   if i.get("note") == "negative_derivation")
    role_keys = sorted({m["roleKey"] for m in metas if m["roleKey"]})
    fs_divs = sorted({m["fsDiv"] for m in metas if m["fsDiv"]})

    draft = {
        "company": company["name"],
        "ticker": ticker,
        "unit": "백만원",
        "annual": {"periods": annual_periods, "segments": annual},
        "quarterly": {"periods": quarter_periods, "segments": quarterly},
        "sources": [],
        "provenance": {
            "endpoint": "GET /api/v1/revenue-segments (iceberg 원천)",
            "fsDiv": fs_divs,
            "roleKeys": role_keys,
        },
        "_주의": (
            "XBRL 부문 팩트로 만든 초안입니다. 분기 값은 단일분기 기준이며 Q2·Q4는 "
            "서버가 누적에서 차감해 유도한 값입니다. 정기보고서의 '4. 매출 및 수주상황' / "
            "'2. 주요 제품 및 서비스' 표와 대조해 검증하고, 부문 구분이 다르면 원문을 "
            "따르세요. 합계와 비중은 렌더링 단계에서 계산하므로 넣지 마십시오."
        ),
    }
    stats = {"derived": derived, "rejected": rejected,
             "role_keys": role_keys, "fs_divs": fs_divs}
    return draft, stats


def table_rows(company: str, title: str, block: dict[str, Any]) -> list[list[Any]]:
    """표 하나 — 부문별 매출액, 합계, 부문별 비중."""
    periods = block.get("periods") or []
    segments_map = block.get("segments") or {}
    rows: list[list[Any]] = [[title], ["구분", *periods]]

    # 한 부문이라도 값이 비면 그 기간의 합계·비중은 내지 않는다 — 부분합을 합계로
    # 쓰면 비중이 100%로 부풀어 그대로 오독된다. 값이 진짜 0이면 JSON에 0을 넣고,
    # 모르는 값만 null로 남긴다.
    totals: list[float | None] = []
    for index in range(len(periods)):
        values = [v[index] if index < len(v) else None for v in segments_map.values()]
        if values and all(isinstance(v, (int, float)) for v in values):
            totals.append(sum(values))
        else:
            totals.append(None)

    for member, values in segments_map.items():
        padded = list(values) + [None] * (len(periods) - len(values))
        rows.append([f"{company} {member} 매출액",
                     *["" if v is None else v for v in padded]])

    rows.append(["합계", *["" if t is None else round(t) for t in totals]])

    for member, values in segments_map.items():
        padded = list(values) + [None] * (len(periods) - len(values))
        share: list[Any] = []
        for index, value in enumerate(padded):
            total = totals[index]
            if isinstance(value, (int, float)) and total:
                share.append(f"{value / total * 100:.1f}%")
            else:
                share.append("")
        rows.append([f"{company} {member} 매출 비중", *share])

    return rows


def render(spec: dict[str, Any]) -> list[list[Any]]:
    """정리예시 탭 구조 그대로 — 1. 연도별 표, 2. 분기별 표, 출처."""
    company = spec.get("company", "")
    unit = spec.get("unit", "백만원")
    grid: list[list[Any]] = [[]]
    grid.extend(table_rows(company, f"1. 연도별 매출액 및 비중 (단위: {unit})", spec.get("annual") or {}))
    grid.append([])
    grid.extend(table_rows(company, f"2. 분기별 매출액 및 비중 (단위: {unit}, 단일분기 기준)",
                           spec.get("quarterly") or {}))
    sources = spec.get("sources") or []
    if sources:
        grid.append([])
        grid.append(["출처"])
        for source in sources:
            if isinstance(source, dict):
                grid.append([f"{source.get('title', '')}  접수번호 {source.get('rcept_no', '')}"])
            else:
                grid.append([str(source)])
    return grid


def main() -> None:
    parser = argparse.ArgumentParser(description="정리예시 시트(CSV) 생성")
    parser.add_argument("company", help="회사명 또는 6자리 종목코드")
    parser.add_argument("--draft", metavar="JSON", help="초안 JSON을 이 경로에 쓴다")
    parser.add_argument("--data", metavar="JSON", help="보정된 JSON을 읽어 CSV를 만든다")
    parser.add_argument("--years", type=int, default=5, help="연도별 표 연수 (기본 5)")
    parser.add_argument("--quarters", type=int, default=5, help="분기별 표 분기수 (기본 5)")
    parser.add_argument("--out", default=None, help="출력 CSV 경로")
    args = parser.parse_args()

    if not args.draft and not args.data:
        fail("--draft 또는 --data 중 하나를 지정하세요. 먼저 --draft로 초안을 만드십시오.")
        return

    if args.data:
        try:
            with open(args.data, encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError) as exc:
            fail(f"{args.data} 를 읽지 못했습니다: {exc}")
            return
        out = args.out or f"{spec.get('company', args.company)}_정리예시_{date.today():%Y%m%d}.csv"
        write_csv(out, render(spec))
        filled = sum(1 for block in ("annual", "quarterly")
                     for values in (spec.get(block) or {}).get("segments", {}).values()
                     for v in values if isinstance(v, (int, float)))
        print(f"생성: {out}")
        print(f"채워진 값 {filled}칸 — 빈 칸은 원문에서 확인되지 않은 자리입니다.")
        return

    try:
        company = resolve(args.company)
    except SkipperError as exc:
        fail(str(exc))
        return

    draft, stats = build_draft(company, args.years, args.quarters)
    with open(args.draft, "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=2)

    members = draft["annual"]["segments"]

    def filled(block: str) -> tuple[int, int]:
        values = [v for row in draft[block]["segments"].values() for v in row]
        return sum(1 for v in values if v is not None), len(values)

    annual_filled, annual_total = filled("annual")
    quarter_filled, quarter_total = filled("quarterly")

    print(f"초안 생성: {args.draft}")
    print(f"기업: {company['name']} ({company['ticker']})")
    print(f"연도별 기간: {', '.join(draft['annual']['periods'])}  "
          f"→ {annual_filled}/{annual_total}칸 채움")
    print(f"분기별 기간: {', '.join(draft['quarterly']['periods'])}  "
          f"→ {quarter_filled}/{quarter_total}칸 채움 (단일분기 기준)")
    if members:
        print(f"부문 후보 {len(members)}개: " + ", ".join(members))
    else:
        # 0행은 "이 기업에 부문 공시가 없다"가 아니다 — 팩트 적재가 아직 안 됐을 수도
        # 있다. 둘을 구분할 수 없으므로 단정하지 않고 원문 확인으로 넘긴다.
        print("부문 후보 없음 — XBRL 부문 팩트가 조회되지 않았습니다.")
        print("      부문 공시가 없는 기업일 수도, 팩트가 아직 적재되지 않은 것일 수도")
        print("      있습니다. 원문 '4. 매출 및 수주상황' 표를 열어 직접 확인하세요.")

    if stats["fs_divs"]:
        print(f"기준: {', '.join(stats['fs_divs'])}  "
              f"표: {', '.join(k[:46] for k in stats['role_keys']) or '(미기록)'}")
    if stats["derived"]:
        print(f"단일분기 유도값 {stats['derived']}칸 (Q2=반기−1Q, Q4=연간−3분기누적).")

    # 표가 둘 이상이면 시계열이 표를 넘나든 것이다 — 표마다 같은 부문의 금액이
    # 달라 증감률이 그대로 오독된다. 값을 지우지는 않되 반드시 드러낸다.
    if len(stats["role_keys"]) > 1:
        print(f"\n경고: 기간에 따라 서로 다른 표가 채택됐습니다 ({len(stats['role_keys'])}종).")
        for key in stats["role_keys"]:
            print(f"      - {key}")
        print("      표마다 같은 부문의 금액이 다릅니다. 표가 바뀐 경계에서 증감률을")
        print("      해석하지 말고, 원문 '4. 매출 및 수주상황' 표로 연결성을 확인하세요.")

    if stats["rejected"]:
        print(f"\n경고: 차감 결과가 음수라 서버가 폐기한 칸이 {stats['rejected']}개입니다.")
        print("      보고서마다 부문 표의 범위가 다르게 태깅됐다는 뜻입니다 (지주회사에서 흔함).")
        print("      해당 분기는 원문 '4. 매출 및 수주상황' 표에서 직접 읽어 채우세요.")

    print("\n다음: 정기보고서 '4. 매출 및 수주상황' 표와 대조해 검증·보정한 뒤 --data 로 렌더링하세요.")


if __name__ == "__main__":
    main()
