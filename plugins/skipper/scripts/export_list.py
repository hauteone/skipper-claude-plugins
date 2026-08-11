#!/usr/bin/env python3
"""목록형 데이터 CSV 내보내기 — REST를 직접 호출해 모델 컨텍스트를 거치지 않는다.

스크리너·공시·리서치 리포트처럼 건수가 많은 목록형 응답을 MCP로 가져오면
대화 컨텍스트를 크게 잡아먹는다. 이 스크립트는 REST 엔드포인트를 직접 호출해
전체(또는 서버 상한까지)를 로컬 CSV로 저장하고, 화면에는 건수·경로·미리보기만
출력한다.

사용:
  python3 export_list.py screener --param market=KOSPI
  python3 export_list.py disclosures --symbol 005930
  python3 export_list.py latest-disclosures --param from=2026-01-01
  python3 export_list.py kr-research-reports --param query=반도체
  python3 export_list.py historical-prices --symbol 005930 --param from=2020-01-01
  python3 export_list.py stock-list

페이지네이션 데이터셋(공시·리서치)은 기본 --max-pages 만큼만 가져오고 멈춘다.
더 남았으면 안내가 출력된다 — 같은 필터에 --start-page N --append --out <경로>를
붙여 다시 실행하면 이어서 같은 파일에 쌓인다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skipper_api import SkipperError, fail, get_json  # noqa: E402

PAGE_SIZE = 100  # 페이지네이션 엔드포인트의 서버 상한

# 데이터셋 정의.
#   path: REST 경로 ({symbol} 치환), mode: single(1회) | paged(page 순회)
#   unwrap: 응답이 {"historical": [...]}처럼 감싸져 있으면 그 필드명
#   fixed: 항상 붙는 쿼리 파라미터 (서버 상한까지 최대한 가져오는 값)
DATASETS: dict[str, dict[str, Any]] = {
    "screener": {
        "path": "/api/v1/screener",
        "mode": "single",
        "fixed": {"limit": 200},
        "note": "서버 상한 200건 — 시가총액 내림차순 상위 200개까지만 온다",
    },
    "latest-disclosures": {
        "path": "/api/v1/disclosures",
        "mode": "paged",
        "note": "시장 전체 공시 — 양이 많으므로 기본 묶음 단위로 끊어 가져온다",
    },
    "disclosures": {
        "path": "/api/v1/disclosures/{symbol}",
        "mode": "paged",
        "needs_symbol": True,
    },
    "kr-research-reports": {
        "path": "/api/v1/kr-research-reports",
        "mode": "paged",
        "note": "symbol 미지정 시 시장 전체 — 양이 많으므로 묶음 단위로 끊어 가져온다",
    },
    "stock-list": {
        "path": "/api/v1/stock-list",
        "mode": "single",
    },
    "historical-prices": {
        "path": "/api/v1/historical-price-full/{symbol}",
        "mode": "single",
        "needs_symbol": True,
        "unwrap": "historical",
        "fixed": {"limit": 5000},
    },
    "investor-flows": {
        "path": "/api/v1/investor-flows/{symbol}",
        "mode": "single",
        "needs_symbol": True,
        "unwrap": "historical",
        "fixed": {"limit": 365},
    },
    "dividends": {
        "path": "/api/v1/dividends/{symbol}",
        "mode": "single",
        "needs_symbol": True,
        "unwrap": "historical",
        "fixed": {"limit": 120},
    },
    "ratios": {
        "path": "/api/v1/ratios/{symbol}",
        "mode": "single",
        "needs_symbol": True,
        "fixed": {"limit": 120},
    },
    "etf-holdings": {
        "path": "/api/v1/etf-holdings/{symbol}",
        "mode": "single",
        "needs_symbol": True,
        "unwrap": "holdings",
    },
}

DEFAULT_MAX_PAGES = 5  # paged 데이터셋 1회 실행당 기본 묶음 (5페이지 = 최대 500건)


def flatten(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """중첩 dict는 점 표기로 펴고, 리스트는 JSON 문자열로 담는다.

    investor-flows의 investors 맵({"foreignTotal": {"netValue": ...}})이
    investors.foreignTotal.netValue 열이 되는 식이다.
    """
    flat: dict[str, Any] = {}
    for key, value in row.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, prefix=f"{name}."))
        elif isinstance(value, list):
            flat[name] = json.dumps(value, ensure_ascii=False)
        else:
            flat[name] = value
    return flat


def collect_columns(rows: list[dict[str, Any]]) -> list[str]:
    """열 순서 = 처음 등장한 순서 (JSON 필드 순서 유지)."""
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def existing_columns(path: str) -> list[str]:
    """--append 시 기존 파일의 헤더를 읽어 열 순서를 맞춘다."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh), [])
    return header


