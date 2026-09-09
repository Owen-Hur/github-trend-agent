"""설정 로딩과 사전 검증.

시크릿 검증은 실행 시작 시점에 한 번에 끝낸다. LLM 호출을 다 마친 뒤
Slack 키가 없어서 터지면 토큰과 시간을 그냥 버리게 된다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ── 수집 파라미터 (2026-09-09 실API 측정 근거) ──────────────────────
# 화→금 3일, 금→화 4일 간격 + 별 축적 인큐베이션 ~3일 = 7일 윈도우.
WINDOW_DAYS = 7
MIN_STARS = 50
CANDIDATE_PER_PAGE = 30  # 중복 제거 후에도 5건이 남도록 넉넉히 받는다
PICK_COUNT = 5

# 트랙 B: 7일 윈도우를 지난 뒤 폭발하는 대형 건 회수용.
BREAKOUT_WINDOW_DAYS = 30
BREAKOUT_MIN_STARS = 5000
BREAKOUT_PICK_COUNT = 3

# 품질 하한선: 이 미만이면 건수를 채우지 않고 줄여 발송한다.
QUALITY_FLOOR = 50

# 중복 제거 상태 보관 기간.
# 트랙 B 윈도우(30일)와 같은 값이라 경계에서 재등장 가능성이 아주 낮게 존재한다.
# 완전히 없애려면 BREAKOUT_WINDOW_DAYS 보다 며칠 크게 잡으면 된다.
SEEN_RETENTION_DAYS = 30

README_EXCERPT_CHARS = 1000

MODEL = "claude-sonnet-5"
TEMPERATURE = 0.6

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "state" / "seen_repos.json"


@dataclass
class Config:
    github_token: str | None
    anthropic_key: str | None
    slack_webhook: str | None
    repository: str | None = None  # owner/repo — Actions가 자동 주입한다

    @classmethod
    def from_env(cls) -> "Config":
        def clean(name: str) -> str | None:
            v = (os.environ.get(name) or "").strip()
            return v or None

        return cls(
            github_token=clean("GH_PAT") or clean("GITHUB_TOKEN"),
            anthropic_key=clean("ANTHROPIC_API_KEY"),
            slack_webhook=clean("SLACK_WEBHOOK_URL"),
            repository=clean("GITHUB_REPOSITORY"),
        )

    def validate(
        self,
        *,
        need_llm: bool,
        targets: list[str] | None = None,
        want_token: bool = False,
    ) -> None:
        missing = []
        if need_llm and not self.anthropic_key:
            missing.append("ANTHROPIC_API_KEY (--no-llm 을 쓰면 불필요)")
        targets = targets or []
        if "slack" in targets and not self.slack_webhook:
            missing.append("SLACK_WEBHOOK_URL (--deliver 에서 slack 을 빼면 불필요)")
        if "issue" in targets:
            if not self.github_token:
                missing.append("GH_PAT (issue 전달에 필요)")
            if not self.repository:
                missing.append("GITHUB_REPOSITORY=owner/repo (issue 전달에 필요)")
        if missing:
            raise SystemExit(
                "필수 환경변수가 없습니다:\n  - " + "\n  - ".join(missing)
            )
        if want_token and not self.github_token:
            # 클라이언트가 비인증 한도(분당 10회)에 맞춰 자체 스로틀링하므로
            # 실행은 되지만 매우 느려진다. 막지 말고 알리기만 한다.
            print("경고: GH_PAT 이 없어 비인증 한도(분당 10회)로 실행합니다. 상당히 느립니다.")
