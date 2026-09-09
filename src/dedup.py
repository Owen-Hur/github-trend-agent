"""중복 제거 상태 관리.

7일 윈도우를 주 2회 조회하므로 회차 간 후보가 크게 겹친다.
한 번 소개한 저장소는 다시 올리지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .models import Repo


class SeenStore:
    """{full_name: {"first_seen": ISO8601, "stars": int, "track": "fresh"|"breakout"}}"""

    def __init__(self, path: Path | None = None):
        self.path = path or config.STATE_PATH
        self.entries: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.entries = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            # 상태 파일이 깨져도 브리핑은 나가야 한다. 최악의 경우 중복 1회.
            print(f"경고: 상태 파일을 읽지 못해 빈 상태로 시작합니다 ({e})")
            self.entries = {}

    def is_seen(self, full_name: str, track: str = "fresh") -> bool:
        entry = self.entries.get(full_name)
        if entry is None:
            return False
        if track == "breakout":
            # 트랙 A로 소개했더라도 나중에 대박이 나면 한 번 더 알린다.
            return entry.get("track") == "breakout"
        return True

    def filter_unseen(self, repos: list[Repo], track: str = "fresh") -> list[Repo]:
        return [r for r in repos if not self.is_seen(r.full_name, track)]

    def mark(self, repos: list[Repo], track: str = "fresh", now: datetime | None = None) -> None:
        stamp = (now or datetime.now(timezone.utc)).isoformat()
        for r in repos:
            self.entries[r.full_name] = {
                "first_seen": stamp,
                "stars": r.stars,
                "track": track,
            }

    def prune(self, now: datetime | None = None) -> int:
        """보관 기간이 지난 항목을 파기해 파일 무한 증식을 막는다."""
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=config.SEEN_RETENTION_DAYS)
        keep, dropped = {}, 0
        for name, entry in self.entries.items():
            try:
                seen_at = datetime.fromisoformat(entry["first_seen"])
            except (KeyError, ValueError):
                dropped += 1
                continue
            if seen_at.tzinfo is None:
                seen_at = seen_at.replace(tzinfo=timezone.utc)
            if seen_at >= cutoff:
                keep[name] = entry
            else:
                dropped += 1
        self.entries = keep
        return dropped

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.entries, ensure_ascii=False, indent=2, sort_keys=True)
        self.path.write_text(payload + "\n", encoding="utf-8")
