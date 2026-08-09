# skipper-claude-plugins

SkipperLabs 상장기업 리서치 플러그인 마켓플레이스 — 한국·미국 상장기업의 공시,
지분, 재무, 배당, 뉴스를 연결한 지식그래프를 MCP 도구 35종으로 제공합니다.
Claude Code와 Claude 데스크탑 양쪽에서 쓸 수 있습니다.

API 키는 SkipperLabs가 사용자별로 발급합니다 — support@skipperlabs.ai

| 환경 | 얻는 것 | 설치 |
|---|---|---|
| **Claude Code** | MCP 도구 35종 + 스킬 4종 + `/skipper` 커맨드 | 아래 3줄 |
| **Claude 데스크탑 / claude.ai** | MCP 도구 35종 | 커스텀 커넥터 URL 1개 |

---

## Claude Code 설치 (3줄)

```bash
export SKIPPER_API_KEY=sk-skp-...                          # 발급받은 API 키 (셸 프로필에 추가 권장)
claude plugin marketplace add hauteone/skipper-claude-plugins
claude plugin install skipper@skipperlabs
```

설치 후 Claude Code를 재시작하면 `skipper` MCP 서버(도구 35종), 스킬 4종,
`/skipper` 커맨드가 활성화됩니다. 확인: `claude mcp list` 또는 대화에서
`/skipper 삼성전자 주주 구성`으로 테스트.

---

## Claude 데스크탑 설치 (커스텀 커넥터)

데스크탑에는 플러그인을 설치하지 않습니다. 대신 MCP 서버를 **커스텀 커넥터**로
연결하면 도구 35종을 그대로 쓸 수 있습니다.

커넥터는 Claude 계정에 등록되므로 **claude.ai에서 한 번 추가하면 데스크탑 앱에도
그대로 나타납니다** (앱과 웹이 같은 계정 설정을 공유).

1. claude.ai 접속 → 설정 → **커넥터**(Connectors) → **커스텀 커넥터 추가**
2. 이름에 `skipper`, URL에 아래를 넣습니다 — `sk-skp-...` 자리에 발급받은 키:

   ```
   https://api.skipperlabs.ai/mcp?apikey=sk-skp-...
   ```

3. **추가**를 누르면 끝입니다. OAuth 설정(고급 설정)은 필요 없습니다.
4. 대화창의 도구 목록에 `skipper`가 보이면 정상입니다.
   `삼성전자 최대주주 지분율 알려줘`로 테스트하세요.

**키를 URL에 넣는 이유**: 데스크탑 커스텀 커넥터는 커스텀 HTTP 헤더를 지원하지
않아 `X-API-Key` 헤더를 넣을 수 없습니다. 그래서 API가 `?apikey=` 쿼리
파라미터도 받도록 되어 있습니다. 다만 **키가 커넥터 설정에 URL로 저장되므로
화면 공유나 스크린샷 시 노출에 주의**하세요. 키가 유출되면
support@skipperlabs.ai 로 재발급을 요청하면 됩니다.

**네트워크**: 커넥터 연결은 사용자 PC가 아니라 Anthropic 서버에서 출발합니다.
`api.skipperlabs.ai`는 공개 인터넷에 열려 있어 별도 방화벽 설정이 필요 없습니다.

### 데스크탑에서 달라지는 것

MCP 도구 35종은 양쪽이 동일합니다. 나머지 구성요소는 이 저장소가 Claude Code
플러그인 형식이라 그대로는 넘어가지 않습니다.

- **`/skipper` 커맨드와 `pe-research` 플레이북** — 플러그인으로 설치될 때만 자동
  적용됩니다. 데스크탑에서는 자연어로 물어보면 되고, 도구는 동일하게 동작합니다.
  플레이북 내용이 필요하면 `plugins/skipper/skills/pe-research/SKILL.md`를
  커스텀 스킬로 올려 쓸 수 있습니다 (설정 → 스킬 → 스킬 만들기, ZIP 업로드).
