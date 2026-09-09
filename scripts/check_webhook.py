"""웹훅 진단 — 어느 채널로 가는지, 살아 있는지 확인한다.

  .venv/bin/python scripts/check_webhook.py          # 발송 없이 상태만 확인
  .venv/bin/python scripts/check_webhook.py --ping   # 짧은 테스트 메시지 1건 발송

Slack 은 실패해도 HTTP 200 을 주는 경우가 있어, 응답 본문을 그대로 보여준다.
"""

import json
import os
import sys
import urllib.error
import urllib.request

url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
if not url:
    sys.exit("SLACK_WEBHOOK_URL 이 없습니다. `set -a; source .env; set +a` 후 다시 실행하세요.")

print(f"웹훅 URL 형태: {url[:36]}...{url[-6:]}  (길이 {len(url)})")
if not url.startswith("https://hooks.slack.com/services/"):
    print("⚠️  형태가 이상합니다. 복사가 잘렸을 수 있습니다.")

ping = "--ping" in sys.argv
payload = {"text": "✅ 웹훅 연결 테스트입니다. 이 메시지가 보이는 채널이 브리핑 수신 채널입니다."}

if not ping:
    # 빈 payload 는 Slack 이 invalid_payload 로 거절한다.
    # 메시지를 만들지 않으면서 웹훅의 생사만 확인하는 용도.
    payload = {}

req = urllib.request.Request(
    url, method="POST",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "User-Agent": "webhook-check"},
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        status, body = r.status, r.read().decode().strip()
except urllib.error.HTTPError as e:
    status, body = e.code, e.read().decode().strip()

print(f"HTTP {status}  응답 본문: {body!r}")
print()
if body == "ok":
    print("→ 웹훅 정상. 테스트 메시지가 도착한 채널이 수신 채널입니다.")
elif body == "invalid_payload":
    print("→ 웹훅은 살아 있습니다(빈 payload 를 보냈으니 정상 반응).")
    print("   실제 채널을 확인하려면 --ping 을 붙여 다시 실행하세요.")
elif body == "channel_not_found":
    print("→ 웹훅이 가리키는 채널이 사라졌습니다(삭제 또는 공개→비공개 전환).")
    print("   Incoming Webhooks 에서 웹훅을 새로 발급해야 합니다.")
elif body == "action_prohibited":
    print("→ 앱이 해당 채널에서 제거됐습니다. 채널에 앱을 다시 추가하거나 웹훅을 재발급하세요.")
elif status == 403 or body == "invalid_token":
    print("→ 웹훅 URL 이 무효합니다. 복사가 잘렸는지 확인하세요.")
else:
    print("→ 예상 밖의 응답입니다. 위 상태코드와 본문을 알려주세요.")
