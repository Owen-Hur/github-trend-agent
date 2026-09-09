"""GitHub Search API 수집 + README 컨텍스트 보강.

엔드포인트는 반드시 api.github.com 서브도메인을 쓴다.
github.com 은 웹 UI 도메인이라 API 호출이 되지 않는다.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import config
from .http_util import HttpError, get_json, get_text
from .models import Repo

API = "https://api.github.com"

# README 상단은 배지 덩어리인 경우가 대부분이라, 그대로 넘기면 LLM에 노이즈만 들어간다.
_BADGE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINKED_BADGE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BLANK_RUN = re.compile(r"\n{3,}")


def clean_readme(raw: str, limit: int = config.README_EXCERPT_CHARS) -> str:
    text = _HTML_COMMENT.sub("", raw)
    text = _LINKED_BADGE.sub("", text)
    text = _BADGE_IMAGE.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _MD_LINK.sub(r"\1", text)  # 링크는 표시 텍스트만 남긴다
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip() not in {"", "|", "---"} or ln == ""]
    text = _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip()
    return text[:limit]


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token
        self._last_call = 0.0
        # 비인증 Search API 한도는 분당 10회(헤더 실측). PAT 인증 시 여유가 생긴다.
        self._min_interval = 2.5 if token else 7.0

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        h = {"Accept": accept}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    # ── 검색 ────────────────────────────────────────────────────────
    def search(self, query: str, per_page: int = 30) -> tuple[list[Repo], int]:
        self._throttle()
        params = urllib.parse.urlencode(
            {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}
        )
        body, headers = get_json(f"{API}/search/repositories?{params}", self._headers())
        remaining = headers.get("x-ratelimit-remaining")
        if remaining is not None:
            print(f"  [rate limit 잔여: {remaining}]")
        return [Repo.from_api(i) for i in body.get("items", [])], body.get("total_count", 0)

    def search_fresh(self, now: datetime | None = None) -> tuple[list[Repo], int]:
        """트랙 A — 최근 생성 & 초기 반응이 붙은 저장소."""
        since = _days_ago(config.WINDOW_DAYS, now)
        q = f"created:>{since} stars:>{config.MIN_STARS}"
        print(f"[트랙 A] {q}")
        return self.search(q, config.CANDIDATE_PER_PAGE)

    def search_breakout(self, now: datetime | None = None) -> tuple[list[Repo], int]:
        """트랙 B — 7일 윈도우를 지난 뒤 폭발한 대형 건."""
        since = _days_ago(config.BREAKOUT_WINDOW_DAYS, now)
        q = f"created:>{since} stars:>{config.BREAKOUT_MIN_STARS}"
        print(f"[트랙 B] {q}")
        return self.search(q, config.CANDIDATE_PER_PAGE)

    def search_topic(self, track: dict, now: datetime | None = None) -> tuple[list[Repo], int]:
        """분야별 트랙 — 니치 분야는 7일 윈도우로 성립하지 않아 30일을 쓴다."""
        since = _days_ago(config.TOPIC_WINDOW_DAYS, now)
        q = f"{track['query']} stars:>{track['min_stars']} created:>{since}"
        print(f"[{track['name']}] {q}")
        return self.search(q, config.CANDIDATE_PER_PAGE)

    def search_year(self, year: int, min_stars: int = 1000, top: int = 10) -> tuple[list[Repo], int]:
        """명예의 전당 — 해당 연도에 생성된 저장소의 현재 누적 별 상위 N건."""
        q = f"created:{year}-01-01..{year}-12-31 stars:>{min_stars}"
        return self.search(q, top)

    # ── 보강 ────────────────────────────────────────────────────────
    def enrich(self, repos: list[Repo]) -> None:
        """description/topics가 부실한 저장소에 README 발췌를 채운다.

        404·빈 README는 조용히 건너뛴다. 보강 실패가 전체 실행을 막아선 안 된다.
        """
        for repo in repos:
            if not repo.needs_enrichment:
                continue
            try:
                raw = get_text(
                    f"{API}/repos/{repo.full_name}/readme",
                    self._headers("application/vnd.github.raw"),
                )
            except (HttpError, OSError) as e:
                print(f"  README 건너뜀 {repo.full_name}: {e}")
                continue
            repo.readme_excerpt = clean_readme(raw)
            if repo.readme_excerpt:
                print(f"  README 보강 {repo.full_name} ({len(repo.readme_excerpt)}자)")


def _days_ago(days: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d")