- **CSV 시트 생성 스킬 3종** — 데스크탑 커스텀 스킬로 그대로 올리는 것은 아직
  지원하지 않습니다. 스킬이 번들한 파이썬 스크립트가 `${CLAUDE_PLUGIN_ROOT}`
  경로와 `SKIPPER_API_KEY` 환경변수를 전제로 API를 직접 호출하는데, 데스크탑
  스킬 실행 환경에는 그 두 가지가 없습니다.

  데스크탑에서 같은 시트가 필요하면 커넥터를 붙인 상태에서 자연어로 요청하세요
  (예: "SK 부문별 매출을 연도별·분기별 표로 만들어 CSV로 줘"). 도구가 데이터를
  가져오고 Claude가 파일을 만들어 줍니다.

> 커스텀 스킬 자체는 데스크탑·Cowork에서 지원됩니다(설정 → 스킬). 실행 가능한
> 스크립트도 포함할 수 있습니다. 위 3종이 안 되는 것은 스킬 기능의 한계가 아니라
> 이 스킬들이 Claude Code 전제로 작성됐기 때문입니다. 데스크탑용 변형을
> 원하시면 support@skipperlabs.ai 로 알려주세요.

## 사용법 (Claude Code)

### 리서치 — `/skipper <질문>`

예: `/skipper 삼성전자 최대주주 지분율 추이`, `/skipper 최근 1년 유상증자 결정한 코스닥 기업`

`/skipper`로 질문하면 리서치 플레이북(도구 라우팅·인용 규율)이 자동 적용되고,
기업 데이터는 skipper MCP 도구로만 조회하도록 강제됩니다.

데스크탑에서는 `/skipper` 없이 자연어로 물어보면 됩니다 — 같은 도구를 씁니다.

### 실사 워크북 시트 만들기 — 스킬 3종

DART 이용 예시 워크북의 세 개 탭을 각각 CSV로 만들어 줍니다. UTF-8 BOM으로 써서
엑셀에서 더블클릭하면 한글이 깨지지 않고 바로 열립니다.

| 커맨드 | 만드는 시트 | 내용 |
|---|---|---|
| `/skipper:raw-bspl <회사>` | Raw_BSPL | 정기보고서별 연결재무제표 4표(재무상태표·포괄손익·자본변동·현금흐름)를 보고서 단위 열 블록으로 |
| `/skipper:raw-segment <회사>` | Raw_부문별매출 | 정기보고서별 "주요 제품 및 서비스" 원문 + XBRL 부문 팩트 표 |
| `/skipper:segment-summary <회사>` | 정리예시 | 연도별·분기별 부문 매출액과 비중 (합계·비중 자동 계산) |

예: `/skipper:raw-bspl SK`, `/skipper:raw-bspl 034730 --reports 6 --unit 억원`

`segment-summary`는 초안을 만든 뒤 공시 원문 표로 검증·보정해 렌더링하는 2단계로
동작합니다 — XBRL 부문 매출만으로는 분기 표가 채워지지 않는 기업이 많기 때문입니다.

## 구성

```
plugins/skipper/
├── .mcp.json                          # 리모트 MCP: https://api.skipperlabs.ai/mcp (X-API-Key 인증)
├── commands/skipper.md                # /skipper 커맨드 — 리서치 진입점 (플레이북·MCP 도구 강제)
├── scripts/                           # 시트 생성 스크립트 (표준 라이브러리만, 설치 불필요)
│   ├── skipper_api.py                 #   공용 API 클라이언트
│   ├── build_raw_bspl.py
│   ├── build_raw_segment.py
│   └── build_segment_summary.py
└── skills/
    ├── pe-research/SKILL.md           # 리서치 플레이북 (도구 라우팅·인용 규율)
    ├── raw-bspl/SKILL.md              # /skipper:raw-bspl
    ├── raw-segment/SKILL.md           # /skipper:raw-segment
    └── segment-summary/SKILL.md       # /skipper:segment-summary
```

