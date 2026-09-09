---
name: github-hall-of-fame
description: GitHub 명예의 전당 — 생성 연도별 누적 스타 TOP N 저장소를 조회해 표로 출력하거나 Markdown 리포트로 저장한다. "연도별 top10", "역대 인기 저장소", "2015년 저장소 순위", "명예의 전당", "hall of fame" 같은 요청에 사용한다.
---

# GitHub 명예의 전당

해당 연도에 **생성된** 저장소의 **현재** 누적 스타 순위를 뽑는다.
"그 해에 인기였던 것"이 아니라 "그 해에 태어나 지금까지 살아남은 것"을 보여준다.

## 실행

프로젝트 루트에서 실행한다. 가상환경이 있으면 `.venv/bin/python`을, 없으면 `python3`을 쓴다.

```bash
python3 -m src.main --mode hall-of-fame
```

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--since <연도>` | 2008 | 조회 시작 연도. 현재 연도부터 역순으로 내려간다 |
| `--top <N>` | 10 | 연도별 출력 개수 |
| `-o <경로>` | (없음) | Markdown 파일로 저장 |
| `--deliver slack` | (없음) | Slack 채널로 발송 |

`-o` 와 `--deliver` 를 모두 생략하면 화면에 출력한다. 둘을 함께 줘도 된다.

### 예시

```bash
# 2008년~현재, 연도별 top10 을 화면에 출력
python3 -m src.main --mode hall-of-fame

# 최근 5년만, 연도별 top20 을 파일로 저장
python3 -m src.main --mode hall-of-fame --since 2021 --top 20 -o HALL_OF_FAME.md

# Slack 채널로 발송 (연도당 한 블록으로 압축된 순위 목록)
python3 -m src.main --mode hall-of-fame --since 2022 --deliver slack
```

**Slack 발송은 되돌릴 수 없으므로 사용자가 명시적으로 요청했을 때만 한다.**
요청받았다면 `--dry-run` 을 함께 붙여 페이로드를 먼저 보여주고 확인받는 편이 안전하다.

## 사용자 요청 해석

- "연도별 top10" / "명예의 전당" → 옵션 없이 기본 실행
- "최근 N년" → `--since (현재연도 - N + 1)`
- "top20" 등 개수 지정 → `--top N`
- "파일로 저장" / "리포트로 만들어줘" → `-o HALL_OF_FAME.md`
- 특정 연도 하나만 물으면 → `--since` 를 그 연도로 두고, 출력에서 해당 연도 표만 사용자에게 보여준다

## 인증 — 중요

2008년부터 조회하면 **연도당 1회씩 총 19회 연속 호출**이 발생한다.
GitHub Search API 한도는 비인증 시 분당 10회라, 토큰이 없으면 자동 스로틀링이 걸려 2분 이상 걸린다.

`GH_PAT` 환경변수가 있으면 분당 30회로 올라가 훨씬 빠르다. `.env` 파일에 있다면 먼저 읽어들인다.

```bash
set -a; source .env; set +a
python3 -m src.main --mode hall-of-fame
```

`.env` 에 `GH_PAT` 이 없고 `gh` CLI 가 인증돼 있다면 그 토큰을 빌려 쓸 수 있다.

```bash
GH_PAT=$(gh auth token) python3 -m src.main --mode hall-of-fame
```

토큰이 전혀 없어도 실행은 된다 — 경고만 뜨고 느리게 진행된다. 막지 않는다.

## 결과 전달

- 화면 출력이면 Markdown 표가 그대로 나오므로 사용자에게 요약해 전달한다
- 연도 수가 많으면 전체를 그대로 붙여넣지 말고, 사용자가 물은 범위만 표로 보여주고 나머지는 파일 경로를 안내한다
- 흥미로운 흐름(연도별 주제 변화, 특정 저장소의 급부상)이 보이면 짚어준다

## 주의

- 기본적으로는 Slack 으로 발송하지 않는다. 정기 브리핑과 별개의 온디맨드 리포트이므로, 채널로 보내려면 `--deliver slack` 을 명시해야 한다
- Slack 은 Markdown 표를 렌더링하지 못하므로 발송 시에는 연도당 한 블록의 목록 형태로 바뀐다
- 소개 이력(`state/seen_repos.json`)을 건드리지 않는다. 몇 번을 돌려도 정기 브리핑에 영향이 없다
- `ANTHROPIC_API_KEY` 는 필요 없다. LLM 분석 없이 GitHub 데이터만 집계한다
