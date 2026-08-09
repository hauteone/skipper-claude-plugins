# skipper-claude-plugins

SkipperLabs 상장기업 리서치 플러그인 마켓플레이스 — 한국·미국 상장기업의 공시,
지분, 재무, 배당, 뉴스를 연결한 지식그래프를 MCP 도구 35종으로 제공합니다.
Claude Code와 Claude 데스크탑 양쪽에서 쓸 수 있습니다.

API 키는 SkipperLabs가 사용자별로 발급합니다 — support@skipperlabs.ai

| 환경 | 설치 방법 | 얻는 것 |
|---|---|---|
| **Claude Code** | 마켓플레이스 2줄 | MCP 도구 35종 + 스킬 4종 + `/skipper` 커맨드 |
| **Claude 데스크탑 / Cowork** | 마켓플레이스 추가 (UI) | MCP 도구 35종 + 스킬 4종 |

양쪽 다 이 저장소를 마켓플레이스로 등록해 설치합니다. API 키는 **플러그인을
활성화할 때 Claude가 물어봅니다** — 미리 준비할 것은 없습니다.

---

## Claude Code 설치

```bash
claude plugin marketplace add hauteone/skipper-claude-plugins
claude plugin install skipper@skipperlabs
```

활성화 시 **SkipperLabs API 키**를 묻습니다. 입력하면 마스킹되어 macOS 키체인에
저장됩니다 (`settings.json`에 평문으로 남지 않습니다).

Claude Code를 재시작하면 `skipper` MCP 서버(도구 35종), 스킬 4종, `/skipper`
커맨드가 활성화됩니다. 확인: `claude mcp list` 또는 `/skipper 삼성전자 주주 구성`.

> 셸 환경변수 `SKIPPER_API_KEY`를 쓰던 기존 방식도 그대로 동작합니다. 키 입력을
> 비워 두면 환경변수로 폴백합니다 (조직 일괄 배포용 — 아래 참조).

---

## Claude 데스크탑 / Cowork 설치

1. Claude 데스크탑 → **Customize → Plugins → 마켓플레이스 추가**
2. **저장소에서 추가**를 선택하고 아래를 입력:

   ```
   hauteone/skipper-claude-plugins
   ```

3. 목록에 나타난 **skipper** 플러그인을 **설치**합니다.
4. 활성화 시 **SkipperLabs API 키**를 묻습니다 — 발급받은 `sk-skp-...` 키를 입력하세요.
5. 대화창에서 `삼성전자 최대주주 지분율 알려줘`로 확인합니다.

**네트워크**: MCP 서버 연결은 사용자 PC가 아니라 Anthropic 서버에서 출발합니다.
`api.skipperlabs.ai`는 공개 인터넷에 열려 있어 사내 방화벽 설정이 필요 없습니다.

### 대안 — 커스텀 커넥터 (도구만 필요할 때)

플러그인 없이 MCP 도구 35종만 쓰려면 커넥터로 붙일 수도 있습니다.
claude.ai → 설정 → **커넥터** → **커스텀 커넥터 추가** → URL:

```
https://api.skipperlabs.ai/mcp?apikey=sk-skp-...
```

커스텀 커넥터는 HTTP 헤더를 지원하지 않아 키를 URL에 넣습니다. **키가 커넥터
설정에 URL로 저장되므로 화면 공유·스크린샷 시 노출에 주의**하세요. 스킬은
따라오지 않으므로, 특별한 이유가 없으면 위의 플러그인 설치를 권합니다.

### 데스크탑에서 달라지는 것

MCP 도구 35종과 스킬은 양쪽 모두에서 동작합니다. 차이는 두 가지입니다.

- **`/skipper` 커맨드** — 슬래시 커맨드는 Claude Code 형식입니다. 데스크탑에서는
  그냥 자연어로 물어보면 되고, 도구와 플레이북은 동일하게 적용됩니다.
- **CSV 시트 생성 스킬 3종** — 스킬 자체는 설치되지만, 번들된 파이썬 스크립트가
  `${CLAUDE_PLUGIN_ROOT}` 경로와 로컬 파일 쓰기를 전제로 해서 데스크탑 실행
  환경에서는 의도대로 동작하지 않습니다. 데스크탑에서 같은 시트가 필요하면
  자연어로 요청하세요 (예: "SK 부문별 매출을 연도별·분기별 표로 만들어 CSV로 줘").
  도구가 데이터를 가져오고 Claude가 파일을 만들어 줍니다.

> 훅과 서브에이전트는 Cowork에서만 실행되며 chat에서는 비활성으로 표시됩니다.
> 이 플러그인은 둘 다 쓰지 않으므로 영향이 없습니다.

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
├── .claude-plugin/plugin.json         # 매니페스트 — userConfig로 API 키를 활성화 시 요청
├── .mcp.json                          # 리모트 MCP: https://api.skipperlabs.ai/mcp
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

## API 키 설정

키를 넣는 방법은 세 가지이고, 위에서부터 우선 적용됩니다.

| 방법 | 대상 | 저장 위치 |
|---|---|---|
| **활성화 시 프롬프트** (기본) | Claude Code·데스크탑 | macOS 키체인 (마스킹 입력) |
| 셸 환경변수 `SKIPPER_API_KEY` | Claude Code | 셸 프로필 |
| 조직 관리 설정 | Claude Code 일괄 배포 | managed-settings.json |

별도 준비 없이 플러그인을 설치하면 Claude가 키를 물어봅니다. 이 값은
`sensitive`로 선언돼 있어 입력이 마스킹되고 `settings.json`에 평문으로 남지
않습니다.

셸 환경변수를 쓰던 기존 방식도 계속 동작합니다 — 프롬프트에서 키를 비워 두면
환경변수로 폴백합니다.

```bash
# 셸 프로필(~/.zshrc 또는 ~/.bashrc)에 한 줄 추가 후 터미널 재시작
echo 'export SKIPPER_API_KEY=sk-skp-...' >> ~/.zshrc
```

확인: Claude Code에서 `/mcp` 입력 → `skipper` 서버가 connected로 보이면 정상입니다.

<details>
<summary>동작 원리</summary>

MCP 설정이 키를 두 경로로 동시에 넘깁니다.

```json
"url": "https://api.skipperlabs.ai/mcp?apikey=${user_config.api_key}",
"headers": { "X-API-Key": "${SKIPPER_API_KEY}" }
```

API는 쿼리 파라미터를 먼저 보고, 비어 있으면 헤더로 폴백합니다. 그래서 프롬프트로
받은 키와 환경변수 방식이 한 설정에서 함께 동작합니다.
</details>

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
