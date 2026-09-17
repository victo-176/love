"""Dream SMS integration tests: parse, fetch loop (200/429/401/non-JSON), validate, dispatch."""
import re
import sys
import types
import os
import json
import time
from datetime import datetime, timedelta

# ---- telebot / deps stubs (same approach as test_evs_extract) ----
_tb = types.ModuleType("telebot")


class _TeleBot:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        def _fn(*a, **k):
            def deco(f):
                return f
            return deco
        return _fn


_tb.TeleBot = _TeleBot
_tb.__path__ = []
_tbt = types.ModuleType("telebot.types")


class _Btn:
    def __init__(self, *a, **k):
        self.__dict__.update(k)

    def to_dict(self):
        return dict(self.__dict__)


class _Markup:
    def __init__(self, *a, **k):
        pass

    def add(self, *a, **k):
        pass

    def row(self, *a, **k):
        pass


_tbt.ReplyKeyboardMarkup = _Markup
_tbt.KeyboardButton = _Btn
_tbt.InlineKeyboardMarkup = _Markup
_tbt.InlineKeyboardButton = _Btn
_tbt.ReplyKeyboardRemove = _Markup
_tbt.ForceReply = _Markup
sys.modules["telebot"] = _tb
sys.modules["telebot.types"] = _tbt

for _name in ("pyotp", "requests", "requests.adapters", "urllib3", "urllib3.util",
              "urllib3.util.retry", "bs4"):
    sys.modules.setdefault(_name, types.ModuleType(_name))


class _Pooled:
    def __init__(self, *a, **k):
        pass


class _Session:
    def __init__(self, *a, **k):
        self.headers = {}
        self.cookies = types.SimpleNamespace(update=lambda **k: None, clear=lambda: None)

    def __getattr__(self, name):
        return lambda *a, **k: None


sys.modules["requests"].Session = _Session
sys.modules["requests.adapters"].HTTPAdapter = _Pooled
sys.modules["urllib3.util.retry"].Retry = _Pooled
sys.modules["bs4"].BeautifulSoup = object

os.environ.setdefault("BOT_TOKEN", "test:token")
os.chdir("/tmp")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402

DREAM_BASE = "http://49.13.121.155"
DREAM_TOKEN = "tok_test_123"


def _panel():
    return {
        "panel_url": DREAM_BASE + "/api/v1",  # trailing /api/v1 must be stripped
        "api_key": DREAM_TOKEN,
        "type": "api",
        "name": "Dream SMS",
    }


