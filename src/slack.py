"""Slack Incoming Webhook 전달 — Block Kit 포맷.

Slack 제약: 메시지당 블록 50개, section text 3,000자.
초과 시 조용히 잘리거나 400이 나므로 코드에서 미리 지킨다.
라벨은 src/i18n.py 를 따른다.
"""

from __future__ import annotations

from . import config, i18n, render
from .http_util import post_json
from .models import Analysis, Briefing, Repo

MAX_BLOCKS = 50
MAX_SECTION_CHARS = 3000


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _escape(text: str) -> str:
    """Slack mrkdwn 예약문자 이스케이프."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _repo_section(repo: Repo, analysis: Analysis) -> dict:
    s = i18n.strings(config.LANGUAGE)
    head = f"*<{repo.html_url}|{_escape(repo.full_name)}>*  ⭐ {repo.stars:,}"
    if repo.language:
        head += f"  ·  {_escape(repo.language)}"

    lines = [
        head,
        f"> {_escape(truncate(analysis.summary, 600))}",
        "",
        f"*{s['field_domains']}*  {_escape(', '.join(analysis.domains))}",
        f"*{s['field_use_case']}*  {_escape(truncate(analysis.use_case, 700))}",
        f"*{s['field_extension']}*  {_escape(truncate(analysis.extension_idea, 700))}",
    ]
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": truncate("\n".join(lines), MAX_SECTION_CHARS)},
    }


def build_blocks(briefing: Briefing) -> list[dict]:
    s = i18n.strings(config.LANGUAGE)
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": render.title(briefing)},
        }
    ]

    if briefing.is_empty:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": s["empty"]}}
        )
        return blocks

    if briefing.fresh:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": s["fresh_heading"].format(
                            days=config.WINDOW_DAYS, count=len(briefing.fresh)
                        ),
                    }
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
                "text": {"type": "plain_text", "text": s["breakout_heading"]},
            }
        )
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": s["breakout_note"].format(days=config.WINDOW_DAYS),
                    }
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
            {"type": "context", "elements": [{"type": "mrkdwn", "text": s["truncated"]}]}
        )
    return blocks


def build_payload(briefing: Briefing) -> dict:
    count = len(briefing.fresh) + len(briefing.breakout)
    return {
        # 알림 미리보기와 블록 미지원 클라이언트용 폴백 텍스트
        "text": f"{render.title(briefing)} · {count}",
        "blocks": build_blocks(briefing),
    }


def send(webhook_url: str, briefing: Briefing) -> None:
    post_json(webhook_url, build_payload(briefing))
