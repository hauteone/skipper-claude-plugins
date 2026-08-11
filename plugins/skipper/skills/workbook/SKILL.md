---
name: workbook
description: >
  한국 상장사의 PE 실사 워크북 시트(엑셀에서 바로 여는 CSV)를 만든다 —
  보고서별 연결재무제표 원자료(Raw_BSPL 탭)와 사업부문 공시 원문+XBRL 팩트
  (Raw_부문별매출 탭). 재무·부문 데이터를 엑셀이나 CSV 파일로 요청받았거나,
  리서치 중 시트 생성 제안을 사용자가 수락했을 때 사용한다. Use when the user
  wants Korean listed-company financial statements or segment disclosures as an
  Excel-ready CSV worksheet, or accepts an offer to build one.
---

# 실사 워크북 시트 생성 — Raw_BSPL · Raw_부문별매출

DART 이용 예시 워크북의 원자료 탭 두 개를 CSV로 만든다. UTF-8 BOM으로 쓰므로
엑셀에서 더블클릭하면 한글이 깨지지 않고 바로 열린다. 산출물은 .xlsx가 아니라
**엑셀에서 바로 여는 CSV**다 — 사용자가 "엑셀로"라고 요청해도 이 형식으로
만들고 그렇게 안내한다.

## 진입 경로 — 두 가지

- **직접 요청** — 사용자가 재무제표·부문 데이터를 파일로 요청했을 때.
- **리서치 중 제안 수락** — pe-research 플레이북이 시트 생성을 제안하고
  사용자가 수락했을 때. 거절한 사용자에게 같은 대화에서 재차 제안하지 않는다.

## 시트 선택

| 요청 | 시트 | 절차 |
|---|---|---|
| 재무제표 4표(재무상태표·포괄손익·자본변동·현금흐름), 보고서별 원값, 재작성 추적 | Raw_BSPL | [references/raw-bspl.md](references/raw-bspl.md) |
| 사업부문·제품 공시 원문 + XBRL 부문 팩트 원자료 | Raw_부문별매출 | [references/raw-segment.md](references/raw-segment.md) |
| 연도별·분기별 부문 매출액·비중 정리표 | 정리예시 | `skipper:segment-summary` 스킬 |

어느 시트인지 모호하면 위 구분으로 짧게 물어 확정한 뒤 해당 절차 파일을 읽는다.

## 공통 준비

1. 회사명이 모호하면 `resolve_company`로 6자리 종목코드를 먼저 확정한다.
2. **실행 환경 확인** — `${CLAUDE_PLUGIN_ROOT}`가 비어 있거나
   `scripts/build_*.py`가 존재하지 않으면 스크립트 조판이 불가능한 환경이다.
   claude.ai 챗의 "스킬" 기능은 플러그인의 개별 스킬 폴더만 올리고
   `scripts/`(스킬 폴더 밖의 공용 디렉터리)는 가져오지 않는다 — Claude Code와
   Cowork는 플러그인 전체를 마운트하므로 이 문제가 없다. 이 경우 MCP 도구로
   데이터를 가져와(파라미터로 크기를 좁혀서) 표로 직접 정리해 전달하고,
   "시트 자동 조판은 스크립트가 실행되는 환경(Claude Code·Cowork)에서만
   가능하다"고 명시해 혼선을 줄인다.

## 인증 — 스크립트가 API를 직접 부르는 경로에서만 필요

Raw_BSPL의 권장 경로(MCP로 가져와 `--from-json`)는 자격증명이 전혀 필요 없다.
스크립트가 API를 직접 호출하는 경로는 세션에 둘 중 하나가 있어야 한다:

- `SKIPPER_API_KEY` — 정적 키(만료 없음, 반복 실행에 권장).
  `support@skipperlabs.ai`에서 발급.
- `SKIPPER_ACCESS_TOKEN` — 단기 액세스 토큰(만료됨). MCP 커넥터가 연결돼
  있으면 `mint_script_token` 도구로 즉시 발급받을 수 있다.
  `SKIPPER_API_KEY`가 있으면 무시된다.

`... 환경변수가 비어 있습니다`가 나오면 순서대로 시도한다:

1. Raw_BSPL은 `--from-json` 경로로 바꾼다 (자격증명 자체가 불필요).
2. MCP 커넥터가 연결돼 있으면 `mint_script_token` 도구를 호출해 `accessToken`을
   받고, **스크립트 실행과 같은 Bash 명령 안에서** 넘긴다:

   ```bash
   SKIPPER_ACCESS_TOKEN="<accessToken>" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_raw_segment.py" ...
   ```

   별도 명령으로 `export`하면 다음 Bash 호출에 이어지지 않는다 — 반드시 같은
   명령 줄에 붙인다. 실행 중 `인증 실패 (401)`이 나오면 토큰이 만료된 것이니
   `mint_script_token`을 다시 호출해 새 토큰으로 재시도한다.
3. 둘 다 안 되면 정적 키 설정(`export SKIPPER_API_KEY="sk-skp-..."`)을 안내한다.

## 공통 실패 처리

- Cowork에서 네트워크 오류(`... 호출 실패 — 네트워크 오류`)가 나면, Cowork
  설정의 네트워크 허용목록(egress allowlist)에 `api.skipperlabs.ai`가 추가돼
  있는지 확인해 달라고 안내한다 — 비어 있으면 기본이 전체 차단이다.
  Raw_BSPL은 `--from-json` 경로(스크립트가 자기 네트워크를 안 씀)로 바꾸면
  이 문제 자체가 없다.
- 값을 지어내지 마라. 스크립트가 실패하면 실패했다고 그대로 보고한다.
