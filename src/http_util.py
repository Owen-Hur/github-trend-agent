"""stdlib만 쓰는 최소 HTTP 헬퍼.

수집 경로가 외부 의존성 없이 돌아가야 `--dry-run --no-llm`을
어디서든 즉시 실행할 수 있다. 유일한 의존성은 analyzer의 anthropic뿐이다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "github-trend-agent"


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 30,
) -> tuple[str, dict[str, str]]:
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("User-Agent", USER_AGENT)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode("utf-8", "replace")) from e


def get_json(url: str, headers: dict[str, str] | None = None) -> tuple[dict, dict[str, str]]:
    body, resp_headers = _request(url, headers=headers)
    return json.loads(body), resp_headers


def get_text(url: str, headers: dict[str, str] | None = None) -> str:
    body, _ = _request(url, headers=headers)
    return body


def post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
) -> str:
    """지수 백오프 재시도 후 응답 본문을 그대로 돌려준다.

    Slack은 "ok" 평문을, GitHub는 JSON을 반환하므로 파싱은 호출자 몫이다.
    최종 실패는 예외로 올려 조용한 실패를 막는다.
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    merged = {"Content-Type": "application/json", **(headers or {})}
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            body, _ = _request(url, method="POST", headers=merged, data=data)
            return body
        except HttpError as e:
            last = e
            # 4xx는 재시도해도 같은 결과다. 인증·페이로드 오류를 즉시 드러낸다.
            if 400 <= e.status < 500 and e.status != 429:
                break
            if attempt < attempts - 1:
                time.sleep(2**attempt)
        except OSError as e:
            last = e
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"POST 실패 ({url.split('?')[0]}): {last}")
