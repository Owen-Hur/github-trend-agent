"""Slack Incoming Webhook 전달 — Block Kit 포맷.

Slack 제약: 메시지당 블록 50개, section text 3,000자.
초과 시 조용히 잘리거나 400이 나므로 코드에서 미리 지킨다.
라벨은 src/i18n.py 를 따른다.
"""

from __future__ import annotations

import time

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

    for name, items in briefing.topics.items():
        if not items:
            continue
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": s["topic_heading"].format(name=name, count=len(items)),
                },
            }
        )
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": s["topic_note"].format(
                            name=name, days=config.TOPIC_WINDOW_DAYS
                        ),
                    }
                ],
            }
        )
        for repo, analysis in items:
            blocks.append(_repo_section(repo, analysis))
            blocks.append({"type": "divider"})

    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()
    return blocks


def chunk_blocks(blocks: list[dict]) -> list[list[dict]]:
    """50블록 한도에 맞춰 나눈다. header 로 시작하는 구획은 쪼개지 않는다.

    잘라내면 뒤쪽 분야가 통째로 사라지므로, 자르는 대신 메시지를 나눈다.
    """
    if len(blocks) <= MAX_BLOCKS:
        return [blocks]

    pages: list[list[dict]] = []
    current: list[dict] = []
    for block in blocks:
        # header 앞에서 끊으면 구획이 메시지를 가로지르지 않는다.
        starts_section = block.get("type") == "header" and current
        if starts_section and len(current) > MAX_BLOCKS - 12:
            pages.append(current)
            current = []
        elif len(current) >= MAX_BLOCKS - 1:
            pages.append(current)
            current = []
        current.append(block)
    if current:
        pages.append(current)
    return pages


def build_payloads(briefing: Briefing) -> list[dict]:
    s = i18n.strings(config.LANGUAGE)
    pages = chunk_blocks(build_blocks(briefing))
    payloads = []
    for i, page in enumerate(pages, 1):
        if len(pages) > 1:
            page = page + [
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": s["continued"].format(page=i, total=len(pages)),
                        }
                    ],
                }
            ]
        payloads.append(
            {
                # 알림 미리보기와 블록 미지원 클라이언트용 폴백 텍스트
                "text": f"{render.title(briefing)} · {briefing.total}",
                "blocks": page,
            }
        )
    return payloads


def build_payload(briefing: Briefing) -> dict:
    """단일 페이로드가 필요한 곳(미리보기 등)에서 첫 장을 돌려준다."""
    return build_payloads(briefing)[0]


def build_hall_of_fame_payloads(hof) -> list[dict]:
    """명예의 전당은 연도당 한 블록으로 압축한다.

    저장소마다 블록을 만들면 5년치만 해도 50블록을 훌쩍 넘고,
    순위표는 한눈에 보는 게 목적이라 나열이 오히려 읽기 좋다.
    Slack 은 Markdown 표를 렌더링하지 못하므로 목록 형태로 만든다.
    """
    title = f"🏆 GitHub 명예의 전당 · 연도별 누적 ⭐ TOP {hof.top}"
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "해당 연도에 *생성된* 저장소의 *현재* 누적 별 순위",
                }
            ],
        },
    ]
    for entry in hof.years:
        lines = [f"*{entry.year}년*  ·  ⭐1k+ 총 {entry.total:,}건", ""]
        for i, r in enumerate(entry.repos, 1):
            lines.append(
                f"`{i:>2}.` ⭐ {r.stars:>7,}  <{r.html_url}|{_escape(r.full_name)}>"
            )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": truncate("\n".join(lines), MAX_SECTION_CHARS),
                },
            }
        )
        blocks.append({"type": "divider"})
    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    pages = chunk_blocks(blocks)
    return [{"text": title, "blocks": page} for page in pages]


def send_payloads(webhook_url: str, payloads: list[dict], label: str = "메시지") -> None:
    for i, payload in enumerate(payloads):
        if i:
            time.sleep(1.2)  # 웹훅 URL당 초당 1회 제한
        body = post_json(webhook_url, payload).strip()
        if body != "ok":
            raise RuntimeError(
                f"Slack 이 {label}를 거부했습니다 ({i + 1}/{len(payloads)}): {body!r}\n"
                "  channel_not_found → 웹훅이 가리키는 채널이 삭제·전환됐습니다.\n"
                "  action_prohibited → 앱이 해당 채널에서 제거됐습니다.\n"
                "  둘 다 Incoming Webhooks 에서 웹훅을 새로 발급해야 합니다."
            )
    if len(payloads) > 1:
        print(f"  (블록 한도로 {len(payloads)}개 메시지로 나눠 발송)")


def send_hall_of_fame(webhook_url: str, hof) -> None:
    send_payloads(webhook_url, build_hall_of_fame_payloads(hof), "명예의 전당")


def send(webhook_url: str, briefing: Briefing) -> None:
    """Slack 은 실패해도 200 을 주는 경우가 있어 응답 본문까지 확인한다.

    성공은 정확히 "ok". 그 외(channel_not_found, action_prohibited 등)는
    메시지가 조용히 버려진 것이므로 실패로 처리한다.
    """
    send_payloads(webhook_url, build_payloads(briefing), "브리핑")
