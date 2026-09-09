# GitHub 트렌드 분석 & Slack 알림 에이전트 — 설계 로드맵

> 최종 갱신: 실행 주기 주 2회(화·금) 확정, 중복 제거·README 보강 필수화, 명예의 전당 모드 추가
> 스택 확정: Python + Claude API(`claude-opus-5`) + Slack Incoming Webhook

## 1. 아키텍처

```
[실행 트리거: GitHub Actions Cron (매일 09:00 KST) / 수동 실행]
           │
           ▼
┌────────────────────────────────────────────────────────┐
│               GitHub Trend Analyst Agent                │
├────────────────────────────────────────────────────────┤
│ 1. 데이터 수집 (GitHub REST Search API)                 │
│    - 트랙 A 신규: created:>7일전 stars:>50               │
│    - 트랙 B 뒤늦게 터진 것: created:>30일전 stars:>5000  │
├────────────────────────────────────────────────────────┤
│ 2. 중복 제거 (state/seen_repos.json, 90일 보관)          │
├────────────────────────────────────────────────────────┤
│ 3. 컨텍스트 보강 (필수) — README 상단 파싱               │
├────────────────────────────────────────────────────────┤
│ 4. LLM 분석 엔진 (Claude, tool schema로 4개 필드 강제)   │
├────────────────────────────────────────────────────────┤
│ 5. 전달 (Slack Incoming Webhook, Block Kit)              │
└────────────────────────────────────────────────────────┘
           │
           ▼
[Slack 채널 수신]
```

## 2. 실행 주기 — 화·금 주 2회

일간 실행을 검토했으나 **주 2회(화·금)로 확정**. 근거:

- `created:>어제 stars:>10` → **0건**. 갓 생성된 저장소는 별이 붙을 물리적 시간이 없어 1일 윈도우는 성립하지 않는다.
- 화→금 3일, 금→화 4일 간격. 별 축적에 필요한 인큐베이션 ~3일을 더하면 **윈도우 7일**이 정확히 필요하다. 화요일에 별이 부족해 탈락한 저장소는 금요일에 4일치 별을 쌓은 채 여전히 7일 윈도우 안에 있어 회수된다. **누락 구멍 없음.**
- 실측(2026-09-09): 화↔금 간격 시뮬레이션 시 top30 중 **15건이 신규**로 교체. 중복 제거 후 상위 5건의 별점대는 **⭐493 / 493 / 484 / 407 / 392**.
  (일간 실행 시 같은 위치의 별점대는 ⭐100~300대로, 주 2회 쪽이 오히려 품질이 높다.)

**사용자 요청으로 매일 실행으로 변경됨** — cron `0 0 * * *` (매일 00:00 UTC = 09:00 KST).
측정상 매일 실행은 회당 별점대가 ⭐100~300으로 화·금(⭐392~493)보다 낮다. 품질이 아쉬우면 `PICK_COUNT`를 5→3으로 낮추면 회당 상위권만 남는다.

## 3. 단계별 상세 명세

### Phase 1 — 데이터 수집 (검증 완료 ✅)

- 엔드포인트: `GET https://api.github.com/search/repositories`
  (원본 설계의 `https://github.com`은 웹 UI 도메인이며 오류. API는 반드시 `api.github.com` 서브도메인 사용)
- **트랙 A (신규)**: `q=created:>{7일 전} stars:>50`, `sort=stars`, `order=desc`, `per_page=30`
  - 후보를 30건 받아 중복 제거 후 상위 5건을 확정한다. `per_page=5`로 받으면 중복 제거 후 개수가 모자란다.
- **트랙 B (뒤늦게 터진 것)**: `q=created:>{30일 전} stars:>5000`
  - 7일 윈도우를 지난 뒤 폭발하는 대형 건을 회수하기 위한 보조 쿼리. 실측상 30일 내 생성분에 ⭐216,389 / 24,574 / 21,416 같은 건이 존재한다.
- **실검증 결과** (2026-09-09 실행):
  - HTTP 200, 7일/⭐50 기준 `total_count` 199건, 상위 항목 정상 반환
  - 응답 필드에 `name`, `full_name`, `html_url`, `description`, `topics`, `stargazers_count` 모두 존재 확인
  - ⚠️ **top30 중 `topics`가 빈 저장소 23건(77%), `description` 80자 미만 18건(60%)** → README 보강은 선택이 아니라 필수
  - 비인증 요청 기준 Search API 한도: **분당 10회** (`x-ratelimit-limit` 헤더 실측)
- 인증: GitHub PAT를 `Authorization: Bearer <TOKEN>` 헤더에 포함. 명예의 전당 모드가 19회 연속 호출을 하므로 PAT가 사실상 필수다.

### Phase 2 — 중복 제거 (필수)