class _Resp:
    def __init__(self, status=200, payload=None, headers=None, body=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self._body = body
        self.url = DREAM_BASE

    def json(self):
        if self._body is not None:
            raise ValueError("not json")
        return self._payload


# ---------------------------------------------------------------------------
def test_validate():
    ok = []

    # 200 => valid
    bot.requests.get = lambda *a, **k: _Resp(200, {"records": [], "count": 0})
    r, code = bot._dreamsms_validate(_panel())
    ok.append((r is True and code == 200))

    # 401 => invalid
    bot.requests.get = lambda *a, **k: _Resp(401, {"error": "invalid_token"})
    r, code = bot._dreamsms_validate(_panel())
    ok.append((r is False and code == 401))

    # 403 => invalid
    bot.requests.get = lambda *a, **k: _Resp(403, {})
    r, code = bot._dreamsms_validate(_panel())
    ok.append((r is False and code == 403))

    assert all(ok), f"validate results: {ok}"
    print("OK test_validate (200 valid / 401,403 invalid)")


# ---------------------------------------------------------------------------
def test_parse():
    records = [
        # numeric code
        {"time": "2026-09-17T17:30:00.000Z", "cli": "Melbet", "number": "2349154635248",
         "content": "Your confirmation code: 5521", "range": "NIGERIA - Melbet sep17"},
        # colon alphanumeric (canonical)
        {"time": "2026-09-17T17:32:31.730Z", "cli": "Melbet", "number": "2349154635248",
         "content": "Do not share your confirmation code with anyone: ekxbr",
         "range": "NIGERIA - Melbet sep17"},
        # mid-sentence filler
        {"time": "2026-09-17T17:33:00.000Z", "cli": "Melbet", "number": "2349154635248",
         "content": "Use code to log in to 63xc3c", "range": "NIGERIA - Melbet sep17"},
        # junk row: no phone
        {"time": "2026-09-17T17:34:00.000Z", "cli": "Melbet", "number": "",
         "content": "code: 1234", "range": "NIGERIA"},
        # row without OTP
        {"time": "2026-09-17T17:35:00.000Z", "cli": "Melbet", "number": "2349154635248",
         "content": "Welcome to Melbet, enjoy!", "range": "NIGERIA"},
        # country from range + ISO normalization
        {"time": "2026-09-17T17:36:10.123Z", "cli": "Melbet", "number": "2348012345678",
         "content": "otp: Z9x8y7", "range": "KENYA - Melbet sep17"},
    ]
    parsed = bot._dreamsms_parse(records)
    codes = [p["otp"] for p in parsed]
    assert "5521" in codes, codes
    assert "ekxbr" in codes, codes
    assert "63xc3c" in codes, codes
    assert "Z9x8y7" in codes, codes
    assert len(parsed) == 4, f"expected 4 usable rows, got {len(parsed)} ({codes})"

    p_ekx = [p for p in parsed if p["otp"] == "ekxbr"][0]
    assert p_ekx["service"] == "Melbet"
    assert p_ekx["phone"] == "2349154635248"
    assert p_ekx["country"] == "Nigeria"  # first alpha word of range, capitalized
    assert p_ekx["timestamp"] == "2026-09-17 17:32:31"  # ISO normalized
    assert "confirmation code with anyone: ekxbr" in p_ekx["full_text"]

    p_ken = [p for p in parsed if p["otp"] == "Z9x8y7"][0]
    assert p_ken["country"] == "Kenya"

    # full_text <= 500
    assert all(len(p["full_text"]) <= 500 for p in parsed)
    print("OK test_parse (numeric / ekxbr / 63xc3c / junk / no-otp / range country / ISO)")


# ---------------------------------------------------------------------------
def test_fetch():
    recs = {"records": [
        {"time": "2026-09-17T17:32:31.730Z", "cli": "Melbet", "number": "2349154635248",
         "content": "Do not share your confirmation code with anyone: ekxbr",
         "range": "NIGERIA - Melbet sep17", "payout": "0.0100", "status": "pending"}
    ], "count": 1}

    # 200 with records
    bot.requests.get = lambda *a, **k: _Resp(200, recs)
    out = bot._dreamsms_fetch(_panel())
    assert isinstance(out, list) and len(out) == 1 and out[0]["otp"] == "ekxbr", out

    # top-level array response
    bot.requests.get = lambda *a, **k: _Resp(200, [recs["records"][0]])
    out = bot._dreamsms_fetch(_panel())
    assert isinstance(out, list) and len(out) == 1, out

    # 429 + Retry-After -> retries once and succeeds
    calls = {"n": 0}

    def _rate_limited(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, {}, headers={"Retry-After": "0"})
        return _Resp(200, recs)

    bot.requests.get = _rate_limited
    out = bot._dreamsms_fetch(_panel())
    assert calls["n"] == 2 and len(out) == 1, (calls, out)

    # 401 -> None (auth failure signal)
    bot.requests.get = lambda *a, **k: _Resp(401, {"error": "invalid_token"})
    out = bot._dreamsms_fetch(_panel())
    assert out is None, out

    # 403 -> None
    bot.requests.get = lambda *a, **k: _Resp(403, {})
    out = bot._dreamsms_fetch(_panel())
    assert out is None, out

    # non-JSON -> []
    bot.requests.get = lambda *a, **k: _Resp(200, body="<html>gateway</html>")
    out = bot._dreamsms_fetch(_panel())
    assert out == [], out

    # 500 -> []
    bot.requests.get = lambda *a, **k: _Resp(500, {})
    out = bot._dreamsms_fetch(_panel())
    assert out == [], out

    print("OK test_fetch (200 / top-level array / 429+retry / 401,403 -> None / non-JSON,500 -> [])")


# ---------------------------------------------------------------------------
def test_url_builder():
    p = _panel()
    url = bot._dreamsms_api_url(p)
    assert url == DREAM_BASE + "/api/v1/messages", url
    p["panel_url"] = DREAM_BASE  # without /api/v1 suffix
    url = bot._dreamsms_api_url(p)
    assert url == DREAM_BASE + "/api/v1/messages", url
    print("OK test_url_builder (/api/v1 stripping)")


# ---------------------------------------------------------------------------
def test_dispatch_and_parity():
    """API panels dispatch to _dreamsms_* and parsed dicts satisfy the shared pipeline."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "bot.py"), encoding="utf-8").read()
    assert "_dreamsms_fetch" in src and "_dreamsms_validate" in src, "dream methods not wired"

    # pipeline entrypoints used by every panel source exist and dream dicts carry the fields
    for fn in ("process_otp", "deliver_otp_dms"):
        assert f"def {fn}" in src, f"{fn} missing"
    for key in ("otp", "service", "phone", "country", "full_text", "timestamp"):
        assert key in bot._dreamsms_parse([
            {"time": "2026-09-17T17:32:31.730Z", "cli": "Melbet", "number": "2349154635248",
             "content": "confirmation code: ekxbr", "range": "NIGERIA"}
        ])[0], "parsed dict missing pipeline key"

    # Functional dispatch: scraped_login / scraped_fetch_otps route "api" panels
    # to the Dream methods (mock load_data + the dream calls, count invocations).
    calls = {"validate": 0, "fetch": 0}
    pid = "dream_test_panel"
    panel = {"panel_url": DREAM_BASE, "api_key": DREAM_TOKEN, "type": "api", "name": "Dream SMS"}
    real_load = bot.load_data

    bot.load_data = lambda: {"panels": {pid: panel}}
    try:
        bot._dreamsms_validate = lambda p: (calls.__setitem__("validate", calls["validate"] + 1), (True, 200))[1]
        bot._dreamsms_fetch = lambda p: (calls.__setitem__("fetch", calls["fetch"] + 1),
                                         bot._dreamsms_parse([
                                             {"time": "2026-09-17T17:32:31.730Z", "cli": "Melbet",
                                              "number": "2349154635248",
                                              "content": "confirmation code: ekxbr", "range": "NIGERIA"}
                                         ]))[1]
        assert bot.scraped_login(pid) is True
        out = bot.scraped_fetch_otps(pid)
    finally:
        bot.load_data = real_load
    assert calls == {"validate": 1, "fetch": 1}, calls
    assert len(out) == 1 and out[0]["otp"] == "ekxbr", out
    print("OK test_dispatch_and_parity (api panel routes to _dreamsms_*; pipeline dict complete)")


# ---------------------------------------------------------------------------
def test_min_interval():
    """min_interval enforcement: second immediate poll must be delayed ~1.1s."""
    bot.requests.get = lambda *a, **k: _Resp(200, {"records": [], "count": 0})
    bot._dreamsms_last_poll.clear()
    t0 = time.time()
    bot._dreamsms_fetch(_panel())
    bot._dreamsms_fetch(_panel())
    dt = time.time() - t0
    assert dt >= 1.0, f"min_interval not enforced (dt={dt:.2f}s)"
    print(f"OK test_min_interval (dt={dt:.2f}s >= 1.1s window)")


if __name__ == "__main__":
    test_url_builder()
    test_validate()
    test_parse()
    test_fetch()
    test_min_interval()
    test_dispatch_and_parity()
    print("ALL DREAMSMS TESTS PASSED")