시트 생성 스크립트는 Python 3.9+ 표준 라이브러리만 씁니다 (`pip install` 불필요).
`SKIPPER_API_KEY`로 `https://api.skipperlabs.ai/api/v1/tools/{도구}`를 직접 호출해
수 MB짜리 재무제표 응답을 대화 컨텍스트를 거치지 않고 파일로 떨굽니다.

## API 키 설정 (Claude Code)

키는 셸 환경변수 `SKIPPER_API_KEY`로 입력합니다 — 플러그인의 MCP 설정이
`${SKIPPER_API_KEY}`를 참조해 요청 헤더(`X-API-Key`)에 자동으로 넣습니다.

```bash
# 셸 프로필(~/.zshrc 또는 ~/.bashrc)에 한 줄 추가 후 터미널 재시작
echo 'export SKIPPER_API_KEY=sk-skp-...' >> ~/.zshrc
```

확인: Claude Code 대화창에서 `/mcp` 입력 → `skipper` 서버가 connected로 보이면
정상입니다. 환경변수 없이 실행하면 서버 연결이 실패하니, 키를 넣은 뒤 Claude
Code를 재시작하세요.

데스크탑은 환경변수를 쓰지 않습니다 — 커넥터 URL의 `?apikey=`가 그 역할을 합니다.

## 사내망 (GitHub 접근 불가 시, Claude Code)

repo를 zip으로 받아 압축 해제 후 로컬 경로로 등록:

```bash
claude plugin marketplace add /path/to/skipper-claude-plugins
claude plugin install skipper@skipperlabs
```

필요한 아웃바운드는 `api.skipperlabs.ai:443` 하나입니다.

데스크탑 커넥터는 사내망 여부와 무관합니다 — 연결이 사용자 PC가 아니라 Anthropic
서버에서 출발하므로 사내 방화벽 설정이 필요 없습니다.

## 조직 일괄 배포 (IT 관리자, Claude Code) — 공용 키 1개, 사용자 제로 셋업

조직 공용 API 키 1개를 관리 설정(managed settings)에 함께 배포하면, 사용자는
아무것도 설정할 필요가 없습니다 (Claude Code 설치가 전부). 관리 설정의 `env`가
모든 세션에 환경변수를 주입하므로 플러그인의 `${SKIPPER_API_KEY}` 참조가 자동으로
채워집니다.

**managed-settings.json** (전체 내용):

```json
{
  "extraKnownMarketplaces": {
    "skipperlabs": {
      "source": { "source": "github", "repo": "hauteone/skipper-claude-plugins" }
    }
  },
  "enabledPlugins": { "skipper@skipperlabs": true },
  "env": {
    "SKIPPER_API_KEY": "sk-skp-공용키를-여기에"
  }
}
```

**배포 위치** (MDM/스크립트로 배포, 관리자 권한 필요 — 사용자 설정보다 항상 우선):

| OS | 경로 |
|---|---|
| macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Windows | `C:\ProgramData\ClaudeCode\managed-settings.json` |
| Linux | `/etc/claude-code/managed-settings.json` |

**공용 키 운영 참고**:

- 공용 키는 SkipperLabs에 "조직 공용" 용도로 요청하세요 — rate limit을 무제한
  또는 인원수에 맞게 넉넉히 설정해 발급합니다 (키 1개의 분당 한도를 전원이
  공유하므로 개인용 기본값(60rpm)으로는 부족합니다).
- 사용량 계측·차단이 조직 단위로만 가능해집니다 (개인별 식별 불가). 인원 변동
  시 회수는 키 교체(재발급 + managed-settings.json 재배포)로 처리합니다.
- 파일은 관리자만 쓰기 가능한 경로라 일반 사용자가 키를 수정할 수 없습니다.
