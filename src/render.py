"""브리핑을 Markdown으로 렌더링한다.

Slack Block Kit과 별개 경로. GitHub Issue·아카이브 파일·Actions 요약이
모두 이 한 벌의 Markdown을 공유한다.
"""

from __future__ import annotations

from datetime import datetime

from .models import Analysis, Briefing, Repo

_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def date_label(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt:%Y-%m-%d} ({_WEEKDAYS[dt.weekday()]})"


def title(briefing: Briefing) -> str:
    return f"🔭 GitHub 트렌드 브리핑 · {date_label(briefing.generated_at)}"


def _repo_block(repo: Repo, analysis: Analysis) -> list[str]:
    head = f"### [{repo.full_name}]({repo.html_url}) · ⭐ {repo.stars:,}"
    if repo.language:
        head += f" · {repo.language}"
    lines = [head, "", f"> {analysis.summary}", ""]
    lines.append(f"**적용 분야** · {', '.join(analysis.domains)}")
    lines.append("")
    lines.append(f"**활용 시나리오** · {analysis.use_case}")
    lines.append("")
    lines.append(f"**확장 아이디어** · {analysis.extension_idea}")
    lines.append("")
    return lines


def to_markdown(briefing: Briefing, *, heading: bool = True) -> str:
    lines: list[str] = []
    if heading:
        lines += [f"# {title(briefing)}", ""]

    if briefing.is_empty:
        lines.append("이번 회차에는 기준을 통과한 신규 저장소가 없습니다.")
        return "\n".join(lines) + "\n"

    if briefing.fresh:
        lines += [f"## 최근 7일 신규 · {len(briefing.fresh)}건", ""]
        for repo, analysis in briefing.fresh:
            lines += _repo_block(repo, analysis)

    if briefing.breakout:
        lines += ["## 🔥 뒤늦게 터진 것", "",
                  "7일 윈도우를 지난 뒤 급상승한 대형 저장소", ""]
        for repo, analysis in briefing.breakout:
            lines += _repo_block(repo, analysis)

    return "\n".join(lines).rstrip() + "\n"
