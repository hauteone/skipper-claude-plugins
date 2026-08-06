# skipper-claude-plugins

SkipperLabs 상장기업 리서치 플러그인 마켓플레이스 — Claude Code에 skipper MCP
도구 35종과 PE 심사 리서치 플레이북을 한 번에 설치합니다.

## 설치 (심사관용, 3줄)

```bash
export SKIPPER_API_KEY=sk-skp-...                          # 발급받은 API 키 (셸 프로필에 추가 권장)
claude plugin marketplace add hauteone/skipper-claude-plugins
claude plugin install skipper@skipperlabs
```

설치 후 Claude Code를 재시작하면 `skipper` MCP 서버(도구 35종), `pe-research`
스킬, `/skipper` 커맨드가 활성화됩니다. 확인: `claude mcp list` 또는 대화에서
`/skipper 삼성전자 주주 구성`으로 테스트.

## 사용법

```
/skipper <질문>
```

예: `/skipper 삼성전자 최대주주 지분율 추이`, `/skipper 최근 1년 유상증자 결정한 코스닥 기업`

`/skipper`로 질문하면 PE 심사 플레이북(도구 라우팅·인용 규율)이 자동 적용되고,
기업 데이터는 skipper MCP 도구로만 조회하도록 강제됩니다. 일반 대화로 물어봐도
동작하지만, 심사·평가 시에는 `/skipper` 사용을 권장합니다. (커맨드는 추후
`/skipper:write` 같은 하위 커맨드로 확장될 수 있습니다.)

API 키는 SkipperLabs가 사용자별로 발급합니다 — support@skipperlabs.ai

## 구성

```
plugins/skipper/
├── .mcp.json                      # 리모트 MCP: https://api.skipperlabs.ai/mcp (X-API-Key 인증)
├── commands/skipper.md            # /skipper 커맨드 — 리서치 진입점 (플레이북·MCP 도구 강제)
└── skills/pe-research/SKILL.md    # PE 심사 리서치 플레이북 (도구 라우팅·인용 규율)
```

## API 키 설정

키는 셸 환경변수 `SKIPPER_API_KEY`로 입력합니다 — 플러그인의 MCP 설정이
`${SKIPPER_API_KEY}`를 참조해 요청 헤더(`X-API-Key`)에 자동으로 넣습니다.

```bash
# 셸 프로필(~/.zshrc 또는 ~/.bashrc)에 한 줄 추가 후 터미널 재시작
echo 'export SKIPPER_API_KEY=sk-skp-...' >> ~/.zshrc
```

확인: Claude Code 대화창에서 `/mcp` 입력 → `skipper` 서버가 connected로 보이면
정상입니다. 환경변수 없이 실행하면 서버 연결이 실패하니, 키를 넣은 뒤 Claude
Code를 재시작하세요.

## 사내망 (GitHub 접근 불가 시)

repo를 zip으로 받아 압축 해제 후 로컬 경로로 등록:

```bash
claude plugin marketplace add /path/to/skipper-claude-plugins
claude plugin install skipper@skipperlabs
```

필요한 아웃바운드는 `api.skipperlabs.ai:443` 하나입니다.

## 조직 일괄 배포 (IT 관리자) — 공용 키 1개, 심사관 제로 셋업

조직 공용 API 키 1개를 관리 설정(managed settings)에 함께 배포하면, 심사관은
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
