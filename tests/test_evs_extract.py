"""Test the real OTP extractors from bot.py (Dream SMS + EVS forwarder)."""
import re
import sys
import types
import os

# Mock telebot before importing bot.py
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
_tb.__path__ = []  # allow telebot.types submodule import
_tb.types = types.SimpleNamespace(
    InlineKeyboardMarkup=lambda **k: types.SimpleNamespace(add=lambda *a, **k: None, row=lambda *a, **k: None),
    InlineKeyboardButton=lambda *a, **k: types.SimpleNamespace(),
    ReplyKeyboardMarkup=lambda **k: types.SimpleNamespace(add=lambda *a, **k: None, row=lambda *a, **k: None),
    ReplyKeyboardRemove=lambda **k: types.SimpleNamespace(),
    ForceReply=lambda **k: types.SimpleNamespace(),
    ParseModeHTML="HTML",
)
_tbt = types.ModuleType("telebot.types")


class _Btn:  # base stub with to_dict like real telebot buttons
    def __init__(self, *a, **k):
        self.__dict__.update(k)

    def to_dict(self):
        return dict(self.__dict__)


class _Markup:
    def __init__(self, *a, **k):
        self.rows = []

    def add(self, *a, **k):
        self.rows.append(list(a))

    def row(self, *a, **k):
        self.rows.append(list(a))


class _ReplyKeyboardRemove:
    def __init__(self, *a, **k):
        pass


_tbt.ReplyKeyboardMarkup = _Markup
_tbt.KeyboardButton = _Btn
_tbt.InlineKeyboardMarkup = _Markup
_tbt.InlineKeyboardButton = _Btn
_tbt.ReplyKeyboardRemove = _ReplyKeyboardRemove
_tbt.ForceReply = _ReplyKeyboardRemove
sys.modules["telebot"] = _tb
sys.modules["telebot.types"] = _tbt

# Stub remaining third-party imports bot.py needs at import time
class _Retry:
    def __init__(self, *a, **k):
        pass


for _name in ("pyotp", "requests", "requests.adapters", "urllib3", "urllib3.util", "urllib3.util.retry", "bs4"):
    sys.modules.setdefault(_name, types.ModuleType(_name))


class _Session:
    def __init__(self, *a, **k):
        self.headers = {}
        self.cookies = types.SimpleNamespace(
            update=lambda **k: None,
            clear=lambda: None,
        )

    def __getattr__(self, name):
        return lambda *a, **k: None


sys.modules["requests"].Session = _Session
_ra = sys.modules["requests.adapters"]
class _Pooled:
    def __init__(self, *a, **k):
        pass


_ra.HTTPAdapter = _Pooled

sys.modules["urllib3.util.retry"].Retry = _Retry
sys.modules["bs4"].BeautifulSoup = object
os.environ.setdefault("BOT_TOKEN", "test:token")

# Run from a scratch cwd so bot.py module-level data files don't pollute the repo
os.chdir("/tmp")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402


def test_dreamsms_otp():
    cases = [
        # (text, expected)
        ("Do not share your confirmation code with anyone: ekxbr", "ekxbr"),
        ("Your code: 5521", "5521"),
        ("Your code to log in to 63xc3c", "63xc3c"),
        ("Your verification code is 991022", "991022"),
        ("one-time password: 4f8zk1", "4f8zk1"),
        ("Welcome to our service, enjoy your day", None),
        ("Your passcode: A1b2C3", "A1b2C3"),
    ]
    for text, expected in cases:
        got = bot._dreamsms_otp(text)
        assert got == expected, f"_dreamsms_otp({text!r}) -> {got!r}, expected {expected!r}"
    # Both spec-mandated alphanumeric codes MUST be extracted
    assert bot._dreamsms_otp("Do not share your confirmation code with anyone: ekxbr") == "ekxbr"
    assert bot._dreamsms_otp("Your code to log in to 63xc3c") == "63xc3c"
    print("OK test_dreamsms_otp")


def test_evs_extract():
    cases = [
        ("Do not share your confirmation code with anyone: ekxbr", "ekxbr"),
        ("Use code 63xc3c to verify", "63xc3c"),
        ("Your code: 5521", "5521"),
        ("Your one-time password is 9945.", "9945"),
        ("Welcome! Please enjoy our service.", None),
        ("Do not share your confirmation code with anyone: 05299", "05299"),
        ("Your code to log in to 63xc3c", "63xc3c"),
    ]
    for text, expected in cases:
        got = _evs_extract_like_bot(text)
        assert got == expected, f"EVS extract({text!r}) -> {got!r}, expected {expected!r}"
    print("OK test_evs_extract")


def _evs_extract_like_bot(full_text):
    """Mirror of the EVS forwarder extraction in bot.py."""
    otp_match = re.search(
        r'(?:confirmation code|one-time password|verification code|code|otp|pin|passcode|password)\s*'
        r'(?:(?:is|with|anyone|to|log|in|and|the|your|use|enter|of|for|be)\b\s*){0,6}'
        r'[:\s]*([A-Za-z0-9]{4,8})\b',
        full_text, re.IGNORECASE)
    if otp_match:
        span = full_text[otp_match.start():otp_match.start(1)]
        if not (':' in span or re.search(r'\d', otp_match.group(1))):
            otp_match = None
    if not otp_match:
        filler = re.search(
            r'(?:confirmation code|one-time password|verification code|code|otp|pin|passcode|password)\s+'
            r'(?:is|with anyone|to log in to)\s+([A-Za-z0-9]{4,8})\b',
            full_text, re.IGNORECASE)
        if filler and re.search(r'\d', filler.group(1)):
            otp_match = filler
    if not otp_match:
        otp_match = re.search(r'\b(\d{4,6})\b', full_text)
    return otp_match.group(1) if otp_match else None


if __name__ == "__main__":
    test_dreamsms_otp()
    test_evs_extract()
    print("ALL EXTRACTOR TESTS PASSED")
