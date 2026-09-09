"""데이터 모델 — GitHub 저장소와 LLM 분석 결과."""

from dataclasses import dataclass, field

from . import config, i18n

# Phase 4 고정 태그 목록. LLM tool schema의 enum과 동일해야 한다.
DOMAINS = i18n.domains(config.LANGUAGE)

# description이 이 길이 미만이면 README 보강 대상.
MIN_DESCRIPTION_LEN = 80


@dataclass
class Repo:
    full_name: str
    name: str
    html_url: str
    description: str
    topics: list[str]
    stars: int
    created_at: str
    language: str | None = None
    readme_excerpt: str = ""

    @classmethod
    def from_api(cls, item: dict) -> "Repo":
        return cls(
            full_name=item["full_name"],
            name=item["name"],
            html_url=item["html_url"],
            description=(item.get("description") or "").strip(),
            topics=item.get("topics") or [],
            stars=item.get("stargazers_count", 0),
            created_at=item.get("created_at", ""),
            language=item.get("language"),
        )

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def repo_name(self) -> str:
        return self.full_name.split("/", 1)[1]

    @property
    def needs_enrichment(self) -> bool:
        """실측상 후보의 대다수(topics 77% 비어있음)가 여기 해당한다."""
        return not self.topics or len(self.description) < MIN_DESCRIPTION_LEN

    def context_text(self) -> str:
        """LLM에 넘길 재료를 한 덩어리로 조립한다."""
        parts = [f"저장소: {self.full_name}", f"별: {self.stars}"]
        if self.language:
            parts.append(f"주 언어: {self.language}")
        if self.topics:
            parts.append(f"토픽: {', '.join(self.topics)}")
        parts.append(f"설명: {self.description or '(없음)'}")
        if self.readme_excerpt:
            parts.append(f"README 발췌:\n{self.readme_excerpt}")
        return "\n".join(parts)


@dataclass
class Analysis:
    full_name: str
    summary: str
    domains: list[str] = field(default_factory=list)
    use_case: str = ""
    extension_idea: str = ""

    @classmethod
    def fallback(cls, repo: Repo, reason: str | None = None) -> "Analysis":
        """LLM 실패·미사용 시 원본 description으로 대체. 전체 실행은 계속된다."""
        s = i18n.strings(config.LANGUAGE)
        reason = reason or s["reason_no_llm"]
        return cls(
            full_name=repo.full_name,
            summary=repo.description or s["fallback_no_desc"],
            domains=repo.topics[:2] or [DOMAINS[-1]],
            use_case=f"({reason})",
            extension_idea=f"({reason})",
        )


@dataclass
class Briefing:
    """한 회차의 발송 내용."""

    generated_at: str
    fresh: list[tuple[Repo, Analysis]] = field(default_factory=list)
    breakout: list[tuple[Repo, Analysis]] = field(default_factory=list)
    # 분야명 → 저장소 목록. 입력 순서(config.TOPIC_TRACKS 순서)를 유지한다.
    topics: dict[str, list[tuple[Repo, Analysis]]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.fresh and not self.breakout and not any(self.topics.values())

    @property
    def total(self) -> int:
        return len(self.fresh) + len(self.breakout) + sum(len(v) for v in self.topics.values())
