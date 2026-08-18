# 서버측 개선 계획 — skipper-graph · skipper-api (2026-08-13)

한화오션 QA 2건에서 확인된 미해결 과제의 실행 계획. 각 항목을 실코드 위치에
앵커링했다.

- 근거: `qa/2026-08-13-hanwha-ocean-backlog-qa.md` (수주잔고),
  `qa/2026-08-13-hanwha-ocean-borrowings-qa.md` (차입내역)
- 이미 완료: `api_balance_sheet` 차입금 통합 계정 매핑
  (skipper-api `2e75699`, `internal/service/raw_extract.go`) — 재검증 PASS
- **오늘 오후 이미 진행된 관련 작업 (검증 필요)**: skipper-graph
  `31496ad`(financial_notes 정형 주석 팩트 — 차입금 등 10년 시계열),
  `8f033ca`(팩트 인용 환산 지시). 오전 QA의 관측은 이 커밋들 이전 시점이다.

---

## 과제 0 — 운영 그래프 배포 상태 확인 (선행, 최우선)

skipper-graph main(`8f033ca`)이 운영 EC2(`compose.prod.yml`,
GraphApiUrl 10.22.2.236)에 반영됐는지부터 확인한다. 오전 QA에서 관측된
증상 중 일부는 main에서 이미 개선됐을 수 있다:

- 현 main의 `mysql_kr.disclosure_sections()`는 **미매칭 시 목차(__TOC__)만
  반환**하는 구조 — 운영에서 관측된 "100KB 전문 덤프" 동작과 다르다.
- `financial_notes` facts 블록(31496ad)은 오전 호출에서 보이지 않았다.

**작업**: 그래프 서비스 재배포 → 아래 스모크 3종 재실행 → 결과에 따라
과제 1·3의 잔여 범위 확정.

```
1) financial_notes(042660, keyword=차입금)   → facts 블록(10년 시계열) 존재?
2) get_document(20260317000644, section=차입금) → 100KB 덤프 대신 __TOC__ 반환?
3) get_document(20260317000644, section=수주상황) → 기존 정상 동작 회귀 없음?
```

---

## 과제 1 — get_document 재무챕터 섹션 도달 (F2, 높음)

### 실측 증상 (2026-08-13 오전, 042660 사업보고서 rcept 20260317000644)

- `section='수주상황'` → 해당 섹션 컴팩트 반환 (정상)
- `section='차입금'`·`'수주'`·`'증권의 발행을 통한 자금조달'` → 셋 모두
  **동일한 100,302자** `text_source:"full"` 덤프. III장 주석 초입에서 잘려
  차입처·이자율·만기 표 도달 불가.

### 원인 (코드 앵커)

- `company_tools.py get_document()`: `disclosure_sections()`가 비면
  `disclosure_full_text(limit=100_000)`로 폴백 → 100KB 덤프의 출처.
- `mysql_kr.py:197 disclosure_sections()`: json 목차를 재귀 순회하며
  `any(k in title for k in filters)` 매칭. 두 갈래 실패 모드:
  - (a) 키워드가 목차 제목에 없음 ('차입금', '수주') — 자연 미스.
  - (b) **제목은 매칭되는데 해당 노드의 content가 비어 있음** 추정
    ('증권의 발행을 통한 자금조달…'은 목차에 존재) — 재무챕터의 json
    content 적재 여부를 DB에서 직접 확인 필요.

### 작업 항목

1. **미매칭 시 full 폴백 제거** — 섹션 인자가 주어졌는데 매칭 실패면
   100KB 전문 대신 `{"section_miss": true, "toc": [...]}` 형태로 목차와
   안내를 반환 (현 main의 __TOC__-only 반환이 이미 이 방향이면 배포로 종결).
   전문이 정말 필요한 호출은 `section` 생략으로 명시하게 한다.
2. **(b) 진단**: 문제 rcept_no의 `disclosures.json`에서 재무챕터 노드
   content 유무 확인 → 비어 있으면 ingest 단계에서 재무챕터 본문 포함하도록
   보강 (또는 해당 챕터는 content 원문에서 오프셋 추출).
3. **주석 2단 정조준**: `section='연결재무제표 주석'` + `keyword='차입금'`
   조합 지원 — 주석은 거대하므로 섹션 안에서 키워드 주변 창(N KB)만 반환.
   (financial_notes facts가 충분하면 우선순위 하향 가능 — 과제 3 결과에 연동.)

### 수용 기준

- `get_document(20260317000644, section='차입금')`이 100KB 덤프를 반환하지
  않는다 (주석 창 또는 명시적 섹션 목록).
- 차입내역 QA 재실행 시 "차입처·이자율·만기" 중 최소 이자율·만기 요약이
  도구 경로로 확인된다.

---

## 과제 2 — list_disclosures 과거 공시 도달 (백로그 QA F1, 높음·소규모)

### 실측 증상

