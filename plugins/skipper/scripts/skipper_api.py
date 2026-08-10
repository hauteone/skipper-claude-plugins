"""skipper 공개 API 클라이언트 — 표준 라이브러리만 사용한다.

스킬의 빌드 스크립트가 그래프 도구를 직접 호출할 때 쓴다. fs_reports처럼 응답이
수 MB인 도구를 모델 컨텍스트를 거치지 않고 받아 파일로 떨구기 위한 경로다.

필요 환경변수:
  SKIPPER_API_KEY   발급받은 API 키 (플러그인 .mcp.json이 쓰는 키와 동일)
  SKIPPER_API_URL   기본값 https://api.skipperlabs.ai

개발용 우회 (SkipperLabs 내부 전용): SKIPPER_GRAPH_URL과 SKIPPER_INTERNAL_TOKEN이
함께 설정되면 그래프 내부 엔드포인트를 직접 호출한다. 외부 사용자와는 무관하다.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_API_URL = "https://api.skipperlabs.ai"
DEFAULT_TIMEOUT = 180

_NO_KEY_MESSAGE = (
    "SKIPPER_API_KEY 환경변수가 비어 있습니다. 발급받은 키를 셸에 설정하세요:\n"
    '  export SKIPPER_API_KEY="sk-skp-..."\n'
    "키 발급 문의: support@skipperlabs.ai"
)


class SkipperError(RuntimeError):
    """도구 호출 실패 — 메시지를 사용자에게 그대로 보여줄 수 있는 수준으로 적는다."""


def _endpoint() -> tuple[str, dict[str, str], bool]:
    """(URL 템플릿, 헤더, 내부모드) — 내부모드면 인자를 {"args": ...}로 감싼다."""
    graph_url = os.environ.get("SKIPPER_GRAPH_URL", "").rstrip("/")
    internal_token = os.environ.get("SKIPPER_INTERNAL_TOKEN", "")
    if graph_url and internal_token:
        return (
            graph_url + "/internal/tools/{name}",
            {"Content-Type": "application/json", "X-Internal-Token": internal_token},
            True,
        )
    api_key = os.environ.get("SKIPPER_API_KEY", "").strip()
    if not api_key:
        raise SkipperError(_NO_KEY_MESSAGE)
    base = os.environ.get("SKIPPER_API_URL", DEFAULT_API_URL).rstrip("/")
    return (
        base + "/api/v1/tools/{name}",
        {"Content-Type": "application/json", "X-API-Key": api_key},
        False,
    )


def _rest_target() -> tuple[str, dict[str, str]]:
    """(베이스 URL, 헤더) — REST 엔드포인트 직접 호출용.

    도구 게이트웨이(/api/v1/tools/{name})는 그래프 도구 화이트리스트만 통과시키므로,
    iceberg 원천을 직접 읽는 엔드포인트는 게이트웨이를 거치지 않고 이 경로로 부른다.
    내부 우회(SKIPPER_GRAPH_URL)는 그래프 전용이라 여기서는 쓰지 않는다.
    """
    api_key = os.environ.get("SKIPPER_API_KEY", "").strip()
    if not api_key:
        raise SkipperError(_NO_KEY_MESSAGE)
    base = os.environ.get("SKIPPER_API_URL", DEFAULT_API_URL).rstrip("/")
    return base, {"X-API-Key": api_key}


def _fetch(req: urllib.request.Request, label: str, timeout: int) -> Any:
    """요청을 보내고 JSON을 파싱한다 — 오류는 전부 SkipperError로 통일한다."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 401:
            raise SkipperError(
                f"API 키 인증 실패 (401) — SKIPPER_API_KEY를 확인하세요. 응답: {detail}"
            ) from exc
        raise SkipperError(f"{label} 호출 실패 (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise SkipperError(f"{label} 호출 실패 — 네트워크 오류: {exc.reason}") from exc

    try:
        return json.loads(body)
    except ValueError as exc:
        raise SkipperError(f"{label} 응답이 JSON이 아닙니다: {body[:200]}") from exc


def call(name: str, timeout: int = DEFAULT_TIMEOUT, **args: Any) -> dict[str, Any]:
    """그래프 도구를 호출해 파싱된 JSON을 반환한다.

    도구가 {"error": ...}를 돌려주면 SkipperError로 올린다 — 호출부가 폴백을
    선택할 수 있도록 HTTP 오류와 같은 예외 타입으로 통일한다.
    """
    template, headers, internal = _endpoint()
    payload = {"args": args} if internal else args
    req = urllib.request.Request(
        template.format(name=name),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    data = _fetch(req, name, timeout)
    if isinstance(data, dict) and data.get("error"):
        raise SkipperError(f"{name}: {data['error']}")
    return data


def get_json(path: str, timeout: int = DEFAULT_TIMEOUT, **params: Any) -> Any:
    """REST 엔드포인트를 GET 한다. 빈 파라미터는 서버 기본값에 맡기고 보내지 않는다."""
    base, headers = _rest_target()
    query = {k: v for k, v in params.items() if v not in (None, "")}
    url = base + path + (("?" + urllib.parse.urlencode(query)) if query else "")
    return _fetch(urllib.request.Request(url, headers=headers, method="GET"), path, timeout)


# 서버가 받는 기간 토큰. Q1~Q4는 단일 3개월값이고 H1·9M이 누적이다.
SEGMENT_PERIODS = ("FY", "H1", "9M", "Q1", "Q2", "Q3", "Q4")


def segments(symbol: str, *, axis: str = "segment", metric: str = "revenue",
             period: str = "FY", fs_div: str = "", limit: int = 5) -> list[dict[str, Any]]:
    """부문·지역·제품별 실적 — 연도 그룹 리스트 (최신 연도 우선).

    그래프 도구(segment_series·segment_facts)와 달리 iceberg 원천을 직접 읽으므로
    그래프 적재가 지연돼도 최신 값이 나온다. 서버가 연결/별도(fsDiv)·표(roleKey)·
    기간을 이미 하나로 좁혀 주므로 한 응답 안에서 부문명은 중복되지 않는다.

    DART에 Q2·Q4 보고서는 없어 각각 H1−Q1, FY−9M로 유도되며 그 항목은
    derived=true다. 차감이 음수면 amount=null + note=negative_derivation으로 온다.
    연도 간 시계열은 name이 아니라 normalizedName으로 조인해야 한다 — 발행사가
    해마다 표기를 바꾼다('카카오' ↔ '㈜카카오').
    """
    if period and period not in SEGMENT_PERIODS:
        raise SkipperError(f"지원하지 않는 기간입니다: {period} (가능: {', '.join(SEGMENT_PERIODS)})")
    data = get_json(f"/api/v1/revenue-segments/{symbol}",
                    axis=axis, metric=metric, period=period, fsDiv=fs_div, limit=limit)
    return data if isinstance(data, list) else []


def resolve(query: str) -> dict[str, str]:
    """회사명/종목코드 → {'ticker','name','market'}. 후보가 없으면 SkipperError."""
    data = call("resolve_company", query=query)
    candidates = data.get("candidates") or []
    if not candidates:
        raise SkipperError(
            f"'{query}'에 해당하는 상장사를 찾지 못했습니다. 종목코드 6자리로 다시 시도하세요."
        )
    top = candidates[0]
    return {
        "ticker": top.get("ticker", ""),
        "name": top.get("name", query),
        "market": top.get("market", ""),
    }


def write_csv(path: str, rows: list[list[Any]]) -> str:
    """UTF-8 BOM으로 CSV를 쓴다 — 엑셀에서 더블클릭해도 한글이 깨지지 않는다."""
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerows(rows)
    return path


def fail(message: str) -> None:
    """오류를 stderr로 내보내고 종료 코드 1로 끝낸다."""
    print(f"오류: {message}", file=sys.stderr)
    raise SystemExit(1)
