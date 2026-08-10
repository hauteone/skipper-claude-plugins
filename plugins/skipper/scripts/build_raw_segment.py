#!/usr/bin/env python3
"""Raw_부문별매출 시트 생성 — 정기보고서별 '주요 제품 및 서비스' 원문 + 부문 팩트 표.

원본 엑셀 'Raw_부문별매출' 탭은 사업·반기·분기보고서의 "2. 주요 제품 및 서비스"
섹션을 보고서마다 복사해 옆으로 붙인 것이다. 이 스크립트는 같은 구조를 재현하고,
그 아래에 XBRL 부문 팩트를 표로 덧붙인다 — 원문은 표 구조가 평문으로 눌려 있어
숫자 작업에는 팩트 표가 필요하다.

사용:
  python3 build_raw_segment.py "SK" --reports 5
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skipper_api import SkipperError, call, fail, resolve, segments, write_csv  # noqa: E402

# 부문 매출이 실리는 두 섹션. '4. 매출 및 수주상황'에 부문별 매출·비중 표가 있고,
# '2. 주요 제품 및 서비스'에는 부문 설명과 종속회사 현황이 있다. 둘 다 필요하다.
SECTION_KEYWORDS = ("주요 제품", "매출 및 수주")
BLOCK_WIDTH = 2  # 본문 1열 + 블록 사이 여백 1열
WRAP_WIDTH = 200

AXIS_NAMES = {"segment": "사업부문", "region": "지역", "product": "제품"}
METRIC_NAMES = {
    "revenue": "매출액", "operating_profit": "영업이익", "assets": "자산",
    "liabilities": "부채", "profit_loss": "손익", "cost_of_sales": "매출원가",
    "gross_profit": "매출총이익", "goodwill": "영업권", "depreciation": "감가상각비",
    "amortisation": "무형자산상각비", "other": "기타",
}
DURATION_NAMES = {"fy": "연간", "q3m": "3개월", "ytd": "누적", "instant": "시점"}

# 연간 + 단일분기 4개. 누적(H1·9M)은 분기 합과 겹쳐 표를 부풀리므로 기본에서 뺀다.
DEFAULT_PERIODS = ("FY", "Q1", "Q2", "Q3", "Q4")


def split_lines(text: str) -> list[str]:
    """평문 섹션을 읽을 수 있는 행으로 쪼갠다 — 한국어 문장 끝과 길이 기준."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    # '...습니다.' / '...입니다.' 같은 종결 뒤에서 끊는다.
    chunks = re.split(r"(?<=다\.)\s+", text)
    lines: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        while len(chunk) > WRAP_WIDTH:
            cut = chunk.rfind(" ", 0, WRAP_WIDTH)
            cut = cut if cut > WRAP_WIDTH // 2 else WRAP_WIDTH
            lines.append(chunk[:cut].strip())
            chunk = chunk[cut:].strip()
        if chunk:
            lines.append(chunk)
    return lines


def fetch_via_series(company: str, reports: int) -> list[dict[str, Any]]:
    """segment_series 한 번으로 보고서 섹션을 가져온다 — 원문은 공시 원본에서 온다.

    같은 응답의 xbrl_facts는 쓰지 않는다. 그쪽은 그래프 적재분이라 표(roleKey)와
    연결/별도(fsDiv) 구분이 없어 한 부문이 여러 값으로 갈린다 — 숫자는
    fetch_facts()가 iceberg 원천에서 직접 받는다.
    """
    data = call("segment_series", query=company, years=reports, quarters=reports)
    picked = []
    for report in (data.get("reports") or [])[:reports]:
        sections = [s for s in report.get("sections") or [] if s.get("title") != "__TOC__"]
        if not sections:
            continue
        picked.append({
            "title": report.get("title", ""),
            "rcept_no": report.get("rcept_no", ""),
            "date": report.get("date", ""),
            "period_hint": report.get("period_hint", ""),
            "sections": sections,
        })
    return picked