- `state/seen_repos.json`에 `{full_name, 최초 소개일, 당시 stars}` 기록
- 90일 경과 항목은 파기 (파일 무한 증식 방지)
- GitHub Actions가 실행 후 갱신분을 커밋 (`permissions: contents: write`)

### Phase 3 — 컨텍스트 보강 (필수)

- 트리거 조건: `description`이 없거나 80자 미만 **또는** `topics`가 빈 배열
  (실측상 후보의 대다수가 여기 해당하므로 사실상 전건 수행)
- `GET /repos/{owner}/{repo}/readme` — `Accept: application/vnd.github.raw`
- 상단 ~1,000자만 취하고, **배지·이미지 링크·HTML 태그는 제거**한다. README 상단은 배지 덩어리인 경우가 대부분이라 그대로 넘기면 LLM에 노이즈만 들어간다.
- 404·빈 README는 조용히 건너뛴다.

### Phase 4 — LLM 분석 엔진

Claude Messages API + **tool schema로 4개 필드를 강제**한다. 자유 텍스트 파싱은 쓰지 않는다.

| 필드 | 타입 | 설명 |
|---|---|---|
| 핵심 요약 | string | 비개발자도 이해할 1문장 기능 정의 |
| 적용 분야 | enum 배열 (1~2개) | AI/ML, 백엔드, 데이터 엔지니어링, DevOps, 보안, 프론트엔드, 기타 |
| 활용 시나리오 | string | 현재 워크플로에 즉시 적용 가능한 예시 |
| 확장 아이디어 | string | 타 도구 결합 시 고도화 방향 |

- 저장소 3~5건을 **한 번의 호출로 배치 처리**한다 (비용·지연 절감, 저장소 간 톤 일관성 확보)
- 깊이 조절: `output_config.effort = medium` (현행 API에서 `temperature` 는 제거됨)
- 실패 시 해당 저장소만 원본 description으로 폴백하고 전체 실행은 계속한다

### Phase 5 — 전달 (Slack Incoming Webhook)

1. `api.slack.com/apps` → **Create New App** → **From scratch**
2. 앱 이름 지정, 대상 워크스페이스 선택 (App Home에서 Bot 표시명 먼저 설정 — 생략 시 다음 단계 오류 발생 가능)
3. **Features → Incoming Webhooks** → 토글 On
4. **Add New Webhook to Workspace** → 채널 선택 → 허용
5. 발급된 `https://hooks.slack.com/services/...` URL에 JSON POST

블록 구성: 헤더 1개 + 저장소당 `section`(제목 링크·⭐·태그) + `fields`(4개 항목) + `divider`. 트랙 B 결과는 "🔥 뒤늦게 터진 것" 섹션으로 분리.

Slack 제약을 코드에 반영: **메시지당 블록 50개, `text` 3,000자** → 필드별 truncate 유틸 필수.
POST 실패 시 지수 백오프 3회 재시도, 최종 실패면 비정상 종료 코드로 Actions를 실패 처리(조용한 실패 방지).

⚠️ 웹훅 생성 계정이 워크스페이스를 나가면 URL이 비활성화될 수 있음 → 공용 계정 또는 이탈 가능성 없는 팀원을 Collaborator로 추가 권장. 웹훅 URL당 초당 1회 전송 제한 있으나 주 2회 실행이므로 무관.

### Phase 6 — 품질 하한선

중복 제거 후 **⭐50 미만만 남는 날은 5건을 억지로 채우지 않는다.** 3건, 2건, 0건으로 줄여 발송한다. "매번 반드시 5건"보다 "기준 미달이면 적게"가 피로도 관리에 낫다. 0건인 날은 "이번 회차 신규 추천 없음"만 발송.

### Phase 7 — 자동화 (GitHub Actions)

```yaml
# .github/workflows/briefing.yml
on:
  schedule:
    - cron: '0 0 * * *'   # 매일 00:00 UTC (09:00 KST)
  workflow_dispatch: {}
permissions:
  contents: write            # state/seen_repos.json 커밋용
```

시크릿 3종: `GH_PAT`, `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL`.
`config.py`에서 **시작 시 한 번에 검증**하고 없으면 즉시 중단한다 (LLM 호출을 다 끝낸 뒤 Slack 키가 없어 터지는 낭비 방지).

## 4. 별도 모드 — 연도별 명예의 전당

브리핑과 성격이 다른 온디맨드 리포트. Slack 정기 푸시가 아니라 **Markdown/HTML 리포트 생성**으로 분리한다.

- `--mode=hall-of-fame`
- 연도별 `created:{YYYY}-01-01..{YYYY}-12-31 stars:>1000`, `sort=stars`, `per_page=10`
- 2008~현재 = 19회 연속 호출 → **PAT 인증 필수** (비인증 분당 10회로는 스로틀링 필요)
- 데이터가 느리게 변하므로 월 1회 또는 수동 실행으로 충분