`days=3800`을 줘도 최근 순 상한에서 잘려 가장 오래된 사업보고서가
FY2022분(2023-03 접수) — 10년 질문의 앞 6개년 접수번호 확보 불가.
(`dart_company`는 최근 1년 고정이라 대안이 못 된다.)

### 원인 (코드 앵커)

- `company_tools.py:134 list_disclosures(ticker, days, category, limit=40)` —
  **limit 파라미터가 함수에는 있으나 게이트웨이 도구 스키마에 미노출**.
  iceberg 쿼리(`mysql_kr.company_disclosures`, LIMIT %s)는 이미 기간·건수를
  받는 구조라 데이터는 있다 (BS 원장은 FY2016까지 확인됨).

### 작업 항목

1. 게이트웨이 스키마에 `limit` 노출 (상한 예: 200).
2. `report_type` 필터 추가 (사업보고서|반기|분기 — title LIKE 매칭):
   `report_type=사업보고서`면 기본 상한으로도 수십 년치가 들어온다.
   페이지네이션보다 싸고 질문 유형(연간 시계열)에 직결.

### 수용 기준

- `list_disclosures(042660, days=3800, report_type=사업보고서)` →
  FY2016~FY2025 사업보고서 rcept_no 전부 반환.
- 수주잔고 QA 재실행: 10개년 수주잔고 표 완주 (각 연도 rcept_no 인용).

---

## 과제 3 — 주석 수치의 정형 제공 (F3) — 이미 착수됨, 검증으로 전환

### 상태

- `31496ad`가 financial_notes에 **정형 주석 팩트(facts) 블록 — 차입금 등
  10년 수치 시계열**을 추가 (iceberg `financial_statement_note_facts`).
  오전 QA의 "XBRL 미적재 → 폴백 발췌뿐" 관측을 이미 겨냥한 작업.

### 작업 항목

1. 배포 후 042660 실측: `financial_notes(042660, keyword=차입금)` facts에
   10년 시계열이 오는지, 값이 Raw_BSPL 원장(FY2025 유동 3.30조/비유동
   2.35조 등)과 일치하는지 교차 검증.
2. facts 커버리지 리포트: note_category별·기업별 적재율 — 한화오션류
   미적재 구간 확인 후 XBRL/노트 팩트 적재 확대의 우선순위 결정 (중기).
3. facts로 해소 안 되는 잔여(차입처별 명세 등)만 과제 1-3(주석 2단
   정조준)으로 넘긴다.

### 수용 기준

- 차입내역 QA 재실행 시 "총액 시계열 + 이자율·만기 수준"까지 MCP 단독
  (스크립트 없이, claude.ai 챗 환경 가정)으로 답변 가능.

---

## 과제 4 — raw_extract FY2018 equity null (경미)

### 실측 증상

`api_balance_sheet(042660, FY)` FY2018 행: `totalEquity=null`,
`totalLiabilitiesAndStockholdersEquity=8,078,299,948,957`(=부채총계,
자산총계 11.9조와 불일치).

### 작업 항목 (skipper-api `internal/service/raw_extract.go`)

1. 2e75699와 동일 패턴: 재현 테스트(RED) → equity 계열 account_id/별칭
   보강 → GREEN. (당시 자본 표기: 자본총계/지배·비지배 구분 이슈 추정.)
2. 파생값 정합 가드: `totalLiabilitiesAndStockholdersEquity`는
   equity null이면 산출하지 말거나 totalAssets와 대사해 불일치 시 null.
3. 전 종목·전 기간 스캔: `totalAssets ≠ totalLiabilities+totalEquity`
   (오차 허용) 행 카운트 → 유사 결함 일괄 파악.

---

## 순서와 종속성

| 순서 | 과제 | 규모 | 종속 |
|---|---|---|---|
| 0 | 그래프 재배포 + 스모크 3종 | 배포만 | — |
| 1 | list_disclosures limit·report_type (과제 2) | 소 | 0 |
| 2 | get_document full 폴백 제거·미매칭 응답 (과제 1-1) | 소 | 0 (main에 이미 있으면 생략) |
| 3 | financial_notes facts 검증·커버리지 (과제 3) | 검증 | 0 |
| 4 | 재무챕터 content 진단·주석 2단 정조준 (과제 1-2·3) | 중 | 3 결과에 연동 |
| 5 | raw_extract equity 보강 + 전 종목 스캔 (과제 4) | 소 | — (병행 가능) |
| 6 | XBRL/노트 팩트 적재 확대 | 대 (중기) | 3 커버리지 리포트 |

## 완료 후 플러그인 후속 (이 레포)

서버 과제 1~3 완료 시 v0.7.10에서 스킬 문구를 되돌린다:

- pe-research: "재무 챕터는 섹션 정조준이 되지 않을 수 있다" → 새 동작
  (섹션 목록 반환·주석 정조준·facts)에 맞게 갱신, "차입처·이자율·만기
  상세는 현재 도구로 불가" 한계 문구 완화.
- 검증은 QA 파일 2건의 재현 절차를 그대로 재실행해 PASS 확인 후 릴리스.