def fetch_facts(ticker: str, axes: list[str], metrics: list[str],
                periods: list[str], limit: int) -> list[dict[str, Any]]:
    """부문 팩트 — 축·지표·기간 조합마다 조회해 한 표로 평탄화한다.

    서버가 조합마다 표(roleKey)를 하나로 고정하므로 같은 부문이 중복되지 않는다.
    Q2·Q4는 누적 차감으로 유도된 값이라 derived 플래그가 붙는다.
    """
    rows: list[dict[str, Any]] = []
    for axis in axes:
        for metric in metrics:
            for period in periods:
                try:
                    groups = segments(ticker, axis=axis, metric=metric,
                                      period=period, limit=limit)
                except SkipperError as exc:
                    print(f"  건너뜀 {axis}/{metric}/{period}: {exc}", file=sys.stderr)
                    continue
                for group in groups:
                    for item in group.get("items") or []:
                        rows.append({
                            "year": group.get("calendarYear", ""),
                            "period": group.get("period", period),
                            "fs_div": group.get("fsDiv", ""),
                            "role_key": group.get("roleKey", ""),
                            "axis_type": group.get("axis", axis),
                            "member": item.get("name", ""),
                            "normalized": item.get("normalizedName", ""),
                            "metric": group.get("metric", metric),
                            "amount": item.get("amount"),
                            "duration_type": item.get("durationType", ""),
                            "derived": bool(item.get("derived")),
                            "note": item.get("note", ""),
                        })
    return rows


def fetch_via_documents(ticker: str, reports: int) -> list[dict[str, Any]]:
    """폴백 — 정기공시 목록을 훑어 보고서별 섹션을 개별 조회한다."""
    listing = call("list_disclosures", ticker=ticker, category="정기공시",
                   days=2000, limit=max(reports * 2, 20))
    picked: list[dict[str, Any]] = []
    for item in listing.get("kr_disclosures") or []:
        if len(picked) >= reports:
            break
        rcept_no = item.get("rcept_no")
        if not rcept_no:
            continue
        # get_document는 키워드 하나만 받으므로 섹션별로 나눠 부르고 합친다.
        sections: list[dict[str, Any]] = []
        seen: set[str] = set()
        doc_date = ""
        for keyword in SECTION_KEYWORDS:
            try:
                doc = call("get_document", doc_id=rcept_no, section=keyword)
            except SkipperError as exc:
                print(f"  건너뜀 {rcept_no} ({keyword}): {exc}", file=sys.stderr)
                continue
            doc_date = doc_date or doc.get("date", "")
            for section in doc.get("sections") or []:
                title = section.get("title", "")
                if title == "__TOC__" or title in seen:
                    continue
                seen.add(title)
                sections.append(section)
        if not sections:
            continue
        sections.sort(key=lambda s: s.get("title", ""))
        picked.append({
            "title": item.get("title", ""),
            "rcept_no": rcept_no,
            "date": doc_date,
            "period_hint": "",
            "sections": sections,
        })
    return picked


def build_block(report: dict[str, Any]) -> list[list[Any]]:
    """보고서 하나의 원문 블록 (세로 행 목록, 각 행 길이 BLOCK_WIDTH)."""
    header = [report["title"]]
    meta = f"접수번호 {report['rcept_no']}"
    if report.get("date"):
        meta += f"  ({report['date']})"
    if report.get("period_hint"):
        meta += f"  — {report['period_hint']}"
    rows: list[list[Any]] = [header, [meta], []]
    for section in report["sections"]:
        rows.append([f"■ {section.get('title', '')}"])
        rows.extend([line] for line in split_lines(section.get("text", "")))
        rows.append([])
    return [row + [""] * (BLOCK_WIDTH - len(row)) for row in rows]


