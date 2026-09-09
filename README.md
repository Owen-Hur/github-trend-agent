# GitHub 트렌드 브리핑 에이전트

매일 오전 9시(KST), 급상승 중인 GitHub 신규 저장소를 수집해 Claude로 분석하고 Slack으로 보낸다.

저장소마다 **핵심 요약 / 적용 분야 / 활용 시나리오 / 확장 아이디어** 4개 필드가 생성된다.
윈도우·임계치·주기는 감이 아니라 실제 Search API 측정값으로 정했다 — 근거는 [설계 문서](github_trend_agent_design.md)에 있다.

## 무엇이 언제 오나

| 요일 | 구성 | 건수 |
|---|---|---|
| 월~목·토·일 | 최근 7일 신규 5건 + 뒤늦게 터진 대형 건 3건 | 8건 |
| **금요일** | 위 8건 + Finance·Quant·Trading·Agent 각 3건 | 20건 |

```
GitHub Actions cron (매일 00:00 UTC = 09:00 KST)
   │
   ├─ 수집     트랙 A: created:>7일  stars:>50
   │           트랙 B: created:>30일 stars:>5000   (뒤늦게 터진 것)
   │           분야별: 30일 윈도우, 분야마다 임계치 개별   (금요일만)
   ├─ 중복 제거  state/seen_repos.json (30일 보관)
   ├─ 보강      README 상단 1,000자 — 배지·HTML 제거
   ├─ 분석      Claude tool schema 로 4개 필드 강제
   └─ 전달      slack / issue / file / summary / stdout
```

맥북이 꺼져 있어도 무관하다. GitHub 서버에서 실행된다.

## 빠른 시작

```bash
# 1. 수집만 확인 — 설치도 키도 필요 없다 (stdlib 만 사용)
python3 -m src.main --dry-run --no-llm

# 2. 분석까지 붙여 미리보기 (발송 안 함)
pip install -r requirements.txt
ANTHROPIC_API_KEY=... python3 -m src.main --dry-run

# 3. 실제 발송
SLACK_WEBHOOK_URL=... ANTHROPIC_API_KEY=... python3 -m src.main
```

자동화는 저장소 시크릿 2개만 등록하면 시작된다. `GH_PAT`은 Actions가 토큰을 자동 주입하므로 불필요하다.

```bash
gh secret set SLACK_WEBHOOK_URL
gh secret set ANTHROPIC_API_KEY
gh workflow run "GitHub 트렌드 브리핑"   # 즉시 확인
```

## Slack 웹훅 발급

유료 구독은 필요 없다. 무료 플랜의 앱 10개 제한만 걸릴 수 있다.

1. <https://api.slack.com/apps> → **Create an App** → **Blank app**
2. 앱 이름·워크스페이스 선택 → 생성
3. 좌측 **Incoming Webhooks** → 토글 **On**
4. **Add New Webhook to Workspace** → 채널 선택 → **Allow**
5. `https://hooks.slack.com/services/...` 복사 (정상 길이 81자)

```bash
python3 scripts/set_webhook.py            # 검증 후 .env 에 저장
python3 scripts/check_webhook.py --ping   # 어느 채널로 가는지 확인
```

> 숨김 입력이라 붙여넣기가 됐는지 보이지 않아 **중복 붙여넣기가 잘 일어난다.** 깨진 URL은 Slack이 문서 페이지로 리다이렉트하며 HTTP 200을 주기 때문에 조용히 실패한다. 위 스크립트가 형식을 검사해 막고, 실행 경로에서도 한 번 더 검증한다.

## 설정

환경변수 — `.env.example` 참고. `.env`는 `.gitignore` 대상이다.

| 변수 | 필요 시점 |
|---|---|
| `SLACK_WEBHOOK_URL` | Slack 발송 시 |
| `ANTHROPIC_API_KEY` | `--no-llm`이 아닐 때 |
| `GH_PAT` | 선택. `issue` 전달·명예의 전당 모드에서 필요 |
| `BRIEFING_LANG` | 선택. `한국어`(기본) / `English` |

수집 파라미터는 [src/config.py](src/config.py) 상단에 모여 있다.

