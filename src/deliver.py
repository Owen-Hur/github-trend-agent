"""전달 경로 — Slack에 묶이지 않도록 sink를 교체 가능하게 둔다.

사용 가능한 대상:
  issue   GitHub Issue 로 발행 (무료·알림·스레드 토론·검색 가능)
  file    briefings/YYYY-MM-DD.md 아카이브 (git 이력에 그대로 남음)
  summary GitHub Actions 실행 요약 화면
  stdout  터미널 출력
  slack   Slack Incoming Webhook (Block Kit)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import render, slack
from .config import Config, PROJECT_ROOT
from .http_util import post_json
from .models import Briefing

TARGETS = ("issue", "file", "summary", "stdout", "slack")
GITHUB_API = "https://api.github.com"


def resolve(spec: str, cfg: Config) -> list[str]:
    """'auto'는 준비된 수단을 골라준다. 명시 지정이 항상 우선."""
    if spec != "auto":
        chosen = [t.strip() for t in spec.split(",") if t.strip()]
        unknown = [t for t in chosen if t not in TARGETS]
        if unknown:
            raise SystemExit(f"알 수 없는 전달 대상: {unknown} (가능: {', '.join(TARGETS)})")
        return chosen
    if cfg.slack_webhook:
        return ["slack"]
    if cfg.github_token and cfg.repository:
        return ["issue", "file"]
    return ["file", "stdout"]


def deliver(briefing: Briefing, targets: list[str], cfg: Config) -> None:
    for target in targets:
        try:
            _SINKS[target](briefing, cfg)
        except Exception as e:
            # 한 경로가 막혀도 나머지는 나가야 한다. 단 전부 실패하면 호출자가 실패 처리.
            print(f"전달 실패 [{target}]: {e}")
            raise


def _to_slack(briefing: Briefing, cfg: Config) -> None:
    slack.send(cfg.slack_webhook, briefing)
    print(f"Slack 발송 완료")


def _to_issue(briefing: Briefing, cfg: Config) -> None:
    if not (cfg.github_token and cfg.repository):
        raise RuntimeError("GH_PAT 와 GITHUB_REPOSITORY 가 모두 필요합니다")
    body = post_json(
        f"{GITHUB_API}/repos/{cfg.repository}/issues",
        {
            "title": render.title(briefing),
            "body": render.to_markdown(briefing, heading=False),
            "labels": ["briefing"],
        },
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {cfg.github_token}",
        },
    )
    url = json.loads(body).get("html_url", "(URL 없음)")
    print(f"Issue 발행 완료: {url}")


def _to_file(briefing: Briefing, cfg: Config) -> None:
    stamp = render.date_label(briefing.generated_at).split(" ")[0]
    path = PROJECT_ROOT / "briefings" / f"{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render.to_markdown(briefing), encoding="utf-8")
    print(f"아카이브 저장: {path.relative_to(PROJECT_ROOT)}")


def _to_summary(briefing: Briefing, cfg: Config) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        raise RuntimeError("GITHUB_STEP_SUMMARY 가 없습니다 (Actions 밖에서 실행 중)")
    with open(target, "a", encoding="utf-8") as f:
        f.write(render.to_markdown(briefing))
    print("Actions 요약에 기록 완료")


def _to_stdout(briefing: Briefing, cfg: Config) -> None:
    print("\n" + render.to_markdown(briefing))


_SINKS = {
    "slack": _to_slack,
    "issue": _to_issue,
    "file": _to_file,
    "summary": _to_summary,
    "stdout": _to_stdout,
}
