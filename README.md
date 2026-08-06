# skipper-claude-plugins

SkipperLabs 상장기업 리서치 플러그인 마켓플레이스 — Claude Code에 skipper MCP
도구 34종과 PE 심사 리서치 플레이북을 한 번에 설치합니다.

## 설치 (심사관용, 3줄)

```bash
export SKIPPER_API_KEY=sk-skp-...                          # 발급받은 API 키 (셸 프로필에 추가 권장)
claude plugin marketplace add hauteone/skipper-claude-plugins
claude plugin install skipper@skipperlabs
```

설치 후 Claude Code를 재시작하면 `skipper` MCP 서버(도구 34종)와 `pe-research`
스킬이 활성화됩니다. 확인: `claude mcp list` 또는 대화에서 "삼성전자 주주 구성
알려줘"로 테스트.

API 키는 SkipperLabs가 사용자별로 발급합니다 — support@skipperlabs.ai

## 구성

```
plugins/skipper/
├── .mcp.json                      # 리모트 MCP: https://api.skipperlabs.ai/mcp (X-API-Key 인증)
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

## 조직 일괄 배포 (IT 관리자)

Claude Code 관리 설정(managed settings)에 아래를 배포하면 심사관 개입 없이
자동 설치됩니다 (심사관은 `SKIPPER_API_KEY` 환경변수만 설정):

```json
{
  "extraKnownMarketplaces": {
    "skipperlabs": {
      "source": { "source": "github", "repo": "hauteone/skipper-claude-plugins" }
    }
  },
  "enabledPlugins": { "skipper@skipperlabs": true }
}
```