def facts_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
    """XBRL 부문 팩트를 정렬된 표로 — 금액은 백만원.

    표(roleKey)와 연결/별도(fsDiv)를 함께 낸다. 같은 부문이라도 표가 다르면 금액이
    다르므로, 연도 간 증감을 볼 때 이 두 열이 같은지 먼저 확인해야 한다.
    """
    if not rows:
        return [["XBRL 부문 팩트 없음 — 원문 섹션의 표에서 직접 읽어야 합니다."]]
    out: list[list[Any]] = [
        ["연도", "기간", "기준", "기간유형", "축", "부문/지역/제품", "정규화명",
         "지표", "금액(백만원)", "비고", "표(roleKey)"]
    ]

    def key(r: dict[str, Any]) -> tuple:
        return (str(r.get("axis_type") or ""), str(r.get("metric") or ""),
                str(r.get("year") or ""), str(r.get("period") or ""),
                str(r.get("member") or ""))

    for r in sorted(rows, key=key, reverse=True):
        amount = r.get("amount")
        remark = []
        if r.get("derived"):
            remark.append("유도값")
        if r.get("note"):
            remark.append(r["note"])
        out.append([
            r.get("year", ""),
            r.get("period", ""),
            r.get("fs_div", ""),
            DURATION_NAMES.get(r.get("duration_type") or "", r.get("duration_type") or ""),
            AXIS_NAMES.get(r.get("axis_type") or "", r.get("axis_type") or ""),
            r.get("member", ""),
            r.get("normalized", ""),
            METRIC_NAMES.get(r.get("metric") or "", r.get("metric") or ""),
            round(amount / 1_000_000) if isinstance(amount, (int, float)) else "",
            " / ".join(remark),
            r.get("role_key", ""),
        ])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw_부문별매출 시트(CSV) 생성")
    parser.add_argument("company", help="회사명 또는 6자리 종목코드")
    parser.add_argument("--reports", type=int, default=5, help="붙일 정기보고서 개수 (최신순, 기본 5)")
    parser.add_argument("--axes", default="segment",
                        help="팩트 축 (쉼표 구분: segment,region,product. 기본 segment)")
    parser.add_argument("--metrics", default="revenue",
                        help="팩트 지표 (쉼표 구분. 기본 revenue)")
    parser.add_argument("--periods", default=",".join(DEFAULT_PERIODS),
                        help=f"팩트 기간 (쉼표 구분. 기본 {','.join(DEFAULT_PERIODS)})")
    parser.add_argument("--years", type=int, default=5, help="팩트 연도 수 (기본 5)")
    parser.add_argument("--out", default=None, help="출력 CSV 경로")
    args = parser.parse_args()

    def split_arg(value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    try:
        company = resolve(args.company)
    except SkipperError as exc:
        fail(str(exc))
        return

    source = "segment_series(원문) + revenue-segments(팩트)"
    try:
        reports = fetch_via_series(company["ticker"], args.reports)
    except SkipperError as exc:
        print(f"segment_series 사용 불가 ({exc}) — 공시 원문 조회로 폴백합니다.", file=sys.stderr)
        source = "list_disclosures + get_document(원문) + revenue-segments(팩트)"
        reports = fetch_via_documents(company["ticker"], args.reports)

    facts = fetch_facts(company["ticker"], split_arg(args.axes), split_arg(args.metrics),
                        split_arg(args.periods), args.years)

    if not reports:
        fail(f"{company['name']}: '주요 제품 및 서비스' 섹션이 있는 정기보고서를 찾지 못했습니다.")
        return

    grid: list[list[Any]] = []
    blocks = [build_block(r) for r in reports]
    height = max(len(b) for b in blocks)
    for i in range(height):
        row: list[Any] = []
        for block in blocks:
            row.extend(block[i] if i < len(block) else [""] * BLOCK_WIDTH)
        grid.append(row)

    grid.append([])
    grid.append([f"■ XBRL 부문 팩트 ({company['name']} {company['ticker']}) — 원문 표의 구조화 값"])
    grid.extend(facts_rows(facts))

    out = args.out or f"{company['name']}_Raw_부문별매출_{date.today():%Y%m%d}.csv"
    write_csv(out, grid)

    print(f"생성: {out}")
    print(f"기업: {company['name']} ({company['ticker']})  출처: {source}")
    print(f"보고서 {len(reports)}건:")
    for r in reports:
        titles = ", ".join(s.get("title", "") for s in r["sections"])
        print(f"  - {r['title']}  접수번호 {r['rcept_no']}  [{titles}]")
    print(f"XBRL 부문 팩트 {len(facts)}행")
    if not facts:
        print("주의: 부문 팩트가 비어 있습니다 — 숫자는 원문 섹션에서 직접 읽어야 합니다.")
        return

    derived = sum(1 for f in facts if f.get("derived"))
    rejected = sum(1 for f in facts if f.get("note") == "negative_derivation")
    if derived:
        print(f"  단일분기 유도값 {derived}행 (Q2=반기−1Q, Q4=연간−3분기누적)")
    if rejected:
        print(f"  차감 결과가 음수라 폐기된 칸 {rejected}행 — 해당 분기는 원문에서 읽으세요")

    # 축·지표별로 표가 하나로 고정됐는지 확인한다. 여러 개면 그 시계열은 표를
    # 넘나든 것이라 연도 간 증감을 그대로 읽으면 안 된다.
    tables: dict[tuple[str, str], set[str]] = {}
    for f in facts:
        if f.get("role_key"):
            tables.setdefault((f["axis_type"], f["metric"]), set()).add(f["role_key"])
    mixed = {k: v for k, v in tables.items() if len(v) > 1}
    if mixed:
        print("\n경고: 기간에 따라 서로 다른 표가 채택된 조합이 있습니다.")
        for (axis, metric), keys in mixed.items():
            names = f"{AXIS_NAMES.get(axis, axis)}/{METRIC_NAMES.get(metric, metric)}"
            print(f"      {names}: {len(keys)}종")
            for key in sorted(keys):
                print(f"        - {key}")
        print("      표마다 같은 부문의 금액이 다릅니다 — 표가 바뀐 경계에서 증감률을")
        print("      해석하지 말고 원문 표로 연결성을 확인하세요.")


if __name__ == "__main__":
    main()
