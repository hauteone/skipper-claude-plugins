#!/usr/bin/env python3
"""Raw_BSPL 시트 생성 — 정기보고서별 연결재무제표 4표를 열 블록으로 나란히 편다.

원본 엑셀 'Raw_BSPL' 탭은 DART 뷰어의 "2. 연결재무제표"(재무상태표·포괄손익계산서·
자본변동표·현금흐름표)를 보고서마다 복사해 옆으로 붙인 것이다. 이 스크립트는 같은
구조를 OpenDART 전체계정(fs_reports)에서 구조화된 값으로 재현한다.

사용:
  python3 build_raw_bspl.py "SK" --reports 4 --unit 백만원
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skipper_api import SkipperError, call, fail, write_csv  # noqa: E402

# 보고서 종류 — 같은 사업연도 안에서의 시간 순서. DART reprt_code 기준.
REPORT_NAMES = {"11013": "1분기보고서", "11012": "반기보고서", "11014": "3분기보고서", "11011": "사업보고서"}
REPORT_ORDER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}

# 재무제표 출력 순서 — DART 뷰어의 2-1 ~ 2-4 순서를 그대로 따른다.
STATEMENTS = [("BS", "재무상태표"), ("CIS", "포괄손익계산서"), ("SCE", "자본변동표"), ("CF", "현금흐름표")]

UNITS = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "억원": 100_000_000}

# 블록 한 칸의 열 구성 (마지막은 블록 사이 여백).
BLOCK_WIDTH = 9


def parse_amount(raw: Any, divisor: int) -> Any:
    """DART 금액 문자열 → 지정 단위 숫자. 빈 값·비수치는 그대로 흘린다."""
    if raw in (None, "", "-"):
        return ""
    text = str(raw).replace(",", "").strip()
    try:
        value = float(text)
    except ValueError:
        return raw
    value /= divisor
    return int(value) if value == int(value) else round(value, 2)


def report_label(report: dict[str, Any], company: str) -> str:
    """'SK 2025년 사업보고서 (연결)' 형태의 블록 제목."""
    name = REPORT_NAMES.get(report.get("reprt_code", ""), report.get("period_type", ""))
    basis = "연결" if report.get("fs_div") == "CFS" else "별도"
    return f"{company} {report.get('bsns_year', '')}년 {name} ({basis})"


def sort_key(report: dict[str, Any]) -> tuple[int, int]:
    """최신 보고서가 먼저 오도록 (사업연도, 보고서순서) 내림차순 정렬용 키."""
    year = int(report.get("bsns_year") or 0)
    return (year, REPORT_ORDER.get(report.get("reprt_code", ""), 0))


def first_value(accounts: list[dict[str, Any]], key: str) -> str:
    """계정 목록에서 해당 키의 첫 번째 값 (기간명 추출용)."""
    for account in accounts:
        if account.get(key):
            return str(account[key])
    return ""


def statement_headers(accounts: list[dict[str, Any]]) -> list[str]:
    """표 하나의 금액 컬럼 6개에 붙일 헤더.

    DART는 표마다 기간 표기가 다르다. 분기보고서의 손익계산서·현금흐름표는
    frmtrm_nm 없이 frmtrm_q_amount(전년동기)만 채우고, 재무상태표는 시점값이라
    누적·3개월 칸이 비어 있다. 실제로 값이 들어찬 칸에만 라벨을 붙인다.
    """
    used = {k: any(a.get(k) for a in accounts) for k in
            ("thstrm_amount", "thstrm_add_amount", "frmtrm_amount",
             "frmtrm_q_amount", "frmtrm_add_amount", "bfefrmtrm_amount")}
    current = first_value(accounts, "thstrm_nm")
    prior_nm = first_value(accounts, "frmtrm_nm")
    prior2 = first_value(accounts, "bfefrmtrm_nm")

    # 당기 누적칸이 따로 있으면 당기칸은 3개월(단일분기) 수치다.
    current_label = f"{current} 3개월" if used["thstrm_add_amount"] else current
    # 분기보고서는 frmtrm_nm이 없다 — frmtrm_amount는 직전기, frmtrm_q_amount는
    # 전년동기라서 폴백 라벨을 서로 다르게 준다.
    prior_label = prior_nm or "전기"
    prior_q = prior_nm or "전년동기"
    prior_q_label = f"{prior_q} 3개월" if used["frmtrm_add_amount"] else prior_q

    labels = [
        current_label if used["thstrm_amount"] else "",
        f"{current} 누적" if used["thstrm_add_amount"] else "",
        prior_label if used["frmtrm_amount"] else "",
        prior_q_label if used["frmtrm_q_amount"] else "",
        f"{prior_q} 누적" if used["frmtrm_add_amount"] else "",
        prior2 if used["bfefrmtrm_amount"] else "",
    ]
    detail = "세부" if any(a.get("account_detail") for a in accounts) else ""
    return ["구분", detail, *labels]


def build_block(report: dict[str, Any], company: str, divisor: int,
                unit: str, wanted: list[str]) -> list[list[Any]]:
    """보고서 하나를 세로 행 목록으로 만든다. 각 행의 길이는 BLOCK_WIDTH."""
    accounts = json.loads(report.get("accounts") or "[]")
    rows: list[list[Any]] = [
        [report_label(report, company)],
        [f"접수번호 {report.get('rcept_no', '')}"],
        [f"(단위 : {unit}, 통화 {report.get('currency', 'KRW')})"],
    ]

    for sj_div, sj_label in STATEMENTS:
        if sj_div not in wanted:
            continue
        picked = [a for a in accounts if a.get("sj_div") == sj_div]
        if not picked:
            continue
        picked.sort(key=lambda a: int(a.get("ord") or 0))
        rows.append([])
        rows.append([f"■ {sj_label}"])
        rows.append(statement_headers(picked))
        for account in picked:
            rows.append([
                account.get("account_nm", ""),
                account.get("account_detail", ""),
                parse_amount(account.get("thstrm_amount"), divisor),
                parse_amount(account.get("thstrm_add_amount"), divisor),
                parse_amount(account.get("frmtrm_amount"), divisor),
                parse_amount(account.get("frmtrm_q_amount"), divisor),
                parse_amount(account.get("frmtrm_add_amount"), divisor),
                parse_amount(account.get("bfefrmtrm_amount"), divisor),
            ])

    return [row + [""] * (BLOCK_WIDTH - len(row)) for row in rows]


def merge_blocks(blocks: list[list[list[Any]]]) -> list[list[Any]]:
    """블록들을 좌우로 이어 붙인다. 짧은 블록은 빈 칸으로 채운다."""
    height = max((len(b) for b in blocks), default=0)
    merged: list[list[Any]] = []
    for i in range(height):
        row: list[Any] = []
        for block in blocks:
            row.extend(block[i] if i < len(block) else [""] * BLOCK_WIDTH)
        merged.append(row)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw_BSPL 시트(CSV) 생성")
    parser.add_argument("company", help="회사명 또는 6자리 종목코드")
    parser.add_argument("--reports", type=int, default=4, help="붙일 보고서 개수 (최신순, 기본 4)")
    parser.add_argument("--fs-div", default="CFS", choices=["CFS", "OFS", "both"],
                        help="CFS=연결(기본), OFS=별도, both=둘 다")
    parser.add_argument("--unit", default="백만원", choices=list(UNITS), help="금액 단위 (기본 백만원)")
    parser.add_argument("--statements", default="BS,CIS,SCE,CF",
                        help="포함할 재무제표 (BS,CIS,SCE,CF 중 콤마 구분)")
    parser.add_argument("--out", default=None, help="출력 CSV 경로")
    parser.add_argument("--from-json", default=None,
                        help="fs_reports 도구 응답 JSON 파일 경로 ('-'면 표준입력). 주면 "
                             "네트워크를 전혀 쓰지 않는다 — SKIPPER_API_KEY/SKIPPER_ACCESS_TOKEN도 "
                             "필요 없다. 에이전트가 MCP로 fs_reports를 직접 호출해 받은 응답을 "
                             "그대로 넘기는 용도다.")
    args = parser.parse_args()

    wanted = [s.strip().upper() for s in args.statements.split(",") if s.strip()]
    divisor = UNITS[args.unit]

    if args.from_json:
        raw = sys.stdin.read() if args.from_json == "-" else open(args.from_json, encoding="utf-8").read()
        try:
            data = json.loads(raw)
        except ValueError as exc:
            fail(f"--from-json 내용이 JSON이 아닙니다: {exc}")
            return
        if isinstance(data, dict) and data.get("error"):
            fail(str(data["error"]))
            return
    else:
        try:
            data = call("fs_reports", query=args.company)
        except SkipperError as exc:
            fail(str(exc))
            return

    company = (data.get("company") or {}).get("name") or args.company
    reports = [r for r in data.get("reports") or [] if r.get("accounts")]
    if args.fs_div != "both":
        reports = [r for r in reports if r.get("fs_div") == args.fs_div]
    if not reports:
        fail(f"{company}: 조건에 맞는 전계정 재무제표 보고서가 없습니다 (fs_div={args.fs_div}).")
        return

    reports.sort(key=sort_key, reverse=True)
    selected = reports[: args.reports]

    blocks = [build_block(r, company, divisor, args.unit, wanted) for r in selected]
    grid = merge_blocks(blocks)

    out = args.out or f"{company}_Raw_BSPL_{date.today():%Y%m%d}.csv"
    write_csv(out, grid)

    print(f"생성: {out}")
    print(f"기업: {company} ({(data.get('company') or {}).get('ticker', '')})")
    print(f"보고서 {len(selected)}건 (단위 {args.unit}):")
    for r in selected:
        print(f"  - {report_label(r, company)}  접수번호 {r.get('rcept_no')}  계정 {r.get('account_count')}개")
    remaining = len(reports) - len(selected)
    if remaining > 0:
        print(f"미포함 보고서 {remaining}건 — 더 넣으려면 --reports 를 올리세요.")


if __name__ == "__main__":
    main()
