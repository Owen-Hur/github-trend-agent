"""네트워크 없이 도는 핵심 로직 테스트: python3 -m tests.test_core"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, deliver, i18n, render, slack  # noqa: E402
from src.dedup import SeenStore  # noqa: E402
from src.github_client import clean_readme  # noqa: E402
from src.main import pick  # noqa: E402
from src.models import Analysis, Briefing, Repo  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def repo(name, stars=100, desc="", topics=None):
    return Repo(
        full_name=name, name=name.split("/")[-1],
        html_url=f"https://github.com/{name}", description=desc,
        topics=topics or [], stars=stars, created_at="2026-09-01T00:00:00Z",
    )


print("\nclean_readme")
raw = """<!-- comment -->
[![Build](https://img.shields.io/badge/build-passing.svg)](https://ci.example.com)
![logo](logo.png)
<h1>My Project</h1>

실제 설명 문장이다. [문서](https://docs.example.com)를 참고하라.



끝."""
cleaned = clean_readme(raw)
check("배지/이미지 제거", "shields.io" not in cleaned and "logo.png" not in cleaned)
check("HTML 태그 제거", "<h1>" not in cleaned and "My Project" in cleaned)
check("주석 제거", "comment" not in cleaned)
check("링크는 표시 텍스트만 남김", "문서" in cleaned and "docs.example.com" not in cleaned)
check("연속 공백줄 압축", "\n\n\n" not in cleaned)
check("본문 보존", "실제 설명 문장이다." in cleaned)
check("길이 제한", len(clean_readme("가" * 5000)) == config.README_EXCERPT_CHARS)

print("\npick — 품질 하한선")
check("하한선 미만 제외", [r.full_name for r in pick([repo("a/a", 200), repo("b/b", 10)], 5)] == ["a/a"])
check("건수를 억지로 채우지 않음", len(pick([repo("a/a", 200)], 5)) == 1)
check("상위 N건 제한", len(pick([repo(f"x/{i}", 100) for i in range(10)], 5)) == 5)

print("\nSeenStore")
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "seen.json"
    now = datetime.now(timezone.utc)
    s = SeenStore(path)
    s.mark([repo("a/a")], "fresh", now)
    s.save()

    s2 = SeenStore(path)
    check("영속화", s2.is_seen("a/a"))
    check("미소개 저장소 통과", [r.full_name for r in s2.filter_unseen([repo("a/a"), repo("b/b")])] == ["b/b"])
    check("fresh 소개분도 breakout 으로는 재등장 가능", not s2.is_seen("a/a", "breakout"))

    s2.mark([repo("old/old")], "fresh", now - timedelta(days=config.SEEN_RETENTION_DAYS + 1))
    check("보관 기간 초과분 파기", s2.prune(now) == 1 and "old/old" not in s2.entries)
    check("유효 항목 유지", "a/a" in s2.entries)

    (Path(d) / "broken.json").write_text("{not json", encoding="utf-8")
    check("깨진 상태 파일에도 계속 진행", SeenStore(Path(d) / "broken.json").entries == {})

print("\nSlack 블록")
a = Analysis("o/r", "요약", ["AI/ML"], "시나리오", "아이디어")
b = Briefing(datetime(2026, 9, 11, tzinfo=timezone.utc).isoformat(),
             fresh=[(repo("o/r", 500), a)], breakout=[(repo("o/big", 9000), a)])
payload = slack.build_payload(b)
blocks = payload["blocks"]
check("폴백 텍스트 존재", bool(payload["text"]))
check("요일 라벨", "(금)" in payload["text"], payload["text"])
check("블록 수 제한", len(blocks) <= slack.MAX_BLOCKS)
check("section 3000자 제한", all(
    len(bl.get("text", {}).get("text", "")) <= slack.MAX_SECTION_CHARS for bl in blocks))
check("마지막 divider 제거", blocks[-1]["type"] != "divider")
check("breakout 섹션 존재", any("뒤늦게 터진 것" in str(bl) for bl in blocks))
check("mrkdwn 이스케이프", "&lt;script&gt;" in str(
    slack.build_payload(Briefing("2026-09-11T00:00:00+00:00",
                                 fresh=[(repo("o/r", 500), Analysis("o/r", "<script>", ["기타"], "", ""))]))))

many = Briefing("2026-09-11T00:00:00+00:00", fresh=[(repo(f"o/{i}", 500), a) for i in range(40)])
pages = slack.chunk_blocks(slack.build_blocks(many))
check("대량 입력 시 여러 메시지로 분할", len(pages) > 1)
check("모든 페이지가 블록 한도 이내", all(len(pg) < slack.MAX_BLOCKS for pg in pages))
check("분할해도 저장소가 유실되지 않음",
      sum(1 for pg in pages for bl in pg if bl.get("type") == "section") == 40)
check("페이로드도 페이지 수만큼 생성", len(slack.build_payloads(many)) == len(pages))

topical = Briefing("2026-09-11T00:00:00+00:00",
                   fresh=[(repo("o/r", 500), a)],
                   topics={"Finance": [(repo("f/x", 300), a)], "Quant": []})
check("분야 트랙 렌더링", "📌 Finance" in str(slack.build_blocks(topical)))
check("빈 분야는 생략", "Quant" not in str(slack.build_blocks(topical)))
check("분야 트랙이 Markdown 에도 반영", "📌 Finance" in render.to_markdown(topical))
check("total 이 분야까지 합산", topical.total == 2)
check("분야만 있어도 비어있지 않음",
      not Briefing("2026-09-11T00:00:00+00:00", topics={"Finance": [(repo("f/x"), a)]}).is_empty)

check("빈 브리핑 처리", len(slack.build_blocks(Briefing("2026-09-11T00:00:00+00:00"))) == 2)

print("\nMarkdown 렌더링")
md = render.to_markdown(b)
check("제목", md.startswith("# 🔭 GitHub 트렌드 브리핑 · 2026-09-11 (금)"))
check("저장소 링크", "[o/r](https://github.com/o/r)" in md)
check("4개 필드 모두 등장", all(k in md for k in ["적용 분야", "활용 시나리오", "확장 아이디어"]) and "> 요약" in md)
check("breakout 구획", "🔥 뒤늦게 터진 것" in md)
check("heading=False 시 제목 생략", not render.to_markdown(b, heading=False).startswith("# "))
check("빈 브리핑 문구", "신규 저장소가 없습니다" in render.to_markdown(Briefing("2026-09-11T00:00:00+00:00")))

print("\n전달 대상 결정")
# 실제 웹훅처럼 보이는 리터럴은 시크릿 스캐너에 걸리므로 조각으로 만든다.
WEBHOOK_OK = "https://hooks.slack.com/services/" + "T" + "0" * 10 + "/B" + "0" * 10 + "/" + "x" * 24
full = config.Config("tok", "key", WEBHOOK_OK, "o/r")
check("auto — slack 우선", deliver.resolve("auto", full) == ["slack"])
check("auto — slack 없으면 issue+file",
      deliver.resolve("auto", config.Config("tok", "key", None, "o/r")) == ["issue", "file"])
check("auto — 아무것도 없으면 file+stdout",
      deliver.resolve("auto", config.Config(None, None, None, None)) == ["file", "stdout"])
check("명시 지정이 우선", deliver.resolve("file,stdout", full) == ["file", "stdout"])
try:
    deliver.resolve("telegram", full)
    check("알 수 없는 대상 거부", False)
except SystemExit:
    check("알 수 없는 대상 거부", True)

print("\n시크릿 사전 검증")
def expect_exit(cfg, **kw):
    try:
        cfg.validate(**kw)
        return False
    except SystemExit:
        return True

check("slack 대상인데 웹훅 없으면 중단",
      expect_exit(config.Config("t", "k", None, "o/r"), need_llm=False, targets=["slack"]))
check("issue 대상인데 repo 없으면 중단",
      expect_exit(config.Config("t", "k", None, None), need_llm=False, targets=["issue"]))
check("LLM 필요한데 키 없으면 중단",
      expect_exit(config.Config("t", None, None, None), need_llm=True, targets=[]))
check("조건 충족 시 통과", not expect_exit(full, need_llm=True, targets=["slack", "file"]))
check("dry-run(대상 없음)은 키 없이도 통과",
      not expect_exit(config.Config(None, None, None, None), need_llm=False, targets=[]))
check("웹훅 URL 중복 붙여넣기 차단",
      expect_exit(config.Config("t", "k", WEBHOOK_OK + WEBHOOK_OK, "o/r"),
                  need_llm=False, targets=["slack"]))
check("웹훅 URL 형식 오류 차단",
      expect_exit(config.Config("t", "k", "https://hooks.slack.com/x", "o/r"),
                  need_llm=False, targets=["slack"]))

print("\nCLI 인자 파싱 — 각 모드가 실제로 기동되는지")
import ast  # noqa: E402
import inspect  # noqa: E402
import textwrap  # noqa: E402

import src.main as _main  # noqa: E402

# validate() 시그니처 변경 때 hall-of-fame 호출부만 누락돼 TypeError 가 났던 회귀.
# 줄바꿈된 호출도 잡히도록 AST 로 실제 키워드 인자를 읽는다.
_params = set(inspect.signature(config.Config.validate).parameters)
_tree = ast.parse(textwrap.dedent(inspect.getsource(_main.main)))
_calls = [
    n for n in ast.walk(_tree)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Attribute) and n.func.attr == "validate"
]
_kwargs = {kw.arg for c in _calls for kw in c.keywords}
check("main() 의 validate 호출 인자가 시그니처와 일치",
      _kwargs <= _params, f"미지원 인자: {_kwargs - _params}")
check("두 모드 모두 validate 를 호출", len(_calls) == 2)

print("\n분야별 트랙 실행 요일")
from src.main import local_weekday, topics_enabled  # noqa: E402
_fri = datetime(2026, 9, 11, tzinfo=timezone.utc)   # KST 금
_wed = datetime(2026, 9, 9, tzinfo=timezone.utc)    # KST 수
_thu_late = datetime(2026, 9, 10, 15, tzinfo=timezone.utc)  # KST 금 00:00
check("금요일에 실행", topics_enabled("auto", _fri))
check("평일에는 건너뜀", not topics_enabled("auto", _wed))
check("KST 기준 경계(UTC 목 15시=KST 금 0시)", topics_enabled("auto", _thu_late))
check("UTC 기준이었다면 목요일", _thu_late.weekday() == 3 and local_weekday(_thu_late) == 4)
check("--topics on 은 요일 무시", topics_enabled("on", _wed))
check("--topics off 는 금요일에도 건너뜀", not topics_enabled("off", _fri))

print("\n언어 설정")
check("기본은 한국어", config.LANGUAGE == "한국어" and "적용 분야" in render.to_markdown(b))
check("한국어 분야 태그", i18n.domains("한국어")[0] == "AI/ML" and "백엔드" in i18n.domains("한국어"))
check("English 분야 태그", i18n.domains("English") == [
    "AI/ML", "Backend", "Data Engineering", "DevOps", "Security", "Frontend", "Other"])
check("미등록 언어는 English 라벨로 대체", i18n.strings("日本語") is i18n.strings("English"))
check("라벨 키 집합이 언어 간 동일",
      set(i18n.strings("한국어")) == set(i18n.strings("English")))

_orig = config.LANGUAGE
try:
    config.LANGUAGE = "English"
    md_en = render.to_markdown(b)
    check("영어 라벨 적용", "**Domains**" in md_en and "**Use case**" in md_en)
    check("영어 제목", "GitHub Trend Briefing" in md_en)
    check("영어 요일", "(Fri)" in md_en, md_en.splitlines()[0])
    check("영어 breakout 구획", "Late Bloomers" in md_en)
    check("Slack 블록도 영어", "Domains" in str(slack.build_payload(b)))
    check("빈 브리핑 영어 문구",
          "No new repositories" in render.to_markdown(Briefing("2026-09-11T00:00:00+00:00")))
finally:
    config.LANGUAGE = _orig
check("원상 복구", config.LANGUAGE == "한국어" and "적용 분야" in render.to_markdown(b))

print("\nAnalysis.fallback")
f = Analysis.fallback(repo("o/r", 100, "원본 설명", ["AI/ML", "DevOps", "보안"]), "LLM 미사용")
check("description 승계", f.summary == "원본 설명")
check("topics 를 도메인으로 활용(최대 2개)", f.domains == ["AI/ML", "DevOps"])
check("사유 표기", "LLM 미사용" in f.use_case)
check("description 없을 때 안내 문구", "저장소를 직접 확인" in Analysis.fallback(repo("o/r")).summary)

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과")
