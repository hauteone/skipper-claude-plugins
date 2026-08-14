---
name: list-export
description: >
  건수가 많은 목록형 데이터(스크리너, 공시 목록, 증권사 리서치 리포트, 일별
  시세, 수급, 상장 종목 목록 등)를 MCP 컨텍스트를 거치지 않고 REST로 직접
  받아 로컬 CSV로 저장한다. 사용자가 목록 전체나 CSV/엑셀 파일을 요청했을
  때, 또는 목록 결과가 커서 대화에는 일부만 보여주게 될 때 사용한다. Use when
  the user wants a full listing (screener, disclosures, research reports,
  prices, flows) exported as a CSV file, or when a list result is too large to
  show fully in conversation.
---

# 목록형 데이터 CSV 내보내기

MCP 도구로 목록을 가져오면 응답 전체가 모델 컨텍스트에 실린다. 100~200건짜리
목록이면 그 자체로 컨텍스트를 크게 소모하고, 잘리거나 요약 과정에서 유실된다.
이 스킬은 REST 엔드포인트를 스크립트로 직접 호출해 **컨텍스트를 거치지 않고**
로컬 CSV로 저장하고, 대화에는 건수·파일 경로·미리보기 몇 줄만 보여준다.

산출물은 UTF-8 BOM CSV다 — 엑셀에서 더블클릭해도 한글이 깨지지 않는다.
사용자가 "엑셀로"라고 요청해도 이 형식으로 만들고 그렇게 안내한다.

## 진입 경로 — 두 가지

- **직접 요청** — 사용자가 목록 전체·CSV·엑셀 파일을 요청했을 때.
- **요약 표시 시 안내** — MCP 도구 결과가 많아 대화에 일부만(상위 N개, 요약)
  보여주게 될 때는, **반드시** 다음 한 줄을 함께 안내한다:
  "전체 N건은 CSV 파일로 내려받을 수 있습니다 — 원하시면 만들어 드릴게요."
  사용자가 수락하면 이 스킬로 진행한다. 거절한 사용자에게 같은 대화에서
  재차 제안하지 않는다.

## 지원 데이터셋

| 데이터 | dataset 인자 | 필수 인자 | 수집 범위 |
|---|---|---|---|
| 종목 스크리너 | `screener` | — | 기본 200건 — `--top N`으로 시총 커서 분할 조회 (예: `--top 500`) |
| 시장 전체 공시 | `latest-disclosures` | — | 묶음 단위 (아래 규칙) |
| 종목별 공시 | `disclosures` | `--symbol` | 묶음 단위 (아래 규칙) |
| 증권사 리서치 리포트 | `kr-research-reports` | — (symbol 선택) | 묶음 단위 (아래 규칙) |
| 상장 종목 목록 | `stock-list` | — | 전체 1회 |
| 일별 시세 | `historical-prices` | `--symbol` | 최대 5000거래일(약 20년) |
| 투자자 수급 | `investor-flows` | `--symbol` | 최대 365거래일 (from/to로 조정) |
| 배당 이력 | `dividends` | `--symbol` | 최대 120건 |
| 재무비율 | `ratios` | `--symbol` | 최대 120건 |
| ETF 구성종목 | `etf-holdings` | `--symbol` | 최신 스냅샷 전체 |

## 사용법

```bash
cd "${CLAUDE_PLUGIN_ROOT}/scripts"
python3 export_list.py screener --param market=KOSPI
python3 export_list.py screener --top 500 --param market=KOSPI
python3 export_list.py disclosures --symbol 005930 --param from=2025-01-01
python3 export_list.py kr-research-reports --param q=반도체
python3 export_list.py historical-prices --symbol 005930 --param from=2020-01-01
```

- 추가 필터는 전부 `--param key=value`로 넘긴다 (REST 쿼리 파라미터 그대로).
  스크리너 필터 예: `--param peLowerThan=10 --param dividendYieldMoreThan=3`
- 파일명 기본값: `<dataset>_<종목코드|시장|all>_<날짜>.csv` (현재 폴더).
  `--out`으로 변경 가능.