| 상수 | 기본값 | 의미 |
|---|---|---|
| `WINDOW_DAYS` / `MIN_STARS` | 7 / 50 | 메인 트랙 윈도우·임계치 |
| `PICK_COUNT` | 5 | 회당 발송 건수 — 품질을 가르는 손잡이 |
| `BREAKOUT_WINDOW_DAYS` / `BREAKOUT_MIN_STARS` | 30 / 5000 | 뒤늦게 터진 것 |
| `TOPIC_TRACKS` | 4개 | 분야별 검색어·임계치 (분야마다 개별) |
| `TOPIC_WEEKDAYS` | `[4]` | 분야별 실행 요일 (0=월, 4=금), KST 기준 |
| `SEEN_RETENTION_DAYS` | 30 | 소개 이력 보관 기간 |

## CLI

| 옵션 | 설명 |
|---|---|
| `--dry-run` | 전달 없이 결과만 출력. 상태 파일도 건드리지 않는다 |
| `--no-llm` | 분석을 건너뛰고 원본 description 사용 |
| `--topics` | `auto`(요일 따름) / `on` / `off` |
| `--deliver` | `slack` `issue` `file` `summary` `stdout` 쉼표 구분. 기본 `auto` |
| `--mode` | `briefing`(기본) / `hall-of-fame` |

Slack이 막혀도 코드 수정 없이 대상만 바꾸면 된다 — `--deliver issue,file`.

### 연도별 명예의 전당

해당 연도에 **생성된** 저장소의 **현재** 누적 별 순위. 정기 발송과 무관한 온디맨드 리포트다.

```bash
GH_PAT=$(gh auth token) python3 -m src.main --mode hall-of-fame -o HALL_OF_FAME.md
```

Claude Code 스킬로도 등록돼 있어 "연도별 top10 보여줘"라고 하면 실행된다.

## 설계에서 중요한 결정 셋

- **7일 윈도우** — `created:>어제 stars:>10`은 **0건**이다. 갓 만든 저장소는 별이 붙을 시간이 없어 2~3일 인큐베이션이 필요하다. 7일은 그걸 포함하면서, 중복 제거와 맞물려 한 번 놓친 저장소를 다음 회차에 회수한다.
- **분야별만 30일** — 7일로는 Finance·Quant·Trading이 각 1건뿐이라 3건을 채울 수 없다. 30일이면 8·10·22건. 반대로 Agent는 490건으로 너무 넓어 임계치만 ⭐1000으로 올렸다.
- **README 보강은 필수** — 후보 top30 중 `topics`가 빈 저장소가 **23건(77%)**. 보강 없이는 LLM에 넘길 재료가 저장소 이름뿐이다.

## 실패했을 때

- **LLM 전량 실패** → 발송하지 않고 종료 코드 1. 상태도 갱신하지 않아 다음 실행에서 온전히 회수된다. 분석 없는 브리핑을 보내면서 저장소 재고만 태우는 일이 없다.
- **잘못된 웹훅** → 응답 본문이 `ok`인지 검증해 조용한 실패를 막는다.
- **실행 자체를 놓침** → Actions cron은 밀린 회차를 따라잡지 않는다. 다만 저장소는 윈도우 안에 남아 다음 실행에서 다시 후보에 오른다.

```bash
gh run list --workflow="briefing.yml" --limit 5
```

## 테스트

```bash
python3 -m tests.test_core
```

네트워크 없이 도는 73건. 배지 제거, 품질 하한선, 상태 파일 파기·손상 복구, Block Kit 제한과 메시지 분할, mrkdwn 이스케이프, 전달 대상 결정, 시크릿·웹훅 검증, 언어 전환, 요일 게이팅을 덮는다.

## 구조

```
src/
├── main.py          오케스트레이션 — 부작용은 여기에만
├── config.py        수집 파라미터 + 환경변수 검증
├── i18n.py          언어별 라벨·요일·분야 태그
├── http_util.py     stdlib HTTP (수집 경로를 무의존성으로 유지)
├── github_client.py Search API + README 보강
├── dedup.py         소개 이력 관리
├── analyzer.py      Claude tool schema 로 4개 필드 생성
├── render.py        Markdown (issue/file/summary 공용)
├── slack.py         Block Kit + 50블록 초과 시 메시지 분할
├── deliver.py       전달 sink 교체
├── hall_of_fame.py  연도별 리포트
└── models.py        Repo / Analysis / Briefing
```

각 모듈은 순수 함수 경계로 잘려 있고 `main.py`만 네트워크·파일을 건드린다.
외부 의존성은 `anthropic` 하나뿐이다.
