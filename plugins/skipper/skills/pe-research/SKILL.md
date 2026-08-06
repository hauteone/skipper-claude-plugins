---
name: pe-research
description: >
  한국·미국 상장기업 리서치와 PE 심사 실무 플레이북. 기업의 지분 구조, 공시 이력,
  재무 검증, 배당, 시장 전체 공시 스크리닝 질문에 사용한다. skipper MCP 도구
  35종의 라우팅 전략과 인용 규율을 담고 있다. Use when researching Korean or US
  listed companies — shareholders, disclosures, financials, dividends, deal screening.
---

# skipper PE 심사 리서치 플레이북

skipper MCP 서버(도구 35종)를 사용해 상장기업을 조사할 때 아래 규율을 따른다.
이 플레이북은 korean-dart-mcp 대비 블라인드 비교 평가(20문항)에서 검증된 도구
전략·답변 규칙을 담고 있다.

## 1. 도구 라우팅 — 질문 유형별 최적 경로

**기업 확정이 먼저다.** 회사명이 조금이라도 모호하면 `resolve_company`(또는
`api_search`)로 6자리 종목코드를 확정한 뒤 진행한다.

| 질문 유형 | 1순위 도구 | 보조 |
|---|---|---|
| 특정 기업의 주주 구성·지분율·지분공시(대량보유) 이력 | `shareholders_detail` | `get_document` |
| 시장 전체 공시 스크리닝 (유상증자·CB·대량보유 등 "어떤 기업들이…") | `search_disclosures` | `get_document` |
| 주주 기준 역탐색 (국민연금 보유 기업, A사의 타법인출자·계열) | `shareholder_screen` | `shareholders_detail` |
| 재무제표·수익성·증감 분석 | `financial_statements` | `api_income_statement`, `api_ratios` |
| 부문·지역·제품별 매출 추이 (연도별·분기별 표) | `segment_series` | `segment_facts`, `get_document` |
| 재무제표 주석 (우발부채·약정·특수관계자·충당부채) | `financial_notes` | `get_document` |
| 배당 이력·배당성향 | `dividend_history` | `api_dividends` |
| 특정 기업의 공시 목록 | `list_disclosures` | — |
| 공시 원문 정독 | `get_document` (대형 문서는 `section=` 정조준) | — |
| 뉴스·이벤트·정성 질문 | `hybrid_search` | `list_disclosures`로 교차 검증 |
| 집계·순위·관계 탐색 (그래프 구조 질문) | `graph_query` | — |
| 시세·수급·ETF·컨센서스·스크리너 | `api_*` 정형 데이터 도구 | — |

주의:
- "지분 30% 미만 기업" 같은 **조건 스크리닝은 `shareholder_screen`이 정답**이다 —
  `graph_query`나 기업별 반복 조회로 우회하면 사례를 놓친다. 조건에 맞는 사례를
  복수로 열거하고, 경계 사례(조건을 아슬아슬하게 벗어난 기업)도 언급하면 좋다.
- `search_disclosures` 결과의 `kind` 필드(신규결정/진행·결과/정정/상환·취득)로
  성격을 구분하라 — 신규 발행결정과 정정·상환을 섞어 세지 마라.
- snippet으로 핵심 파악이 되면 건별 `get_document`는 꼭 필요한 소수 건만 한다.
- 사업보고서 같은 대형 문서는 `get_document(doc_id, section="타법인출자")`처럼
  섹션을 정조준한다. 목차는 `__TOC__`로 먼저 확인할 수 있다.

## 2. 인용 규율 — 모든 수치에 출처와 기준을 단다

- 공시 인용: **접수번호(rcept_no)와 접수일자**를 함께 표기한다. 접수번호는 도구
  결과의 값을 **그대로 복사**한다 — 절대 만들어내지 마라.
- 뉴스 인용: 제목·발행일·언론사. 내부 ID(kr:*, 뉴스 번호)는 인용 금지.
- 재무 수치: period_end(기준일)와 **연결(CFS)/별도(OFS) 기준**을 명시한다.
  기준이 다른 수치를 기준 표시 없이 병기하지 마라.
- 지분율: 산정 기준(의결권 있는 주식 vs 발행주식총수)과 보고서 기준일을 명시한다.
- 언론의 반올림 수치(예: "40조")보다 공시 원문의 확정값을 우선한다.
- 뉴스에서 얻은 핵심 수치(조달액·발행가 등)는 공시 원문과 교차 검증한 뒤 인용한다.

## 3. 답변 구성 규칙

- 도구 결과에 근거해서만 답한다. 확인 안 되는 내용은 "확인되지 않는다"고 명시한다.
  단, **도구가 이미 반환한 데이터를 "확인되지 않는다"고 쓰지 마라** — 반환된
  필드를 끝까지 활용한다.
- 이력·목록형 질문에는 **조회 기간을 명시**하고, 확인된 건을 **빠짐없이 열거**한다.
  표본만 보여줄 때는 전체 건수와 표본임을 밝힌다.
- 보조 비교 지표(분기 평균 환산 등)를 제시할 때는 산식을 명시한다.
- 원인·배경 해석은 도구 결과로 확인될 때만 서술한다.
- 공시 원문의 공란('-') 필드는 "기재 없음"으로 표기하고 값을 추정하지 마라.

## 4. PE 심사 표준 워크플로

딜 스크리닝·기업 실사형 질문은 아래 순서로 조사를 조립한다:

1. **기업 확정** — `resolve_company`
2. **개요** — `company_profile` (섹터·최신지표·거래소 라이브 밸류에이션·관계·주요주주)
3. **지배구조** — `shareholders_detail` (5% 주주 표·특수관계인 합계·소액주주·최근 2년
   지분공시) → 필요 시 `shareholder_screen`으로 계열·타법인출자 역탐색
4. **자금조달·이벤트 이력** — `list_disclosures` / `search_disclosures` (기간 명시)
5. **재무 검증** — `financial_statements` (연결+별도, YoY) → `financial_notes`로
   우발부채·약정·특수관계자 거래 확인
6. **주주환원** — `dividend_history`
7. **시장 맥락** — `hybrid_search` (뉴스·경쟁·공급망), `api_*` (시세·수급·컨센서스)

각 단계의 근거(접수번호·기준일)를 모아 최종 답변에서 출처 목록으로 정리한다.
