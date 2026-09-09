"""오케스트레이션 — 부작용(네트워크·파일)은 이 파일에만 모은다.

사용:
  python -m src.main --dry-run --no-llm     # 수집만 확인
  python -m src.main --dry-run              # LLM까지, Slack 페이로드는 stdout
  python -m src.main                        # 실제 발송
  python -m src.main --mode hall-of-fame -o HALL_OF_FAME.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import analyzer, config, deliver, hall_of_fame, render, slack
from .dedup import SeenStore
from .github_client import GitHubClient
from .models import Briefing, Repo


_WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


def local_weekday(now: datetime) -> int:
    """설정된 시간대(기본 KST) 기준 요일. 0=월 … 6=일."""
    return (now + timedelta(hours=config.LOCAL_UTC_OFFSET_HOURS)).weekday()


def topics_enabled(mode: str, now: datetime) -> bool:
    """분야별 트랙 실행 여부. on/off 는 요일과 무관하게 강제한다."""
    if mode == "on":
        return True
    if mode == "off":
        return False
    return local_weekday(now) in config.TOPIC_WEEKDAYS


def pick(repos: list[Repo], count: int) -> list[Repo]:
    """품질 하한선을 적용해 상위 N건을 고른다.

    기준 미달인 날은 억지로 채우지 않고 건수를 줄인다.
    안 읽히는 브리핑은 품질이 0이므로, 적게 보내는 편이 낫다.
    """
    return [r for r in repos if r.stars >= config.QUALITY_FLOOR][:count]


def run_briefing(args: argparse.Namespace, cfg: config.Config, targets: list[str]) -> int:
    now = datetime.now(timezone.utc)
    client = GitHubClient(cfg.github_token)
    store = SeenStore()

    dropped = store.prune(now)
    if dropped:
        print(f"상태 파일에서 만료 항목 {dropped}건 파기")
    print(f"기존 소개 이력: {len(store.entries)}건\n")

    fresh_candidates, fresh_total = client.search_fresh(now)
    print(f"  후보 {len(fresh_candidates)}건 수집 (전체 매칭 {fresh_total:,}건)")
    fresh = pick(store.filter_unseen(fresh_candidates, "fresh"), config.PICK_COUNT)
    print(f"  중복 제거 + 하한선 적용 후 {len(fresh)}건 확정\n")

    breakout_candidates, breakout_total = client.search_breakout(now)
    print(f"  후보 {len(breakout_candidates)}건 수집 (전체 매칭 {breakout_total:,}건)")
    breakout = store.filter_unseen(breakout_candidates, "breakout")[: config.BREAKOUT_PICK_COUNT]
    print(f"  중복 제거 후 {len(breakout)}건 확정\n")

    topics: dict[str, list[Repo]] = {}
    run_topics = topics_enabled(args.topics, now)
    if not run_topics:
        weekdays = ", ".join(_WEEKDAY_NAMES[d] for d in config.TOPIC_WEEKDAYS)
        print(f"[분야별 트랙] 건너뜀 — {weekdays}요일에만 실행합니다 "
              f"(오늘은 {_WEEKDAY_NAMES[local_weekday(now)]}요일). "
              f"강제 실행하려면 --topics on\n")
    for track in config.TOPIC_TRACKS if run_topics else []:
        candidates, total = client.search_topic(track, now)
        # 메인 트랙에서 이미 뽑힌 저장소는 분야 트랙에서도 제외한다.
        already = {r.full_name for r in fresh + breakout}
        unseen = [
            r
            for r in store.filter_unseen(candidates, f"topic:{track['name']}")
            if r.full_name not in already
        ]
        picked = pick(unseen, config.TOPIC_PICK_COUNT)
        topics[track["name"]] = picked
        print(f"  후보 {len(candidates)}건 (전체 {total:,}건) → {len(picked)}건 확정\n")

    selected = fresh + breakout + [r for v in topics.values() for r in v]
    if not selected:
        print("기준을 통과한 신규 저장소가 없습니다.")

    if selected:
        print("README 컨텍스트 보강:")
        client.enrich(selected)
        print()

    use_llm = not args.no_llm
    api_key = cfg.anthropic_key if use_llm else None
    if use_llm and selected:
        print(f"LLM 분석 ({config.MODEL}, {len(selected)}건 배치)...")
    analyzed, all_failed = analyzer.analyze_with_fallback(selected, api_key)
    if all_failed and not args.dry_run:
        # 분석 없는 브리핑을 보내면 쓸모가 없는 데다, 저장소가 소개 이력에
        # 기록되어 다음 회차에서 제외된다. 발송하지 않고 실패로 끝낸다.
        print(
            "\n중단: LLM 분석이 전량 실패했습니다. 발송하지 않고 상태도 갱신하지 않습니다.\n"
            "  일시적 네트워크 오류일 수 있으니 워크플로를 재실행해 보세요.\n"
            "  분석 없이 강행하려면 --no-llm 을 붙이면 됩니다.",
            file=sys.stderr,
        )
        return 1

    by_name = {r.full_name: (r, a) for r, a in analyzed}
    briefing = Briefing(
        generated_at=now.isoformat(),
        fresh=[by_name[r.full_name] for r in fresh],
        breakout=[by_name[r.full_name] for r in breakout],
        topics={
            name: [by_name[r.full_name] for r in items]
            for name, items in topics.items()
        },
    )

    if args.dry_run:
        print("\n" + "=" * 70)
        print(f"DRY RUN — 실제 전달 안 함 (대상이었다면: {', '.join(targets)})")
        print("=" * 70)
        print(render.to_markdown(briefing))
        if "slack" in targets:
            print("-" * 70)
            print("Slack 페이로드:")
            print(json.dumps(slack.build_payload(briefing), ensure_ascii=False, indent=2))
        print("\n상태 파일은 갱신하지 않았습니다 (dry-run).")
        return 0

    deliver.deliver(briefing, targets, cfg)

    store.mark(fresh, "fresh", now)
    store.mark(breakout, "breakout", now)
    for name, items in topics.items():
        store.mark(items, f"topic:{name}", now)
    store.save()
    print(f"상태 파일 갱신: {store.path}")
    return 0


def run_hall_of_fame(args: argparse.Namespace, cfg: config.Config) -> int:
    client = GitHubClient(cfg.github_token)
    print(f"{args.since}년~현재 연도별 수집 시작...")
    report = hall_of_fame.generate(client, since=args.since, top=args.top)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n리포트 저장: {args.out}")
    else:
        print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="GitHub 트렌드 분석 & Slack 알림 에이전트")
    p.add_argument("--mode", choices=["briefing", "hall-of-fame"], default="briefing")
    p.add_argument("--dry-run", action="store_true", help="실제 전달 없이 결과만 출력")
    p.add_argument("--no-llm", action="store_true", help="LLM 분석을 건너뛰고 원본 설명 사용")
    p.add_argument(
        "--deliver",
        default="auto",
        help="전달 대상 쉼표 구분 (%s). auto는 준비된 수단을 자동 선택"
        % ", ".join(deliver.TARGETS),
    )
    p.add_argument(
        "--topics",
        choices=["auto", "on", "off"],
        default="auto",
        help="분야별 트랙 실행 여부. auto 는 설정된 요일에만 실행 (기본)",
    )
    p.add_argument("--since", type=int, default=hall_of_fame.FIRST_YEAR)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("-o", "--out", help="hall-of-fame 리포트 저장 경로")
    args = p.parse_args(argv)

    cfg = config.Config.from_env()
    if args.mode == "hall-of-fame":
        # 19회 연속 호출 → 비인증(분당 10회)이면 스로틀링으로 매우 느려진다.
        cfg.validate(need_llm=False, targets=[], want_token=True)
        return run_hall_of_fame(args, cfg)

    targets = deliver.resolve(args.deliver, cfg)
    cfg.validate(need_llm=not args.no_llm, targets=[] if args.dry_run else targets)
    return run_briefing(args, cfg, targets)


if __name__ == "__main__":
    sys.exit(main())
