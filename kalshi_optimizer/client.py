import os
import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from auth import sign_request, load_private_key

PROD_BASE   = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE   = "https://demo-api.kalshi.co/trade-api/v2"
_API_PREFIX = "/trade-api/v2"   # prepended to path in RSA-PSS signature

_last_call_times: list = []
_MAX_READS_PER_SEC = 18   # stay under 20/s limit


def _rate_limit():
    now = time.monotonic()
    _last_call_times[:] = [t for t in _last_call_times if now - t < 1.0]
    if len(_last_call_times) >= _MAX_READS_PER_SEC:
        time.sleep(1.0 - (now - _last_call_times[0]))
    _last_call_times.append(time.monotonic())


def _should_retry(exc: Exception) -> bool:
    if not isinstance(exc, requests.HTTPError):
        return False
    resp = exc.response
    if resp is None:
        return True
    # Only retry rate-limit and server errors; not auth/client errors
    return resp.status_code == 429 or resp.status_code >= 500


class KalshiClient:
    def __init__(self, demo: bool = False):
        self.base = DEMO_BASE if demo else PROD_BASE
        self.key_id = os.environ["KALSHI_API_KEY_ID"]
        self.private_key = load_private_key(os.environ["KALSHI_PRIVATE_KEY_PATH"])

    def _headers(self, method: str, path: str) -> dict:
        # Kalshi signature must include /trade-api/v2 prefix in the path
        return sign_request(self.private_key, self.key_id, method, _API_PREFIX + path)

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
    )
    def get(self, path: str, params: dict = None) -> dict:
        _rate_limit()
        # Build query string manually so the signed path matches the sent URL exactly.
        # Using requests' params= would URL-encode differently from our manual build.
        if params:
            from urllib.parse import urlencode
            qs = "?" + urlencode(params)
            full_path = path + qs
        else:
            qs = ""
            full_path = path
        resp = requests.get(
            self.base + full_path,
            headers=self._headers("GET", full_path),
        )
        if resp.status_code == 429:
            raise requests.HTTPError("Rate limited", response=resp)
        resp.raise_for_status()
        return resp.json()

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
    )
    def post(self, path: str, body: dict) -> dict:
        _rate_limit()
        resp = requests.post(
            self.base + path,
            json=body,
            headers={**self._headers("POST", path), "Content-Type": "application/json"},
        )
        if resp.status_code == 429:
            raise requests.HTTPError("Rate limited", response=resp)
        resp.raise_for_status()
        return resp.json()
