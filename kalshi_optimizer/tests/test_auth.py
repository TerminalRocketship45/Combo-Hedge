import time
from unittest.mock import MagicMock
from auth import sign_request

def _make_key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())

def test_sign_request_returns_three_headers():
    key = _make_key()
    headers = sign_request(key, "test-key-id", "GET", "/trade-api/v2/events")
    assert set(headers.keys()) == {"KALSHI-ACCESS-KEY", "KALSHI-ACCESS-TIMESTAMP", "KALSHI-ACCESS-SIGNATURE"}

def test_sign_request_timestamp_is_recent():
    key = _make_key()
    headers = sign_request(key, "test-key-id", "GET", "/trade-api/v2/events")
    ts = int(headers["KALSHI-ACCESS-TIMESTAMP"])
    now_ms = int(time.time() * 1000)
    assert abs(ts - now_ms) < 5000

def test_sign_request_key_id_matches():
    key = _make_key()
    headers = sign_request(key, "my-key-id", "GET", "/trade-api/v2/events")
    assert headers["KALSHI-ACCESS-KEY"] == "my-key-id"

def test_sign_request_signature_is_base64():
    import base64
    key = _make_key()
    headers = sign_request(key, "test-key-id", "POST", "/trade-api/v2/markets")
    sig = headers["KALSHI-ACCESS-SIGNATURE"]
    decoded = base64.b64decode(sig)
    assert len(decoded) > 0
