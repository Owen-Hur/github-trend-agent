"""브리핑을 Markdown으로 렌더링한다.

Slack Block Kit과 별개 경로. GitHub Issue·아카이브 파일·Actions 요약이
모두 이 한 벌의 Markdown을 공유한다. 라벨은 src/i18n.py 를 따른다.
"""

from __future__ import annotations

from datetime import datetime

from . import config, i18n
from .models import Analysis, Briefing, Repo


def _s() -> dict:
    return i18n.strings(config.LANGUAGE)


def date_label(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt:%Y-%m-%d} ({_s()['weekdays'][dt.weekday()]})"


def title(briefing: Briefing) -> str:
    return f"{_s()['title']} · {date_label(briefing.generated_at)}"


def _repo_block(repo: Repo, analysis: Analysis) -> list[str]:
    s = _s()
    head = f"### [{repo.full_name}]({repo.html_url}) · ⭐ {repo.stars:,}"
    if repo.language:
        head += f" · {repo.language}"
    return [
        head,
        "",
        f"> {analysis.summary}",
        "",
        f"**{s['field_domains']}** · {', '.join(analysis.domains)}",
        "",
        f"**{s['field_use_case']}** · {analysis.use_case}",
        "",
        f"**{s['field_extension']}** · {analysis.extension_idea}",
        "",
    ]


def to_markdown(briefing: Briefing, *, heading: bool = True) -> str:
    s = _s()
    lines: list[str] = []
    if heading:
        lines += [f"# {title(briefing)}", ""]

    if briefing.is_empty:
        lines.append(s["empty"])
        return "\n".join(lines) + "\n"

    if briefing.fresh:
        lines += [
            "## " + s["fresh_heading"].format(
                days=config.WINDOW_DAYS, count=len(briefing.fresh)
            ),
            "",
        ]
        for repo, analysis in briefing.fresh:
            lines += _repo_block(repo, analysis)

    if briefing.breakout:
        lines += [
            "## " + s["breakout_heading"],
            "",
            s["breakout_note"].format(days=config.WINDOW_DAYS),
            "",
        ]
        for repo, analysis in briefing.breakout:
            lines += _repo_block(repo, analysis)

    for name, items in briefing.topics.items():
        if not items:
            continue
        lines += [
            "## " + s["topic_heading"].format(name=name, count=len(items)),
            "",
            s["topic_note"].format(name=name, days=config.TOPIC_WINDOW_DAYS),
            "",
        ]
        for repo, analysis in items:
            lines += _repo_block(repo, analysis)

    return "\n".join(lines).rstrip() + "\n"
