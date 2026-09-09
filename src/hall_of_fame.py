"""연도별 명예의 전당 리포트.

브리핑과 성격이 다르다. 정기 푸시가 아니라 온디맨드 리포트이므로
수집(collect)과 표현(to_markdown / Slack 블록)을 분리해 둔다.

2008~현재 = 19회 연속 검색 호출이므로 PAT 인증이 사실상 필수다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .github_client import GitHubClient
from .models import Repo

FIRST_YEAR = 2008


@dataclass
class YearEntry:
    year: int
    repos: list[Repo]
    total: int  # 해당 연도 ⭐1k+ 저장소 전체 수


@dataclass
class HallOfFame:
    generated_at: str
    top: int
    years: list[YearEntry]


def collect(client: GitHubClient, since: int = FIRST_YEAR, top: int = 10) -> HallOfFame:
    now = datetime.now(timezone.utc)
    years: list[YearEntry] = []
    for year in range(now.year, since - 1, -1):
        repos, total = client.search_year(year, top=top)
        if not repos:
            continue
        print(f"  {year}년 수집 완료 ({len(repos)}건)")
        years.append(YearEntry(year=year, repos=repos, total=total))
    return HallOfFame(generated_at=now.isoformat(), top=top, years=years)


def to_markdown(hof: HallOfFame) -> str:
    stamp = hof.generated_at[:16].replace("T", " ")
    lines = [
        f"# GitHub 명예의 전당 — 생성 연도별 누적 ⭐ TOP {hof.top}",
        "",
        f"> 생성 시각: {stamp} UTC",
        "> 기준: 해당 연도에 **생성된** 저장소의 **현재** 누적 별 순위 (⭐1,000 이상)",
        "",
    ]
    for entry in hof.years:
        lines += [
            f"## {entry.year}년 생성 (⭐1k+ 총 {entry.total:,}건)",
            "",
            "| # | ⭐ | 저장소 | 설명 |",
            "|---:|---:|---|---|",
        ]
        for i, r in enumerate(entry.repos, 1):
            desc = (r.description or "").replace("|", "\\|")
            if len(desc) > 90:
                desc = desc[:89] + "…"
            lines.append(
                f"| {i} | {r.stars:,} | [{r.full_name}]({r.html_url}) | {desc} |"
            )
        lines.append("")
    return "\n".join(lines)


def generate(client: GitHubClient, since: int = FIRST_YEAR, top: int = 10) -> str:
    """수집 + Markdown 렌더링을 한 번에."""
    return to_markdown(collect(client, since=since, top=top))
