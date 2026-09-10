"""연도별 명예의 전당 리포트.

브리핑과 성격이 다르다. 정기 푸시가 아니라 온디맨드 리포트이므로
수집(collect)과 표현(to_markdown / Slack 블록)을 분리해 둔다.

2008~현재 = 19회 연속 검색 호출이므로 PAT 인증이 사실상 필수다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import config, i18n
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
    # full_name → Analysis. 비어 있으면 순위 목록만 렌더링한다.
    analyses: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.analyses is None:
            self.analyses = {}

    @property
    def analyzed(self) -> bool:
        return bool(self.analyses)

    def all_repos(self) -> list[Repo]:
        return [r for entry in self.years for r in entry.repos]


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


def analyze(hof: HallOfFame, client: GitHubClient, api_key: str) -> int:
    """연도 단위로 나눠 분석한다.

    50건을 한 번에 넣으면 출력 토큰 한도에 걸리고 서술 품질도 떨어진다.
    연도당 10건 안팎이면 브리핑에서 검증된 배치 크기와 비슷하다.
    실패한 연도는 건너뛰고 나머지는 계속 진행한다.
    """
    from . import analyzer

    done = 0
    for entry in hof.years:
        client.enrich(entry.repos)
        print(f"  {entry.year}년 분석 중 ({len(entry.repos)}건)...")
        results = analyzer.analyze(entry.repos, api_key)
        if not results:
            print(f"  경고: {entry.year}년 분석 실패 — 순위만 표시됩니다")
            continue
        hof.analyses.update(results)
        done += len(results)
    return done


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

        if hof.analyzed:
            s = i18n.strings(config.LANGUAGE)
            for i, r in enumerate(entry.repos, 1):
                a = hof.analyses.get(r.full_name)
                if not a:
                    continue
                lines += [
                    f"**{i}. [{r.full_name}]({r.html_url})** · ⭐ {r.stars:,}",
                    "",
                    f"> {a.summary}",
                    "",
                    f"**{s['field_domains']}** · {', '.join(a.domains)}",
                    "",
                    f"**{s['field_use_case']}** · {a.use_case}",
                    "",
                    f"**{s['field_extension']}** · {a.extension_idea}",
                    "",
                ]
    return "\n".join(lines)


def generate(client: GitHubClient, since: int = FIRST_YEAR, top: int = 10) -> str:
    """수집 + Markdown 렌더링을 한 번에."""
    return to_markdown(collect(client, since=since, top=top))
