# GitHub 트렌드 브리핑 에이전트

**매일 오전 9시(KST)**, 최근 급상승한 GitHub 신규 저장소를 수집해 Claude로 분석하고 Slack으로 보낸다.

주기·윈도우·임계치는 감이 아니라 **실제 GitHub Search API 측정값**에 근거해 정했다. 근거는 아래 [설계 근거](#설계-근거)에 정리돼 있고, 전체 설계 문서는 [github_trend_agent_design.md](github_trend_agent_design.md)에 있다.

---

## 동작 방식

```
GitHub Actions cron (매일 00:00 UTC = 09:00 KST)
        │
        ├─ 트랙 A  created:>7일전 stars:>50      → 후보 30건
        ├─ 트랙 B  created:>30일전 stars:>5000   → 뒤늦게 터진 대형 건
        │
        ├─ 중복 제거   state/seen_repos.json (30일 보관)
        ├─ 품질 하한선  ⭐50 미만이면 건수를 줄여 발송
        ├─ 컨텍스트 보강 README 상단 1,000자 (배지·HTML 제거)
        ├─ LLM 분석    Claude tool schema로 4개 필드 강제
        │
        └─ 전달        slack / issue / file / summary / stdout
```

저장소마다 다음 4개 필드가 생성된다.

| 필드 | 내용 |
|---|---|
| 핵심 요약 | 비개발자도 이해할 1문장 기능 정의 |
| 적용 분야 | 고정 태그에서 1~2개 (AI/ML, 백엔드, 데이터 엔지니어링, DevOps, 보안, 프론트엔드, 기타) |
| 활용 시나리오 | 현재 워크플로에 즉시 적용 가능한 예시 |
| 확장 아이디어 | 타 도구 결합 시 고도화 방향 |

---

## 빠른 시작

### 1. 아무것도 없이 수집만 확인

외부 의존성이 필요 없다. 수집·조립 경로는 표준 라이브러리만 쓴다.

```bash
python3 -m src.main --dry-run --no-llm
```

실제 GitHub API를 호출해 후보를 뽑고, 발송 없이 결과를 출력한다.

### 2. LLM 분석까지 붙이기

```bash
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... python3 -m src.main --dry-run
```

### 3. Slack 연결

아래 [Slack 연결하기](#slack-연결하기) 절차로 웹훅 URL을 발급한 뒤:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \
ANTHROPIC_API_KEY=sk-ant-... \
python3 -m src.main
```

### 4. 자동화

저장소 시크릿 3개를 등록하면 매일 자동 발송이 시작된다.

```bash
gh secret set SLACK_WEBHOOK_URL
gh secret set ANTHROPIC_API_KEY
```

바로 확인하려면 수동 실행:

```bash
gh workflow run "GitHub 트렌드 브리핑"
```

---

## Slack 연결하기

> **유료 구독은 필요 없다.** Incoming Webhooks는 무료 플랜을 포함한 모든 플랜에서 쓸 수 있다.
> 다만 무료 플랜은 **워크스페이스당 앱·연동 10개 제한**이 있어, 이미 10개가 차 있으면 하나를 지워야 추가된다.

1. <https://api.slack.com/apps> → **Create New App** → **From scratch**
2. 앱 이름을 짓고 대상 워크스페이스를 선택한다
3. 좌측 **App Home**에서 Bot 표시명(Display Name)을 **먼저** 설정한다
   — 이걸 건너뛰면 다음 단계에서 오류가 날 수 있다
4. 좌측 **Features → Incoming Webhooks** → 토글 **On**
5. 하단 **Add New Webhook to Workspace** → 게시할 채널 선택 → **허용**
6. 발급된 `https://hooks.slack.com/services/...` URL을 복사

### 발송 전에 서식 먼저 보기

`--dry-run`이 Slack에 보낼 페이로드를 그대로 출력한다. 출력의 `blocks` 배열을
<https://app.slack.com/block-kit-builder>에 붙이면 실제 렌더링을 미리 볼 수 있다.

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \
python3 -m src.main --dry-run --no-llm
```

### 주의

- **웹훅 생성 계정이 워크스페이스를 나가면 URL이 비활성화될 수 있다.** 공용 계정을 쓰거나, 이탈 가능성이 낮은 팀원을 앱 Collaborator로 추가해 두는 편이 안전하다.
- 웹훅 URL당 초당 1회 전송 제한이 있으나, 주 2회 실행이므로 무관하다.
- 마켓플레이스의 구형 "Incoming WebHooks" 커스텀 연동은 legacy이며 지원 종료 예정이다. 위 절차(앱을 직접 만드는 방식)를 쓸 것.

---

## 환경변수

| 변수 | 필수 여부 |
|---|---|
| `SLACK_WEBHOOK_URL` | `--deliver`에 `slack`이 포함될 때 필수 |
| `ANTHROPIC_API_KEY` | `--no-llm`이 아닐 때 필수 |
| `GH_PAT` | 브리핑에서는 선택(rate limit 여유). `issue` 전달과 명예의 전당 모드에서는 필수 |
| `GITHUB_REPOSITORY` | `issue` 전달에만 필요. Actions 안에서는 자동 주입 |
| `BRIEFING_LANG` | 선택. 브리핑 언어 (`한국어` 기본 / `English`). 미등록 언어를 넣으면 라벨은 영어, 본문은 해당 언어 |

`.env.example`을 참고할 것. `.env`는 `.gitignore`에 있다.

---

## CLI

```bash
python3 -m src.main [옵션]
```

| 옵션 | 설명 |
|---|---|
| `--dry-run` | 실제 전달 없이 결과만 출력. 상태 파일도 건드리지 않는다 |
| `--no-llm` | LLM 분석을 건너뛰고 원본 description 사용 |
| `--deliver` | 전달 대상. 쉼표 구분. 기본값 `auto` |
| `--mode` | `briefing`(기본) 또는 `hall-of-fame` |

### 전달 대상

| 값 | 설명 |
|---|---|
| `slack` | Block Kit 웹훅 |
| `issue` | 회차별 GitHub Issue — 알림·스레드 토론·검색 가능 |
| `file` | `briefings/YYYY-MM-DD.md` 아카이브 |
| `summary` | GitHub Actions 실행 요약 화면 |
| `stdout` | 터미널 |
| `auto` | 준비된 수단을 자동 선택 (웹훅 있으면 slack, 없으면 issue+file) |

Slack이 막히거나 정책이 바뀌어도 **코드 수정 없이 대상만 교체**하면 된다.

```bash
python3 -m src.main --deliver issue,file    # Slack 없이 운영
```

---

## 연도별 명예의 전당

해당 연도에 **생성된** 저장소의 **현재** 누적 별 순위를 뽑는다. 정기 발송이 아닌 온디맨드 리포트다.

```bash
GH_PAT=ghp_... python3 -m src.main --mode hall-of-fame -o HALL_OF_FAME.md
```

2008년~현재까지 연도당 1회, 총 19회 연속 호출이므로 **PAT 인증을 권장**한다. 비인증(분당 10회)이면 자동 스로틀링이 걸려 매우 느려진다.

`--since 2020`으로 시작 연도를, `--top 20`으로 연도별 개수를 조정할 수 있다.

---

## 설계 근거

주기와 임계치는 2026-09-09에 실제 API를 측정해 정했다.

### 왜 매일이 아니라 화·금인가

1일 윈도우는 성립하지 않는다. `created:>어제 stars:>10` → **0건**. 갓 생성된 저장소는 별이 붙을 물리적 시간이 없다.

주기별로 회당 뽑히는 상위 5건의 별점대를 비교하면:

| 주기 | 회당 상위 5건 별점대 | 주간 발송량 |
|---|---|---|
| 매일 (3일 윈도우) | ⭐100 ~ 300 | 35건 |
| **화·금 (7일 윈도우)** | **⭐392 ~ 493** | **10건** |
| 주 1회 (7일 윈도우) | ⭐332 ~ 1,127 | 5건 |

화요일이 상위 5건을 소비했는데도 금요일 픽이 ⭐392~493으로 나온다. 윈도우가 3일 미끄러지면서 top30의 절반(15건)이 교체되기 때문이다. **화·금은 처리량을 2배로 늘리면서 품질 비용을 거의 내지 않는 지점**이다.

### 왜 7일 윈도우인가

화→금 3일, 금→화 4일 간격에 별 축적 인큐베이션 ~3일을 더하면 7일이 나온다. 화요일에 별이 부족해 탈락한 저장소는 금요일에 4일치 별을 쌓은 채 여전히 윈도우 안에 있어 회수된다. **누락 구멍이 없다.**

### 왜 README 보강이 필수인가

후보 top30 중 **`topics`가 빈 저장소 23건(77%)**, `description` 80자 미만 18건(60%). 보강 없이는 LLM에 넘길 재료가 저장소 이름뿐인 경우가 태반이다.

### 왜 ⭐1k를 기준으로 삼지 않는가

| 생성 후 경과 | ⭐1k+ 도달 수 |
|---|---|
| 3일 | 1건 |
| 7일 | 5건 |
| 14일 | 20건 |
| 30일 | 90건 |
| 90일 | 431건 |
| 365일 | 3,558건 |

**3일 안에 ⭐1k를 넘긴 저장소는 전 GitHub 통틀어 1건.** ⭐1k는 2주~1개월 단위의 현상이다. 이를 임계치로 삼으면 2~4주 늦게 발견하게 된다. 지금 브리핑이 뽑는 ⭐300~500 구간이 "1k 직전" 단계다.

---

## 튜닝

수집 파라미터는 [src/config.py](src/config.py) 상단 상수로 모여 있다.

| 상수 | 기본값 | 의미 |
|---|---|---|
| `WINDOW_DAYS` | 7 | 트랙 A 윈도우 |
| `MIN_STARS` | 50 | 트랙 A 별 임계치 |
| `PICK_COUNT` | 5 | 회당 발송 건수 |
| `QUALITY_FLOOR` | 50 | 이 미만이면 건수를 채우지 않음 |
| `BREAKOUT_WINDOW_DAYS` | 30 | 트랙 B 윈도우 |
| `BREAKOUT_MIN_STARS` | 5000 | 트랙 B 별 임계치 |
| `SEEN_RETENTION_DAYS` | 30 | 소개 이력 보관 기간 |
| `LANGUAGE` | 한국어 | 브리핑 언어 (`BRIEFING_LANG` 환경변수로 덮어씀) |

3일 간격에 신규가 15건 유입되는데 5건만 소비하므로 헤드룸이 있다. `PICK_COUNT`는 7까지 품질 저하 없이 올릴 수 있다. 다만 **5로 시작해 실제로 다 읽히는지 보고 조정**하길 권한다 — 늘리는 건 쉽고 줄이는 건 어렵다.

> `SEEN_RETENTION_DAYS`(30)가 `BREAKOUT_WINDOW_DAYS`(30)와 같아, 경계에서 트랙 B 항목이 드물게 재등장할 여지가 있다. 완전히 없애려면 35로 올리면 된다.

---

## 테스트

네트워크 없이 도는 핵심 로직 테스트 43건.

```bash
python3 -m tests.test_core
```

배지·HTML 제거, 품질 하한선, 상태 파일 영속화·파기·손상 복구, Block Kit 제한(50블록/3,000자), mrkdwn 이스케이프, 전달 대상 결정, 시크릿 사전 검증, fallback 동작을 덮는다.

---

## 구조

```
src/
├── main.py          오케스트레이션 — 부작용은 여기에만
├── config.py        환경변수 + 수집 파라미터 상수
├── http_util.py     stdlib 기반 HTTP (수집 경로를 무의존성으로 유지)
├── github_client.py Search API(트랙 A/B) + README 보강
├── dedup.py         소개 이력 관리
├── analyzer.py      Claude tool schema로 4개 필드 생성
├── render.py        Markdown 렌더링 (issue/file/summary 공용)
├── slack.py         Block Kit 빌드 + 제한 준수
├── deliver.py       전달 sink 교체
├── hall_of_fame.py  연도별 리포트
└── models.py        Repo / Analysis / Briefing
```

각 모듈은 순수 함수 경계로 잘려 있고 `main.py`만 네트워크·파일을 건드린다. 그래서 LLM·Slack 없이도 단계별로 검증된다.

유일한 외부 의존성은 `anthropic`이다.
