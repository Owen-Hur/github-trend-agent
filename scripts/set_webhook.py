"""웹훅 URL 을 검증한 뒤 .env 에 저장한다.

  python3 scripts/set_webhook.py

숨김 입력은 붙여넣기가 됐는지 눈으로 확인할 수 없어 중복 붙여넣기가 일어나기 쉽다.
그래서 저장 전에 형식을 검사하고, 값 대신 길이와 마스킹된 형태만 보여준다.
"""

import getpass
import pathlib
import re
import sys

PATTERN = re.compile(r"^https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+$")
ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"

raw = getpass.getpass("Slack Webhook URL (화면에 표시되지 않습니다): ")
url = "".join(raw.split())  # 공백·줄바꿈 제거

print()
if url.count("https://") > 1:
    sys.exit(f"❌ URL 이 {url.count('https://')}번 붙여넣어졌습니다 ({len(url)}자). 한 번만 붙여넣고 다시 시도하세요.")
if not PATTERN.match(url):
    sys.exit(
        f"❌ 형식이 맞지 않습니다 ({len(url)}자).\n"
        "   기대 형태: https://hooks.slack.com/services/T.../B.../토큰\n"
        "   Slack 앱 설정 → Incoming Webhooks 에서 Copy 버튼으로 다시 복사하세요."
    )

lines = []
if ENV.exists():
    lines = [ln for ln in ENV.read_text(encoding="utf-8").splitlines()
             if not ln.startswith("SLACK_WEBHOOK_URL=")]
lines.append(f"SLACK_WEBHOOK_URL={url}")
ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
ENV.chmod(0o600)

print(f"✅ 저장 완료 — {len(url)}자, {url[:40]}...{url[-4:]}")
print("   다음: .venv/bin/python scripts/check_webhook.py --ping")
