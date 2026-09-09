"""연도별 명예의 전당 리포트.

브리핑과 성격이 다르다. Slack 정기 푸시가 아니라 온디맨드 Markdown 리포트로
분리한다. 데이터가 느리게 변하므로 월 1회 또는 수동 실행으로 충분하다.

2008~현재 = 19회 연속 검색 호출이므로 PAT 인증이 사실상 필수다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .github_client import GitHubClient

FIRST_YEAR = 2008


def generate(client: GitHubClient, since: int = FIRST_YEAR, top: int = 10) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "# GitHub 명예의 전당 — 생성 연도별 누적 ⭐ TOP {}".format(top),
        "",
        f"> 생성 시각: {now:%Y-%m-%d %H:%M} UTC",
        "> 기준: 해당 연도에 **생성된** 저장소의 **현재** 누적 별 순위 (⭐1,000 이상)",
        "",
    ]

    for year in range(now.year, since - 1, -1):
        repos, total = client.search_year(year, top=top)
        if not repos:
            continue
        print(f"  {year}년 수집 완료 ({len(repos)}건)")
        lines.append(f"## {year}년 생성 (⭐1k+ 총 {total:,}건)")
        lines.append("")
        lines.append("| # | ⭐ | 저장소 | 설명 |")
        lines.append("|---:|---:|---|---|")
        for i, r in enumerate(repos, 1):
            desc = (r.description or "").replace("|", "\\|")
            if len(desc) > 90:
                desc = desc[:89] + "…"
            lines.append(
                f"| {i} | {r.stars:,} | [{r.full_name}]({r.html_url}) | {desc} |"
            )
        lines.append("")

    return "\n".join(lines)
