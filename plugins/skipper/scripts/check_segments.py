#!/usr/bin/env python3
"""부문 데이터 정합성 검사 — 워크북에 넣기 전에 숫자가 앞뒤가 맞는지 확인한다.

부문 API가 표(roleKey)와 연결/별도(fsDiv)를 하나로 좁혀 주지만, 좁혀진 값이
'맞는' 값이라는 보장은 없다. 잘못 태깅된 표를 골랐어도 응답은 깔끔하게 나온다.
이 스크립트는 원문을 열지 않고도 잡을 수 있는 모순을 찾는다.

검사 6종:
  C1 부문명 중복      한 응답에 같은 부문이 두 번 나오면 좁히기가 실패한 것
  C2 매출 음수        매출은 음수일 수 없다
  C3 H1 + Q3 = 9M    서로 다른 보고서의 직접 태깅값끼리 맞아야 한다 (유도 무관)
  C4 ΣQ1..Q4 = FY    C3의 따름정리지만 유도 경로가 달라 따로 본다
  C5 부문합 = 연결매출  손익계산서 매출과 대조한다. 초과분이 크면 부문 하나가 과대
  C6 표·부문 일관성    기간마다 표가 바뀌면 그 경계에서 증감률은 성립하지 않는다

C5가 가장 강하다 — 부문 밖 독립 지표와 맞대므로, 표를 잘못 골라 한 부문이
부풀었을 때 이것만 잡아낸다.

사용:
  python3 check_segments.py 034730
  python3 check_segments.py 034730 005930 006260 --year 2025
  python3 check_segments.py --top 30          # 여러 종목 스윕
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skipper_api import SkipperError, get_json, resolve, segments  # noqa: E402

# 부문합이 연결매출을 넘을 수 있는 정상 범위. 부문 매출에는 내부거래가 포함되고
# 연결매출은 그것을 제거한 뒤라, 부문합이 조금 큰 것은 정상이다. 크게 넘으면
# 한 부문이 다른 기준(총액·상위 연결범위)으로 태깅됐다는 신호다.
DEFAULT_TOLERANCE = 15.0  # %


def pct(a: float, b: float) -> float:
    return (a - b) / b * 100 if b else 0.0


def fetch(symbol: str, period: str, limit: int) -> dict[int, dict[str, Any]]:
    """{연도: 그룹} — 연도별로 하나씩."""
    try:
        groups = segments(symbol, period=period, limit=limit)
    except SkipperError:
        return {}
    out = {}
    for g in groups:
        try:
            out[int(g.get("calendarYear") or 0)] = g
        except (TypeError, ValueError):
            continue
    return out


def amounts(group: dict[str, Any] | None) -> dict[str, int]:
    """{정규화부문명: 금액} — null 은 제외한다."""
    if not group:
        return {}
    return {i.get("normalizedName") or i.get("name"): i["amount"]
            for i in (group.get("items") or [])
            if isinstance(i.get("amount"), (int, float))}


def consolidated_revenue(symbol: str, limit: int) -> dict[tuple[int, str], int]:
    """{(연도, 기간): 연결매출} — 손익계산서."""
    out: dict[tuple[int, str], int] = {}
    try:
        rows = get_json(f"/api/v1/income-statement/{symbol}", period="quarter", limit=limit)
    except SkipperError:
        return out
    for r in rows if isinstance(rows, list) else []:
        try:
            year = int(r.get("calendarYear") or 0)
        except (TypeError, ValueError):
            continue
        rev = r.get("revenue")
        if year and isinstance(rev, (int, float)):
            out[(year, str(r.get("period") or ""))] = int(rev)
    return out


class Report:
    def __init__(self, symbol: str, name: str) -> None:
        self.symbol, self.name = symbol, name
        self.findings: list[tuple[str, str, str]] = []  # (검사, 심각도, 메시지)

    def add(self, check: str, severity: str, message: str) -> None:
        self.findings.append((check, severity, message))

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for _, s, _ in self.findings)


def check(symbol: str, name: str, year: int, tolerance: float) -> Report:
    rep = Report(symbol, name)
    limit = 6
    per = {p: fetch(symbol, p, limit) for p in ("FY", "H1", "9M", "Q1", "Q2", "Q3", "Q4")}

    groups_this_year = {p: g.get(year) for p, g in per.items()}
    if not any(groups_this_year.values()):
        rep.add("C0", "SKIP", f"{year}년 부문 데이터 없음")
        return rep

    # C1 부문명 중복 / C2 음수
    for period, group in groups_this_year.items():
        items = (group or {}).get("items") or []
        names = [i.get("name") for i in items]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            rep.add("C1", "FAIL", f"{period}: 부문명 중복 {sorted(dupes)}")
        neg = [(i.get("name"), i["amount"]) for i in items
               if isinstance(i.get("amount"), (int, float)) and i["amount"] < 0]
        if neg:
            rep.add("C2", "FAIL", f"{period}: 매출 음수 {neg}")

    # C3 H1 + Q3 = 9M
    h1, q3, m9 = (amounts(groups_this_year[p]) for p in ("H1", "Q3", "9M"))
    if h1 and q3 and m9:
        bad = []
        for key in sorted(set(h1) & set(q3) & set(m9)):
            diff = pct(h1[key] + q3[key], m9[key])
            if abs(diff) > 0.01:
                bad.append(f"{key} {diff:+.2f}%")
        rep.add("C3", "FAIL" if bad else "PASS",
                f"H1+Q3 vs 9M: {'불일치 ' + ', '.join(bad) if bad else '전 부문 일치'}")

    # C4 ΣQ1..Q4 = FY
    quarters = [amounts(groups_this_year[f"Q{i}"]) for i in (1, 2, 3, 4)]
    fy = amounts(groups_this_year["FY"])
    if fy and all(quarters):
        bad = []
        for key in sorted(set(fy)):
            if not all(key in q for q in quarters):
                continue
            diff = pct(sum(q[key] for q in quarters), fy[key])
            if abs(diff) > 0.01:
                bad.append(f"{key} {diff:+.2f}%")
        rep.add("C4", "FAIL" if bad else "PASS",
                f"ΣQ1..Q4 vs FY: {'불일치 ' + ', '.join(bad) if bad else '전 부문 일치'}")

    # C5 부문합 = 연결매출
    cons = consolidated_revenue(symbol, limit * 5)
    for period in ("FY", "Q1", "Q3"):
        seg = amounts(groups_this_year[period])
        target = cons.get((year, period))
        if not seg or not target:
            continue
        total = sum(seg.values())
        over = pct(total, target)
        if over <= tolerance:
            rep.add("C5", "PASS", f"{period}: 부문합 {total/1e12:.1f}조 vs 연결 "
                                  f"{target/1e12:.1f}조 ({over:+.1f}%)")
            continue
        # 어느 부문을 빼면 허용 범위에 들어오는지 짚는다 — 과대 태깅 후보.
        suspect = ""
        for member, value in sorted(seg.items(), key=lambda kv: -kv[1]):
            if abs(pct(total - value, target)) <= tolerance:
                suspect = f"  ← '{member}'({value/1e12:.1f}조) 제외 시 {pct(total-value, target):+.1f}%"
                break
        rep.add("C5", "FAIL", f"{period}: 부문합 {total/1e12:.1f}조 vs 연결 "
                              f"{target/1e12:.1f}조 ({over:+.1f}%){suspect}")

    # C6 표·부문 집합 일관성
    roles = {g.get("roleKey") for g in groups_this_year.values() if g and g.get("roleKey")}
    if len(roles) > 1:
        rep.add("C6", "WARN", f"기간마다 다른 표 {len(roles)}종: {sorted(roles)}")
    member_sets = {p: frozenset(amounts(g)) for p, g in groups_this_year.items() if g}
    if len({frozenset(s) for s in member_sets.values()}) > 1:
        base = max(member_sets.values(), key=len)
        diffs = {p: sorted(base ^ s) for p, s in member_sets.items() if s != base}
        rep.add("C6", "WARN", f"기간마다 부문 구성이 다름: {diffs}")

    return rep


def main() -> None:
    parser = argparse.ArgumentParser(description="부문 데이터 정합성 검사")
    parser.add_argument("symbols", nargs="*", help="6자리 종목코드 또는 회사명")
    parser.add_argument("--year", type=int, default=0, help="검사 연도 (기본: 직전 연도)")
    parser.add_argument("--top", type=int, default=0,
                        help="스크리너 상위 N종목을 대상으로 스윕 (symbols 대신)")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help=f"C5 부문합 초과 허용률 %% (기본 {DEFAULT_TOLERANCE})")
    args = parser.parse_args()

    from datetime import date
    year = args.year or date.today().year - 1

    targets: list[tuple[str, str]] = []
    if args.top:
        try:
            rows = get_json("/api/v1/stock-list", limit=args.top)
        except SkipperError as exc:
            print(f"오류: 종목 목록 조회 실패 — {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        for r in (rows if isinstance(rows, list) else [])[:args.top]:
            sym = r.get("symbol") or r.get("shortcode") or ""
            if sym:
                targets.append((sym, r.get("name") or r.get("title") or sym))
    else:
        for q in args.symbols:
            try:
                c = resolve(q)
                targets.append((c["ticker"], c["name"]))
            except SkipperError as exc:
                print(f"  건너뜀 {q}: {exc}", file=sys.stderr)

    if not targets:
        print("검사할 종목이 없습니다. 종목코드를 주거나 --top N 을 쓰세요.", file=sys.stderr)
        raise SystemExit(1)

    print(f"부문 정합성 검사 — {year}년, 종목 {len(targets)}개, C5 허용률 {args.tolerance}%\n")
    failed = 0
    for symbol, name in targets:
        rep = check(symbol, name, year, args.tolerance)
        mark = "FAIL" if rep.failed else ("SKIP" if any(s == "SKIP" for _, s, _ in rep.findings) else "PASS")
        failed += rep.failed
        print(f"{'='*74}\n[{mark}] {name} ({symbol})\n{'='*74}")
        for c, sev, msg in rep.findings:
            print(f"  {sev:4} {c}  {msg}")
        if not rep.findings:
            print("  (검사 항목 없음)")
        print()

    print(f"요약: {len(targets)}종목 중 FAIL {failed}건")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
