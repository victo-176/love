"""Live-test of the real Number Panel functions in bot.py (login + fetch)."""
import re
import sys
import types
import os
import time

# ---- telebot / deps stubs (same as other tests) ----
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

# real requests/bs4 are available in this env; replace the stubs with the real ones
for _real in ("requests", "requests.adapters", "urllib3", "urllib3.util",
              "urllib3.util.retry", "bs4"):
    sys.modules.pop(_real, None)
import requests  # noqa: E402
import bs4  # noqa: E402
import urllib3.util.retry  # noqa: E402
assert hasattr(requests, "Session"), "real requests not loaded"


class _Pooled:
    def __init__(self, *a, **k):
        pass


class _Session:
    def __init__(self, *a, **k):
        self.headers = {}
        self.cookies = types.SimpleNamespace(update=lambda **k: None, clear=lambda: None)

    def __getattr__(self, name):
        return lambda *a, **k: None




os.environ.setdefault("BOT_TOKEN", "test:token")
os.chdir("/tmp")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402

# single live run: login + fetch once (respect the portal's 1-min login cooldown)
cfg = dict(bot.NUMBERPANEL_DEFAULT_CONFIG)
assert bot.np_login(cfg), "np_login FAILED"
print("OK np_login")

msgs = bot.np_fetch_otps(cfg)
print(f"OK np_fetch_otps -> {len(msgs)} new message(s) (priming run)")
assert isinstance(msgs, list)

# second fetch: primed now; empty is fine, list is required
msgs2 = bot.np_fetch_otps(cfg)
print(f"OK np_fetch_otps (primed) -> {len(msgs2)} message(s)")

# formatter smoke test
if msgs2:
    fmt = bot.np_format_otp_message(msgs2[0])
    print("OK np_format_otp_message:\n", fmt[:200])

# ---------------------------------------------------------------
# OFFLINE: canned export CSV through the real fetch/parse path
# ---------------------------------------------------------------
class _Resp:
    status_code = 200
    url = "http://tempnumbers.net/client/SMSCDRStats"
    headers = {}

    def __init__(self, text=""):
        self.text = text


csv_today = (
    "Date , Range , Number , CLI , SMS , Currency , My Payout \n"
    "2026-09-18 21:24:30, Nigeria-Smile-KM-52, 2347020510004, TWVerify, "
    "Your ChatDip Messenger verification code is 4675, $, 0.012 \n"
    "2026-09-18 21:28:24, Nigeria-Smile-KM-52, 2347020510022, PariPulse, "
    "Verification code 57664, $, 0.012 \n"
    "2026-09-18 21:29:00, Nigeria-Smile-KM-52, 2347020510033, DBbet, "
    "Username: 1796934011 Password: yvycyxth Do not share this information., $, 0.012 \n"
    "Total SMS, , , CurrencyUSDEURGBP, My Payout\n"
)
csv_yesterday = (
    "Date , Range , Number , CLI , SMS , Currency , My Payout \n"
    "2026-09-17 10:00:00, Ghana-Test-01, 2331234567890, Melbet, "
    "Your confirmation code: ekxbr, $, 0.010 \n"
)


def _fake_get(url, params=None, timeout=None, **k):
    if "SMSCDRStats" in url:
        return _Resp("sesskey=1234567890 res/data_smscdr.php?x&sesskey=1234567890")
    if "exportsmscdr" in url:
        d = (params or {}).get("fdate1", "")[:10]
        return _Resp(csv_today if d == __import__("datetime").datetime.now().strftime("%Y-%m-%d") else csv_yesterday)
    return _Resp("")


bot._np_logged_in = True  # skip live login for the offline part
bot._np_session.get = _fake_get
bot._np_last_hashes.clear()
bot._np_primed = True

parsed = bot.np_fetch_otps(cfg)
texts = [m["otp"] for m in parsed]
assert "4675" in texts, texts
assert "57664" in texts, texts
assert "ekxbr" in texts, texts
assert "" in texts, texts  # username/password row has no OTP but must be kept
assert len(parsed) == 4, parsed

unp = [m for m in parsed if m["otp"] == ""][0]
assert unp["number"] == "2347020510033", unp  # phone NOT hijacked by Username text
assert "yvycyxth" in unp["full_text"], unp
assert unp["service"] == "DBbet"

mel = [m for m in parsed if m["otp"] == "ekxbr"][0]
assert mel["number"] == "2331234567890"

fmt = bot.np_format_otp_message(parsed[0])
assert "OTP: " in fmt
print(f"OK offline parse: {len(parsed)} rows (numeric, alphanumeric ekxbr, no-OTP row, dedup)")

# dedup: second identical fetch must return nothing
parsed2 = bot.np_fetch_otps(cfg)
assert parsed2 == [], parsed2
print("OK offline dedup: repeated fetch returns 0")

print("ALL NUMBERPANEL TESTS PASSED")
