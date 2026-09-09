"""Claude 기반 분석 엔진.

4개 필드를 자유 텍스트로 받지 않고 tool schema로 강제한다.
"4개 필드 누락 없음"이 검증 기준이므로 파싱 실패 여지를 스키마로 없앤다.
"""

from __future__ import annotations

from . import config
from .models import DOMAINS, Analysis, Repo

SYSTEM_TEMPLATE = """당신은 개발팀에 GitHub 신규 저장소를 소개하는 기술 애널리스트다.
주어진 저장소 각각에 대해 4개 필드를 채워라.

- 핵심 요약: 비개발자도 이해할 수 있는 1문장 기능 정의. 저장소 이름을 그대로 되풀이하지 말 것.
- 적용 분야: 주어진 목록에서 1~2개만 고를 것.
- 활용 시나리오: 실무 워크플로에 당장 적용 가능한 구체적 예시 1~2문장.
- 확장 아이디어: 다른 도구와 결합했을 때의 고도화 방향 1~2문장.

재료가 부실한 저장소는 추측을 지어내지 말고 확인 가능한 범위에서만 서술하라.
summary / use_case / extension_idea 세 필드의 본문은 반드시 {language}(으)로 작성한다.
domains 는 주어진 enum 값을 그대로 사용한다(번역하지 말 것)."""

SYSTEM = SYSTEM_TEMPLATE.format(language=config.LANGUAGE)

ANALYSIS_TOOL = {
    "name": "submit_analysis",
    "description": "각 저장소의 분석 결과를 제출한다. 입력된 모든 저장소를 빠짐없이 포함해야 한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analyses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "full_name": {"type": "string", "description": "owner/repo 형식"},
                        "summary": {"type": "string"},
                        "domains": {
                            "type": "array",
                            "items": {"type": "string", "enum": DOMAINS},
                            "minItems": 1,
                            "maxItems": 2,
                        },
                        "use_case": {"type": "string"},
                        "extension_idea": {"type": "string"},
                    },
                    "required": [
                        "full_name",
                        "summary",
                        "domains",
                        "use_case",
                        "extension_idea",
                    ],
                },
            }
        },
        "required": ["analyses"],
    },
}


def analyze(repos: list[Repo], api_key: str) -> dict[str, Analysis]:
    """저장소 전체를 한 번의 호출로 배치 처리한다.

    개별 호출보다 비용·지연이 낮고 저장소 간 서술 톤이 일관된다.
    실패 시 빈 dict을 돌려주면 호출자가 fallback으로 채운다.
    """
    if not repos:
        return {}

    try:
        import anthropic
    except ImportError:
        print("경고: anthropic 패키지가 없습니다. 원본 description으로 대체합니다.")
        return {}

    blocks = "\n\n---\n\n".join(r.context_text() for r in repos)
    prompt = f"다음 {len(repos)}개 저장소를 분석하라.\n\n{blocks}"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            output_config={"effort": config.EFFORT},
            system=SYSTEM,
            tools=[ANALYSIS_TOOL],
            tool_choice={"type": "tool", "name": "submit_analysis"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:  # 네트워크·인증·한도 무엇이든 전체 실행은 계속한다
        print(f"경고: LLM 호출 실패 ({e}). 원본 description으로 대체합니다.")
        return {}

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return _to_analyses(block.input.get("analyses", []))
    print("경고: LLM 응답에 tool_use 블록이 없습니다.")
    return {}


def _to_analyses(items: list[dict]) -> dict[str, Analysis]:
    out: dict[str, Analysis] = {}
    for item in items:
        name = item.get("full_name")
        if not name:
            continue
        out[name] = Analysis(
            full_name=name,
            summary=item.get("summary", ""),
            domains=item.get("domains") or ["기타"],
            use_case=item.get("use_case", ""),
            extension_idea=item.get("extension_idea", ""),
        )
    return out


def analyze_with_fallback(repos: list[Repo], api_key: str | None) -> list[tuple[Repo, Analysis]]:
    """분석에 실패한 저장소만 골라 fallback을 채운다.

    LLM을 아예 쓰지 않은 경우와 호출이 실패한 경우를 구분해 표기한다.
    """
    if api_key:
        results = analyze(repos, api_key)
        reason = "분석 실패"
    else:
        results = {}
        reason = "LLM 미사용"
    return [(r, results.get(r.full_name) or Analysis.fallback(r, reason)) for r in repos]