- 실행 후 stdout의 건수·경로·미리보기를 사용자에게 그대로 전달한다.
  CSV 내용 전체를 대화에 다시 붙여넣지 않는다 — 그러면 이 스킬의 목적이
  무너진다.

## 대량 데이터셋 묶음 규칙 (시장 전체 공시·리서치 리포트)

`latest-disclosures`, `kr-research-reports`(symbol 미지정), `disclosures`는
페이지네이션 데이터셋이다. **한 번에 전체를 순회하지 않는다** — 기본
`--max-pages 5`(최대 500건)만 가져오고 멈춘다.

1. 첫 실행 후 stdout에 "더 남아 있을 수 있습니다"가 나오면, 수집 건수를
   알리고 **계속 가져올지 사용자에게 물어본다**.
2. 사용자가 수락하면 stdout이 알려준 이어받기 명령을 그대로 실행한다
   (`--start-page N --append --out <같은 파일>` + 같은 필터 인자).
3. "마지막 페이지까지 모두 수집했습니다"가 나올 때까지 이 과정을 반복하되,
   매 묶음마다 다시 물어본다. 사용자가 "끝까지 다 가져와"라고 명시했으면
   묻지 않고 반복해도 된다.

## 실행 환경 확인 — 두 가지 폴백 케이스

**케이스 1 — 스크립트가 없는 환경.** `${CLAUDE_PLUGIN_ROOT}`가 비어 있거나
`scripts/export_list.py`가 존재하지 않으면 스크립트 실행이 불가능한
환경이다(claude.ai 챗의 "스킬" 기능은 플러그인의 개별 스킬 폴더만 올리고
`scripts/`는 가져오지 않는다). 사유는 "CSV 자동 내보내기는 스크립트가
실행되는 환경에서만 가능하다" 한 줄만 쓴다.

**케이스 2 — 스크립트는 있지만 외부 REST가 막힌 환경.** 클라우드 샌드박스
(claude.ai Cowork 등)는 플러그인 전체가 마운트되지만 외부 API 직접 호출이
네트워크 정책으로 차단될 수 있다 — 스크립트가 네트워크 오류로 실패하면 이
경우다. 사유는 "이 환경은 외부 API 직접 호출이 막혀 있어 MCP 도구로
수집했다" 한 줄만 쓴다.

두 케이스 모두 MCP 도구로 폴백해 수집·정리해 전달하며, **API 키·토큰
이야기는 꺼내지 않는다** (키가 있어도 해결되지 않는 환경 문제라 "키가
없어서"는 틀린 설명이다). 폴백에서 스크리너 200건 초과가 필요하면
`api_screener`를 `marketCapLowerThan` 커서로 나눠 호출하고 `symbol` 기준으로
중복을 제거하며 병합한다 (경계 시총 종목이 다음 페이지에 다시 올 수 있다).

## 인증

스크립트가 REST API를 직접 호출하므로 인증이 필요하다. 아래 순서로 **스스로
해결**한다 — 키가 없다는 사실을 사용자에게 알리거나 확인받지 않는다:

1. `SKIPPER_API_KEY`가 설정돼 있으면 그대로 실행한다 (만료 없는 정적 키,
   반복 실행에 권장. 발급: `support@skipperlabs.ai`).
2. 없으면 `mint_script_token` MCP 도구로 단기 토큰을 발급받아, 스크립트
   실행과 **같은 셸 명령 안에서** `SKIPPER_ACCESS_TOKEN="<값>"`으로 함께
   넘긴다 (별도 export는 다음 Bash 호출로 이어지지 않는다). **이것이 키
   없는 세션의 정상 경로다** — 조용히 진행하고, 401(만료)이 나면 다시
   발급받아 재시도한다.
3. `mint_script_token` 도구까지 세션에 없어서 1·2 모두 불가능할 때만 MCP
   도구 수집으로 폴백하고, 그때 비로소 "정적 키(`SKIPPER_API_KEY`)를
   설정하면 전체 목록 CSV 내보내기가 가능하다"고 한 줄만 안내한다.
