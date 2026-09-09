"""브리핑 언어별 문자열.

LLM이 생성하는 본문뿐 아니라 라벨·요일·분야 태그까지 한곳에 모은다.
새 언어를 추가하려면 여기 항목 하나만 늘리면 된다.

등록되지 않은 언어를 지정하면 라벨·태그는 English를 쓰되,
LLM 본문은 지정한 언어로 생성된다.
"""

from __future__ import annotations

KOREAN = "한국어"
ENGLISH = "English"

_TABLE: dict[str, dict] = {
    KOREAN: {
        "domains": ["AI/ML", "백엔드", "데이터 엔지니어링", "DevOps", "보안", "프론트엔드", "기타"],
        "weekdays": ["월", "화", "수", "목", "금", "토", "일"],
        "title": "🔭 GitHub 트렌드 브리핑",
        "fresh_heading": "최근 {days}일 신규 · {count}건",
        "breakout_heading": "🔥 뒤늦게 터진 것",
        "breakout_note": "{days}일 윈도우를 지난 뒤 급상승한 대형 저장소",
        "field_domains": "적용 분야",
        "field_use_case": "활용 시나리오",
        "field_extension": "확장 아이디어",
        "empty": "이번 회차에는 기준을 통과한 신규 저장소가 없습니다.",
        "truncated": "…블록 수 제한으로 일부 생략됨",
        "fallback_no_desc": "(설명 없음 — 저장소를 직접 확인하세요)",
        "reason_no_llm": "LLM 미사용",
        "reason_failed": "분석 실패",
    },
    ENGLISH: {
        "domains": ["AI/ML", "Backend", "Data Engineering", "DevOps", "Security", "Frontend", "Other"],
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "title": "🔭 GitHub Trend Briefing",
        "fresh_heading": "New in the last {days} days · {count}",
        "breakout_heading": "🔥 Late Bloomers",
        "breakout_note": "Large repositories that surged after the {days}-day window closed",
        "field_domains": "Domains",
        "field_use_case": "Use case",
        "field_extension": "Extension idea",
        "empty": "No new repositories met the bar this run.",
        "truncated": "…truncated due to block limit",
        "fallback_no_desc": "(No description — check the repository directly)",
        "reason_no_llm": "LLM skipped",
        "reason_failed": "Analysis failed",
    },
}


def strings(language: str) -> dict:
    """등록되지 않은 언어는 English 라벨로 대체한다."""
    return _TABLE.get(language, _TABLE[ENGLISH])


def domains(language: str) -> list[str]:
    return strings(language)["domains"]


def available() -> list[str]:
    return list(_TABLE)
