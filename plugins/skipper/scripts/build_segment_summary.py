#!/usr/bin/env python3
"""정리예시 시트 생성 — 연도별·분기별 부문 매출액과 비중 표.

원본 엑셀 '정리예시' 탭의 두 표를 그대로 만든다:
  1. 연도별 매출액 및 비중 (단위: 백만원)
  2. 분기별 매출액 및 비중 (단위: 백만원, 단일분기 기준)

2단계로 쓴다.

  --draft  XBRL 부문 팩트로 초안 JSON을 만든다. 커버리지가 비면 null로 남긴다.
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
from skipper_api import SkipperError, call, fail, resolve, write_csv  # noqa: E402

UNIT_DIVISOR = 1_000_000  # 원 → 백만원
QUARTER_BY_MONTH = {"03": 1, "06": 2, "09": 3, "12": 4}
# 정기보고서 종류 → 그 보고서가 끝내는 분기.
REPORT_QUARTER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}


def normalize_member(name: str) -> str:
    """부문명 표기 흔들림을 흡수한다 ('SK이노베이션 계열' / 'SK이노베이션㈜' → 'SK이노베이션')."""
    text = re.sub(r"\s+", " ", name or "").strip()
    text = re.sub(r"(㈜|\(주\)|주식회사)", "", text)
    text = re.sub(r"\s*계열$", "", text.strip())
    return text.strip()


def is_total(name: str) -> bool:
    """합계 행은 부문이 아니다 — 합계는 스크립트가 다시 계산한다."""
    return normalize_member(name).replace(" ", "") in {"합계", "부문합계", "총계", "소계"}


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


def fetch_facts(ticker: str) -> list[dict[str, Any]]:
    """부문 매출 팩트 — segment_series 우선, 없으면 segment_facts."""
    try:
        data = call("segment_series", query=ticker, years=5, quarters=5)
        return (data.get("xbrl_facts") or {}).get("rows") or []
    except SkipperError:
        try:
            return (call("segment_facts", query=ticker) or {}).get("rows") or []
        except SkipperError:
            return []


def index_facts(facts: list[dict[str, Any]]) -> dict[tuple[str, int, int], dict[str, int]]:
    """부문 매출 팩트를 (부문, 사업연도, 분기) → {기간유형: 백만원}으로 색인한다."""
    store: dict[tuple[str, int, int], dict[str, int]] = {}
    for fact in facts:
        if fact.get("axis_type") != "segment" or fact.get("metric") != "revenue":
            continue
        if is_total(fact.get("member", "")):
            continue
        amount = fact.get("amount")
        quarter = REPORT_QUARTER.get(str(fact.get("reprt_code") or ""))
        try:
            year = int(fact.get("bsns_year") or 0)
        except (TypeError, ValueError):
            continue
        if not year or not quarter or not isinstance(amount, (int, float)):
            continue
        duration = fact.get("duration_type") or ("fy" if quarter == 4 else "ytd")
        key = (normalize_member(fact.get("member", "")), year, quarter)
        store.setdefault(key, {})[duration] = round(amount / UNIT_DIVISOR)
    return store


def cumulative(store: dict, member: str, year: int, quarter: int) -> int | None:
    """해당 분기까지의 누적 매출. 1분기는 누적과 단일이 같다."""
    cell = store.get((member, year, quarter)) or {}
    if "ytd" in cell:
        return cell["ytd"]
    if quarter == 4 and "fy" in cell:
        return cell["fy"]
    if quarter == 1 and "q3m" in cell:
        return cell["q3m"]
    return None


def single_quarter(store: dict, member: str, year: int, quarter: int) -> tuple[int | None, str]:
    """단일분기 매출과 그 출처. 3개월 팩트가 있으면 그 값, 없으면 누적 차감.

    반기보고서는 상반기 누적, 3분기보고서는 9개월 누적, 사업보고서는 연간이라
    그대로 쓰면 분기 표가 부풀어 오른다.

    차감 결과가 음수면 버린다. 매출은 음수일 수 없으므로, 음수는 두 보고서의
    부문 표가 서로 다른 범위로 태깅됐다는 신호다 (지주회사에서 흔하다). 그런
    값을 그대로 내보내면 워크북에 -59조 같은 수치가 그대로 박힌다.
    """
    cell = store.get((member, year, quarter)) or {}
    if "q3m" in cell:
        return cell["q3m"], "q3m"
    current = cumulative(store, member, year, quarter)
    if current is None:
        return None, "none"
    if quarter == 1:
        return current, "q3m"
    previous = cumulative(store, member, year, quarter - 1)
    if previous is None:
        return None, "none"
    value = current - previous
    if value < 0:
        return None, "rejected"
    return value, "derived"


def build_draft(company: dict[str, str], facts: list[dict[str, Any]],
                years: int, quarters: int) -> tuple[dict[str, Any], dict[str, int]]:
    """XBRL 팩트로 초안을 만든다. 커버 밖 칸은 null로 남겨 보정 대상임을 드러낸다."""
    store = index_facts(facts)
    members = sorted({key[0] for key in store})

    fact_years = sorted({key[1] for key in store if "fy" in store[key]})
    last_year = fact_years[-1] if fact_years else date.today().year - 1
    annual_periods = [str(last_year - i) for i in range(years - 1, -1, -1)]
    annual = {
        member: [(store.get((member, int(year), 4)) or {}).get("fy") for year in annual_periods]
        for member in members
    }

    quarter_periods = quarter_labels(latest_quarter(company["ticker"]), quarters)
    parsed = [parse_quarter_label(label) for label in quarter_periods]
    quarterly: dict[str, list[Any]] = {}
    rejected = 0
    for member in members:
        row: list[Any] = []
        for year, quarter in parsed:
            value, provenance = single_quarter(store, member, year, quarter)
            rejected += provenance == "rejected"
            row.append(value)
        quarterly[member] = row

    draft = {
        "company": company["name"],
        "ticker": company["ticker"],
        "unit": "백만원",
        "annual": {"periods": annual_periods, "segments": annual},
        "quarterly": {"periods": quarter_periods, "segments": quarterly},
        "sources": [],
        "_주의": (
            "XBRL 부문 팩트로 만든 초안입니다. 분기 값은 3개월 팩트가 있으면 그 값을, "
            "없으면 누적에서 직전 누적을 빼 단일분기로 환산했습니다. 정기보고서의 "
            "'4. 매출 및 수주상황' / '2. 주요 제품 및 서비스' 표와 대조해 검증하고, "
            "부문 구분이 다르면 원문을 따르세요. 합계와 비중은 렌더링 단계에서 "
            "계산하므로 넣지 마십시오."
        ),
    }
    return draft, {"rejected": rejected}


def table_rows(company: str, title: str, block: dict[str, Any]) -> list[list[Any]]:
    """표 하나 — 부문별 매출액, 합계, 부문별 비중."""
    periods = block.get("periods") or []
    segments = block.get("segments") or {}
    rows: list[list[Any]] = [[title], ["구분", *periods]]

    # 한 부문이라도 값이 비면 그 기간의 합계·비중은 내지 않는다 — 부분합을 합계로
    # 쓰면 비중이 100%로 부풀어 그대로 오독된다. 값이 진짜 0이면 JSON에 0을 넣고,
    # 모르는 값만 null로 남긴다.
    totals: list[float | None] = []
    for index in range(len(periods)):
        values = [v[index] if index < len(v) else None for v in segments.values()]
        if values and all(isinstance(v, (int, float)) for v in values):
            totals.append(sum(values))
        else:
            totals.append(None)

    for member, values in segments.items():
        padded = list(values) + [None] * (len(periods) - len(values))
        rows.append([f"{company} {member} 매출액",
                     *["" if v is None else v for v in padded]])

    rows.append(["합계", *["" if t is None else round(t) for t in totals]])

    for member, values in segments.items():
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

    facts = fetch_facts(company["ticker"])
    draft, stats = build_draft(company, facts, args.years, args.quarters)
    with open(args.draft, "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=2)

    segments = draft["annual"]["segments"]

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
          f"→ {quarter_filled}/{quarter_total}칸 채움 (단일분기 환산 적용)")
    if segments:
        print(f"부문 후보 {len(segments)}개: " + ", ".join(segments))
    else:
        # 0행은 "이 기업에 부문 공시가 없다"가 아니다 — 팩트 적재가 아직 안 됐을 수도
        # 있다. 둘을 구분할 수 없으므로 단정하지 않고 원문 확인으로 넘긴다.
        print("부문 후보 없음 — XBRL 부문 팩트가 조회되지 않았습니다.")
        print("      부문 공시가 없는 기업일 수도, 팩트가 아직 적재되지 않은 것일 수도")
        print("      있습니다. 원문 '4. 매출 및 수주상황' 표를 열어 직접 확인하세요.")

    if stats["rejected"]:
        print(f"\n경고: 누적 차감 결과가 음수라 폐기한 칸이 {stats['rejected']}개입니다.")
        print("      보고서마다 부문 표의 범위가 다르게 태깅됐다는 뜻입니다 (지주회사에서 흔함).")
        print("      이 기업의 분기 표는 XBRL로 만들 수 없습니다 — 원문 '4. 매출 및 수주상황'")
        print("      표에서 직접 읽어 채우세요. 남아 있는 분기 값도 같은 이유로 의심해야 합니다.")

    print("\n다음: 정기보고서 '4. 매출 및 수주상황' 표와 대조해 검증·보정한 뒤 --data 로 렌더링하세요.")


if __name__ == "__main__":
    main()
