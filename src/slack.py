"""Slack Incoming Webhook 전달 — Block Kit 포맷.

Slack 제약: 메시지당 블록 50개, section text 3,000자.
초과 시 조용히 잘리거나 400이 나므로 코드에서 미리 지킨다.
"""

from __future__ import annotations

from .http_util import post_json
from .models import Analysis, Briefing, Repo

MAX_BLOCKS = 50
MAX_SECTION_CHARS = 3000

_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _escape(text: str) -> str:
    """Slack mrkdwn 예약문자 이스케이프."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _repo_section(repo: Repo, analysis: Analysis) -> dict:
    head = f"*<{repo.html_url}|{_escape(repo.full_name)}>*  ⭐ {repo.stars:,}"
    if repo.language:
        head += f"  ·  {_escape(repo.language)}"

    lines = [
        head,
        f"> {_escape(truncate(analysis.summary, 600))}",
        "",
        f"*적용 분야*  {_escape(', '.join(analysis.domains))}",
        f"*활용 시나리오*  {_escape(truncate(analysis.use_case, 700))}",
        f"*확장 아이디어*  {_escape(truncate(analysis.extension_idea, 700))}",
    ]
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": truncate("\n".join(lines), MAX_SECTION_CHARS)},
    }


def build_blocks(briefing: Briefing) -> list[dict]:
    date_label = _date_label(briefing.generated_at)
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔭 GitHub 트렌드 브리핑 · {date_label}"},
        }
    ]

    if briefing.is_empty:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "이번 회차에는 기준을 통과한 신규 저장소가 없습니다.",
                },
            }
        )
        return blocks

    if briefing.fresh:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"최근 7일 신규 · {len(briefing.fresh)}건"}
                ],
            }
        )
        for repo, analysis in briefing.fresh:
            blocks.append(_repo_section(repo, analysis))
            blocks.append({"type": "divider"})

    if briefing.breakout:
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔥 뒤늦게 터진 것"},
            }
        )
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "7일 윈도우를 지난 뒤 급상승한 대형 저장소"}
                ],
            }
        )
        for repo, analysis in briefing.breakout:
            blocks.append(_repo_section(repo, analysis))
            blocks.append({"type": "divider"})

    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    if len(blocks) > MAX_BLOCKS:
        blocks = blocks[: MAX_BLOCKS - 1]
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "…블록 수 제한으로 일부 생략됨"}],
            }
        )
    return blocks


def build_payload(briefing: Briefing) -> dict:
    date_label = _date_label(briefing.generated_at)
    count = len(briefing.fresh) + len(briefing.breakout)
    return {
        # 알림 미리보기와 블록 미지원 클라이언트용 폴백 텍스트
        "text": f"GitHub 트렌드 브리핑 · {date_label} · {count}건",
        "blocks": build_blocks(briefing),
    }


def send(webhook_url: str, briefing: Briefing) -> None:
    post_json(webhook_url, build_payload(briefing))


def _date_label(iso: str) -> str:
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt:%Y-%m-%d} ({_WEEKDAYS[dt.weekday()]})"