def write_rows(path: str, columns: list[str], rows: list[dict[str, Any]], append: bool) -> None:
    """UTF-8 BOM으로 쓴다 — 엑셀에서 더블클릭해도 한글이 깨지지 않는다."""
    mode = "a" if append else "w"
    with open(path, mode, newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        if not append:
            writer.writerow(columns)
        for row in rows:
            writer.writerow([("" if row.get(c) is None else row.get(c, "")) for c in columns])


def fetch_single(path: str, params: dict[str, Any], unwrap: str | None) -> list[dict[str, Any]]:
    data = get_json(path, **params)
    if unwrap and isinstance(data, dict):
        data = data.get(unwrap) or []
    if not isinstance(data, list):
        raise SkipperError(f"예상과 다른 응답 형식입니다 (list가 아님): {str(data)[:200]}")
    return data


def fetch_paged(path: str, params: dict[str, Any], start_page: int,
                max_pages: int) -> tuple[list[dict[str, Any]], int, bool]:
    """(rows, 마지막으로 읽은 page, 더 남았을 가능성) — 짧은 페이지가 나오면 끝."""
    rows: list[dict[str, Any]] = []
    fetched_last = start_page - 1  # 아직 아무 페이지도 안 읽은 상태
    last_full = False
    for offset in range(max_pages):
        page = start_page + offset
        chunk = get_json(path, page=page, limit=PAGE_SIZE, **params)
        if not isinstance(chunk, list):
            raise SkipperError(f"예상과 다른 응답 형식입니다 (list가 아님): {str(chunk)[:200]}")
        rows.extend(chunk)
        fetched_last = page
        last_full = len(chunk) >= PAGE_SIZE
        if not last_full:
            break
    return rows, fetched_last, last_full


def parse_extra_params(pairs: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            fail(f"--param은 key=value 형식이어야 합니다: {pair}")
        key, _, value = pair.partition("=")
        params[key] = value
    return params


def main() -> None:
    parser = argparse.ArgumentParser(description="skipper 목록형 데이터 CSV 내보내기")
    parser.add_argument("dataset", choices=sorted(DATASETS), help="내보낼 데이터셋")
    parser.add_argument("--symbol", default="", help="KRX 6자리 종목코드 (종목 단위 데이터셋 필수)")
    parser.add_argument("--param", action="append", default=[],
                        help="추가 쿼리 파라미터 key=value (반복 지정 가능). 예: --param market=KOSPI")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"페이지네이션 데이터셋의 1회 실행당 페이지 수 (기본 {DEFAULT_MAX_PAGES} = 최대 {DEFAULT_MAX_PAGES * PAGE_SIZE}건)")
    parser.add_argument("--start-page", type=int, default=0, help="이어받기 시작 페이지 (0-베이스)")
    parser.add_argument("--append", action="store_true", help="기존 CSV에 이어붙인다 (헤더 생략)")
    parser.add_argument("--out", default=None, help="출력 CSV 경로")
    args = parser.parse_args()

    spec = DATASETS[args.dataset]
    if spec.get("needs_symbol") and not args.symbol:
        fail(f"{args.dataset}은(는) --symbol이 필요합니다 (KRX 6자리 종목코드)")

    params = {**spec.get("fixed", {}), **parse_extra_params(args.param)}
    path = spec["path"].format(symbol=args.symbol)

    key = args.symbol or params.get("market", "") or "all"
    out = args.out or f"{args.dataset}_{key}_{date.today():%Y%m%d}.csv"
    if args.append and not os.path.exists(out):
        fail(f"--append 대상 파일이 없습니다: {out} (--out으로 기존 파일을 지정하세요)")

    try:
        if spec["mode"] == "paged":
            raw, last_page, maybe_more = fetch_paged(path, params, args.start_page, args.max_pages)
        else:
            raw = fetch_single(path, params, spec.get("unwrap"))
            last_page, maybe_more = 0, False
    except SkipperError as exc:
        fail(str(exc))
        return  # fail이 SystemExit을 던지지만 타입체커용

    rows = [flatten(r) for r in raw]
    columns = existing_columns(out) if args.append else collect_columns(rows)
    write_rows(out, columns, rows, args.append)

    # 화면 출력은 최소한으로 — 건수·경로·미리보기 5행. 전체 데이터는 파일에만 있다.
    print(f"데이터셋: {args.dataset}")
    if spec.get("note"):
        print(f"참고: {spec['note']}")
    print(f"이번 실행 수집: {len(rows)}건 → {out} ({'이어붙임' if args.append else '새 파일'})")
    print(f"열 {len(columns)}개: {', '.join(columns[:12])}{' ...' if len(columns) > 12 else ''}")
    if rows:
        print("\n미리보기 (상위 5행):")
        preview_cols = columns[:8]
        print("  " + " | ".join(preview_cols))
        for row in rows[:5]:
            print("  " + " | ".join(str(row.get(c, ""))[:20] for c in preview_cols))
    if maybe_more:
        print(
            f"\n마지막 페이지가 꽉 차 있어 더 남아 있을 수 있습니다 (page {last_page}까지 수집)."
            f"\n이어서 가져오려면 (같은 필터 인자를 그대로 붙여서):"
            f"\n  python3 export_list.py {args.dataset} --start-page {last_page + 1} --append --out {out}"
        )
    elif spec["mode"] == "paged":
        print("\n마지막 페이지까지 모두 수집했습니다.")


if __name__ == "__main__":
    main()