### 실측 참고 — 별 축적 속도 (2026-09-09)

| 생성 후 경과 | ⭐1k+ 도달 저장소 수 | 구간 증가분 |
|---|---|---|
| 3일 | 1건 | — |
| 7일 | 5건 | +4 |
| 14일 | 20건 | +15 |
| 30일 | 90건 | +70 |
| 60일 | 253건 | +163 |
| 90일 | 431건 | +178 |
| 180일 | 1,543건 | +1,112 |
| 365일 | 3,558건 | +2,015 |

**3일 안에 ⭐1k를 넘긴 저장소는 전 GitHub 통틀어 1건.** ⭐1k는 2주~1개월 단위의 현상이다.
→ 브리핑이 뽑는 ⭐300~500 구간은 "1k 직전" 단계이며, 1k를 임계치로 삼으면 2~4주 늦게 발견하게 된다. 현재 임계치(⭐50 + 상위 5건)가 적정하다.

## 5. 파일 구조

```
GithubResearch/
├── .github/workflows/briefing.yml
├── src/
│   ├── main.py          # 오케스트레이션, CLI 플래그(--dry-run/--no-llm/--mode)
│   ├── config.py        # 환경변수 로딩·사전 검증 + 수집 파라미터 상수
│   ├── http_util.py     # stdlib 기반 HTTP (수집 경로를 무의존성으로 유지)
│   ├── github_client.py # Search API(트랙 A/B) + README 보강·배지 제거
│   ├── dedup.py         # seen_repos.json 로드/필터/갱신/파기
│   ├── analyzer.py      # Claude tool schema로 4개 필드 생성
│   ├── slack.py         # Block Kit 빌드 + 제한 준수 + POST 재시도
│   ├── hall_of_fame.py  # 연도별 리포트 생성
│   └── models.py        # Repo / Analysis / Briefing 데이터클래스
├── state/seen_repos.json
├── tests/test_core.py   # 네트워크 없이 도는 핵심 로직 테스트
├── requirements.txt     # anthropic (유일한 외부 의존성)
└── .env.example
```

각 모듈은 순수 함수 경계로 자르고 `main.py`만 부작용(네트워크·파일)을 조립한다.
수집·조립 경로는 stdlib만 쓰므로 `--dry-run --no-llm`은 아무 설치 없이 즉시 실행된다.

## 6. 로드맵

| 단계 | 작업 내용 | 검증 기준 | 상태 |
|---|---|---|---|
| Phase 1 | Search API 쿼리 로직 (트랙 A/B) | 7일 내 저장소 30건 후보 추출 | **완료 ✅ 실API 검증** |
| Phase 2 | 중복 제거 state 관리 | 직전 회차 소개분이 재등장하지 않음 | **완료 ✅ 단위 테스트** |
| Phase 3 | README 보강 + 배지 제거 | topics 빈 저장소도 분석 가능한 재료 확보 | **완료 ✅ 실API 8/8건 발동** |
| Phase 4 | Claude tool schema 4개 필드 | 4개 필드 모두 누락 없이 생성 확인 | **완료 ✅ 실발송 검증** |
| Phase 5 | Slack Webhook 연동 (Block Kit) | 채널에 서식 깨짐 없이 메시지 수신 | **완료 ✅ 실발송 검증** |
| Phase 6 | 품질 하한선 로직 | 후보 부족 시 건수 축소 발송 확인 | **완료 ✅ 단위 테스트** |
| Phase 7 | GH Actions cron 배포 | 개입 없이 매일 자동 발송 | 워크플로 작성 완료 — **시크릿 등록 대기** |
| 별도 | 명예의 전당 모드 | 2008~현재 연도별 top10 리포트 생성 | **완료 ✅ 실API 검증** |

## 7. 검증 순서

1. `--dry-run --no-llm` → 수집 결과 JSON 출력. Phase 1 재현 확인
2. `--dry-run` → LLM까지 태우고 Slack 페이로드를 stdout에. Block Kit Builder에 붙여 서식 확인
3. 실제 Webhook 1회 발송 → 채널 수신 확인
4. `workflow_dispatch` 수동 실행 → 시크릿 경로 검증
5. cron 방치 → 다음 화요일 자동 발송 확인

## 8. 미확인/추정 사항 (근거 불충분)

- PAT 인증 시 Search API의 정확한 분당 요청 한도 수치는 공식 문서에서 최종 확인하지 못함 (명예의 전당 모드 19회 연속 호출 시 실측 필요)
- 트랙 B의 임계치 ⭐5000은 실측 분포에 근거한 추정치. 운영하며 조정 필요
- LLM 호출 실패·API 키 만료 시 별도 알림 경로 없음 → 최소한 Actions 실패 알림은 활성화 권장
