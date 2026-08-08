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
import urllib.request
from typing import Any

DEFAULT_API_URL = "https://api.skipperlabs.ai"
DEFAULT_TIMEOUT = 180


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
        raise SkipperError(
            "SKIPPER_API_KEY 환경변수가 비어 있습니다. 발급받은 키를 셸에 설정하세요:\n"
            '  export SKIPPER_API_KEY="sk-skp-..."\n'
            "키 발급 문의: support@skipperlabs.ai"
        )
    base = os.environ.get("SKIPPER_API_URL", DEFAULT_API_URL).rstrip("/")
    return (
        base + "/api/v1/tools/{name}",
        {"Content-Type": "application/json", "X-API-Key": api_key},
        False,
    )


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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 401:
            raise SkipperError(
                f"API 키 인증 실패 (401) — SKIPPER_API_KEY를 확인하세요. 응답: {detail}"
            ) from exc
        raise SkipperError(f"{name} 호출 실패 (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise SkipperError(f"{name} 호출 실패 — 네트워크 오류: {exc.reason}") from exc

    try:
        data = json.loads(body)
    except ValueError as exc:
        raise SkipperError(f"{name} 응답이 JSON이 아닙니다: {body[:200]}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise SkipperError(f"{name}: {data['error']}")
    return data


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
