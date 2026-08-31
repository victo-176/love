# ============================================
#  LOVE PREMIUM - FULLY MODIFIED CODE
#  (Part 1 of ~9) 
#  Features: Multi-admin, price/OTP, live support,
#  referral 0.001, balance system
# ============================================
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import time
import threading
import os
import uuid
import html
import re
import pyotp
import random
import copy
from datetime import datetime
# ==================== LOGGING ====================
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def log(msg):
    logger.info(msg)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
# ============================================
# --- MULTI-ADMIN CONFIGURATION (NEW) ---
# ============================================
MAIN_ADMINS = [7696816703,8653648506]  # ⬅️ ADD/REMOVE MAIN ADMIN IDs HERE
ADMIN_ID = MAIN_ADMINS[0]  # Primary admin (used as fallback for old references)

def is_main_admin(user_id):
    """Check if user is one of the MAIN_ADMINS."""
    return user_id in MAIN_ADMINS

def is_admin(user_id):
    """Check if user is main admin OR extra admin."""
    if user_id in MAIN_ADMINS:
        return True
    try:
        data = load_data()
        return user_id in data.get("extra_admins", [])
    except:
        return False

def notify_all_admins(text, markup=None):
    """Send a notification to ALL main admins."""
    for admin_id in MAIN_ADMINS:
        try:
            safe_send(admin_id, text, markup)
        except:
            pass

# ============================================
# --- STYLE & BULLETPROOF COPY BUTTON PATCH ---
# ============================================
_old_inline_dict = InlineKeyboardButton.to_dict
def _new_inline_dict(self):
    d = _old_inline_dict(self)
    if hasattr(self, 'style'):
        d['style'] = self.style

    if hasattr(self, 'custom_copy_text') and self.custom_copy_text:
        d['copy_text'] = {'text': str(self.custom_copy_text)}
        if 'callback_data' in d:
            del d['callback_data']

    return d
InlineKeyboardButton.to_dict = _new_inline_dict

_old_kb_dict = KeyboardButton.to_dict
def _new_kb_dict(self):
    d = _old_kb_dict(self)
    if hasattr(self, 'style'): d['style'] = self.style
    return d
KeyboardButton.to_dict = _new_kb_dict

def ibtn(text, callback_data=None, url=None, style=None, copy_text_str=None):
    kwargs = {'text': text}
    if copy_text_str:
        kwargs['callback_data'] = "fake_copy_btn"
    else:
        if callback_data: kwargs['callback_data'] = callback_data
        if url: kwargs['url'] = url
    b = InlineKeyboardButton(**kwargs)
    if style: b.style = style
    if copy_text_str:
        b.custom_copy_text = copy_text_str
    return b

def rbtn(text, style=None):
    b = KeyboardButton(text=text)
    if style: b.style = style
    return b
# ============================================

# --- CONFIGURATION ---
TOKEN = "8197426033:AAHyvcU2MxyzvEaQal9cH2uB9bqzxjRoaD8"

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=50)

# --- OTP BOT (for forwarding to OTP groups) ---
OTP_BOT_TOKEN = "8197426033:AAHyvcU2MxyzvEaQal9cH2uB9bqzxjRoaD8"
try:
    otp_bot = telebot.TeleBot(OTP_BOT_TOKEN, threaded=False)
except Exception:
    otp_bot = None

req_session = requests.Session()
retries = Retry(total=5, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=1000, pool_maxsize=1000, max_retries=retries)
req_session.mount('http://', adapter)
req_session.mount('https://', adapter)
DATA_FILE = "Loveotp.json"
DEFAULT_APPS = []

def get_app_list(data):
    """Get apps list, with backward compatibility for old flat list format."""
    apps = data.get("apps", DEFAULT_APPS)
    if not apps:
        return []
    # Convert old flat list format to new dict format
    result = []
    for app in apps:
        if isinstance(app, str):
            result.append({"folder": "OTHER", "name": app})
        elif isinstance(app, dict):
            result.append(app)
    return result

def get_folders(data):
    """Get unique folder names from apps."""
    apps = get_app_list(data)
    folders = []
    seen = set()
    for app in apps:
        folder = app.get("folder", "OTHER").upper()
        if folder not in seen:
            folders.append(folder)
            seen.add(folder)
    return sorted(folders)

def get_apps_in_folder(data, folder):
    """Get app names in a specific folder."""
    apps = get_app_list(data)
    return [a["name"] for a in apps if a.get("folder", "OTHER").upper() == folder.upper()]

def get_combo_list(data):
    """Get combos list."""
    return data.get("combos", [])

def get_combos_in_folder(data, folder):
    """Get combos in a specific folder."""
    combos = get_combo_list(data)
    return [c for c in combos if c.get("folder", "OTHER").upper() == folder.upper()]

def get_all_folders_with_items(data):
    """Get all folders that have apps OR combos."""
    folders = set()
    for app in get_app_list(data):
        folders.add(app.get("folder", "OTHER").upper())
    for combo in get_combo_list(data):
        folders.add(combo.get("folder", "OTHER").upper())
    return sorted(folders)

active_polls = {}
user_states = {}
data_lock = threading.RLock()
menu_message_id = {}
two_fa_message_id = {}
login_sessions = {}
user_cooldowns = {}
open_reply_sessions = {}  # (NEW) live support tracking

# ==================== CURRENCY CONVERTER ====================
USD_TO_NGN_CACHE = None
USD_TO_NGN_CACHE_TIME = 0
USD_TO_INR_CACHE = None
USD_TO_INR_CACHE_TIME = 0
USD_TO_CURRENCY_CACHE = {}
USD_TO_CURRENCY_CACHE_TIME = 0

def get_usd_to_ngn():
    global USD_TO_NGN_CACHE, USD_TO_NGN_CACHE_TIME
    now = time.time()
    if USD_TO_NGN_CACHE is not None and (now - USD_TO_NGN_CACHE_TIME) < 300:
        return USD_TO_NGN_CACHE
    try:
        resp = req_session.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rate = data.get("rates", {}).get("NGN")
            if rate:
                USD_TO_NGN_CACHE = rate
                USD_TO_NGN_CACHE_TIME = now
                return rate
    except Exception as e:
        print(f"Error fetching exchange rate: {e}")
    fallback = 1500.0
    USD_TO_NGN_CACHE = fallback
    USD_TO_NGN_CACHE_TIME = now
    return fallback

def get_usd_to_inr():
    global USD_TO_INR_CACHE, USD_TO_INR_CACHE_TIME
    now = time.time()
    if USD_TO_INR_CACHE is not None and (now - USD_TO_INR_CACHE_TIME) < 300:
        return USD_TO_INR_CACHE
    try:
        resp = req_session.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rate = data.get("rates", {}).get("INR")
            if rate:
                USD_TO_INR_CACHE = rate
                USD_TO_INR_CACHE_TIME = now
                return rate
    except Exception as e:
        print(f"Error fetching INR rate: {e}")
    fallback = 83.0
    USD_TO_INR_CACHE = fallback
    USD_TO_INR_CACHE_TIME = now
    return fallback

def get_usd_to_currency(currency_code):
    global USD_TO_CURRENCY_CACHE, USD_TO_CURRENCY_CACHE_TIME
    now = time.time()
    if USD_TO_CURRENCY_CACHE and (now - USD_TO_CURRENCY_CACHE_TIME) < 300:
        if currency_code in USD_TO_CURRENCY_CACHE:
            return USD_TO_CURRENCY_CACHE[currency_code]
    try:
        resp = req_session.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rates = data.get("rates", {})
            USD_TO_CURRENCY_CACHE = rates
            USD_TO_CURRENCY_CACHE_TIME = now
            return rates.get(currency_code)
    except Exception as e:
        print(f"Error fetching rates: {e}")
    return None

# ============ MULTI-PANEL API FORMATS ============
PANEL_FORMATS = {
    "nexaotp": {
        "label": "NexaOTP (nxa_ key)",
        "get_number": "/api/v1/numbers/get",
        "get_sms": "/api/v1/numbers/{number_id}/sms",
        "http_method": "POST",
        "auth_header": "X-API-Key",
        "post_body": {"range": "{service}"},
        "number_field": "number",
        "otp_field": "otp",
        "sms_field": "sms",
        "success_field": "success",
        "id_field": "number_id"
    },
    "ins_agent": {
        "label": "INS Agent API (sk_ key)",
        "get_number": "/api/functions/agent-api/numbers?status=assigned&limit={limit}&cli={service}",
        "get_sms": "/api/functions/agent-api/otp?number={number_id}&limit=5",
        "get_stats": "/api/functions/agent-api/stats",
        "get_cli_ranges": "/api/functions/agent-api/cli-ranges",
        "http_method": "GET",
        "auth_header": "x-api-key",
        "number_field": "number",
        "otp_field": "otp_code",
        "sms_field": "message_text",
        "success_field": "ok",
        "id_field": "id",
        "data_wrapper": "data"
    },
    "standard": {
        "label": "Standard API",
        "get_number": "/getNumber?service={service}&country={country}",
        "get_sms": "/numbers/{number_id}/sms",
        "http_method": "GET",
        "auth_header": "X-API-Key",
        "number_field": "number",
        "otp_field": "otp",
        "sms_field": "sms",
        "success_field": "success",
        "id_field": "id"
    },
    "daisysms": {
        "label": "DaisySMS / 5sim Type",
        "get_number": "/stubs/handler_api.php?api_key={api_key}&action=getNumber&service={service}&country={country}",
        "get_sms": "/stubs/handler_api.php?api_key={api_key}&action=getStatus&id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "number_field": "phone",
        "otp_field": "code",
        "sms_field": "full_sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id"
    },
    "smshub": {
        "label": "SMSHub Type",
        "get_number": "/api/getNumber?api_key={api_key}&service={service}&country={country}",
        "get_sms": "/api/getStatus?api_key={api_key}&id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "response",
        "success_value": "1",
        "id_field": "id"
    },
    "grizzlysms": {
        "label": "GrizzlySMS / Tiger Type",
        "get_number": "/api/get-number?apikey={api_key}&service={service}&country={country}",
        "get_sms": "/api/get-sms?apikey={api_key}&id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "number_field": "number",
        "otp_field": "otp",
        "sms_field": "message",
        "success_field": "success",
        "id_field": "request_id"
    },
    "custom": {
        "label": "Custom / Manual URL",
        "get_number": "",
        "get_sms": "",
        "http_method": "GET",
        "auth_header": "X-API-Key",
        "number_field": "number",
        "otp_field": "otp",
        "sms_field": "sms",
        "success_field": "success",
        "id_field": "id"
    },
    "ints": {
        "label": "INTS Panel (Login Based)",
        "login_endpoint": "/signin",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id",
        "has_captcha": True,
        "captcha_type": "math"
    },
    "ints_v2": {
        "label": "INTS v2 (signmein)",
        "login_endpoint": "/signmein",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id",
        "has_captcha": True,
        "captcha_type": "math"
    },
    "numberpanel": {
        "label": "Number Panel",
        "login_endpoint": "/signin",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id",
        "has_captcha": True,
        "captcha_type": "math"
    },
    "sms_panel": {
        "label": "SMS Panel (/sms type)",
        "login_endpoint": "/signmein",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id",
        "has_captcha": True,
        "captcha_type": "math"
    },
    "konekta": {
        "label": "Konekta Premium",
        "login_endpoint": "/login",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id"
    },
    "timesms": {
        "label": "Time SMS",
        "login_endpoint": "/signin",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id",
        "has_captcha": True,
        "captcha_type": "math"
    },
    "grand_panel": {
        "label": "Grand Panel",
        "login_endpoint": "/signin",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id"
    },
    "pscall": {
        "label": "PSCall Panel",
        "login_endpoint": "/signin",
        "get_number": "/api/getNumber?service={service}&country={country}",
        "get_sms": "/api/getStatus?id={number_id}",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "session",
        "number_field": "number",
        "otp_field": "code",
        "sms_field": "sms",
        "success_field": "status",
        "success_value": "OK",
        "id_field": "id"
    },
    "lamix": {
        "label": "Lamix CRAPI (Token)",
        "get_number": "",
        "get_sms": "/viewstats?token={api_key}&num={number_id}&dt1={dt1}&dt2={dt2}&records=10",
        "http_method": "GET",
        "auth_header": "",
        "auth_type": "token_url",
        "number_field": "num",
        "otp_field": "otp",
        "sms_field": "message",
        "success_field": "status",
        "success_value": "success",
        "id_field": "num",
        "data_wrapper": "data"
    }
}

# ============ URL BASE HELPERS ============
def _get_api_base(api_url, fmt_name=""):
    from urllib.parse import urlparse
    url = api_url.rstrip("/")
    if not url:
        return url
    if fmt_name == "ins_agent":
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    if fmt_name == "lamix":
        idx = url.lower().find("/crapi/lamix")
        if idx != -1:
            return url[:idx + 12]
        idx = url.lower().find("/crapi")
        if idx != -1:
            return url[:idx + 6]
        return url
    if fmt_name in ("ints", "ints_v2"):
        idx = url.lower().find("/ints")
        if idx != -1:
            return url[:idx + 5]
    if fmt_name == "numberpanel":
        idx = url.lower().find("/numberpanel")
        if idx != -1:
            return url[:idx + 12]
    if fmt_name == "sms_panel":
        idx = url.lower().find("/sms")
        if idx != -1:
            return url[:idx + 4]
    for suffix in ["/dashboard", "/admin", "/panel", "/home", "/app", "/login", "/signin"]:
        if url.lower().endswith(suffix):
            url = url[:len(url) - len(suffix)]
            break
    return url

def detect_panel_format(api_url, api_key=""):
    url = api_url.lower().rstrip("/")
    if "handler_api" in url or "stubs" in url or "5sim" in url or "daisysms" in url:
        return "daisysms"
    if "smshub" in url or "sms-hub" in url:
        return "smshub"
    if "grizzly" in url or "tiger" in url or "bear" in url:
        return "grizzlysms"
    if api_key.startswith("nxa_"):
        return "nexaotp"
    if api_key.startswith("sk_"):
        return "ins_agent"
    if url.endswith("/ints") or "/ints/" in url or "/ints?" in url:
        return "ints"
    if "numberpanel" in url.lower():
        return "numberpanel"
    if url.endswith("/sms") or "/sms/" in url:
        return "sms_panel"
    if "konektapremium" in url or "konekta" in url:
        return "konekta"
    if "timesms" in url:
        return "timesms"
    if "grand-panel" in url or "grandpanel" in url:
        return "grand_panel"
    if "pscall" in url:
        return "pscall"
    if "imssms" in url:
        return "ints"
    if "crapi/lamix" in url or "crapi" in url:
        return "lamix"
    return "standard"

def build_api_url(panel, endpoint_type, **kwargs):
    api_url = panel.get("api_url", "").rstrip("/")
    api_key = panel.get("api_key", "")
    fmt_name = panel.get("api_format", detect_panel_format(api_url, api_key))
    fmt = PANEL_FORMATS.get(fmt_name, PANEL_FORMATS["standard"])
    custom_endpoints = panel.get("custom_endpoints", {})
    if endpoint_type in custom_endpoints and custom_endpoints[endpoint_type]:
        template = custom_endpoints[endpoint_type]
    else:
        template = fmt.get(endpoint_type, "")
    if not template:
        return None
    safe_kwargs = {"api_key": api_key, "service": kwargs.get("service", ""), "country": kwargs.get("country", ""), "number_id": kwargs.get("number_id", ""), "limit": kwargs.get("limit", "10")}
    safe_kwargs.update({k: v for k, v in kwargs.items() if k not in safe_kwargs})
    try:
        url = template.format(**safe_kwargs)
    except (KeyError, IndexError):
        url = template
    if url.startswith("http"):
        return url
    base = _get_api_base(api_url, fmt_name)
    return f"{base}{url}"

def get_panel_http_method(panel):
    api_key = panel.get("api_key", "")
    fmt_name = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), api_key))
    fmt = PANEL_FORMATS.get(fmt_name, PANEL_FORMATS["standard"])
    return fmt.get("http_method", "GET").upper()

def get_api_headers(panel):
    api_key = panel.get("api_key", "")
    fmt_name = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), api_key))
    fmt = PANEL_FORMATS.get(fmt_name, PANEL_FORMATS["standard"])
    auth_header = fmt.get("auth_header", "X-API-Key")
    if auth_header:
        return {auth_header: api_key}
    return {}

def parse_number_response(panel, res_data):
    api_key = panel.get("api_key", "")
    fmt_name = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), api_key))
    fmt = PANEL_FORMATS.get(fmt_name, PANEL_FORMATS["standard"])
    success_field = fmt.get("success_field", "success")
    success_value = fmt.get("success_value", None)
    is_success = False
    if success_value:
        is_success = str(res_data.get(success_field, "")) == str(success_value)
    else:
        is_success = bool(res_data.get(success_field, False))
    if not is_success:
        for k in ["success", "status", "response", "ok", "result"]:
            v = res_data.get(k)
            if v is True or v == 1 or v == "1" or v == "OK" or v == "ok" or v == "SUCCESS":
                is_success = True
                break
    number = None
    for field in [fmt.get("number_field", "number"), "number", "phone", "phoneNumber", "tel"]:
        if res_data.get(field):
            number = str(res_data[field])
            break
    num_id = None
    for field in [fmt.get("id_field", "id"), "id", "request_id", "order_id", "activation_id"]:
        if res_data.get(field):
            num_id = str(res_data[field])
            break
    return {"success": is_success, "number": number, "id": num_id}

def parse_sms_response(panel, res_data):
    api_key = panel.get("api_key", "")
    fmt_name = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), api_key))
    fmt = PANEL_FORMATS.get(fmt_name, PANEL_FORMATS["standard"])
    success_field = fmt.get("success_field", "success")
    success_value = fmt.get("success_value", None)
    is_success = False
    if success_value:
        is_success = str(res_data.get(success_field, "")) == str(success_value)
    else:
        is_success = bool(res_data.get(success_field, False))
    if not is_success:
        for k in ["success", "status", "response", "ok", "result"]:
            v = res_data.get(k)
            if v is True or v == 1 or v == "1" or v == "OK" or v == "ok" or v == "SUCCESS":
                is_success = True
                break
    otp = None
    for field in [fmt.get("otp_field", "otp"), "otp", "code", "sms_code", "verification_code"]:
        if res_data.get(field):
            otp = str(res_data[field])
            break
    sms = ""
    for field in [fmt.get("sms_field", "sms"), "sms", "message", "full_sms", "text", "msg"]:
        if res_data.get(field):
            sms = str(res_data[field])
            break
    service = ""
    for field in ["service", "app_name", "app", "serviceName", "platform"]:
        if res_data.get(field):
            service = str(res_data[field])
            break
    return {"success": is_success, "otp": otp, "sms": sms, "service": service}
    # ============================================
#  PART 2 - DETECTION & COUNTRY DATA
# ============================================
# WEB SCRAPING PANEL FUNCTIONS (Choice SMS / INTS)
# BeautifulSoup imported lazily in scraped_login()
import hashlib as _hashlib

_panel_sessions = {}

def _get_panel_session(panel_id):
    if panel_id not in _panel_sessions:
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*',
        })
        _panel_sessions[panel_id] = s
    return _panel_sessions[panel_id]

COUNTRY_FLAGS_SCRAPED = {
    'NIGERIA': '🇳🇬', 'GHANA': '🇬🇭',
    'KENYA': '🇰🇪', 'SOUTH AFRICA': '🇿🇦',
    'EGYPT': '🇪🇬', 'MOROCCO': '🇲🇦',
    'UAE': '🇦🇪', 'INDIA': '🇮🇳',
    'USA': '🇺🇸', 'UK': '🇬🇧',
    'RUSSIA': '🇷🇺', 'BRAZIL': '🇧🇷',
    'PHILIPPINES': '🇵🇭', 'INDONESIA': '🇮🇩',
    'TURKEY': '🇹🇷', 'PAKISTAN': '🇵🇰',
    'BANGLADESH': '🇧🇩', 'SOUTH KOREA': '🇰🇷',
    'CHINA': '🇨🇳', 'JAPAN': '🇯🇵',
    'GERMANY': '🇩🇪', 'FRANCE': '🇫🇷',
    'SPAIN': '🇪🇸', 'ITALY': '🇮🇹',
    'CANADA': '🇨🇦', 'AUSTRALIA': '🇦🇺',
    'MEXICO': '🇲🇽', 'COLOMBIA': '🇨🇴',
    'ARGENTINA': '🇦🇷', 'THAILAND': '🇹🇭',
    'VIETNAM': '🇻🇳', 'MALAYSIA': '🇲🇾',
    'SINGAPORE': '🇸🇬', 'CAMBODIA': '🇰🇭',
    'MYANMAR': '🇲🇲', 'SRI LANKA': '🇱🇰',
    'NEPAL': '🇳🇵', 'TANZANIA': '🇹🇿',
    'UGANDA': '🇺🇬', 'RWANDA': '🇷🇼',
    'CONGO': '🇨🇬', 'ANGOLA': '🇦🇴',
    'MOZAMBIQUE': '🇲🇿', 'ZIMBABWE': '🇿🇼',
    'ZAMBIA': '🇿🇲', 'MALAWI': '🇲🇼',
    'LAOS': '🇱🇦', 'LEBANON': '🇱🇧',
    'TUNISIA': '🇹🇹', 'ALGERIA': '🇩🇿',
    'LIBYA': '🇱🇾', 'SAUDI ARABIA': '🇸🇦',
    'KUWAIT': '🇰🇼', 'QATAR': '🇶🇦',
    'JORDAN': '🇯🇴', 'ISRAEL': '🇮🇱',
    'CHILE': '🇨🇱', 'PERU': '🇵🇪',
    'ECUADOR': '🇪🇨', 'VENEZUELA': '🇻🇪',
    'PANAMA': '🇵🇦', 'COSTA RICA': '🇨🇷',
    'CUBA': '🇨🇺', 'JAMAICA': '🇯🇲',
    'TRINIDAD': '🇹🇹', 'HAITI': '🇭🇹',
}

SERVICE_EMOJIS_SCRAPED = {
    'BOLT': '🚗', 'UBER': '🚗', 'GOOGLE': '🔍',
    'FACEBOOK': '👤', 'WHATSAPP': '💬', 'PAYPAL': '💳',
    'AMAZON': '📦', 'MICROSOFT': '💻', 'APPLE': '🍎',
    'INSTAGRAM': '📸', 'TWITTER': '🐦', 'TIKTOK': '🎵',
    'BANK': '🏦', 'TELEGRAM': '📱', 'DISCORD': '🎮',
    'SPOTIFY': '🎵', 'NETFLIX': '🎬', 'GREENBET': '🎰',
    'AFROPARI': '🎰', 'CHAT': '💬', 'CASHAPP': '💰',
    'VENMO': '💵', 'SNAPCHAT': '👻', 'SIGNAL': '🔒',
}

def _extract_country_scraped(text):
    for country in COUNTRY_FLAGS_SCRAPED:
        if country in text.upper():
            return country
    return "Unknown"

def _extract_service_scraped(text):
    for service in SERVICE_EMOJIS_SCRAPED:
        if service in text.upper():
            return service
    return "Unknown"

def _mask_phone_scraped(phone):
    if not phone or len(phone) < 8:
        return phone or "N/A"
    digits = re.sub(r'\D', '', phone)
    if len(digits) <= 7:
        return digits
    return digits[:7] + '****' + digits[-4:]

def _format_otp_scraped(otp):
    otp = otp.strip()
    if re.fullmatch(r'\d{6}', otp):
        return f"{otp[:3]}-{otp[3:]}"
    return otp

def _extract_otp_scraped(text):
    m = re.search(r'\b(\d{3}-\d{3})\b', text)
    if m:
        return m.group(1)
    m = re.search(r'code\s*[:]?\s*(\d{4,6})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\b(\d{4,6})\b', text)
    return m.group(1) if m else None

def _extract_phone_scraped(text):
    m = re.search(r'(\+?\d{10,15})', text)
    return m.group(1) if m else "N/A"

def scraped_login(panel_id):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log("[SCRAPED] beautifulsoup4 not installed. Run: pip install beautifulsoup4")
        return False
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return False
    panel_url = panel.get("panel_url", "").rstrip("/")
    username = panel.get("login_user", "")
    password = panel.get("login_pass", "")
    if not panel_url or not username or not password:
        log(f"[SCRAPED] Missing creds for {panel.get('name', panel_id)}")
        return False
    session = _get_panel_session(panel_id)
    try:
        resp = session.get(f"{panel_url}/login", timeout=30)
        soup = BeautifulSoup(resp.text, 'html.parser')
        page_text = soup.get_text()
        numbers = re.findall(r'(\d+)\s*\+\s*(\d+)', page_text)
        login_data = {'username': username, 'password': password}
        if numbers:
            num1, num2 = numbers[0]
            login_data['capt'] = str(int(num1) + int(num2))
            log(f"[SCRAPED] Captcha: {num1} + {num2} = {login_data['capt']}")
        resp = session.post(f"{panel_url}/signin", data=login_data, timeout=30, allow_redirects=True)
        if "dashboard" in resp.url.lower() or resp.status_code == 200:
            log(f"[SCRAPED] Login OK: {panel.get('name', panel_id)}")
            return True
        resp = session.post(f"{panel_url}/login", data=login_data, timeout=30, allow_redirects=True)
        if "dashboard" in resp.url.lower() or resp.status_code == 200:
            log(f"[SCRAPED] Login OK (alt): {panel.get('name', panel_id)}")
            return True
        log(f"[SCRAPED] Login failed: {panel.get('name', panel_id)}")
        return False
    except Exception as e:
        log(f"[SCRAPED] Login error: {e}")
        return False

def _get_sesskey_scraped(panel_id):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return None
    panel_url = panel.get("panel_url", "").rstrip("/")
    panel_type = panel.get("panel_type", "agent")
    session = _get_panel_session(panel_id)
    # ALL INTS panels use /agent/ path regardless of type
    report_paths = [
        f"{panel_url}/agent/SMSCDRReports",
        f"{panel_url}/agent/smscdr",
        f"{panel_url}/agent/dashboard",
        f"{panel_url}/SMSCDRReports",
        f"{panel_url}/smscdr",
        panel_url,
    ]
    for report_url in report_paths:
        try:
            resp = session.get(report_url, timeout=30, allow_redirects=True)
            log(f"[SESSKEY] {report_url} -> {resp.status_code}, url={resp.url}")
            if resp.status_code != 200:
                continue
            html = resp.text
            if "login" in resp.url.lower() or "signin" in resp.url.lower():
                log(f"[SESSKEY] Redirected to login, session lost")
                continue
            patterns = [
                r'data_smscdr\.php\?[^\"\']*sesskey=([a-f0-9]{32})',
                r'sesskey=([a-f0-9]{32})',
                r'"sesskey"\s*:\s*"([a-f0-9]{32})"',
                r"sesskey=([a-f0-9]{32})",
                r'session[_-]?key=([a-f0-9]{32})',
            ]
            for pattern in patterns:
                m2 = re.search(pattern, html, re.IGNORECASE)
                if m2:
                    log(f"[SESSKEY] Found: {m2.group(1)[:8]}... from {report_url}")
                    return m2.group(1)
            clean = re.sub(r'<[^>]+>', ' ', html)
            clean = re.sub(r'\s+', ' ', clean).strip()
            log(f"[SESSKEY] No sesskey. Sample: {clean[:200]}")
        except Exception as e:
            log(f"[SESSKEY] Error: {report_url}: {e}")
            continue
    log(f"[SESSKEY] Not found for {panel.get('name', panel_id)}")
    return None


def scraped_fetch_otps(panel_id):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return []
    panel_url = panel.get("panel_url", "").rstrip("/")
    panel_type = panel.get("panel_type", "agent")
    session = _get_panel_session(panel_id)
    sms_list = []
    try:
        sesskey = _get_sesskey_scraped(panel_id)
        if not sesskey:
            return []
        today = datetime.now().strftime("%Y-%m-%d")
        # ALL INTS panels use /agent/ path for the API
        api_path = f"{panel_url}/agent/res/data_smscdr.php"
        params = {
            "draw": "1", "start": "0", "length": "50",
            "search[value]": "", "search[regex]": "false",
            "order[0][column]": "0", "order[0][dir]": "asc",
            "fdate1": f"{today} 00:00:00", "fdate2": f"{today} 23:59:59",
            "frange": "", "fclient": "", "fnum": "", "fcli": "",
            "fgdate": "", "fgmonth": "", "fgrange": "", "fgclient": "",
            "fgnumber": "", "fgcli": "", "fg": "0", "sesskey": sesskey,
        }
        resp = session.get(api_path, params=params, timeout=30)
        if resp.status_code != 200:
            return []
        try:
            data_resp = resp.json()
        except:
            return []
        records = []
        if isinstance(data_resp, dict):
            if 'data' in data_resp:
                records = data_resp['data']
            elif 'aaData' in data_resp:
                records = data_resp['aaData']
        elif isinstance(data_resp, list):
            records = data_resp
        for record in records:
            record_text = " ".join(str(f) for f in record) if isinstance(record, list) else str(record)
            if not re.search(r'code\s*[:]?\s*\d{4,6}', record_text, re.IGNORECASE):
                continue
            otp = _extract_otp_scraped(record_text)
            if not otp:
                continue
            service = _extract_service_scraped(record_text)
            country = _extract_country_scraped(record_text)
            phone = _extract_phone_scraped(record_text)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dm = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', record_text)
            if dm:
                timestamp = dm.group(1)
            sms_list.append({
                'otp': otp, 'service': service, 'country': country,
                'phone': phone, 'full_text': record_text[:500], 'timestamp': timestamp,
            })
        if sms_list:
            log(f"[SCRAPED] Found {len(sms_list)} OTPs from {panel.get('name', panel_id)}")
        return sms_list
    except Exception as e:
        log(f"[SCRAPED] Fetch error: {e}")
        return []

def build_vertex_otp_message(sms, watermark="EARNINGWITHSIMPLETASK"):
    service = sms.get('service', 'Unknown')
    country = sms.get('country', 'Unknown')
    flag = COUNTRY_FLAGS_SCRAPED.get(country, '🌍')
    phone = sms.get('phone', 'N/A')
    masked = _mask_phone_scraped(phone)
    otp = sms.get('otp', 'N/A')
    formatted_otp = _format_otp_scraped(otp) if '-' not in otp else otp
    time_part = sms.get('timestamp', '')
    if ' ' in time_part:
        time_part = time_part.split(' ')[1]
    service_emoji = SERVICE_EMOJIS_SCRAPED.get(service, '📱')
    sep = "\u2501" * 13
    text = (
        f"{html.escape(watermark)}\n"
        f"{sep}\n"
        f"{flag} {service_emoji} {service} 🟢\n"
        f"📱 {masked}\n"
        f"🔑 OTP: {formatted_otp}\n"
        f"Don't share this code with others\n"
        f"⏰ {time_part}"
    )
    return text

def scraped_panel_test(panel_id, chat_id):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        safe_send(chat_id, "⚠️ Panel not found")
        return
    safe_send(chat_id, f"🧪 <b>TESTING:</b> {html.escape(panel.get('name', ''))}\n\u23f3 Logging in...")
    if scraped_login(panel_id):
        sesskey = _get_sesskey_scraped(panel_id)
        otps = scraped_fetch_otps(panel_id)
        safe_send(chat_id,
            f"✅ <b>CONNECTION OK!</b>\n\n"
            f"🔐 <b>Login:</b> ✅\n"
            f"🔑 <b>Sesskey:</b> {'✅' if sesskey else '⚠️'}\n"
            f"📱 <b>OTPs Found:</b> {len(otps)}")
    else:
        safe_send(chat_id, "❌ <b>CONNECTION FAILED!</b>\nCheck URL, username, password.")

_scraped_monitor_hashes = {}

def scraped_monitor_tick():
    data = load_data()
    watermark = data.get("watermark", "VERTEX OTP")
    scraped_panels = {pid: p for pid, p in data.get("panels", {}).items()
                      if p.get("status") == "active" and p.get("type") == "scraped"}
    if not scraped_panels:
        return
    for pid, panel in scraped_panels.items():
        try:
            otps = scraped_fetch_otps(pid)
            hashes = _scraped_monitor_hashes.setdefault(pid, set())
            for sms in otps:
                sms_id = _hashlib.md5(
                    (sms['otp'] + sms['timestamp'] + sms.get('service', '')).encode()
                ).hexdigest()
                if sms_id in hashes:
                    continue
                hashes.add(sms_id)
                msg = build_vertex_otp_message(sms, watermark)
                forward_to_forward_groups(msg)
                log(f"[SCRAPED MONITOR] OTP {sms['otp']} from {sms.get('service','?')} forwarded to groups")
        except Exception as e:
            log(f"[SCRAPED MONITOR] Error processing {panel.get('name', pid)}: {e}")

# ============================================
#  PART 2 (CONTINUED) - DETECTION & COUNTRY DATA
# ============================================

# --- ENHANCED LANGUAGE DETECTION ---
def detect_language(text):
    if not text: return "EN"
    text_str = str(text)
    if any('\u0600' <= c <= '\u06ff' for c in text_str):
        if any(w in text_str.lower() for w in ["كود", "رمز", "تحقق", "التحقق", "تأكيد", "واتساب"]): return "AR"
        if any(w in text_str.lower() for w in ["کوڈ", "رمز", "تصدیق", "واٹس"]): return "UR"
        if any(w in text_str.lower() for w in ["کد", "رمز", "تأیید", "واتس"]): return "FA"
        if any(w in text_str.lower() for w in ["پاسه", "رمز", "کوډ"]): return "PS"
        return "AR"
    if any('\u0980' <= c <= '\u09ff' for c in text_str): return "BN"
    if any('\u0900' <= c <= '\u097f' for c in text_str): return "HI"
    if any('\u0b80' <= c <= '\u0bff' for c in text_str): return "TA"
    if any('\u0c00' <= c <= '\u0c7f' for c in text_str): return "TE"
    if any('\u0c80' <= c <= '\u0cff' for c in text_str): return "KN"
    if any('\u0d00' <= c <= '\u0d7f' for c in text_str): return "ML"
    if any('\u0d80' <= c <= '\u0dff' for c in text_str): return "SI"
    if any('\u1000' <= c <= '\u109f' for c in text_str): return "MY"
    if any('\u1780' <= c <= '\u17ff' for c in text_str): return "KM"
    if any('\u0e80' <= c <= '\u0eff' for c in text_str):
        if not any('\u0e00' <= c <= '\u0e7f' for c in text_str): return "LO"
    if any('\u0e00' <= c <= '\u0e7f' for c in text_str): return "TH"
    if any('\u4e00' <= c <= '\u9fff' for c in text_str): return "ZH"
    if any('\u3040' <= c <= '\u309f' for c in text_str): return "JA"
    if any('\u30a0' <= c <= '\u30ff' for c in text_str): return "JA"
    if any('\uac00' <= c <= '\ud7af' for c in text_str): return "KO"
    if any('\u1100' <= c <= '\u11ff' for c in text_str): return "KO"
    if any('\u0400' <= c <= '\u04ff' for c in text_str): return "RU"
    if any('\u10a0' <= c <= '\u10ff' for c in text_str): return "KA"
    if any('\u0530' <= c <= '\u058f' for c in text_str): return "HY"
    if any('\u0370' <= c <= '\u03ff' for c in text_str): return "EL"
    if any('\u0590' <= c <= '\u05ff' for c in text_str): return "HE"
    if any('\u1200' <= c <= '\u137f' for c in text_str): return "AM"
    if any('\u0f00' <= c <= '\u0fff' for c in text_str): return "BO"
    if any(c in 'ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ' for c in text_str): return "VN"
    text_lower = text_str.lower()
    if any(w in text_lower for w in ["código", "contraseña", "verificación", "clave", "acceso"]): return "ES"
    if any(w in text_lower for w in ["code secret", "vérification", "mot de passe", "confirmation", "votre code"]): return "FR"
    if any(w in text_lower for w in ["código de", "senha de", "verificação", "chave", "acesso"]): return "PT"
    if any(w in text_lower for w in ["doğrulama", "şifre", "kod", "giriş", "onay", "parola"]): return "TR"
    if any(w in text_lower for w in ["kode verifikasi", "pengesahan", "kata laluan", "kod", "sahkan"]): return "ID"
    if any(w in text_lower for w in ["bestätigungscode", "sicherheitscode", "passwort", "zugangscode", "verifizierung"]): return "DE"
    if any(w in text_lower for w in ["codice di", "verifica", "password", "conferma", "accesso"]): return "IT"
    if any(w in text_lower for w in ["verificatiecode", "bevestigingscode", "toegangscode", "wachtwoord"]): return "NL"
    if any(w in text_lower for w in ["kod weryfikacyjny", "hasło", "potwierdzenie", "dostęp", "klucz"]): return "PL"
    if any(w in text_lower for w in ["cod de", "parola", "confirmare", "verificare", "acces"]): return "RO"
    if any(w in text_lower for w in ["ověřovací kód", "heslo", "přístup", "potvrzení"]): return "CS"
    if any(w in text_lower for w in ["overovací kód", "heslo", "prístup", "potvrdenie"]): return "SK"
    if any(w in text_lower for w in ["megerősítő kód", "jelszó", "hozzáférés", "ellenőrzés"]): return "HU"
    if any(w in text_lower for w in ["verifieringskod", "lösenord", "bekräftelse", "åtkomst"]): return "SV"
    if any(w in text_lower for w in ["verifiseringskode", "passord", "bekreftelse", "tilgang"]): return "NO"
    if any(w in text_lower for w in ["bekræftelseskode", "adgangskode", "verifikation", "bekræft"]): return "DA"
    if any(w in text_lower for w in ["vahvistuskoodi", "salasana", "tunnus", "varmennus"]): return "FI"
    if any(w in text_lower for w in ["potvrdni kod", "lozinka", "pristup", "verifikacija"]): return "HR"
    if any(w in text_lower for w in ["potrditvena koda", "geslo", "dostop", "preverjanje"]): return "SL"
    if any(w in text_lower for w in ["patvirtinimo kodas", "slaptažodis", "prieiga", "patikrinimas"]): return "LT"
    if any(w in text_lower for w in ["apstiprinājuma kods", "parole", "piekļuve", "verifikācija"]): return "LV"
    if any(w in text_lower for w in ["kinnituskood", "parool", "juurdepääs", "kontroll"]): return "ET"
    if any(w in text_lower for w in ["code ng", "password", "pagpapatunay", "access", "kumpirmasyon"]): return "TL"
    return "EN"

# --- ENHANCED SERVICE DETECTION ---
SERVICE_SMS_KEYWORDS = {
    "whatsapp": ["whatsapp", "wa", "wap", "w/a", "whatsapp business", "whatsapp code", "whatsapp verification", "whatsapp kod"],
    "facebook": ["facebook", "fb", "meta", "fbook", "fb code", "facebook code", "fb confirmation"],
    "instagram": ["instagram", "insta", "ig", "ig code", "instagram code"],
    "telegram": ["telegram", "tg", "tele", "telegram code", "tg code"],
    "google": ["google", "gmail", "youtube", "g-", "google voice", "google verification"],
    "tiktok": ["tiktok", "tik tok", "tikvideo", "tiktok code", "tik code"],
    "snapchat": ["snapchat", "snap", "snap code", "snapchat code"],
    "twitter": ["twitter", "x.com", "x code", "your x confirmation", "twitter code"],
    "binance": ["binance", "bnb", "binances", "binance verification"],
    "melbet": ["melbet", "mel", "melbet code"],
    "bkash": ["bkash", "b-kash", "bkash code"],
    "nagad": ["nagad", "nagad code"],
    "imo": ["imo", "imo code", "imo verification"],
    "microsoft": ["microsoft", "ms", "outlook", "microsoft account", "ms code"],
    "apple": ["apple", "icloud", "itunes", "apple id", "apple code"],
    "paypal": ["paypal", "pay pal", "paypal code"],
    "uber": ["uber", "uber code", "uber verification"],
    "amazon": ["amazon", "amzn", "amazon code"],
    "netflix": ["netflix", "netflix code"],
    "discord": ["discord", "discord code"],
    "spotify": ["spotify", "spotify code"],
    "linkedin": ["linkedin", "linked in", "linkedin code"],
    "yahoo": ["yahoo", "yahoo code"],
    "viber": ["viber", "viber code"],
    "line": ["line", "line code", "line verification"],
    "wechat": ["wechat", "we chat", "wechat code"],
    "signal": ["signal", "signal code"],
}

def detect_service_from_sms(sms_text, app_name=""):
    if not sms_text and not app_name:
        return "Unknown"
    sms_lower = str(sms_text).lower() if sms_text else ""
    app_lower = str(app_name).lower() if app_name else ""
    if any(w in sms_lower for w in ["whatsapp", "wa ", " w/a", "whatsapp code", "whatsapp kod", "whatsapp verification"]):
        return "Whatsapp"
    for service, keywords in SERVICE_SMS_KEYWORDS.items():
        for kw in keywords:
            if kw in sms_lower:
                return service.title()
    if app_lower and app_lower != "custom search":
        for service, keywords in SERVICE_SMS_KEYWORDS.items():
            for kw in keywords:
                if kw in app_lower or app_lower in service:
                    return service.title()
        return app_name.title()
    return "Unknown"

# --- ALL 240+ COUNTRY FLAGS ---
COUNTRY_FLAGS = {
    "afghanistan": "🇦🇫", "albania": "🇦🇱", "algeria": "🇩🇿", "andorra": "🇦🇩", "angola": "🇦🇴",
    "antigua and barbuda": "🇦🇬", "argentina": "🇦🇷", "armenia": "🇦🇲", "australia": "🇦🇺",
    "austria": "🇦🇹", "azerbaijan": "🇦🇿", "bahamas": "🇧🇸", "bahrain": "🇧🇭",
    "bangladesh": "🇧🇩", "barbados": "🇧🇧", "belarus": "🇧🇾", "belgium": "🇧🇪", "belize": "🇧🇿",
    "benin": "🇧🇯", "bhutan": "🇧🇹", "bolivia": "🇧🇴", "bosnia and herzegovina": "🇧🇦",
    "botswana": "🇧🇼", "brazil": "🇧🇷", "brunei": "🇧🇳", "bulgaria": "🇧🇬",
    "burkina faso": "🇧🇫", "burundi": "🇧🇮", "cambodia": "🇰🇭", "cameroon": "🇨🇲",
    "canada": "🇨🇦", "cape verde": "🇨🇻", "central african republic": "🇨🇫", "chad": "🇹🇩",
    "chile": "🇨🇱", "china": "🇨🇳", "colombia": "🇨🇴", "comoros": "🇰🇲", "congo": "🇨🇬",
    "costa rica": "🇨🇷", "cote d'ivoire": "🇨🇮", "ivory coast": "🇨🇮",
    "croatia": "🇭🇷", "cuba": "🇨🇺", "cyprus": "🇨🇾", "czech republic": "🇨🇿",
    "denmark": "🇩🇰", "djibouti": "🇩🇯", "dominica": "🇩🇲", "dominican republic": "🇩🇴",
    "drc": "🇨🇩", "ecuador": "🇪🇨", "egypt": "🇪🇬", "el salvador": "🇸🇻",
    "equatorial guinea": "🇬🇶", "eritrea": "🇪🇷", "estonia": "🇪🇪", "eswatini": "🇸🇿",
    "ethiopia": "🇪🇹", "fiji": "🇫🇯", "finland": "🇫🇮", "france": "🇫🇷",
    "gabon": "🇬🇦", "gambia": "🇬🇲", "georgia": "🇬🇪", "germany": "🇩🇪", "ghana": "🇬🇭",
    "greece": "🇬🇷", "grenada": "🇬🇩", "guatemala": "🇬🇹", "guinea": "🇬🇳",
    "guinea bissau": "🇬🇼", "guyana": "🇬🇾", "haiti": "🇭🇹", "honduras": "🇭🇳",
    "hong kong": "🇭🇰", "hungary": "🇭🇺", "iceland": "🇮🇸", "india": "🇮🇳",
    "indonesia": "🇮🇩", "iran": "🇮🇷", "iraq": "🇮🇶", "ireland": "🇮🇪", "israel": "🇮🇱",
    "italy": "🇮🇹", "jamaica": "🇯🇲", "japan": "🇯🇵", "jordan": "🇯🇴", "kazakhstan": "🇰🇿",
    "kenya": "🇰🇪", "kiribati": "🇰🇮", "kosovo": "🇽🇰", "kuwait": "🇰🇼", "kyrgyzstan": "🇰🇬",
    "laos": "🇱🇦", "latvia": "🇱🇻", "lebanon": "🇱🇧", "lesotho": "🇱🇸", "liberia": "🇱🇷",
    "libya": "🇱🇾", "liechtenstein": "🇱🇮", "lithuania": "🇱🇹", "luxembourg": "🇱🇺",
    "macau": "🇲🇴", "madagascar": "🇲🇬", "malawi": "🇲🇼", "malaysia": "🇲🇾", "maldives": "🇲🇻",
    "mali": "🇲🇱", "malta": "🇲🇹", "marshall islands": "🇲🇭", "mauritania": "🇲🇷",
    "mauritius": "🇲🇺", "mexico": "🇲🇽", "micronesia": "🇫🇲", "moldova": "🇲🇩",
    "monaco": "🇲🇨", "mongolia": "🇲🇳", "montenegro": "🇲🇪", "morocco": "🇲🇦",
    "mozambique": "🇲🇿", "myanmar": "🇲🇲", "namibia": "🇳🇦", "nauru": "🇳🇷", "nepal": "🇳🇵",
    "netherlands": "🇳🇱", "new zealand": "🇳🇿", "nicaragua": "🇳🇮", "niger": "🇳🇪",
    "nigeria": "🇳🇬", "north korea": "🇰🇵", "north macedonia": "🇲🇰", "norway": "🇳🇴",
    "oman": "🇴🇲", "pakistan": "🇵🇰", "palau": "🇵🇼", "palestine": "🇵🇸", "panama": "🇵🇦",
    "papua new guinea": "🇵🇬", "paraguay": "🇵🇾", "peru": "🇵🇪", "philippines": "🇵🇭",
    "poland": "🇵🇱", "portugal": "🇵🇹", "qatar": "🇶🇦", "romania": "🇷🇴", "russia": "🇷🇺",
    "rwanda": "🇷🇼", "saint kitts and nevis": "🇰🇳", "saint lucia": "🇱🇨",
    "saint vincent and the grenadines": "🇻🇨", "samoa": "🇼🇸", "san marino": "🇸🇲",
    "sao tome and principe": "🇸🇹", "saudi arabia": "🇸🇦", "senegal": "🇸🇳", "serbia": "🇷🇸",
    "seychelles": "🇸🇨", "sierra leone": "🇸🇱", "singapore": "🇸🇬", "slovakia": "🇸🇰",
    "slovenia": "🇸🇮", "solomon islands": "🇸🇧", "somalia": "🇸🇴", "south africa": "🇿🇦",
    "south korea": "🇰🇷", "south sudan": "🇸🇸", "spain": "🇪🇸", "sri lanka": "🇱🇰",
    "sudan": "🇸🇩", "suriname": "🇸🇷", "sweden": "🇸🇪", "switzerland": "🇨🇭", "syria": "🇸🇾",
    "taiwan": "🇹🇼", "tajikistan": "🇹🇯", "tanzania": "🇹🇿", "thailand": "🇹🇭",
    "timor leste": "🇹🇱", "togo": "🇹🇬", "tonga": "🇹🇴", "trinidad and tobago": "🇹🇹",
    "tunisia": "🇹🇳", "turkey": "🇹🇷", "turkmenistan": "🇹🇲", "tuvalu": "🇹🇻",
    "uganda": "🇺🇬", "ukraine": "🇺🇦", "uae": "🇦🇪", "united arab emirates": "🇦🇪",
    "united kingdom": "🇬🇧", "uk": "🇬🇧", "usa": "🇺🇸", "united states": "🇺🇸",
    "uruguay": "🇺🇾", "uzbekistan": "🇺🇿", "vanuatu": "🇻🇺", "vatican city": "🇻🇦",
    "venezuela": "🇻🇪", "vietnam": "🇻🇳", "yemen": "🇾🇪", "zambia": "🇿🇲", "zimbabwe": "🇿🇼",
    "anguilla": "🇦🇮", "aruba": "🇦🇼", "bermuda": "🇧🇲", "british virgin islands": "🇻🇬",
    "cayman islands": "🇰🇾", "curacao": "🇨🇼", "falkland islands": "🇫🇰",
    "french guiana": "🇬🇫", "greenland": "🇬🇱", "guadeloupe": "🇬🇵",
    "guam": "🇬🇺", "martinique": "🇲🇶", "mayotte": "🇾🇹", "montserrat": "🇲🇸",
    "new caledonia": "🇳🇨", "niue": "🇳🇺", "norfolk island": "🇳🇫",
    "northern mariana islands": "🇲🇵", "pitcairn islands": "🇵🇳", "puerto rico": "🇵🇷",
    "reunion": "🇷🇪", "saint helena": "🇸🇭", "tokelau": "🇹🇰",
    "turks and caicos islands": "🇹🇨", "us virgin islands": "🇻🇮",
    "wallis and futuna": "🇼🇫", "western sahara": "🇪🇭", "cook islands": "🇨🇰",
    "french polynesia": "🇵🇫", "gibraltar": "🇬🇮", "faroe islands": "🇫🇴",
    "svalbard and jan mayen": "🇸🇯", "aland islands": "🇦🇽", "jersey": "🇯🇪",
    "guernsey": "🇬🇬", "isle of man": "🇮🇲", "saint pierre and miquelon": "🇵🇲",
    "sint maarten": "🇸🇽", "bonaire": "🇧🇶"
}

# ==================== PHONE TO COUNTRY DETECTION ====================
PHONE_PREFIXES = {
    '234': 'NIGERIA', '233': 'GHANA', '254': 'KENYA', '27': 'SOUTH AFRICA',
    '20': 'EGYPT', '212': 'MOROCCO', '216': 'TUNISIA', '213': 'ALGERIA',
    '218': 'LIBYA', '971': 'UAE', '966': 'SAUDI ARABIA', '965': 'KUWAIT',
    '974': 'QATAR', '968': 'OMAN', '973': 'BAHRAIN', '962': 'JORDAN',
    '972': 'ISRAEL', '90': 'TURKEY', '91': 'INDIA', '92': 'PAKISTAN',
    '880': 'BANGLADESH', '94': 'SRI LANKA', '977': 'NEPAL',
    '63': 'PHILIPPINES', '62': 'INDONESIA', '60': 'MALAYSIA',
    '65': 'SINGAPORE', '66': 'THAILAND', '84': 'VIETNAM', '855': 'CAMBODIA',
    '95': 'MYANMAR', '44': 'UK', '61': 'AUSTRALIA', '49': 'GERMANY',
    '33': 'FRANCE', '34': 'SPAIN', '39': 'ITALY', '55': 'BRAZIL',
    '52': 'MEXICO', '54': 'ARGENTINA', '57': 'COLOMBIA', '51': 'PERU',
    '56': 'CHILE', '593': 'ECUADOR', '591': 'BOLIVIA', '595': 'PARAGUAY',
    '598': 'URUGUAY', '58': 'VENEZUELA', '506': 'COSTA RICA', '507': 'PANAMA',
    '502': 'GUATEMALA', '504': 'HONDURAS', '503': 'EL SALVADOR', '505': 'NICARAGUA',
    '242': 'CONGO', '243': 'DRC', '244': 'ANGOLA', '258': 'MOZAMBIQUE',
    '263': 'ZIMBABWE', '260': 'ZAMBIA', '265': 'MALAWI', '261': 'MADAGASCAR',
    '230': 'MAURITIUS', '248': 'SEYCHELLES', '1264': 'ANGUILLA',
    '1684': 'AMERICAN SAMOA', '1671': 'GUAM', '1809': 'DOMINICAN REPUBLIC',
    '1787': 'PUERTO RICO', '1868': 'TRINIDAD', '1876': 'JAMAICA',
    '1242': 'BAHAMAS', '1246': 'BARBADOS', '592': 'GUYANA', '597': 'SURINAME',
    '501': 'BELIZE', '509': 'HAITI', '53': 'CUBA', '1': 'USA',
}

def detect_country_from_phone(phone):
    """Detect country from phone number prefix."""
    digits = re.sub(r'[^0-9]', '', phone)
    if digits.startswith('+'):
        digits = digits[1:]
    for length in [3, 2, 1]:
        prefix = digits[:length]
        if prefix in PHONE_PREFIXES:
            return PHONE_PREFIXES[prefix]
    return 'Unknown'

COUNTRY_ISO = {
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ", "andorra": "AD", "angola": "AO",
    "antigua and barbuda": "AG", "argentina": "AR", "armenia": "AM", "australia": "AU",
    "austria": "AT", "azerbaijan": "AZ", "bahamas": "BS", "bahrain": "BH", "bangladesh": "BD",
    "barbados": "BB", "belarus": "BY", "belgium": "BE", "belize": "BZ", "benin": "BJ",
    "bhutan": "BT", "bolivia": "BO", "bosnia and herzegovina": "BA", "botswana": "BW",
    "brazil": "BR", "brunei": "BN", "bulgaria": "BG", "burkina faso": "BF", "burundi": "BI",
    "cambodia": "KH", "cameroon": "CM", "canada": "CA", "cape verde": "CV",
    "central african republic": "CF", "chad": "TD", "chile": "CL", "china": "CN",
    "colombia": "CO", "comoros": "KM", "congo": "CG", "costa rica": "CR", "cote d'ivoire": "CI",
    "ivory coast": "CI", "croatia": "HR", "cuba": "CU", "cyprus": "CY", "czech republic": "CZ",
    "denmark": "DK", "djibouti": "DJ", "dominica": "DM", "dominican republic": "DO",
    "drc": "CD", "ecuador": "EC", "egypt": "EG", "el salvador": "SV", "equatorial guinea": "GQ",
    "eritrea": "ER", "estonia": "EE", "eswatini": "SZ", "ethiopia": "ET", "fiji": "FJ",
    "finland": "FI", "france": "FR", "gabon": "GA", "gambia": "GM", "georgia": "GE",
    "germany": "DE", "ghana": "GH", "greece": "GR", "grenada": "GD", "guatemala": "GT",
    "guinea": "GN", "guinea bissau": "GW", "guyana": "GY", "haiti": "HT", "honduras": "HN",
    "hong kong": "HK", "hungary": "HU", "iceland": "IS", "india": "IN", "indonesia": "ID",
    "iran": "IR", "iraq": "IQ", "ireland": "IE", "israel": "IL", "italy": "IT",
    "jamaica": "JM", "japan": "JP", "jordan": "JO", "kazakhstan": "KZ", "kenya": "KE",
    "kiribati": "KI", "kosovo": "XK", "kuwait": "KW", "kyrgyzstan": "KG", "laos": "LA",
    "latvia": "LV", "lebanon": "LB", "lesotho": "LS", "liberia": "LR", "libya": "LY",
    "liechtenstein": "LI", "lithuania": "LT", "luxembourg": "LU", "macau": "MO",
    "madagascar": "MG", "malawi": "MW", "malaysia": "MY", "maldives": "MV", "mali": "ML",
    "malta": "MT", "marshall islands": "MH", "mauritania": "MR", "mauritius": "MU",
    "mexico": "MX", "micronesia": "FM", "moldova": "MD", "monaco": "MC", "mongolia": "MN",
    "montenegro": "ME", "morocco": "MA", "mozambique": "MZ", "myanmar": "MM", "namibia": "NA",
    "nauru": "NR", "nepal": "NP", "netherlands": "NL", "new zealand": "NZ", "nicaragua": "NI",
    "niger": "NE", "nigeria": "NG", "north korea": "KP", "north macedonia": "MK", "norway": "NO",
    "oman": "OM", "pakistan": "PK", "palau": "PW", "palestine": "PS", "panama": "PA",
    "papua new guinea": "PG", "paraguay": "PY", "peru": "PE", "philippines": "PH", "poland": "PL",
    "portugal": "PT", "qatar": "QA", "romania": "RO", "russia": "RU", "rwanda": "RW",
    "saint kitts and nevis": "KN", "saint lucia": "LC", "saint vincent and the grenadines": "VC",
    "samoa": "WS", "san marino": "SM", "sao tome and principe": "ST", "saudi arabia": "SA",
    "senegal": "SN", "serbia": "RS", "seychelles": "SC", "sierra leone": "SL", "singapore": "SG",
    "slovakia": "SK", "slovenia": "SI", "solomon islands": "SB", "somalia": "SO",
    "south africa": "ZA", "south korea": "KR", "south sudan": "SS", "spain": "ES",
    "sri lanka": "LK", "sudan": "SD", "suriname": "SR", "sweden": "SE", "switzerland": "CH",
    "syria": "SY", "taiwan": "TW", "tajikistan": "TJ", "tanzania": "TZ", "thailand": "TH",
    "timor leste": "TL", "togo": "TG", "tonga": "TO", "trinidad and tobago": "TT",
    "tunisia": "TN", "turkey": "TR", "turkmenistan": "TM", "tuvalu": "TV", "uganda": "UG",
    "ukraine": "UA", "uae": "AE", "united arab emirates": "AE", "united kingdom": "GB", "uk": "GB",
    "usa": "US", "united states": "US", "uruguay": "UY", "uzbekistan": "UZ", "vanuatu": "VU",
    "vatican city": "VA", "venezuela": "VE", "vietnam": "VN", "yemen": "YE", "zambia": "ZM", "zimbabwe": "ZW",
    "anguilla": "AI", "aruba": "AW", "bermuda": "BM", "cayman islands": "KY", "curacao": "CW",
    "greenland": "GL", "guam": "GU", "puerto rico": "PR", "reunion": "RE", "western sahara": "EH"
}

# Country -> Currency code mapping (ISO 4217)
COUNTRY_CURRENCY = {
    "AF": "AFN", "AL": "ALL", "DZ": "DZD", "AD": "EUR", "AO": "AOA",
    "AG": "XCD", "AR": "ARS", "AM": "AMD", "AU": "AUD", "AT": "EUR",
    "AZ": "AZN", "BS": "BSD", "BH": "BHD", "BD": "BDT", "BB": "BBD",
    "BY": "BYN", "BE": "EUR", "BZ": "BZD", "BJ": "XOF", "BT": "BTN",
    "BO": "BOB", "BA": "BAM", "BW": "BWP", "BR": "BRL", "BN": "BND",
    "BG": "BGN", "BF": "XOF", "BI": "BIF", "KH": "KHR", "CM": "XAF",
    "CA": "CAD", "CV": "CVE", "CF": "XAF", "TD": "XAF", "CL": "CLP",
    "CN": "CNY", "CO": "COP", "KM": "KMF", "CG": "XAF", "CD": "CDF",
    "CR": "CRC", "CI": "XOF", "HR": "EUR", "CU": "CUP", "CY": "EUR",
    "CZ": "CZK", "DK": "DKK", "DJ": "DJF", "DM": "XCD", "DO": "DOP",
    "EC": "USD", "EG": "EGP", "SV": "USD", "GQ": "XAF", "ER": "ERN",
    "EE": "EUR", "SZ": "SZL", "ET": "ETB", "FJ": "FJD", "FI": "EUR",
    "FR": "EUR", "GA": "XAF", "GM": "GMD", "GE": "GEL", "DE": "EUR",
    "GH": "GHS", "GR": "EUR", "GD": "XCD", "GT": "GTQ", "GN": "GNF",
    "GW": "XOF", "GY": "GYD", "HT": "HTG", "HN": "HNL", "HK": "HKD",
    "HU": "HUF", "IS": "ISK", "IN": "INR", "ID": "IDR", "IR": "IRR",
    "IQ": "IQD", "IE": "EUR", "IL": "ILS", "IT": "EUR", "JM": "JMD",
    "JP": "JPY", "JO": "JOD", "KZ": "KZT", "KE": "KES", "KI": "AUD",
    "KW": "KWD", "KG": "KGS", "LA": "LAK", "LV": "EUR", "LB": "LBP",
    "LS": "LSL", "LR": "LRD", "LY": "LYD", "LI": "CHF", "LT": "EUR",
    "LU": "EUR", "MO": "MOP", "MG": "MGA", "MW": "MWK", "MY": "MYR",
    "MV": "MVR", "ML": "XOF", "MT": "EUR", "MH": "USD", "MR": "MRU",
    "MU": "MUR", "MX": "MXN", "FM": "USD", "MD": "MDL", "MC": "EUR",
    "MN": "MNT", "ME": "EUR", "MA": "MAD", "MZ": "MZN", "MM": "MMK",
    "NA": "NAD", "NR": "AUD", "NP": "NPR", "NL": "EUR", "NZ": "NZD",
    "NI": "NIO", "NE": "XOF", "NG": "NGN", "KP": "KPW", "MK": "MKD",
    "NO": "NOK", "OM": "OMR", "PK": "PKR", "PW": "USD", "PA": "PAB",
    "PG": "PGK", "PY": "PYG", "PE": "PEN", "PH": "PHP", "PL": "PLN",
    "PT": "EUR", "QA": "QAR", "RO": "RON", "RU": "RUB", "RW": "RWF",
    "KN": "XCD", "LC": "XCD", "VC": "XCD", "WS": "WST", "SM": "EUR",
    "ST": "STN", "SA": "SAR", "SN": "XOF", "RS": "RSD", "SC": "SCR",
    "SL": "SLL", "SG": "SGD", "SK": "EUR", "SI": "EUR", "SB": "SBD",
    "SO": "SOS", "ZA": "ZAR", "KR": "KRW", "SS": "SSP", "ES": "EUR",
    "LK": "LKR", "SD": "SDG", "SR": "SRD", "SE": "SEK", "CH": "CHF",
    "SY": "SYP", "TW": "TWD", "TJ": "TJS", "TZ": "TZS", "TH": "THB",
    "TL": "USD", "TG": "XOF", "TO": "TOP", "TT": "TTD", "TN": "TND",
    "TR": "TRY", "TM": "TMT", "TV": "AUD", "UG": "UGX", "UA": "UAH",
    "AE": "AED", "GB": "GBP", "US": "USD", "UY": "UYU", "UZ": "UZS",
    "VU": "VUV", "VA": "EUR", "VE": "VES", "VN": "VND", "YE": "YER",
    "ZM": "ZMW", "ZW": "ZWL"
}

PHONE_TO_COUNTRY = {
    "1": "United States", "7": "Russia", "20": "Egypt", "27": "South Africa",
    "30": "Greece", "31": "Netherlands", "32": "Belgium", "33": "France",
    "34": "Spain", "36": "Hungary", "39": "Italy", "40": "Romania",
    "41": "Switzerland", "43": "Austria", "44": "United Kingdom", "45": "Denmark",
    "46": "Sweden", "47": "Norway", "48": "Poland", "49": "Germany",
    "51": "Peru", "52": "Mexico", "53": "Cuba", "54": "Argentina",
    "55": "Brazil", "56": "Chile", "57": "Colombia", "58": "Venezuela",
    "60": "Malaysia", "61": "Australia", "62": "Indonesia", "63": "Philippines",
    "64": "New Zealand", "65": "Singapore", "66": "Thailand", "81": "Japan",
    "82": "South Korea", "84": "Vietnam", "86": "China", "90": "Turkey",
    "91": "India", "92": "Pakistan", "93": "Afghanistan", "94": "Sri Lanka",
    "95": "Myanmar", "98": "Iran", "211": "South Sudan", "212": "Morocco",
    "213": "Algeria", "216": "Tunisia", "218": "Libya", "220": "Gambia",
    "221": "Senegal", "222": "Mauritania", "223": "Mali", "224": "Guinea",
    "225": "Cote d'Ivoire", "226": "Burkina Faso", "227": "Niger", "228": "Togo",
    "229": "Benin", "230": "Mauritius", "231": "Liberia", "232": "Sierra Leone",
    "233": "Ghana", "234": "Nigeria", "235": "Chad", "236": "Central African Republic",
    "237": "Cameroon", "238": "Cape Verde", "239": "Sao Tome and Principe", "240": "Equatorial Guinea",
    "241": "Gabon", "242": "Congo", "243": "DRC", "244": "Angola", "245": "Guinea Bissau",
    "249": "Sudan", "250": "Rwanda", "251": "Ethiopia", "252": "Somalia", "253": "Djibouti",
    "254": "Kenya", "255": "Tanzania", "256": "Uganda", "257": "Burundi",
    "258": "Mozambique", "260": "Zambia", "261": "Madagascar", "262": "Reunion",
    "263": "Zimbabwe", "264": "Namibia", "265": "Malawi", "266": "Lesotho",
    "267": "Botswana", "268": "Eswatini", "269": "Comoros", "291": "Eritrea",
    "350": "Gibraltar", "351": "Portugal", "352": "Luxembourg", "353": "Ireland",
    "354": "Iceland", "355": "Albania", "356": "Malta", "357": "Cyprus",
    "358": "Finland", "359": "Bulgaria", "370": "Lithuania", "371": "Latvia",
    "372": "Estonia", "373": "Moldova", "374": "Armenia", "375": "Belarus",
    "376": "Andorra", "377": "Monaco", "378": "San Marino", "379": "Vatican City",
    "380": "Ukraine", "381": "Serbia", "382": "Montenegro", "383": "Kosovo",
    "385": "Croatia", "386": "Slovenia", "387": "Bosnia and Herzegovina",
    "389": "North Macedonia", "420": "Czech Republic", "421": "Slovakia",
    "423": "Liechtenstein", "501": "Belize", "502": "Guatemala", "503": "El Salvador",
    "504": "Honduras", "505": "Nicaragua", "506": "Costa Rica", "507": "Panama",
    "509": "Haiti", "591": "Bolivia", "592": "Guyana", "593": "Ecuador",
    "595": "Paraguay", "597": "Suriname", "598": "Uruguay", "670": "Timor Leste",
    "673": "Brunei", "674": "Nauru", "675": "Papua New Guinea",
    "676": "Tonga", "677": "Solomon Islands", "678": "Vanuatu", "679": "Fiji",
    "680": "Palau", "685": "Samoa", "686": "Kiribati", "687": "New Caledonia",
    "688": "Tuvalu", "689": "French Polynesia", "691": "Micronesia",
    "692": "Marshall Islands", "850": "North Korea", "852": "Hong Kong",
    "853": "Macau", "855": "Cambodia", "856": "Laos", "880": "Bangladesh",
    "886": "Taiwan", "960": "Maldives", "961": "Lebanon", "962": "Jordan",
    "963": "Syria", "964": "Iraq", "965": "Kuwait", "966": "Saudi Arabia",
    "967": "Yemen", "968": "Oman", "970": "Palestine", "971": "UAE",
    "972": "Israel", "973": "Bahrain", "974": "Qatar", "975": "Bhutan",
    "976": "Mongolia", "977": "Nepal", "992": "Tajikistan", "993": "Turkmenistan",
    "994": "Azerbaijan", "995": "Georgia", "996": "Kyrgyzstan", "998": "Uzbekistan"
}

SERVICE_SHORTS = {
    "whatsapp": "WA", "facebook": "FB", "instagram": "IG", "telegram": "TG",
    "twitter": "TW", "google": "GO", "gmail": "GM", "youtube": "YT",
    "apple": "AP", "microsoft": "MS", "tiktok": "TT", "snapchat": "SC",
    "binance": "BN", "melbet": "MB", "bkash": "BK", "nagad": "NG",
    "imo": "IMO", "paypal": "PP", "uber": "UB", "amazon": "AMZ",
    "netflix": "NF", "discord": "DC", "spotify": "SP", "linkedin": "LI",
    "yahoo": "YH", "viber": "VB", "line": "LN", "wechat": "WC", "signal": "SG"
}

EMOJI_COLLECTION = {
    "whatsapp": "💚", "facebook": "📘", "instagram": "📷", "telegram": "✈️",
    "twitter": "𝕏", "google": "🔍", "gmail": "📧", "youtube": "🎬",
    "apple": "🍎", "microsoft": "💻", "tiktok": "🎵", "snapchat": "👻",
    "binance": "💰", "melbet": "🎰", "bkash": "💳", "nagad": "📲",
    "imo": "💭", "paypal": "💵", "uber": "🚗", "amazon": "📦",
    "netflix": "🎬", "discord": "💬", "spotify": "🎧", "linkedin": "💼",
    "yahoo": "📧", "viber": "💜", "line": "💚", "wechat": "💚", "signal": "🔒"
}
# ============================================
#  PART 3 - HELPER FUNCTIONS & DATA LAYER
# ============================================

def get_country_flag(country_name):
    if not country_name: return "🌍"
    name = str(country_name).lower().strip()
    if name in COUNTRY_FLAGS: return COUNTRY_FLAGS[name]
    for country, flag in COUNTRY_FLAGS.items():
        if len(country) >= 4 and (country in name or name in country): return flag
    return "🌍"

def get_iso_code(country_name):
    name = str(country_name).lower().strip()
    if name in COUNTRY_ISO: return COUNTRY_ISO[name]
    for country, iso in COUNTRY_ISO.items():
        if country in name or name in country: return iso
    return name[:2].upper() if len(name) >= 2 else "UN"

def emo(keyword, default="✨"):
    if not keyword: return default
    kw = str(keyword).lower().strip()
    if kw in EMOJI_COLLECTION: return EMOJI_COLLECTION[kw]
    for key, emoji in EMOJI_COLLECTION.items():
        if len(key) >= 3 and key in kw: return emoji
    flag = get_country_flag(kw)
    if flag != "🌍": return flag
    return default

def get_short_service(service_name):
    name = str(service_name).lower().strip()
    if name in SERVICE_SHORTS: return SERVICE_SHORTS[name]
    return name[:2].upper() if len(name) >= 2 else "SV"

def mask_number(phone):
    phone_str = str(phone).replace('+', '')
    if len(phone_str) >= 6:
        return f"{phone_str[:3]}XXX{phone_str[-3:]}"
    return phone_str

def get_country_from_number(phone_number):
    number = str(phone_number).replace('+', '').strip()
    for code_len in [3, 2, 1]:
        if len(number) >= code_len:
            code = number[:code_len]
            if code in PHONE_TO_COUNTRY: return PHONE_TO_COUNTRY[code]
    return "Unknown"

def format_url(url):
    url = url.strip()
    if url and not url.startswith(('http://', 'https://', 'tg://')): return 'https://' + url
    return url

def extract_channel_identifier(url):
    url = url.strip()
    if url.lstrip('-').isdigit():
        return int(url)
    if url.startswith("@"):
        return url
    if "t.me/" in url:
        parts = url.split("t.me/")
        if len(parts) > 1:
            username = parts[1].split("/")[0].split("?")[0]
            if username.startswith("+"):
                return None
            if not username.startswith("@"):
                username = "@" + username
            return username
    return None

def is_private_invite_link(url):
    url = url.strip()
    if "t.me/+" in url or "t.me/joinchat/" in url:
        return True
    return False

def get_force_channel_link(ch):
    if isinstance(ch, dict):
        return ch.get("link", "")
    return ch

def get_force_channel_chat_id(ch):
    if isinstance(ch, dict):
        return ch.get("chat_id")
    return extract_channel_identifier(ch)

def get_force_channel_type(ch):
    if isinstance(ch, dict):
        return ch.get("chat_type", "channel")
    return "channel"

def detect_chat_type(chat_info):
    if chat_info and hasattr(chat_info, 'type'):
        if chat_info.type in ['group', 'supergroup']:
            return "group"
    return "channel"

def clean_html_tags(text):
    text = re.sub(r'<tg-emoji[^>]*>', '', text)
    text = re.sub(r'</tg-emoji>', '', text)
    return text

# ==================== SAFE TELEGRAM SEND/EDIT ====================
def safe_edit(chat_id, text, reply_markup=None, message_id=None):
    clean_text = clean_html_tags(text)
    target_msg_id = message_id if message_id else (menu_message_id.get(chat_id))
    if target_msg_id:
        for _attempt in range(2):
            try:
                return bot.edit_message_text(clean_text, chat_id=chat_id, message_id=target_msg_id, parse_mode="HTML", reply_markup=reply_markup)
            except Exception as e:
                err = str(e).lower()
                if "message is not modified" in err:
                    return None
                if "message to edit not found" in err:
                    break
                if _attempt == 0 and ("timeout" in err or "connection" in err):
                    time.sleep(0.5)
                    continue
                break
    try:
        msg = bot.send_message(chat_id, clean_text, parse_mode="HTML", reply_markup=reply_markup)
        if msg: menu_message_id[chat_id] = msg.message_id
        return msg
    except: return None

def safe_edit_2fa(chat_id, text, reply_markup=None):
    try:
        clean_text = clean_html_tags(text)
        if chat_id in two_fa_message_id:
            return bot.edit_message_text(clean_text, chat_id=chat_id, message_id=two_fa_message_id[chat_id], parse_mode="HTML", reply_markup=reply_markup)
        else:
            msg = bot.send_message(chat_id, clean_text, parse_mode="HTML", reply_markup=reply_markup)
            if msg:
                two_fa_message_id[chat_id] = msg.message_id
            return msg
    except:
        return None

def safe_send(chat_id, text, reply_markup=None, reply_to=None):
    clean_text = clean_html_tags(text)
    for _attempt in range(2):
        try:
            msg = bot.send_message(chat_id, clean_text, parse_mode="HTML", reply_markup=reply_markup, reply_to_message_id=reply_to)
            if msg:
                menu_message_id[chat_id] = msg.message_id
            return msg
        except Exception as e:
            err = str(e).lower()
            if _attempt == 0 and ("timeout" in err or "connection" in err):
                time.sleep(0.5)
                continue
            return None

# ==================== DATA LAYER (with price_per_otp default) ====================
def load_data():
    with data_lock:
        if not os.path.exists(DATA_FILE):
            default_data = {
                "users": [], "services_data": {}, "forward_groups": [-1002309151984],
                "main_otp_link": "https://t.me/EARNINGWITHSIMPLETASK", "watermark": "EARNINGWITHSIMPLETASK",
                "force_join_enabled": False, "force_join_channels": [],
                "otp_counts": {}, "leaderboard": {},
                "balances": {}, "refers": {}, "withdrawals": [],
                "settings": {
                    "cooldown": 1,
                    "num_per_request": 1,
                    "support_link": "https://t.me/UNSTOPPABLEPLUS001",
                    "price_per_otp": 0.001  # NEW DEFAULT
                },
                "panels": {}, "apps": [], "combos": [], "month_sms": 0, "today_sms": 0, "sms_date": "",
                "traffic_log": {}, "extra_admins": [], "banned_users": [],
                "premium_users": [], "premium_type": "lifetime",
                "withdrawal_requests": [],
                "maintenance": False,
                "min_withdraw": 1.0,
                "balance_clean_date": "",
                "balance_clean_amount": 0.0
            }
            with open(DATA_FILE, "w", encoding='utf-8') as f:
                json.dump(default_data, f, indent=4)
            return default_data
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            data = json.load(f)
            # Ensure all keys exist
            if "force_join_enabled" not in data: data["force_join_enabled"] = False
            if "force_join_channels" not in data: data["force_join_channels"] = []
            if "otp_counts" not in data: data["otp_counts"] = {}
            if "leaderboard" not in data: data["leaderboard"] = {}
            if "settings" not in data:
                data["settings"] = {
                    "cooldown": 1,
                    "num_per_request": 1,
                    "support_link": "https://t.me/UNSTOPPABLEPLUS001",
                    "price_per_otp": 0.001
                }
            if "panels" not in data: data["panels"] = {}
            if "apps" not in data: data["apps"] = DEFAULT_APPS
            if "month_sms" not in data: data["month_sms"] = 0
            if "today_sms" not in data: data["today_sms"] = 0
            if "sms_date" not in data: data["sms_date"] = ""
            if "traffic_log" not in data: data["traffic_log"] = {}
            if "extra_admins" not in data: data["extra_admins"] = []
            if "banned_users" not in data: data["banned_users"] = []
            if "premium_users" not in data: data["premium_users"] = []
            if "premium_type" not in data: data["premium_type"] = "lifetime"
            if "balances" not in data: data["balances"] = {}
            if "refers" not in data: data["refers"] = {}
            if "withdrawal_requests" not in data: data["withdrawal_requests"] = []
            if "maintenance" not in data: data["maintenance"] = False
            if "min_withdraw" not in data: data["min_withdraw"] = 1.0
            if "balance_clean_date" not in data: data["balance_clean_date"] = ""
            if "balance_clean_amount" not in data: data["balance_clean_amount"] = 0.0
            st = data.get("settings", {})
            if "num_per_request" not in st or st["num_per_request"] == 0:
                st["num_per_request"] = st.get("premium_num_per_request", 5)
            if "support_link" not in st:
                st["support_link"] = "https://t.me/UNSTOPPABLEPLUS001"
            if "price_per_otp" not in st:  # ENSURE KEY EXISTS
                st["price_per_otp"] = 0.001
            data["settings"] = st
            return data

def save_data(data):
    with data_lock:
        with open(DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4)

# ==================== USER MANAGEMENT ====================
def add_user(user_id):
    data = load_data()
    if user_id not in data.get("users", []):
        data.setdefault("users", []).append(user_id)
        save_data(data)
        total_users = len(data.get("users", []))
        try:
            user_info = bot.get_chat(user_id)
            first_name = html.escape(user_info.first_name or "User")
        except:
            first_name = "User"
        notify_text = (
            f"━━━━━━━━━━━━━━━\n"
            f"《 🆕 <b>NEW USER JOINED</b> 》\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 <b>USER:</b> <a href='tg://user?id={user_id}'>{first_name}</a>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"👥 <b>TOTAL USERS:</b> <code>{total_users}</code>\n"
            f"━━━━━━━━━━━━━━━"
        )
        # Notify ALL main admins
        notify_all_admins(notify_text)

def update_leaderboard(user_id, first_name):
    data = load_data()
    user_id_str = str(user_id)
    if "otp_counts" not in data: data["otp_counts"] = {}
    if "leaderboard" not in data: data["leaderboard"] = {}
    data.setdefault("otp_counts", {}).setdefault(user_id_str, 0)
    data["otp_counts"][user_id_str] += 1
    data.setdefault("leaderboard", {})[user_id_str] = {"name": first_name or f"User{user_id}", "count": data["otp_counts"][user_id_str]}
    save_data(data)

def get_total_ranges():
    data = load_data()
    count = 0
    for panel in data.get("panels", {}).values():
        count += len(panel.get("ranges", {}))
    return count

def get_total_panels():
    data = load_data()
    return len(data.get("panels", {}))

def get_total_apps():
    data = load_data()
    return len(get_app_list(data))

def get_total_available_numbers():
    data = load_data()
    total = 0
    # Count from combos
    for combo in data.get("combos", []):
        nums = combo.get("numbers", [])
        used = combo.get("used_numbers", [])
        total += len([n for n in nums if n not in used])
    # Count from panel ranges
    for panel in data.get("panels", {}).values():
        if panel.get("status") != "active":
            continue
        if panel.get("fetch_type", "manual") == "auto":
            continue
        for rng in panel.get("ranges", {}).values():
            nums = rng.get("numbers", [])
            used = rng.get("used_numbers", [])
            total += len([n for n in nums if n not in used])
    return total

def is_premium_user(user_id):
    return True

def get_premium_badge(user_id):
    return ""

def get_premium_type():
    data = load_data()
    return data.get("premium_type", "lifetime")

# ==================== MATH CAPTCHA SOLVER ====================
def _solve_math_captcha(html_text):
    m = re.search(r'(\d+)\s*[\+]\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
    if m:
        return str(int(m.group(1)) + int(m.group(2)))
    m = re.search(r'(\d+)\s*[-]\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
    if m:
        return str(int(m.group(1)) - int(m.group(2)))
    m = re.search(r'(\d+)\s*[*]\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
    if m:
        return str(int(m.group(1)) * int(m.group(2)))
    m = re.search(r'(\d+)\s*x\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
    if m:
        return str(int(m.group(1)) * int(m.group(2)))
    m = re.search(r'What\s+is\s+(\d+)\s*([+\-*x])\s*(\d+)', html_text, re.IGNORECASE)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        if op == '+': return str(a + b)
        if op == '-': return str(a - b)
        if op in ('*', 'x'): return str(a * b)
    m = re.search(r'(\d+)\s*([+\-*x])\s*(\d+)', html_text)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        if op == '+': return str(a + b)
        if op == '-': return str(a - b)
        if op in ('*', 'x'): return str(a * b)
    return None

# ==================== LOGIN SESSION MANAGEMENT ====================
def do_login_session(panel):
    login_url = panel.get("login_url", "")
    username = panel.get("login_user", "")
    password = panel.get("login_pass", "")
    if not login_url or not username:
        return None
    api_url = panel.get("api_url", "")
    api_fmt = panel.get("api_format", "")
    fmt = PANEL_FORMATS.get(api_fmt, {})
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        is_ints_type = api_fmt in ("ints", "ints_v2", "numberpanel", "sms_panel", "konekta", "timesms", "grand_panel", "pscall")
        if is_ints_type:
            base_url = login_url.rstrip("/")
            for suffix in ["/signin", "/signmein", "/login", "/api/login"]:
                if base_url.endswith(suffix):
                    base_url = base_url[:-len(suffix)]
                    break
            login_ep = fmt.get("login_endpoint", "/signin")
            full_login_url = f"{base_url}{login_ep}"
            try:
                page_res = session.get(full_login_url, timeout=15, allow_redirects=True)
                page_html = page_res.text
            except:
                page_html = ""
            captcha_answer = _solve_math_captcha(page_html) if page_html else None
            login_data = {"username": username, "password": password}
            if captcha_answer:
                login_data["capt"] = captcha_answer
                login_data["captcha"] = captcha_answer
            res = session.post(full_login_url, data=login_data, timeout=15, allow_redirects=True)
            login_success = False
            if res.status_code == 200:
                response_text = res.text.lower()
                if "dashboard" in response_text or "welcome" in response_text or "balance" in response_text:
                    login_success = True
                elif "logout" in response_text or "signout" in response_text:
                    login_success = True
                elif "error" not in response_text and "invalid" not in response_text and "failed" not in response_text:
                    if session.cookies and len(session.cookies) > 0:
                        login_success = True
            elif res.status_code in (301, 302):
                login_success = True
            if not login_success and session.cookies:
                try:
                    check_res = session.get(f"{base_url}/dashboard", timeout=10, allow_redirects=False)
                    if check_res.status_code == 200:
                        login_success = True
                    elif check_res.status_code in (301, 302):
                        loc = check_res.headers.get("location", "").lower()
                        if "login" not in loc and "signin" not in loc:
                            login_success = True
                except:
                    pass
            if login_success:
                token = ""
                try:
                    token_match = re.search(r'token["\']?\s*[:=]\s*["\']([^"\']+)["\']', res.text)
                    if token_match:
                        token = token_match.group(1)
                except:
                    pass
                return {"session": session, "token": token, "cookies": dict(session.cookies)}
            alt_endpoints = ["/signmein", "/signin", "/login"]
            for alt_ep in alt_endpoints:
                if alt_ep == login_ep:
                    continue
                try:
                    alt_url = f"{base_url}{alt_ep}"
                    alt_page = session.get(alt_url, timeout=10, allow_redirects=True)
                    if alt_page.status_code == 200 and "username" in alt_page.text.lower():
                        captcha_alt = _solve_math_captcha(alt_page.text)
                        alt_data = {"username": username, "password": password}
                        if captcha_alt:
                            alt_data["capt"] = captcha_alt
                            alt_data["captcha"] = captcha_alt
                        alt_res = session.post(alt_url, data=alt_data, timeout=15, allow_redirects=True)
                        if session.cookies and len(session.cookies) > 0:
                            alt_text = alt_res.text.lower()
                            if "error" not in alt_text and "invalid" not in alt_text:
                                return {"session": session, "token": "", "cookies": dict(session.cookies)}
                except:
                    continue
        login_data = {"username": username, "password": password}
        res = session.post(login_url, json=login_data, timeout=15)
        if res.status_code == 200:
            try:
                resp_json = res.json()
                token = resp_json.get("token") or resp_json.get("access_token") or resp_json.get("session") or resp_json.get("key", "")
                if token:
                    return {"session": session, "token": token, "cookies": dict(session.cookies)}
            except:
                pass
            if session.cookies:
                return {"session": session, "token": "", "cookies": dict(session.cookies)}
        res2 = session.post(login_url, data={"username": username, "password": password}, timeout=15)
        if res2.status_code == 200:
            if session.cookies:
                return {"session": session, "token": "", "cookies": dict(session.cookies)}
            try:
                resp_json2 = res2.json()
                token2 = resp_json2.get("token") or resp_json2.get("access_token") or resp_json2.get("key", "")
                if token2:
                    return {"session": session, "token": token2, "cookies": {}}
            except:
                pass
    except:
        pass
    return None

def get_login_session(panel_id):
    if panel_id in login_sessions:
        return login_sessions[panel_id]
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return None
    result = do_login_session(panel)
    if result:
        login_sessions[panel_id] = result
    return result

def increment_sms_count():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("sms_date") != today:
        data["sms_date"] = today
        data["today_sms"] = 0
    data["today_sms"] = data.get("today_sms", 0) + 1
    data["month_sms"] = data.get("month_sms", 0) + 1
    save_data(data)

# ==================== FORCE JOIN SYSTEM ====================
def get_force_join_buttons():
    data = load_data()
    channels = data.get("force_join_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        link = ch.get("link")
        chat_id = ch.get("chat_id")
        title = ch.get("title", "Channel")
        ch_type = ch.get("chat_type", "channel")
        label = f"👥 JOIN GROUP" if ch_type == "group" else "📢 JOIN CHANNEL"
        if link:
            markup.add(ibtn(text=label, url=link, style="primary"))
        else:
            try:
                if chat_id:
                    invite = bot.export_chat_invite_link(chat_id)
                    if invite:
                        markup.add(ibtn(text=label, url=invite, style="primary"))
            except:
                pass
    markup.add(ibtn(text="✅ JOINED ✅", callback_data="check_join", style="success"))
    return markup

def show_force_join_message(chat_id, message_id=None, reply_to=None):
    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 ⚠️ <b>ACCESS DENIED</b> 》\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📢 <b>JOIN OUR CHANNELS TO USE THIS BOT</b>\n\n"
        f"<b>CLICK JOINED AFTER JOINING</b>"
    )
    markup = get_force_join_buttons()
    if message_id:
        safe_edit(chat_id, text, markup, message_id)
    else:
        safe_send(chat_id, text, markup, reply_to=reply_to)

# ==================== MAINTENANCE ====================
def is_maintenance_mode():
    data = load_data()
    return data.get("maintenance", False)

def broadcast_maintenance_message(chat_id, enabled):
    data = load_data()
    users = data.get("users", [])
    if enabled:
        msg = "🔧 <b>MAINTENANCE MODE ACTIVATED</b>\n\nThe bot is currently under maintenance. Please wait until it's back online."
    else:
        msg = "✅ <b>MAINTENANCE MODE DEACTIVATED</b>\n\nThe bot is now fully operational. You can continue using it."
    success = 0
    for u in users:
        try:
            safe_send(u, msg)
            success += 1
            time.sleep(0.05)
        except:
            pass
    safe_send(chat_id, f"📢 Broadcast sent to {success} users.")

def toggle_maintenance(chat_id, enabled):
    data = load_data()
    data["maintenance"] = enabled
    save_data(data)
    broadcast_maintenance_message(chat_id, enabled)

# ==================== MAIN MENU (UPDATED) ====================
def get_main_menu(user_id):
    data = load_data()
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(rbtn("📱 GET NUMBER", "primary"), rbtn("📊 TRAFFIC", "success"))
    markup.add(rbtn("🔐 2FA ONLINE", "danger"), rbtn("🏆 LEADERBOARD", "primary"))
    markup.add(rbtn("📈 STOCK INFO", "success"), rbtn("📩 SUPPORT", "primary"))
    markup.add(rbtn("👥 REFERRALS", "primary"), rbtn("💳 WITHDRAW", "danger"))
    markup.add(rbtn("📱 MY NUMBERS", "primary"), rbtn("📊 MY STATS", "success"))
    markup.add(rbtn("💳 WD HISTORY", "danger"), rbtn("❓ HELP", "primary"))
    if is_admin(user_id):
        markup.add(rbtn("⚙️ ADMIN PANEL", "danger"))
    return markup

def get_2fa_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(ibtn("🔐 GENERATE 2FA CODE", callback_data="2fa_generate", style="primary"),
               ibtn("🔙 BACK TO MAIN MENU", callback_data="2fa_back", style="danger"))
    return markup

def get_leaderboard_menu():
    markup = InlineKeyboardMarkup()
    markup.add(ibtn("🔄 REFRESH", callback_data="refresh_leaderboard", style="primary"))
    markup.add(ibtn("❌ CLOSE", callback_data="close_menu", style="danger"))
    return markup

def get_admin_menu(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("📋 MANAGE PANELS", callback_data="admin_manage_panels", style="success"),
               ibtn("🔥 COMBO", callback_data="admin_manage_apps", style="danger"))
    markup.add(ibtn("⚙️ SYSTEM", callback_data="admin_system", style="danger"),
               ibtn("👤 USER VIEW", callback_data="admin_user_view", style="primary"))
    markup.add(ibtn("📢 BROADCAST", callback_data="admin_broadcast", style="danger"),
               ibtn("🔗 OTP GROUPS", callback_data="admin_group_settings", style="primary"))
    markup.add(ibtn("📣 FORCE JOIN", callback_data="admin_force_join", style="success"),
               ibtn("💎 WATERMARK", callback_data="admin_set_watermark", style="primary"))
    markup.add(ibtn("💳 MANAGE BALANCE", callback_data="admin_manage_balances", style="success"),
               ibtn("➕ ADD BALANCE", callback_data="admin_add_balance", style="success"))
    data = load_data()
    maint_status = "🟢 ENABLED" if data.get("maintenance") else "🔴 DISABLED"
    maint_style = "danger" if data.get("maintenance") else "success"
    markup.add(ibtn(f"🔧 MAINTENANCE: {maint_status}", callback_data="admin_maintenance", style=maint_style))
    markup.add(ibtn("💲 SET MIN WITHDRAW", callback_data="admin_set_min_withdraw", style="success"),
               ibtn("🧹 CLEAN BALANCES", callback_data="admin_clean_balances", style="danger"))
    markup.add(ibtn("📊 WITHDRAW STATS", callback_data="admin_withdraw_stats", style="primary"),
               ibtn("🤖 VIEW MEMBER BOT", callback_data="admin_view_member_bot", style="primary"))
    markup.add(ibtn("📈 FULL STATS", callback_data="admin_stats", style="success"),
               ibtn("👥 ALL USERS", callback_data="admin_all_users", style="primary"))
    markup.add(ibtn("📦 STOCK SUMMARY", callback_data="admin_stock_summary", style="success"),
               ibtn("📱 ALL NUMBERS", callback_data="admin_all_numbers", style="primary"))
    markup.add(ibtn("🚫 BLACKLIST", callback_data="admin_blacklist", style="danger"),
               ibtn("🛡️ ANTI-SPAM", callback_data="admin_anti_spam", style="primary"))
    if is_main_admin(user_id):
        markup.add(ibtn("👮 MANAGE ADMIN", callback_data="admin_manage_admins", style="danger"))
    markup.add(ibtn("❌ CLOSE", callback_data="close_menu", style="danger"))
    return markup

def get_force_join_menu():
    data = load_data()
    is_enabled = data.get("force_join_enabled", False)
    channels = data.get("force_join_channels", [])
    status_text = "🟢 ENABLED" if is_enabled else "🔴 DISABLED"
    status_style = "success" if is_enabled else "danger"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(ibtn(f"TOGGLE: {status_text}", callback_data="toggle_force_join", style=status_style))
    color_cycle = ["primary", "success", "danger"]
    for idx, ch in enumerate(channels):
        display = ch.get("title", str(ch.get("chat_id", "Unknown")))
        ch_type_str = ch.get("chat_type", "channel")
        type_icon = "👥" if ch_type_str == "group" else "📢"
        markup.add(ibtn(f"❌ {type_icon} {display}", callback_data=f"delfjc_{idx}", style=color_cycle[idx % 3]))
    markup.add(ibtn("➕ ADD CHANNEL/GROUP", callback_data="add_fjc", style="primary"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="success"))
    return markup

def get_group_settings_menu():
    data = load_data()
    markup = InlineKeyboardMarkup(row_width=1)
    otp_link = data.get("main_otp_link", "")
    markup.add(ibtn("🔗 SET OTP GROUP LINK", callback_data="set_main_otp_link", style="primary"))
    if otp_link and otp_link != "https://t.me/":
        markup.add(ibtn("🗑️ REMOVE OTP LINK", callback_data="del_main_otp_link", style="danger"))
    markup.add(ibtn("➕ ADD FORWARD GROUP", callback_data="add_fwd_group", style="success"))
    fwd_groups = data.get("forward_groups", [])
    if fwd_groups:
        color_cycle_grp = ["primary", "success", "danger"]
        for g_idx, grp in enumerate(fwd_groups):
            btn_count = len(grp.get('buttons', []))
            markup.add(ibtn(f"⚙️ {grp['chat_id']} [{btn_count} BTNS]", callback_data=f"editgrp_{grp['chat_id']}", style=color_cycle_grp[g_idx % 3]))
    if fwd_groups:
        markup.add(ibtn("📤 SEND TEST MESSAGE TO ALL GROUPS", callback_data="admin_send_test_msg", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
    return markup

def get_admin_system_menu():
    data = load_data()
    st = data.get("settings", {})
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn(f"⏳ COOLDOWN: {st.get('cooldown', 60)}s", callback_data="sys_cooldown", style="danger"),
               ibtn(f"📱 NUM/REQ: {st.get('num_per_request', 5)}", callback_data="sys_num_per_req", style="success"))
    markup.add(ibtn("🛠️ SUPPORT LINK", callback_data="sys_support", style="primary"),
               ibtn(f"💲 PRICE: ${st.get('price_per_otp', 0.001):.4f}", callback_data="sys_price", style="success"))
    markup.add(ibtn("🛠️ SERVICES", callback_data="admin_services", style="primary"),
               ibtn(f"📱 MAX NUM: {st.get('max_numbers', 10)}", callback_data="sys_max_numbers", style="success"))
    markup.add(ibtn("🔧 MAINTENANCE MSG", callback_data="admin_maint_msg", style="danger"),
               ibtn("📡 OTP MONITOR", callback_data="admin_otp_monitor", style="primary"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="success"))
    return markup
    # ============================================
#  PART 4 - MAIN DISPLAY FUNCTIONS
# ============================================


# ============================================
#  ADDITIONAL USER & ADMIN FUNCTIONS (145+ FEATURES)
# ============================================

# --- HELPER: Get emoji for country ---



# ============================================
#  ADDITIONAL USER & ADMIN FUNCTIONS (145+ FEATURES)
# ============================================

# --- USER: VIEW MY NUMBERS ---
def show_my_numbers(chat_id):
    data = load_data()
    sessions = data.get("number_session", {})
    my_sessions = {k: v for k, v in sessions.items() if v.get("user_id") == chat_id}
    if not my_sessions:
        markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
        safe_send(chat_id, "━━━━━━━━━━━━━━━\n《 📱 <b>MY NUMBERS</b> 》\n━━━━━━━━━━━━━━━\n\n<b>NO NUMBERS ASSIGNED YET</b>\n<b>Use GET NUMBER to request one!</b>\n━━━━━━━━━━━━━━━", markup)
        return
    text = "━━━━━━━━━━━━━━━\n《 📱 <b>MY NUMBERS</b> 》\n━━━━━━━━━━━━━━━\n\n"
    for sid, sess in list(my_sessions.items())[-10:]:
        number = sess.get("number", "?")
        app = sess.get("app", "?")
        status = sess.get("status", "?")
        otp = sess.get("otp_code", "")
        status_emoji = "✅" if status == "completed" else "⏳" if status in ("polling", "awaiting_manual_otp") else "📝"
        text += f"{status_emoji} <code>{number}</code> | {emo(app)} {app.upper()}\n"
        if otp:
            text += f"   🔑 OTP: <code>{otp}</code>\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
    safe_send(chat_id, text, markup)

# --- USER: VIEW STATS ---
def show_my_stats(chat_id):
    data = load_data()
    uid = str(chat_id)
    bal = data.get("balances", {}).get(uid, 0.0)
    otps = data.get("otp_counts", {}).get(uid, 0)
    referrals = len(data.get("refers", {}).get(uid, []))
    sessions = data.get("number_session", {})
    my_sessions = {k: v for k, v in sessions.items() if v.get("user_id") == chat_id}
    total_numbers = len(my_sessions)
    completed = len([v for v in my_sessions.values() if v.get("status") == "completed"])
    wd = [w for w in data.get("withdrawal_requests", []) if w.get("user_id") == chat_id]
    total_withdrawn = sum(w.get("amount", 0) for w in wd if w.get("status") == "approved")
    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 📊 <b>MY STATS</b> 》\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>BALANCE:</b> ${bal:.4f}\n"
        f"🔑 <b>OTPs RECEIVED:</b> {otps}\n"
        f"👥 <b>REFERRALS:</b> {referrals}\n"
        f"📱 <b>NUMBERS USED:</b> {total_numbers}\n"
        f"✅ <b>COMPLETED:</b> {completed}\n"
        f"💳 <b>TOTAL WITHDRAWN:</b> ${total_withdrawn:.2f}\n"
        f"━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
    safe_send(chat_id, text, markup)

# --- USER: HELP MENU ---
def show_help_menu(chat_id):
    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 ❓ <b>HELP MENU</b> 》\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>GET NUMBER</b> — Request phone for OTP\n"
        f"📊 <b>TRAFFIC</b> — View network info\n"
        f"🔐 <b>2FA ONLINE</b> — Generate 2FA codes\n"
        f"🏆 <b>LEADERBOARD</b> — Top earning users\n"
        f"📈 <b>STOCK INFO</b> — Check number stock\n"
        f"📩 <b>SUPPORT</b> — Live chat with admin\n"
        f"👥 <b>REFERRALS</b> — Share & earn $0.001/friend\n"
        f"💳 <b>WITHDRAW</b> — Request withdrawal\n"
        f"📱 <b>MY NUMBERS</b> — View assigned numbers\n"
        f"📊 <b>MY STATS</b> — Your personal stats\n"
        f"💳 <b>WD HISTORY</b> — Past withdrawals\n"
        f"━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
    safe_send(chat_id, text, markup)

# --- USER: WITHDRAWAL HISTORY ---
def show_withdrawal_history(chat_id):
    data = load_data()
    wds = [w for w in data.get("withdrawal_requests", []) if w.get("user_id") == chat_id]
    if not wds:
        markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
        safe_send(chat_id, "━━━━━━━━━━━━━━━\n《 💳 <b>WITHDRAWAL HISTORY</b> 》\n━━━━━━━━━━━━━━━\n\n<b>NO WITHDRAWALS YET</b>\n━━━━━━━━━━━━━━━", markup)
        return
    text = "━━━━━━━━━━━━━━━\n《 💳 <b>WITHDRAWAL HISTORY</b> 》\n━━━━━━━━━━━━━━━\n\n"
    for w in wds[-10:]:
        wd_id = w.get("id", "?")
        amt = w.get("amount", 0)
        status = w.get("status", "?")
        method = w.get("payment_method", "?").upper()
        ts = w.get("timestamp", "")[:10]
        icon = "⏳" if status == "pending" else "✅" if status == "approved" else "❌"
        text += f"{icon} <code>{wd_id}</code> | ${amt:.2f} | {method} | {ts}\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: VIEW ALL USERS ---
def show_all_users(chat_id):
    data = load_data()
    users = data.get("users", [])
    if not users:
        safe_send(chat_id, "❌ <b>NO USERS REGISTERED</b>")
        return
    text = f"━━━━━━━━━━━━━━━\n《 👥 <b>ALL USERS</b> ({len(users)}) 》\n━━━━━━━━━━━━━━━\n\n"
    for uid in users[:30]:
        bal = data.get("balances", {}).get(str(uid), 0.0)
        otps = data.get("otp_counts", {}).get(str(uid), 0)
        banned = "🚫" if uid in data.get("banned_users", []) else ""
        text += f"🆔 <code>{uid}</code> | 💰${bal:.4f} | 🔑{otps} {banned}\n"
    if len(users) > 30:
        text += f"\n... and {len(users) - 30} more"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("🔍 SEARCH USER", callback_data="admin_search_user", style="primary"),
               ibtn("📊 USER STATS", callback_data="admin_user_statistics", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: USER STATISTICS ---
def show_user_statistics(chat_id):
    data = load_data()
    users = data.get("users", [])
    banned = data.get("banned_users", [])
    otp_users = data.get("otp_counts", {})
    total_bal = sum(data.get("balances", {}).values())
    today = datetime.now().strftime("%Y-%m-%d")
    today_otps = sum(1 for sid, sess in data.get("number_session", {}).items() if sess.get("timestamp", "").startswith(today))
    text = (
        f"━━━━━━━━━━━━━━━\n《 📊 <b>USER STATISTICS</b> 》\n━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Total Users:</b> {len(users)}\n"
        f"🚫 <b>Banned:</b> {len(banned)}\n"
        f"✅ <b>Active OTP Users:</b> {len(otp_users)}\n"
        f"💰 <b>Total Balance:</b> ${total_bal:.4f}\n"
        f"📱 <b>Today's OTPs:</b> {today_otps}\n"
        f"━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_user_view", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: SEARCH USER ---
def show_search_user(chat_id):
    user_states[chat_id] = {"state": "admin_search_user"}
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_user_view", style="primary"))
    safe_send(chat_id, "🔍 <b>SEARCH USER</b>\nEnter User ID or @username\n\n❌ /cancel to cancel", markup)

# --- ADMIN: SEARCH NUMBERS ---
def show_search_numbers(chat_id):
    user_states[chat_id] = {"state": "admin_search_numbers"}
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_manage_panels", style="primary"))
    safe_send(chat_id, "🔍 <b>SEARCH NUMBERS</b>\nEnter phone number to search\n\n❌ /cancel to cancel", markup)

# --- ADMIN: VIEW ALL NUMBERS ---
def show_all_numbers(chat_id):
    data = load_data()
    all_nums = []
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            for n in rng.get("numbers", []):
                status = "✅ Available" if n not in rng.get("used_numbers", []) else "🔒 Used"
                all_nums.append((n, rng.get("app", "?"), rng.get("name", "?"), status))
    if not all_nums:
        safe_send(chat_id, "❌ <b>NO NUMBERS IN SYSTEM</b>")
        return
    text = f"━━━━━━━━━━━━━━━\n《 📱 <b>ALL NUMBERS</b> ({len(all_nums)}) 》\n━━━━━━━━━━━━━━━\n\n"
    for n, app, country, status in all_nums[:20]:
        text += f"<code>{n}</code> | {emo(app)} {app} | {get_country_flag(country)} {country} | {status}\n"
    if len(all_nums) > 20:
        text += f"\n... and {len(all_nums) - 20} more"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("🔍 SEARCH", callback_data="admin_search_numbers", style="primary"),
               ibtn("📊 STOCK", callback_data="admin_stock_summary", style="success"))
    markup.add(ibtn("⬆️ EXPORT CSV", callback_data="admin_export_numbers", style="primary"),
               ibtn("♻️ EXPIRE", callback_data="admin_expire_numbers", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="admin_manage_panels", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: VIEW AVAILABLE NUMBERS ---
def show_available_numbers(chat_id):
    data = load_data()
    avail = []
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            for n in rng.get("numbers", []):
                if n not in rng.get("used_numbers", []):
                    avail.append((n, rng.get("app", "?"), rng.get("name", "?")))
    text = f"━━━━━━━━━━━━━━━\n《 ✅ <b>AVAILABLE</b> ({len(avail)}) 》\n━━━━━━━━━━━━━━━\n\n"
    for n, app, country in avail[:20]:
        text += f"<code>{n}</code> | {emo(app)} {app} | {get_country_flag(country)} {country}\n"
    if len(avail) > 20:
        text += f"\n... and {len(avail) - 20} more"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_manage_panels", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: VIEW RENTED NUMBERS ---
def show_rented_numbers(chat_id):
    data = load_data()
    rented = []
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            for n in rng.get("numbers", []):
                if n in rng.get("used_numbers", []):
                    rented.append((n, rng.get("app", "?"), rng.get("name", "?")))
    text = f"━━━━━━━━━━━━━━━\n《 🔒 <b>RENTED</b> ({len(rented)}) 》\n━━━━━━━━━━━━━━━\n\n"
    for n, app, country in rented[:20]:
        text += f"<code>{n}</code> | {emo(app)} {app} | {get_country_flag(country)} {country}\n"
    if len(rented) > 20:
        text += f"\n... and {len(rented) - 20} more"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup()
    markup.add(ibtn("♻️ RELEASE ALL", callback_data="release_all_rented", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="admin_manage_panels", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: STOCK SUMMARY ---
def show_stock_summary(chat_id):
    data = load_data()
    stock = {}
    total_avail = 0
    total_used = 0
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            app = rng.get("app", "Unknown")
            country = rng.get("name", "Unknown")
            nums = rng.get("numbers", [])
            used = rng.get("used_numbers", [])
            avail = len([n for n in nums if n not in used])
            key = f"{app}|{country}"
            if key not in stock:
                stock[key] = {"app": app, "country": country, "available": 0, "total": 0}
            stock[key]["available"] += avail
            stock[key]["total"] += len(nums)
            total_avail += avail
            total_used += len(used)
    for combo in data.get("combos", []):
        nums = combo.get("numbers", [])
        used = combo.get("used_numbers", [])
        avail = len([n for n in nums if n not in used])
        total_avail += avail
        total_used += len(used)
    text = f"━━━━━━━━━━━━━━━\n《 📦 <b>STOCK SUMMARY</b> 》\n━━━━━━━━━━━━━━━\n\n"
    text += f"📊 <b>AVAILABLE:</b> {total_avail}\n"
    text += f"🔒 <b>RENTED:</b> {total_used}\n\n"
    for key, info in sorted(stock.items()):
        text += f"📱 {emo(info['app'])} {info['app']} | {get_country_flag(info['country'])} {info['country']} — {info['available']}/{info['total']}\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("📱 ALL", callback_data="admin_all_numbers", style="primary"),
               ibtn("✅ AVAILABLE", callback_data="admin_available_numbers", style="success"))
    markup.add(ibtn("🔒 RENTED", callback_data="admin_rented_numbers", style="danger"),
               ibtn("🔍 SEARCH", callback_data="admin_search_numbers", style="primary"))
    markup.add(ibtn("⬆️ EXPORT CSV", callback_data="admin_export_numbers", style="success"),
               ibtn("♻️ EXPIRE", callback_data="admin_expire_numbers", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="admin_manage_panels", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: EXPORT NUMBERS CSV ---
def show_export_numbers(chat_id):
    data = load_data()
    lines = ["number,app,country,status"]
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            for n in rng.get("numbers", []):
                status = "available" if n not in rng.get("used_numbers", []) else "used"
                lines.append(f"{n},{rng.get('app','')},{rng.get('name','')},{status}")
    if len(lines) <= 1:
        safe_send(chat_id, "❌ <b>NO NUMBERS TO EXPORT</b>")
        return
    import io
    csv_text = "\n".join(lines)
    file_bytes = io.BytesIO(csv_text.encode("utf-8"))
    file_bytes.name = "numbers_export.csv"
    try:
        bot.send_document(chat_id, file_bytes, caption=f"📊 <b>EXPORTED {len(lines)-1} NUMBERS</b>", parse_mode="HTML")
    except Exception as e:
        safe_send(chat_id, f"❌ <b>EXPORT FAILED:</b> {html.escape(str(e))}")

# --- ADMIN: EXPIRE OLD NUMBERS ---
def show_expire_numbers(chat_id):
    data = load_data()
    expired = 0
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            used = rng.get("used_numbers", [])
            expired += len(used)
            rng["used_numbers"] = []
    save_data(data)
    safe_send(chat_id, f"✅ <b>EXPIRED {expired} NUMBERS</b>")

# --- ADMIN: RELEASE ALL RENTED ---
def release_all_rented(chat_id):
    data = load_data()
    released = 0
    for pid, panel in data.get("panels", {}).items():
        for rid, rng in panel.get("ranges", {}).items():
            used = rng.get("used_numbers", [])
            released += len(used)
            rng["used_numbers"] = []
    save_data(data)
    safe_send(chat_id, f"✅ <b>RELEASED {released} NUMBERS</b>")

# --- ADMIN: WITHDRAWAL HISTORY ---
def show_admin_withdrawal_history(chat_id):
    data = load_data()
    wds = data.get("withdrawal_requests", [])
    if not wds:
        safe_send(chat_id, "✅ <b>NO WITHDRAWAL HISTORY</b>")
        return
    text = f"━━━━━━━━━━━━━━━\n《 💳 <b>WD HISTORY</b> ({len(wds)}) 》\n━━━━━━━━━━━━━━━\n\n"
    for w in wds[-15:]:
        wd_id = w.get("id", "?")
        uid = w.get("user_id", "?")
        amt = w.get("amount", 0)
        status = w.get("status", "?")
        method = w.get("payment_method", "?").upper()
        icon = "⏳" if status == "pending" else "✅" if status == "approved" else "❌"
        text += f"{icon} <code>{wd_id}</code> | 👤<code>{uid}</code> | ${amt:.2f} | {method}\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_withdraw_stats", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: TOTAL BALANCES ---
def show_total_balances(chat_id):
    data = load_data()
    balances = data.get("balances", {})
    total = sum(balances.values())
    positive = sum(b for b in balances.values() if b > 0)
    zero = sum(1 for b in balances.values() if b == 0)
    text = (
        f"━━━━━━━━━━━━━━━\n《 💰 <b>TOTAL BALANCES</b> 》\n━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Sum All:</b> ${total:.4f}\n"
        f"💵 <b>Positive:</b> ${positive:.4f}\n"
        f"👥 <b>With Balance:</b> {len([b for b in balances.values() if b > 0])}\n"
        f"0️⃣ <b>Zero Balance:</b> {zero}\n"
        f"━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: ADD ALL BONUS ---
def show_add_all_bonus(chat_id):
    user_states[chat_id] = {"state": "admin_add_all_bonus"}
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
    safe_send(chat_id, "💰 <b>ADD BONUS TO ALL USERS</b>\nEnter amount per user (USD)\n<i>e.g. 0.01, 0.10</i>\n\n❌ /cancel to cancel", markup)

# --- ADMIN: DEDUCT ALL FEE ---
def show_deduct_all_fee(chat_id):
    user_states[chat_id] = {"state": "admin_deduct_all_fee"}
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
    safe_send(chat_id, "💸 <b>DEDUCT FEE FROM ALL USERS</b>\nEnter amount per user (USD)\n<i>e.g. 0.01, 0.10</i>\n\n❌ /cancel to cancel", markup)

# --- ADMIN: SERVICES MANAGEMENT ---
def show_services_menu(chat_id):
    data = load_data()
    services = data.get("services", [])
    text = "━━━━━━━━━━━━━━━\n《 🛠️ <b>SERVICES</b> 》\n━━━━━━━━━━━━━━━\n\n"
    if services:
        for svc in services:
            name = svc.get("name", "?")
            price = svc.get("price", data.get("settings", {}).get("price_per_otp", 0.001))
            text += f"📱 {emo(name)} <b>{name}</b> — ${price:.4f}/OTP\n"
    else:
        text += "<b>No custom services.</b>\nDefault pricing applies.\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("➕ ADD", callback_data="admin_add_service", style="success"),
               ibtn("❌ REMOVE", callback_data="admin_remove_service", style="danger"))
    markup.add(ibtn("✏️ EDIT PRICE", callback_data="admin_edit_service_price", style="primary"),
               ibtn("💲 PRICE ALL", callback_data="admin_set_price_all", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="admin_system", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: BROADCAST TARGETED ---
def show_broadcast_targeted(chat_id):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(ibtn("📢 SEND TO ALL", callback_data="broadcast_all", style="primary"))
    markup.add(ibtn("🟢 ACTIVE ONLY", callback_data="broadcast_active", style="success"))
    markup.add(ibtn("💬 SPECIFIC USER", callback_data="broadcast_specific", style="primary"))
    markup.add(ibtn("💰 BY BALANCE", callback_data="broadcast_by_balance", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
    safe_send(chat_id, "━━━━━━━━━━━━━━━\n《 📢 <b>BROADCAST</b> 》\n━━━━━━━━━━━━━━━\n\n<b>SELECT TARGET:</b>", markup)

# --- ADMIN: FULL STATS ---
def show_full_stats(chat_id):
    data = load_data()
    users = data.get("users", [])
    balances = data.get("balances", {})
    otp_counts = data.get("otp_counts", {})
    wds = data.get("withdrawal_requests", {})
    today = datetime.now().strftime("%Y-%m-%d")
    today_sms = data.get("today_sms", 0)
    month_sms = data.get("month_sms", 0)
    total_balance = sum(balances.values())
    pending_wd = sum(1 for w in data.get("withdrawal_requests", []) if w.get("status") == "pending")
    approved_wd = sum(1 for w in data.get("withdrawal_requests", []) if w.get("status") == "approved")
    total_wd_amount = sum(w.get("amount", 0) for w in data.get("withdrawal_requests", []) if w.get("status") == "approved")
    text = (
        f"┌─────────────────────┐\n"
        f"│  📊 <b>FULL SYSTEM STATS</b>  │\n"
        f"└─────────────────────┘\n\n"
        f"👥 <b>Users:</b> {len(users)}\n"
        f"✅ <b>OTP Active:</b> {len(otp_counts)}\n"
        f"📋 <b>Panels:</b> {sum(1 for p in data.get('panels', {}).values() if p.get('status') == 'active')}\n"
        f"💰 <b>Total Balance:</b> ${total_balance:.4f}\n"
        f"📱 <b>Today SMS:</b> {today_sms}\n"
        f"📅 <b>Month SMS:</b> {month_sms}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💳 <b>Withdrawals:</b>\n"
        f"  ⏳ Pending: {pending_wd}\n"
        f"  ✅ Approved: {approved_wd}\n"
        f"  💵 Total Paid: ${total_wd_amount:.2f}\n"
        f"━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("📅 TODAY", callback_data="stat_today", style="primary"),
               ibtn("📈 TOP USERS", callback_data="show_leaderboard", style="success"))
    markup.add(ibtn("📊 STOCK", callback_data="admin_stock_summary", style="primary"),
               ibtn("👥 ALL USERS", callback_data="admin_all_users", style="success"))
    markup.add(ibtn("⬆️ EXPORT", callback_data="stat_export", style="primary"),
               ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: TODAY STATS ---
def show_today_stats(chat_id):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_otps = sum(1 for sid, sess in data.get("number_session", {}).items() if sess.get("timestamp", "").startswith(today))
    today_wds = [w for w in data.get("withdrawal_requests", []) if w.get("timestamp", "").startswith(today)]
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_stats", style="primary"))
    safe_send(chat_id,
        f"━━━━━━━━━━━━━━━\n📅 <b>TODAY ({today})</b>\n━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>OTPs:</b> {today_otps}\n"
        f"💳 <b>Withdrawals:</b> {len(today_wds)}\n"
        f"━━━━━━━━━━━━━━━", markup)

# --- ADMIN: EXPORT STATS CSV ---
def show_export_stats(chat_id):
    data = load_data()
    lines = ["user_id,balance,otps,referrals,total_withdrawn"]
    for uid in data.get("users", []):
        bal = data.get("balances", {}).get(str(uid), 0.0)
        otps = data.get("otp_counts", {}).get(str(uid), 0)
        refs = len(data.get("refers", {}).get(str(uid), []))
        wds = [w for w in data.get("withdrawal_requests", []) if w.get("user_id") == uid]
        approved_wds = sum(w.get("amount", 0) for w in wds if w.get("status") == "approved")
        lines.append(f"{uid},{bal:.4f},{otps},{refs},{approved_wds:.2f}")
    import io
    csv_text = "\n".join(lines)
    file_bytes = io.BytesIO(csv_text.encode("utf-8"))
    file_bytes.name = "user_stats_export.csv"
    try:
        bot.send_document(chat_id, file_bytes, caption="📊 <b>USER STATS EXPORT</b>", parse_mode="HTML")
    except Exception as e:
        safe_send(chat_id, f"❌ <b>EXPORT FAILED:</b> {html.escape(str(e))}")

# --- ADMIN: BLACKLIST ---
def show_blacklist_menu(chat_id):
    data = load_data()
    blacklist = data.get("blacklist", [])
    text = f"━━━━━━━━━━━━━━━\n《 🚫 <b>BLACKLIST</b> ({len(blacklist)}) 》\n━━━━━━━━━━━━━━━\n\n"
    if blacklist:
        for uid in blacklist[:20]:
            text += f"🚫 <code>{uid}</code>\n"
    else:
        text += "<b>Blacklist empty.</b>\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("➕ ADD", callback_data="admin_blacklist_add", style="danger"),
               ibtn("♻️ REMOVE", callback_data="admin_blacklist_remove", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
    safe_send(chat_id, text, markup)

# --- ADMIN: ANTI-SPAM TOGGLE ---
def show_anti_spam_toggle(chat_id):
    data = load_data()
    enabled = data.get("anti_spam", False)
    data["anti_spam"] = not enabled
    save_data(data)
    status = "✅ ENABLED" if data["anti_spam"] else "❌ DISABLED"
    safe_send(chat_id, f"🛡️ <b>ANTI-SPAM:</b> {status}")
    show_admin_panel(chat_id)

# --- ADMIN: MAINTENANCE MESSAGE ---
def show_set_maintenance_msg(chat_id):
    data = load_data()
    current = data.get("maintenance_msg", "Bot is under maintenance. Please try again later.")
    user_states[chat_id] = {"state": "set_maintenance_msg"}
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_system", style="primary"))
    safe_send(chat_id, f"🔧 <b>CURRENT MSG:</b>\n<i>{html.escape(current)}</i>\n\nEnter new message:", markup)

# --- ADMIN: TOGGLE OTP MONITORING ---
def toggle_otp_monitoring(chat_id):
    data = load_data()
    data["otp_monitoring_enabled"] = not data.get("otp_monitoring_enabled", True)
    save_data(data)
    status = "✅ ENABLED" if data["otp_monitoring_enabled"] else "❌ DISABLED"
    safe_send(chat_id, f"📡 <b>OTP MONITORING:</b> {status}")
    show_admin_system(chat_id)

# --- ADMIN: TEST OTP MONITORING ---
def test_otp_monitoring(chat_id):
    data = load_data()
    otp_link = data.get("main_otp_link", "")
    fwd = data.get("forward_groups", [])
    scraped = {pid: p for pid, p in data.get("panels", {}).items()
               if p.get("status") == "active" and p.get("type") == "scraped"}
    text = (
        f"━━━━━━━━━━━━━━━\n📡 <b>OTP MONITOR STATUS</b>\n━━━━━━━━━━━━━━━\n\n"
        f"🔗 <b>OTP Link:</b> <code>{html.escape(otp_link or 'Not set')}</code>\n"
        f"📢 <b>Forward Groups:</b> {len(fwd)}\n"
        f"🤖 <b>Scraped Panels:</b> {len(scraped)}\n"
    )
    if scraped:
        text += "\n<b>Panels:</b>\n"
        for pid, panel in scraped.items():
            text += f"  • {html.escape(panel.get('name', pid))} ({panel.get('panel_type', '?')})\n"
    if not fwd:
        text += "\n⚠️ <b>NO FORWARD GROUPS!</b> OTPs won't be sent!\n"
    text += "\n━━━━━━━━━━━━━━━"
    safe_send(chat_id, text)


def show_main_menu(chat_id, first_name=None, reply_to=None):
    if not first_name:
        try: first_name = bot.get_chat(chat_id).first_name
        except: first_name = "VIP User"
    data = load_data()
    watermark = data.get("watermark", "VERTEX OTP")
    balance = data.get("balances", {}).get(str(chat_id), 0.0)
    text = (
        f"┌─────────────────────┐\n"
        f"│  👑 <b>NUMBER BOT</b>  │\n"
        f"└─────────────────────┘\n"
        f"\n"
        f"👋 <b>WELCOME,</b> <a href='tg://user?id={chat_id}'>{html.escape(first_name)}</a>!\n"
        f"💰 <b>BALANCE:</b> ${balance:.4f}\n\n"
        f"📱 <b>GET NUMBER</b> — OTP SERVICE\n"
        f"📊 <b>TRAFFIC</b> — LIVE NETWORK\n"
        f"🔐 <b>2FA ONLINE</b> — AUTHENTICATOR\n"
        f"🏆 <b>LEADERBOARD</b> — TOP USERS\n"
        f"📈 <b>STOCK INFO</b> — CHECK STOCK\n"
        f"📩 <b>SUPPORT</b> — LIVE CHAT WITH ADMIN\n"
        f"👥 <b>REFERRALS</b> — VIEW & EARN\n"
        f"💳 <b>WITHDRAW</b> — REQUEST WITHDRAWAL\n"
        f"━━━━━━━━━━━━━━━\n"
        f"永 <b>POWERED BY {html.escape(watermark)}</b> 🔴"
    )
    msg = safe_send(chat_id, text, get_main_menu(chat_id), reply_to=reply_to)
    if msg: menu_message_id[chat_id] = msg.message_id

def show_referrals(chat_id):
    data = load_data()
    user_id = chat_id
    referrals = data.get("refers", {}).get(str(user_id), [])
    balance = data.get("balances", {}).get(str(user_id), 0.0)
    total_earned = len(referrals) * 0.001  # CHANGED: 0.10 -> 0.001
    try:
        bot_me = bot.get_me()
        bot_username = bot_me.username
    except:
        bot_username = "Anon_MatrixV3_bot"
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    text = (
        f"🔗 <b>Your Referral Link</b>\n\n"
        f"{link}\n\n"
        f"📊 <b>Stats</b>\n"
        f"💰 Balance: ${balance:.4f}\n"
        f"👥 Referrals: {len(referrals)}\n"
        f"💵 Total Earned: ${total_earned:.4f}\n\n"
        f"Share this link to earn $0.001 per new user!"  # CHANGED
    )
    markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
    safe_send(chat_id, text, markup)

def show_user_services(chat_id):
    """Show services (apps + combos) in compact format like screenshots."""
    data = load_data()
    st = data.get("settings", {})
    price = st.get("price_per_otp", 0.001)
    data_wm = data.get("watermark", "VERTEX OTP")

    # Collect services from combos only
    all_services = []
    seen = set()
    for combo in data.get("combos", []):
        name = combo.get("name", "")
        if name and name.upper() not in seen:
            avail = len(combo.get("numbers", [])) - len(combo.get("used_numbers", []))
            if avail > 0:
                all_services.append({"name": name, "count": avail, "type": "combo"})
                seen.add(name.upper())

    markup = InlineKeyboardMarkup(row_width=1)
    if all_services:
        for svc in all_services:
            icon = "🔥" if svc["type"] == "combo" else emo(svc["name"])
            markup.add(ibtn(
                f"{icon} {svc['name'].upper()}",
                callback_data=f"usr_svc|{svc['name']}",
                style="primary"
            ))
    else:
        markup.add(ibtn("⚠️ NO SERVICE AVAILABLE", callback_data="ignore", style="danger"))

    markup.add(ibtn("✖ Cancel", callback_data="close_menu", style="danger"))

    text = (
        f"⭐ <b>SELECT SERVICE</b>\n"
        f"🆓 <b>FREE NUMBERS</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"永 <b>{html.escape(data_wm)}</b>"
    )
    safe_send(chat_id, text, markup)


def show_user_service_countries(chat_id, service_name, message_id=None):
    """Show countries for a selected service (from combos)."""
    data = load_data()
    countries = {}
    # From combos only
    for combo in data.get("combos", []):
        if combo.get("name", "").upper() != service_name.upper():
            continue
        combo_countries = combo.get("countries", {})
        combo_numbers = combo.get("numbers", [])
        combo_used = combo.get("used_numbers", [])
        for cty, nums in combo_countries.items():
            key = cty.lower()
            avail = len([n for n in nums if n not in combo_used])
            if avail > 0:
                if key not in countries:
                    countries[key] = {"name": cty, "count": 0}
                countries[key]["count"] += avail

    markup = InlineKeyboardMarkup(row_width=1)
    buttons = []
    color_cycle = ["primary", "success", "danger"]
    for idx, (key, cdata) in enumerate(countries.items()):
        if cdata["count"] == 0:
            continue
        flag = get_country_flag(cdata["name"])
        count_str = "API" if cdata["count"] == "API" else str(cdata["count"])
        buttons.append(ibtn(
            f"{flag} {cdata['name'].upper()} ({count_str})",
            callback_data=f"usr_cnt|{service_name}|{key}",
            style=color_cycle[idx % 3]
        ))

    if buttons:
        markup.add(*buttons)
    markup.add(ibtn("↩ Back", callback_data="back_to_user_services", style="danger"))

    flag_emoji = emo(service_name)
    text = (
        f"{flag_emoji} <b>{html.escape(service_name.upper())}</b>\n"
        f"📍 <b>SELECT COUNTRY:</b>"
    )
    safe_send(chat_id, text, markup, message_id)


def show_user_number_status(chat_id, service_name, country_name, number, session_id, message_id=None):
    """Show number status card like the screenshot."""
    flag = get_country_flag(country_name)
    data_wm = load_data().get("watermark", "VERTEX OTP")
    status = "⏳ Waiting for SMS"

    text = (
        f"📞 <b>Number:</b> {html.escape(number)}\n"
        f"📍 <b>Country:</b> {flag} {html.escape(country_name)}\n"
        f"📱 <b>Service:</b> {html.escape(service_name.upper())}\n"
        f"⏳ <b>Status:</b> {status}\n"
        f"━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(ibtn("👁 View OTP", callback_data=f"check_otp|{session_id}", style="primary"))
    markup.add(ibtn("🔄 Change Number", callback_data=f"change_num|{service_name}", style="danger"))
    markup.add(ibtn("↩ Back", callback_data="back_to_user_services", style="primary"))

    safe_send(chat_id, text, markup, message_id)
def show_user_countries(chat_id, app_name, message_id=None):
    """Redirect to the new compact format."""
    show_user_service_countries(chat_id, app_name, message_id)


def show_2fa_menu_display(chat_id):
    sep = "━" * 13
    text = f"{sep}\n《 🔐 <b>2FA AUTHENTICATOR</b> 》\n{sep}\n🔐 <b>GENERATE SECURE 2FA CODES</b>\n📱 <b>ENTER YOUR SECRET KEY</b>\n\n<b>CLICK GENERATE 2FA CODE BELOW</b>"
    safe_send(chat_id, text, get_2fa_menu())

def show_traffic_info(chat_id):
    data = load_data()
    traffic_log = data.get("traffic_log", {})
    if not traffic_log:
        markup = InlineKeyboardMarkup()
        markup.add(ibtn("🔄 REFRESH", callback_data="refresh_traffic", style="primary"))
        markup.add(ibtn("❌ CLOSE", callback_data="close_menu", style="danger"))
        safe_send(chat_id, f"━━━━━━━━━━━━━━━\n《 📊 <b>NETWORK TRAFFIC</b> 》\n━━━━━━━━━━━━━━━\n<b>No traffic data yet.</b>", markup)
        return
    lines = []
    lines.append("┌─────────────────┐")
    lines.append("│  📶 <b>NETWORK TRAFFIC</b>  │")
    lines.append("└─────────────────┘")
    lines.append("")
    for app_name, countries in traffic_log.items():
        app_emoji = emo(app_name)
        lines.append(f"[ {app_emoji} <b>{html.escape(app_name)}</b> ]")
        lines.append("")
        sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)
        for country_name, success_count in sorted_countries:
            flag = get_country_flag(country_name)
            iso = get_iso_code(country_name)
            lines.append(f"├─ {flag} <b>{html.escape(country_name)} ({iso})</b>")
            lines.append(f"│  └ Success: {success_count}")
        lines.append("")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    markup = InlineKeyboardMarkup()
    markup.add(ibtn("🔄 REFRESH", callback_data="refresh_traffic", style="primary"))
    markup.add(ibtn("❌ CLOSE", callback_data="close_menu", style="danger"))
    safe_send(chat_id, text, markup)

def log_traffic(app_name, country_name):
    if not app_name or not country_name:
        return
    data = load_data()
    traffic = data.setdefault("traffic_log", {})
    app_key = app_name.title()
    country_key = country_name.title()
    if app_key not in traffic:
        traffic[app_key] = {}
    traffic[app_key][country_key] = traffic[app_key].get(country_key, 0) + 1
    save_data(data)

def show_support(chat_id, first_name):
    text = (
        f"┏━━━━━━━ 🌙 ━━━━━━━┓\n"
        f"═《 <b>𝗦𝗨𝗣𝗣𝗢𝗥𝗧</b> 》═\n"
        f"━━━━━━━━━━━━━\n"
        f"👋 <b>𝗛𝗘𝗟𝗟𝗢,</b> <a href='tg://user?id={chat_id}'>{html.escape(first_name)}</a>!\n"
        f"💬 <b>𝗟𝗜𝗩𝗘 𝗖𝗛𝗔𝗧 𝗪𝗜𝗧𝗛 𝗔𝗗𝗠𝗜𝗡</b>\n\n"
        f"➤ <b>TAP THE BUTTON BELOW</b>\n"
        f"➤ <b>TO SEND A MESSAGE</b>\n"
        f"➤ <b>ADMINS WILL REPLY HERE</b>\n"
        f"┗━━━━━━━ ⚡ ━━━━━━━┛"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(ibtn("💬 START LIVE CHAT", callback_data="open_support_ticket", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="close_menu", style="danger"))
    safe_send(chat_id, text, markup)

def show_leaderboard(chat_id, message_id=None):
    data = load_data()
    leaderboard = data.get("leaderboard", {})
    text = "━━━━━━━━━━━━━━━\n《 🏆 <b>LEADERBOARD</b> 》\n━━━━━━━━━━━━━━━\n\n"
    if not leaderboard:
        text += "<b>⚠️ NO DATA YET</b>\n\n<b>BE THE FIRST TO GET OTP!</b>"
    else:
        sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        stylish_nums = ["➊", "➋", "➌", "➍", "➎", "➏", "➐", "➑", "➒", "➓"]
        for idx, (uid, udata) in enumerate(sorted_lb):
            name = html.escape(udata.get("name", "User"))
            count = udata.get("count", 0)
            mention = f"<a href='tg://user?id={uid}'>{name}</a>"
            text += f"{stylish_nums[idx]}  {mention}  —  {count} OTP\n"
            text += "━━━━━━━━━━━━━━━\n"
    watermark = data.get("watermark", "VERTEX OTP")
    text += f"\n🚀 <b>POWERED BY {html.escape(watermark)}</b>\n━━━━━━━━━━━━━━━"
    safe_send(chat_id, text, get_leaderboard_menu())

def show_admin_panel(chat_id, message_id=None):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("sms_date") != today:
        data["today_sms"] = 0
    avail_nums = get_total_available_numbers()
    st = data.get("settings", {})
    active_panels = sum(1 for p in data.get("panels", {}).values() if p.get("status") == "active")
    total_panels = get_total_panels()
    watermark = data.get("watermark", "Vertex_OTP")
    text = (
        f"┌─────────────────────┐\n"
        f"│  👑 <b>ADMIN CONTROL PANEL</b>  │\n"
        f"└─────────────────────┘\n"
        f"\n"
        f"┌── <b>📊 Statistics</b>\n"
        f"│  👥 Users: <code>{len(data.get('users', []))}</code>\n"
        f"│  👮 Admins: <code>{len(data.get('extra_admins', []))}</code>\n"
        f"│  🎚 Main Admins: <code>{len(MAIN_ADMINS)}</code>\n"
        f"│  📢 OTP Groups: <code>{len(data.get('forward_groups', []))}</code>\n"
        f"├── <b>🔧 Infrastructure</b>\n"
        f"│  📋 Panels: <code>{active_panels}/{total_panels}</code>\n"
        f"│  📦 Apps: <code>{get_total_apps()}</code>\n"
        f"│  📱 Ranges: <code>{get_total_ranges()}</code>\n"
        f"│  🔢 Available: <code>{avail_nums}</code>\n"
        f"├── <b>📈 Activity</b>\n"
        f"│  📅 Month: <code>{data.get('month_sms', 0)}</code> SMS\n"
        f"│  📊 Today: <code>{data.get('today_sms', 0)}</code> SMS\n"
        f"├── <b>⚙️ Config</b>\n"
        f"│  ⏳ Cooldown: <code>{st.get('cooldown', 60)}s</code>\n"
        f"│  📱 Num/Req: <code>{st.get('num_per_request', 5)}</code>\n"
        f"│  💲 Price/OTP: <code>${st.get('price_per_otp', 0.001):.4f}</code>\n"
        f"└─────────────────────┘\n"
        f"永 <b>{html.escape(watermark)}</b>"
    )
    safe_send(chat_id, text, get_admin_menu(chat_id))

def show_admin_system(chat_id, message_id=None):
    data = load_data()
    st = data.get("settings", {})
    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 ⚙️ <b>SYSTEM SETTINGS</b> 》\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔧 <b>SETTINGS:</b>\n"
        f"  ⏳ Cooldown: <code>{st.get('cooldown', 60)}s</code>\n"
        f"  📱 Num/Req: <code>{st.get('num_per_request', 5)}</code>\n"
        f"  💲 Price/OTP: <code>${st.get('price_per_otp', 0.001):.4f}</code>\n"
        f"  🛠️ Support: <code>{html.escape(st.get('support_link', 'https://t.me/Vertex_OTP'))}</code>\n"
        f"━━━━━━━━━━━━━━━"
    )
    safe_send(chat_id, text, get_admin_system_menu())

def show_user_view(chat_id, message_id=None):
    data = load_data()
    users = len(data.get("users", []))
    verified = len(data.get("otp_counts", {}).keys())
    banned = len(data.get("banned_users", []))
    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 👤 <b>USER VIEW</b> 》\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 <b>LIVE STATISTICS:</b>\n\n"
        f"👥 <b>TOTAL USERS:</b> <b>{users}</b>\n"
        f"✅ <b>VERIFIED USERS:</b> <b>{verified}</b>\n"
        f"🚫 <b>BANNED USERS:</b> <b>{banned}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🕒 <b>UPDATED:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("💎 USER PROFILE", callback_data="uv_profile", style="primary"),
               ibtn("🚫 BAN / UNBAN", callback_data="uv_ban_menu", style="danger"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="success"))
    safe_send(chat_id, text, markup)

def show_stock_info(chat_id, message_id=None):
    data = load_data()
    stock_data = {}
    total_avail = 0
    # Count from combos
    for combo in data.get("combos", []):
        app = combo.get("name", "UNKNOWN").upper()
        nums = combo.get("numbers", [])
        used = combo.get("used_numbers", [])
        combo_countries = combo.get("countries", {})
        for cty, cty_nums in combo_countries.items():
            avail = len([n for n in cty_nums if n not in used])
            if avail > 0:
                if app not in stock_data:
                    stock_data[app] = {}
                stock_data[app][cty] = stock_data[app].get(cty, 0) + avail
                total_avail += avail
    # Count from panel ranges
    for panel in data.get("panels", {}).values():
        if panel.get("status") != "active":
            continue
        if panel.get("fetch_type", "manual") == "auto":
            continue
        for rng in panel.get("ranges", {}).values():
            app = rng.get("app", "UNKNOWN").upper()
            cname = rng.get("name", "Unknown").title()
            nums = rng.get("numbers", [])
            used = rng.get("used_numbers", [])
            avail = len([n for n in nums if n not in used])
            if avail > 0:
                if app not in stock_data:
                    stock_data[app] = {}
                stock_data[app][cname] = stock_data[app].get(cname, 0) + avail
                total_avail += avail
    text = f"━━━━━━━━━━━━━━━\n《 📈 <b>STOCK INFO</b> 》\n━━━━━━━━━━━━━━━\n"
    if not stock_data:
        text += "\n<b>⚠️ NO STOCK AVAILABLE!</b>\n<b>UPLOAD NUMBERS VIA 🔥 COMBO.</b>\n"
    else:
        for app, countries in stock_data.items():
            text += f"\n📦 <b>APP: {emo(app)} {app}</b>\n"
            for country, count in sorted(countries.items(), key=lambda x: x[1], reverse=True):
                flag = get_country_flag(country)
                text += f" ├ {flag} <b>{country}:</b> <code>{count}</code> nums\n"
    text += f"\n━━━━━━━━━━━━━━━\n📊 <b>TOTAL AVAILABLE:</b> <code>{total_avail}</code>\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("🔄 REFRESH", callback_data="refresh_stock", style="success"),
               ibtn("❌ CLOSE", callback_data="close_menu", style="danger"))
    safe_send(chat_id, text, markup)

def show_support_menu(chat_id, message_id=None):
    """Show the support menu with live chat option."""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(ibtn("💬 OPEN SUPPORT TICKET", callback_data="open_support_ticket", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="close_menu", style="danger"))
    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 📩 <b>SUPPORT CHAT</b> 》\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>Click the button below to start a live chat with an admin.</b>\n\n"
        f"Your message will be forwarded to all available admins.\n"
        f"Admins can reply directly to you."
    )
    safe_send(chat_id, text, markup)

# ==================== PANEL MANAGEMENT ====================
def show_panel_list(chat_id, message_id=None):
    data = load_data()
    markup = InlineKeyboardMarkup(row_width=1)
    color_cycle = ["primary", "success", "danger"]
    for idx, (panel_id, panel) in enumerate(data.get("panels", {}).items()):
        status_icon = "🟢" if panel.get("status") == "active" else "🔴"
        rng_count = len(panel.get("ranges", {}))
        f_type = panel.get("fetch_type", "manual")
        if f_type == "manual":
            total_nums = sum(len(r.get("numbers", [])) for r in panel.get("ranges", {}).values())
            btn_text = f"{status_icon} [MANUAL] {panel['name'].upper()} | R:{rng_count} N:{total_nums}"
        else:
            btn_text = f"{status_icon} [AUTO] {panel['name'].upper()} | R:{rng_count} (API)"
        markup.add(ibtn(btn_text, callback_data=f"panel_view|{panel_id}", style=color_cycle[idx % 3]))
    markup.add(ibtn("➕ Add Panel", callback_data="add_panel", style="success"))
    markup.add(ibtn("🔙 Back to Admin", callback_data="back_to_admin", style="primary"))
    total_panels = len(data.get('panels', {}))
    total_all_nums = sum(sum(len(r.get("numbers", [])) for r in p.get("ranges", {}).values()) for p in data.get("panels", {}).values() if p.get("fetch_type", "manual") == "manual")
    text = f"┌─────────────────┐\n│ 📋 <b>API Panels</b>\n├─────────────────┤\n│ Total Panels: <code>{total_panels}</code>\n│ Total Manual Numbers: <code>{total_all_nums}</code>\n└─────────────────┘"
    safe_send(chat_id, text, markup)

def show_panel_detail(chat_id, panel_id, message_id=None):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        show_panel_list(chat_id, message_id)
        return
    status_icon = "🟢" if panel.get("status") == "active" else "🔴"
    status_text = "Active" if panel.get("status") == "active" else "Inactive"
    p_type = panel.get("type", "api")
    f_type = panel.get("fetch_type", "manual").title()
    rng_count = len(panel.get("ranges", {}))
    api_fmt = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), panel.get("api_key", "")))
    fmt_label = PANEL_FORMATS.get(api_fmt, {}).get("label", api_fmt.upper())
    if p_type == "api":
        type_label = "🔌 API Panel"
        api_url = panel.get("api_url", "Not set")
        api_connected = "✅ Connected" if panel.get("api_key") else "❌ Not set"
        creds_line = f"🔑 API: {api_connected}\n│ 🌐 URL: {html.escape(str(api_url))}"
    else:
        type_label = "🔐 Login Panel"
        login_url = panel.get("login_url", "Not set")
        login_active = "✅ Active" if panel.get("login_user") else "❌ Not set"
        creds_line = f"🔐 Login: {login_active}\n│ 🌐 URL: {html.escape(str(login_url))}"
    if f_type.lower() == "manual":
        total_nums = sum(len(r.get("numbers", [])) for r in panel.get("ranges", {}).values())
        num_str = str(total_nums)
    else:
        num_str = "Auto API (Dynamic)"
    text = (
        f"┌─────────────────┐\n"
        f"│ 🔧 <b>{html.escape(panel['name'])}</b>\n"
        f"├─────────────────┤\n"
        f"│ <b>Type:</b> {type_label}\n"
        f"│ <b>Format:</b> {fmt_label}\n"
        f"│ <b>Generation:</b> {f_type}\n"
        f"│ <b>Status:</b> {status_icon} {status_text}\n"
        f"│ {creds_line}\n"
        f"│ 📱 <b>Ranges:</b> {rng_count}\n"
        f"│ 🔢 <b>Total Numbers:</b> {num_str}\n"
        f"└─────────────────┘"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("🔍 Test Connection", callback_data=f"panel_test|{panel_id}", style="primary"))
    if p_type == "api":
        markup.add(ibtn("🔑 Set API Creds", callback_data=f"panel_setcreds|{panel_id}", style="success"))
    else:
        markup.add(ibtn("🔐 Set Login Creds", callback_data=f"panel_setlogin|{panel_id}", style="success"))
    markup.add(ibtn(f"📋 Format: {api_fmt.upper()}", callback_data=f"panel_format|{panel_id}", style="primary"))
    markup.add(ibtn("📱 View Ranges", callback_data=f"panel_ranges|{panel_id}", style="primary"),
               ibtn("✏️ Rename", callback_data=f"panel_rename|{panel_id}", style="success"))
    toggle_text = "🔴 Deactivate" if panel.get("status") == "active" else "🟢 Activate"
    markup.add(ibtn(toggle_text, callback_data=f"panel_toggle|{panel_id}", style="danger"),
               ibtn("❌ Delete Panel", callback_data=f"panel_delete|{panel_id}", style="danger"))
    if p_type == "api":
        markup.add(ibtn("🔐 Switch to Login Creds", callback_data=f"panel_switch|{panel_id}", style="primary"))
    else:
        markup.add(ibtn("🔌 Switch to API Creds", callback_data=f"panel_switch|{panel_id}", style="primary"))
    markup.add(ibtn("🔙 Back to Panels", callback_data="admin_manage_panels", style="success"))
    safe_send(chat_id, text, markup)

def show_panel_format_menu(chat_id, panel_id, message_id=None):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel: return
    current = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), panel.get("api_key", "")))
    markup = InlineKeyboardMarkup(row_width=1)
    for fmt_name, fmt_data in PANEL_FORMATS.items():
        check = " ✅" if current == fmt_name else ""
        style = "success" if current == fmt_name else "primary"
        markup.add(ibtn(f"{fmt_data['label']}{check}", callback_data=f"set_pfmt|{panel_id}|{fmt_name}", style=style))
    markup.add(ibtn("🔧 Set Custom Endpoints", callback_data=f"panel_custom_ep|{panel_id}", style="danger"))
    markup.add(ibtn("🔙 Back", callback_data=f"panel_view|{panel_id}", style="success"))
    safe_edit(chat_id, f"━━━━━━━━━━━━━━━\n《 📋 <b>API FORMAT</b> 》\n━━━━━━━━━━━━━━━\n<b>Panel:</b> {html.escape(panel['name'])}\n<b>Current:</b> {current.upper()}\n\n<b>SELECT FORMAT:</b>", markup, message_id)

def show_panel_ranges(chat_id, panel_id, message_id=None):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return
    ranges = panel.get("ranges", {})
    f_type = panel.get("fetch_type", "manual")
    markup = InlineKeyboardMarkup(row_width=1)
    color_cycle = ["primary", "success", "danger"]
    text_lines = []
    for idx, (rng_id, rng) in enumerate(ranges.items()):
        nums = rng.get("numbers", [])
        total = len(nums)
        flag = get_country_flag(rng.get("name", ""))
        app_name = rng.get("app", "?").upper()
        rng_code = rng.get("range_code", "NA")
        api_cc = rng.get("country_code", "")
        cc_label = f" | CC:{api_cc}" if api_cc else ""
        if f_type == "manual":
            status_icon = "🟢" if total > 0 else "🔴"
            text_lines.append(f"{status_icon} {flag} {rng['name']} | {app_name} ({rng_code}){cc_label} | {total} nums")
            markup.add(ibtn(f"🔧 {flag} {rng['name']} [{total}]", callback_data=f"view_range|{panel_id}|{rng_id}", style=color_cycle[idx % 3]))
        else:
            text_lines.append(f"🟢 {flag} {rng['name']} | {app_name} ({rng_code}){cc_label} | AUTO API")
            markup.add(ibtn(f"🔧 {flag} {rng['name']} [API]", callback_data=f"view_range|{panel_id}|{rng_id}", style=color_cycle[idx % 3]))
    markup.add(ibtn("➕ Add Range", callback_data=f"add_range|{panel_id}", style="success"))
    markup.add(ibtn("🔙 Back to Panel", callback_data=f"panel_view|{panel_id}", style="primary"))
    header = f"━━━━━━━━━━━━━━━\n《 📱 <b>Ranges — {html.escape(panel['name'])}</b> 》\n━━━━━━━━━━━━━━━"
    if text_lines:
        body = "\n".join(text_lines)
        text = f"{header}\n{body}"
    else:
        if f_type == "auto":
            text = f"{header}\n<b>No ranges added yet.</b>\n\n⚠️ <i>Add ranges with Country + Service + Country Code</i>\n<i>to start fetching numbers from API.</i>"
        else:
            text = f"{header}\n<b>No ranges added yet.</b>\n<i>Add ranges and then add numbers for this panel.</i>"
    safe_edit(chat_id, text, markup, message_id)

def show_range_detail(chat_id, panel_id, rng_id, message_id=None):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return
    rng = panel.get("ranges", {}).get(rng_id)
    if not rng:
        show_panel_ranges(chat_id, panel_id, message_id)
        return
    f_type = panel.get("fetch_type", "manual")
    flag = get_country_flag(rng.get("name", ""))
    rng_code = rng.get("range_code", "N/A")
    api_cc = rng.get("country_code", "N/A")
    if f_type == "manual":
        nums = rng.get("numbers", [])
        used = rng.get("used_numbers", [])
        avail = len([n for n in nums if n not in used])
        cycle_status = "🟢 Active" if len(nums) > 0 else "🔴 Empty"
        text = (
            f"┌─────────────────┐\n"
            f"│ 📱 <b>{flag} {html.escape(rng['name'])}</b>\n"
            f"├─────────────────┤\n"
            f"│ 📦 App: <b>{rng.get('app', 'N/A').upper()}</b>\n"
            f"│ 🔗 Service Code: <code>{rng_code}</code>\n"
            f"│ 🌍 Country Code: <code>{api_cc}</code>\n"
            f"│ 📊 Total Added: <code>{len(nums)}</code>\n"
            f"│ ✅ Available: <code>{avail}</code>\n"
            f"│ 🔄 Served: <code>{len(used)}</code>\n"
            f"│ ♻️ Status: {cycle_status}\n"
            f"│ 💡 <i>Numbers auto-recycle when all served</i>\n"
            f"└─────────────────┘"
        )
    else:
        text = (
            f"┌─────────────────┐\n"
            f"│ 📱 <b>{flag} {html.escape(rng['name'])}</b>\n"
            f"├─────────────────┤\n"
            f"│ 📦 App: <b>{rng.get('app', 'N/A').upper()}</b>\n"
            f"│ 🔗 Service Code: <code>{rng_code}</code>\n"
            f"│ 🌍 Country Code: <code>{api_cc}</code>\n"
            f"│ 🤖 Type: <b>Auto API (Direct Fetch)</b>\n"
            f"│ 💡 <i>Numbers fetched from API directly</i>\n"
            f"└─────────────────┘"
        )
    markup = InlineKeyboardMarkup(row_width=2)
    if f_type == "manual":
        markup.add(ibtn("➕ Add Numbers", callback_data=f"add_nums|{panel_id}|{rng_id}", style="success"))
    markup.add(ibtn("❌ Delete Range", callback_data=f"del_range|{panel_id}|{rng_id}", style="danger"))
    markup.add(ibtn("🔙 Back", callback_data=f"panel_ranges|{panel_id}", style="primary"))
    safe_send(chat_id, text, markup)

def show_app_list(chat_id, message_id=None):
    data = load_data()
    apps = get_app_list(data)
    markup = InlineKeyboardMarkup(row_width=1)
    color_cycle = ["primary", "success", "danger"]
    if apps:
        # Group by folder
        folders = {}
        for app in apps:
            folder = app.get("folder", "OTHER").upper()
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(app["name"])
        idx = 0
        for folder in sorted(folders.keys()):
            markup.add(ibtn(f"📁 {folder}", callback_data="ignore", style="primary"))
            for app_name in folders[folder]:
                markup.add(ibtn(f"  ❌ {emo(app_name)} {app_name}", callback_data=f"del_app|{app_name}", style=color_cycle[idx % 3]))
                idx += 1
    else:
        markup.add(ibtn("📭 No apps configured", callback_data="ignore", style="danger"))
    # Show combos from TXT uploads
    combos = data.get("combos", [])
    if combos:
        markup.add(ibtn("📦 <b>COMBOS (TXT)</b>", callback_data="ignore", style="danger"))
        for ci, combo in enumerate(combos):
            cname = combo.get("name", f"Combo {ci+1}")
            total_nums = sum(len(nums) for nums in combo.get("countries", {}).values())
            markup.add(ibtn(f"  ❌ {emo(cname)} {cname} ({total_nums})", callback_data=f"del_combo|{ci}", style="danger"))
    total = len(apps) + len(combos)
    markup.add(ibtn("➕ Add App (Name Only)", callback_data="add_combo", style="success"))
    markup.add(ibtn("🔥 Add Combo (TXT)", callback_data="add_combo", style="danger"))
    markup.add(ibtn("🔙 Back to Admin", callback_data="back_to_admin", style="primary"))
    text = f"┌────────────────┐\n🔥 <b>Combo Management</b>\n├────────────────┤\n📦 Combos: <code>{len(combos)}</code> | Apps: <code>{len(apps)}</code>\n📊 Total: <code>{total}</code>\n│ <i>Tap ❌ to remove</i>\n└────────────────┘"
    safe_send(chat_id, text, markup)

def show_manage_admins(chat_id, message_id=None):
    data = load_data()
    admins = data.get("extra_admins", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for adm in admins:
        markup.add(ibtn(f"❌ REMOVE: {adm}", callback_data=f"deladm_{adm}", style="danger"))
    markup.add(ibtn("➕ ADD ADMIN", callback_data="add_new_admin", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
    safe_send(chat_id, f"━━━━━━━━━━━━━━━\n《 👮 <b>MANAGE ADMINS</b> 》\n━━━━━━━━━━━━━━━\n<b>TOTAL EXTRA ADMINS:</b> {len(admins)}", markup)

def show_ban_unban_menu(chat_id, message_id=None):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("🔨 BAN", callback_data="uv_ban_do", style="danger"),
               ibtn("♻️ UNBAN", callback_data="uv_unban_list", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="admin_user_view", style="primary"))
    safe_edit(chat_id, f"━━━━━━━━━━━━━━━\n《 🚫 BAN / UNBAN MENU 》\n━━━━━━━━━━━━━━━\nCHOOSE AN ACTION:", markup, message_id)

def show_unban_list(chat_id, message_id=None):
    data = load_data()
    banned = data.get("banned_users", [])
    markup = InlineKeyboardMarkup(row_width=1)
    if not banned:
        safe_edit(chat_id, f"━━━━━━━━━━━━━━━\n《 ♻️ <b>UNBAN USER</b> 》\n━━━━━━━━━━━━━━━\n<b>✅ NO BANNED USERS FOUND!</b>",
                  InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="uv_ban_menu", style="success")), message_id)
        return
    for uid in banned:
        markup.add(ibtn(f"♻️ UNBAN: {uid}", callback_data=f"unban_{uid}", style="success"))
    markup.add(ibtn("🔙 BACK", callback_data="uv_ban_menu", style="primary"))
    safe_edit(chat_id, f"━━━━━━━━━━━━━━━\n《 ♻️ <b>UNBAN LIST</b> 》\n━━━━━━━━━━━━━━━\n<b>SELECT A USER TO UNBAN:</b>", markup, message_id)
    # ============================================
#  PART 5 - OTP CORE LOGIC & NUMBER FETCHING
# ============================================

# -------------------- PANEL FORMAT DETECTION --------------------
def fetch_from_auto_panel(panel, rng, user_id=None, app_name=None):
    """
    Fetch a number from an auto panel using the configured API format.
    Returns dict with 'number', 'activation_id' or None on failure.
    """
    f_type = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), panel.get("api_key", "")))
    api_key = panel.get("api_key", "")
    api_url = panel.get("api_url", "").rstrip("/")
    rng_code = rng.get("range_code", "")
    api_cc = rng.get("country_code", "")

    try:
        if f_type == "smspin":
            # SMS Pin / SMS Spin Verify format
            # e.g. https://smspinverify.com/stubs/handler_api.php?api_key=XXX&action=getNumber&country=XX&service=XX
            params = {
                "api_key": api_key,
                "action": "getNumber",
                "country": api_cc,
                "service": rng_code,
            }
            resp = requests.get(f"{api_url}/stubs/handler_api.php", params=params, timeout=15)
            resp_text = resp.text.strip()
            log(f"[AUTO] smspin response: {resp_text}")
            if resp_text.startswith("ACCESS_NUMBER"):
                parts = resp_text.split(":")
                if len(parts) >= 3:
                    activation_id = parts[1]
                    number = parts[2]
                    if not number.startswith("+"):
                        number = "+" + number
                    return {"number": number, "activation_id": activation_id}
            return None

        elif f_type == "5sim":
            # 5sim format: GET https://5sim.net/v1/user/buy/activation/{country}/{operator}/any/{product}
            # or simpler: GET https://5sim.net/v1/user/get/activations
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
            # Try buy activation endpoint
            cc = api_cc.lower()
            product = rng_code.lower()
            url = f"{api_url}/v1/user/buy/activation/{cc}/any/{product}"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                dataj = resp.json()
                number = dataj.get("phone", dataj.get("number", ""))
                activation_id = dataj.get("id", dataj.get("activationId", ""))
                if number:
                    if not number.startswith("+"):
                        number = "+" + number
                    return {"number": number, "activation_id": str(activation_id)}
            log(f"[AUTO] 5sim response: {resp.status_code} {resp.text[:200]}")
            return None

        elif f_type == "smshub":
            # SMS Hub format
            params = {
                "api_key": api_key,
                "action": "getNumber",
                "country": api_cc,
                "service": rng_code,
            }
            resp = requests.get(api_url, params=params, timeout=15)
            resp_text = resp.text.strip()
            log(f"[AUTO] smshub response: {resp_text}")
            if "ACCESS_NUMBER" in resp_text:
                parts = resp_text.split(":")
                if len(parts) >= 3:
                    activation_id = parts[1]
                    number = parts[2]
                    if not number.startswith("+"):
                        number = "+" + number
                    return {"number": number, "activation_id": activation_id}
            return None

        elif f_type == "onlinesim":
            # OnlineSim format
            params = {
                "apikey": api_key,
                "action": "getNumber",
                "country": api_cc,
                "service": rng_code,
            }
            resp = requests.get(f"{api_url}/api/getNumber.php", params=params, timeout=15)
            dataj = resp.json()
            if dataj.get("response") == "1":
                number = dataj.get("number", "")
                tzid = dataj.get("tzid", "")
                if number:
                    return {"number": number, "activation_id": str(tzid)}
            return None

        else:
            log(f"[AUTO] Unknown format: {f_type}")
            return None
    except Exception as e:
        log(f"[AUTO] Error fetching from {f_type}: {e}")
        return None


# -------------------- MANUAL NUMBER FETCHING --------------------
def get_number_from_panel(panel_id, rng_id, user_id=None, app_name=None):
    """
    Get number from a panel range.
    For manual panels: grab first unused number.
    For auto panels: fetch from API.
    """
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return None
    rng = panel.get("ranges", {}).get(rng_id)
    if not rng:
        return None
    f_type = panel.get("fetch_type", "manual")

    if f_type == "auto":
        # Auto fetch from API
        result = fetch_from_auto_panel(panel, rng, user_id, app_name)
        if result:
            return result
        return None
    else:
        # Manual: grab first unused number
        nums = rng.get("numbers", [])
        used = rng.get("used_numbers", [])
        available = [n for n in nums if n not in used]
        if not available:
            # Auto-recycle: if all numbers used, reset used list
            if nums:
                rng["used_numbers"] = []
                used = []
                available = nums[:]  # all become available again
                log(f"[MANUAL] Auto-recycled numbers for {panel.get('name')}/{rng.get('name')}")
                save_data(data)
            else:
                return None
        chosen = available[0]
        # Mark as used
        if chosen not in used:
            used.append(chosen)
        rng["used_numbers"] = used
        save_data(data)
        # Return just the number, no activation_id for manual
        if not chosen.startswith("+"):
            chosen = "+" + chosen
        return {"number": chosen, "activation_id": None}


# -------------------- FIND NUMBER FOR USER (All Panels Search) --------------------
def find_number_for_user(app_name, country_name=None, user_id=None):
    """
    Search combos for a number matching app + country.
    Returns dict with 'number', 'activation_id', 'panel_id', 'rng_id', 'app', 'country'.
    """
    data = load_data()
    import random

    log(f"[FIND] Searching: app={app_name}, country={country_name}")

    # Search combos (primary source)
    for combo in data.get("combos", []):
        if combo.get("name", "").upper() != app_name.upper():
            continue
        combo_countries = combo.get("countries", {})
        combo_used = combo.get("used_numbers", [])
        log(f"[FIND] Found combo: {combo.get('name')}, countries={list(combo_countries.keys())}, used={len(combo_used)}")

        # Find matching country numbers
        available = []
        matched_country = "Unknown"
        if country_name:
            target = country_name.lower()
            for cty, nums in combo_countries.items():
                if cty.lower() == target:
                    matched_country = cty
                    available = [n for n in nums if n not in combo_used]
                    log(f"[FIND] Matched country: {cty}, available={len(available)}")
                    break
            if not available:
                log(f"[FIND] No match for country '{country_name}' in {list(combo_countries.keys())}")
        else:
            for cty, nums in combo_countries.items():
                avail = [n for n in nums if n not in combo_used]
                if avail:
                    matched_country = cty
                    available = avail
                    break

        if available:
            number = random.choice(available)
            combo_used.append(number)
            combo["used_numbers"] = combo_used
            # Permanently delete number from stock
            combo["numbers"] = [n for n in combo.get("numbers", []) if n != number]
            for cty in combo.get("countries", {}).keys():
                combo["countries"][cty] = [n for n in combo["countries"][cty] if n != number]
            save_data(data)
            log(f"[FIND] Returning number: {number} from {matched_country} (deleted from stock)")
            return {
                "number": number,
                "activation_id": f"COMBO_{int(time.time())}",
                "panel_id": "combo",
                "rng_id": combo.get("name", ""),
                "app": app_name,
                "country": matched_country
            }

    # Fallback: if no country matched, pick ANY available number from the combo
    for combo in data.get("combos", []):
        if combo.get("name", "").upper() != app_name.upper():
            continue
        combo_used = combo.get("used_numbers", [])
        all_available = [n for n in combo.get("numbers", []) if n not in combo_used]
        if all_available:
            number = random.choice(all_available)
            combo_used.append(number)
            combo["used_numbers"] = combo_used
            save_data(data)
            cty = detect_country_from_phone(number)
            log(f"[FIND] Fallback: {number} from {cty}")
            return {
                "number": number,
                "activation_id": f"COMBO_{int(time.time())}",
                "panel_id": "combo",
                "rng_id": combo.get("name", ""),
                "app": app_name,
                "country": cty
            }

    # Fallback: search panel ranges
    candidates = []
    for panel_id, panel in data.get("panels", {}).items():
        if panel.get("status") != "active":
            continue
        for rng_id, rng in panel.get("ranges", {}).items():
            rng_app = rng.get("app", "").upper()
            if rng_app != app_name.upper():
                continue
            rng_name = rng.get("name", "").lower()
            if country_name and rng_name != country_name.lower():
                continue
            candidates.append((panel_id, panel, rng_id, rng))
    candidates.sort(key=lambda x: (0 if x[1].get("fetch_type") == "auto" else 1))
    for panel_id, panel, rng_id, rng in candidates:
        result = get_number_from_panel(panel_id, rng_id, user_id, app_name)
        if result:
            result["panel_id"] = panel_id
            result["rng_id"] = rng_id
            result["app"] = app_name
            result["country"] = rng.get("name", "Unknown")
            return result

    return None


# -------------------- BALANCE CHECK --------------------
def has_sufficient_balance(user_id, price=None):
    """Check if user has enough balance for an OTP."""
    data = load_data()
    if price is None:
        price = data.get("settings", {}).get("price_per_otp", 0.001)
    balance = data.get("balances", {}).get(str(user_id), 0.0)
    return balance >= price


def deduct_otp_cost(user_id, price=None):
    """Deduct the cost of one OTP from user balance."""
    data = load_data()
    if price is None:
        price = data.get("settings", {}).get("price_per_otp", 0.001)
    uid = str(user_id)
    current = data["balances"].get(uid, 0.0)
    if current >= price:
        data.setdefault("balances", {})[uid] = round(current - price, 6)
        save_data(data)
        return True
    return False


# -------------------- FETCH NUMBER LOGIC (Main handler logic) --------------------
def fetch_number_logic(chat_id, app_name, country_key=None, message_id=None):
    """
    Main logic to fetch a number for a user.
    Handles balance check, number fetching, and OTP timeout.
    """
    data = load_data()
    user_id = str(chat_id)
    st = data.get("settings", {})
    price = st.get("price_per_otp", 0.001)

    # Numbers are FREE - no balance check

    # Find number instantly
    try:
        result = find_number_for_user(app_name, country_key, chat_id)
    except Exception as e:
        log(f"[FETCH ERROR] {e}")
        safe_send(chat_id, f"━━━━━━━━━━━━━━━\n《 ❌ <b>ERROR</b> 》\n━━━━━━━━━━━━━━━\n\n<code>{html.escape(str(e))}</code>", get_main_menu(chat_id))
        return
    if not result:
        safe_send(chat_id, f"━━━━━━━━━━━━━━━\n《 ❌ <b>NO NUMBERS AVAILABLE</b> 》\n━━━━━━━━━━━━━━━\n\n⚠️ <b>ALL STOCKS EXHAUSTED!</b>\n<b>UPLOAD MORE NUMBERS</b>", get_main_menu(chat_id))
        return

    number = result["number"]
    activation_id = result["activation_id"]
    panel_id = result.get("panel_id", "")
    rng_id = result.get("rng_id", "")
    country_name = result.get("country", "Unknown")
    flag = get_country_flag(country_name)

    # Numbers are FREE - no cost deduction

    # 6. Update cooldown
    data.setdefault("last_otp_time", {})[user_id] = time.time()

    # 7. Update stats
    data["total_sms"] = data.get("total_sms", 0) + 1
    data["today_sms"] = data.get("today_sms", 0) + 1
    data["month_sms"] = data.get("month_sms", 0) + 1
    data["sms_date"] = datetime.now().strftime("%Y-%m-%d")

    # 8. Update leaderboard
    lb = data.get("leaderboard", {})
    if user_id not in lb:
        lb[user_id] = {"name": "User", "count": 0}
    try:
        lb[user_id]["name"] = bot.get_chat(chat_id).first_name or "User"
    except:
        pass
    lb[user_id]["count"] = lb[user_id].get("count", 0) + 1
    data.setdefault("leaderboard", {})[user_id] = lb[user_id]

    # 9. Save number session
    session_id = str(int(time.time()))
    activation_uid = activation_id or f"MANUAL_{session_id}"
    data.setdefault("number_session", {})[session_id] = {
        "user_id": chat_id,
        "number": number,
        "activation_id": activation_uid,
        "app": app_name,
        "country": country_name,
        "panel_id": panel_id,
        "rng_id": rng_id,
        "time": time.time(),
        "status": "awaiting_otp",
        "price": price,
    }
    save_data(data)

    # 10. Show number to user instantly
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("🔄 CHANGE NUMBER", callback_data=f"change_num|{app_name}|{country_key or 'any'}", style="primary"),
               ibtn("🔗 OTP GROUP", url="https://t.me/EARNINGWITHSIMPLETASK", style="success"))
    markup.add(ibtn("❌ CANCEL", callback_data=f"cancel_session|{session_id}", style="danger"),
               ibtn("🔙 MAIN MENU", callback_data="close_menu", style="primary"))

    text = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 ✅ <b>NUMBER RECEIVED</b> 》\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 <b>APP:</b> {emo(app_name)} {app_name.upper()}\n"
        f"🌍 <b>COUNTRY:</b> {flag} {country_name}\n"
        f"💲 <b>CHARGED:</b> ${price:.4f}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"⏳ <b>WAITING FOR OTP...</b>\n"
        f"📱 <b>Join OTP Group for updates</b>\n"
        f"━━━━━━━━━━━━━━━"
    )
    if message_id:
        safe_edit(chat_id, text, markup, message_id)
    else:
        safe_send(chat_id, text, markup)

    # 11. Admin notification removed per request


# -------------------- OTP CHECK LOGIC --------------------
def poll_otp_with_status(chat_id, session_id, message_id=None):
    """
    Check OTP status for a session.
    For auto panels: poll the API for SMS status.
    For manual: ask user to input the OTP code.
    """
    data = load_data()
    session = data.get("number_session", {}).get(session_id)
    if not session:
        safe_edit(chat_id, "⚠️ <b>SESSION EXPIRED</b>", get_main_menu(chat_id), message_id)
        return

    user_id = session.get("user_id")
    if user_id != chat_id:
        safe_edit(chat_id, "⚠️ <b>UNAUTHORIZED</b>", get_main_menu(chat_id), message_id)
        return

    number = session.get("number", "Unknown")
    activation_id = session.get("activation_id", "")
    app_name = session.get("app", "Unknown")
    country_name = session.get("country", "Unknown")
    panel_id = session.get("panel_id", "")
    rng_id = session.get("rng_id", "")

    # Check if auto panel (has activation_id without MANUAL_ prefix)
    is_auto = activation_id and not str(activation_id).startswith("MANUAL_")

    if is_auto:
        # Auto: poll the API for SMS
        panel = data.get("panels", {}).get(panel_id)
        if not panel:
            safe_edit(chat_id, "⚠️ <b>PANEL DISABLED</b>", get_main_menu(chat_id), message_id)
            return

        api_format = panel.get("api_format", detect_panel_format(panel.get("api_url", ""), panel.get("api_key", "")))
        api_key = panel.get("api_key", "")
        api_url = panel.get("api_url", "").rstrip("/")

        otp_code = None
        try:
            if api_format == "smspin":
                params = {
                    "api_key": api_key,
                    "action": "getStatus",
                    "id": activation_id,
                }
                resp = requests.get(f"{api_url}/stubs/handler_api.php", params=params, timeout=15)
                resp_text = resp.text.strip()
                log(f"[OTP] smspin status: {resp_text}")
                if "STATUS_OK" in resp_text:
                    parts = resp_text.split(":")
                    if len(parts) >= 2:
                        otp_code = parts[1].strip()

            elif api_format == "5sim":
                headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
                url = f"{api_url}/v1/user/check/{activation_id}"
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dataj = resp.json()
                    if dataj.get("status") == "RECEIVED":
                        sms_list = dataj.get("sms", [])
                        if sms_list:
                            otp_code = sms_list[0].get("text", sms_list[0].get("code", ""))

            elif api_format == "smshub":
                params = {"api_key": api_key, "action": "getStatus", "id": activation_id}
                resp = requests.get(api_url, params=params, timeout=15)
                resp_text = resp.text.strip()
                if "STATUS_OK" in resp_text:
                    parts = resp_text.split(":")
                    if len(parts) >= 2:
                        otp_code = parts[1].strip()

            elif api_format == "onlinesim":
                params = {"apikey": api_key, "action": "getState", "tzid": activation_id}
                resp = requests.get(f"{api_url}/api/getState.php", params=params, timeout=15)
                dataj = resp.json()
                if isinstance(dataj, list) and len(dataj) > 0:
                    if dataj[0].get("response") == "1":
                        otp_code = dataj[0].get("number", "")

        except Exception as e:
            log(f"[OTP] Poll error: {e}")

        if otp_code:
            # OTP received!
            session["status"] = "completed"
            session["otp_code"] = otp_code
            save_data(data)

            # Update leaderboard
            lb = data.get("leaderboard", {})
            uid = str(chat_id)
            if uid not in lb:
                lb[uid] = {"name": "", "count": 0}
            lb[uid]["count"] = lb[uid].get("count", 0) + 0  # already counted at fetch

            # Notify admins
            notify_all_admins(
                f"✅ <b>OTP RECEIVED</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 <b>USER:</b> <a href='tg://user?id={chat_id}'>User {chat_id}</a>\n"
                f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                f"🔑 <b>OTP:</b> <code>{otp_code}</code>\n"
                f"🆔 <b>SID:</b> <code>{session_id}</code>\n"
                f"━━━━━━━━━━━━━━━"
            )

            text = (
                f"━━━━━━━━━━━━━━━\n"
                f"《 ✅ <b>OTP RECEIVED</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                f"🔑 <b>OTP CODE:</b> <code>{otp_code}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📦 <b>APP:</b> {emo(app_name)} {app_name.upper()}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"✅ <b>YOU CAN NOW USE THIS CODE</b>\n"
                f"━━━━━━━━━━━━━━━"
            )
            markup = InlineKeyboardMarkup().add(ibtn("📋 MAIN MENU", callback_data="close_menu", style="success"))
            safe_edit(chat_id, text, markup, message_id)
        else:
            # Still waiting
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(ibtn("🔄 CHECK AGAIN", callback_data=f"check_otp|{session_id}", style="primary"),
                       ibtn("❌ CANCEL", callback_data=f"cancel_session|{session_id}", style="danger"))
            markup.add(ibtn("🔙 MAIN MENU", callback_data="close_menu", style="success"))
            text = (
                f"━━━━━━━━━━━━━━━\n"
                f"《 ⏳ <b>WAITING FOR OTP</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"⏱ <b>OTP NOT RECEIVED YET</b>\n"
                f"🔄 <b>CLICK CHECK AGAIN</b>\n"
                f"━━━━━━━━━━━━━━━"
            )
            safe_edit(chat_id, text, markup, message_id)

    else:
        # Manual panel: ask user to type the OTP they received
        session["status"] = "awaiting_manual_otp"
        save_data(data)

        text = (
            f"━━━━━━━━━━━━━━━\n"
            f"《 ⌨️ <b>ENTER OTP CODE</b> 》\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"<b>PLEASE TYPE THE OTP CODE</b>\n"
            f"<b>YOU RECEIVED ON THIS NUMBER</b>\n\n"
            f"💡 <i>Example: 123456</i>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"❌ <b>TYPE /cancel to abort</b>"
        )
        markup = InlineKeyboardMarkup().add(ibtn("❌ CANCEL", callback_data=f"cancel_session|{session_id}", style="danger"))
        safe_edit(chat_id, text, markup, message_id)


# -------------------- CANCEL SESSION --------------------
def cancel_number_session(chat_id, session_id, message_id=None):
    """Cancel an active number session and optionally recycle the number."""
    data = load_data()
    session = data.get("number_session", {}).get(session_id)
    if not session:
        safe_edit(chat_id, "⚠️ SESSION NOT FOUND", get_main_menu(chat_id), message_id)
        return

    user_id = session.get("user_id")
    if user_id != chat_id and not is_main_admin(chat_id):
        safe_edit(chat_id, "⚠️ UNAUTHORIZED", get_main_menu(chat_id), message_id)
        return

    number = session.get("number", "Unknown")
    panel_id = session.get("panel_id", "")
    rng_id = session.get("rng_id", "")
    activation_id = session.get("activation_id", "")

    # For manual panels: recycle number back to available pool
    if panel_id and rng_id and str(activation_id).startswith("MANUAL_"):
        panel = data.get("panels", {}).get(panel_id)
        if panel:
            rng = panel.get("ranges", {}).get(rng_id)
            if rng:
                used = rng.get("used_numbers", [])
                if number in used:
                    used.remove(number)
                    rng["used_numbers"] = used
                    log(f"[RECYCLE] Number {number} returned to pool")

    # Remove session
    data.setdefault("number_session", {}).pop(session_id, None)
    save_data(data)

    safe_edit(chat_id, f"━━━━━━━━━━━━━━━\n《 ❌ <b>SESSION CANCELLED</b> 》\n━━━━━━━━━━━━━━━\n📱 <b>NUMBER:</b> <code>{number}</code>\n━━━━━━━━━━━━━━━\n<b>SESSION CLOSED</b>", get_main_menu(chat_id), message_id)
    # ============================================
#  PART 6 - CALLBACK QUERY HANDLERS
# ============================================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id if call.message else call.from_user.id
    message_id = call.message.message_id if call.message else None
    user_id = call.from_user.id
    data = call.data

    # ============ IGNORE & CLOSE ============
    if data == "ignore":
        bot.answer_callback_query(call.id)
        return

    if data == "close_menu":
        bot.answer_callback_query(call.id)
        show_main_menu(chat_id, call.from_user.first_name)
        return

    # ============ ADMIN CHECK ============
    if data.startswith("admin_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            safe_send(chat_id, "⚠️ <b>ACCESS DENIED</b> — <b>ADMIN ONLY</b> ⚠️")
            return
        handle_admin_callbacks(chat_id, message_id, data, call)

    # ============ USER PANEL NAVIGATION ============
    elif data == "show_numbers":
        bot.answer_callback_query(call.id)
        show_user_services(chat_id)

    elif data.startswith("usr_folder|"):
        bot.answer_callback_query(call.id)
        folder = data.split("|", 1)[1]
        show_user_folder_apps(chat_id, folder, message_id)

    elif data.startswith("usr_app|"):
        bot.answer_callback_query(call.id)
        app_name = data.split("|", 1)[1]
        show_user_countries(chat_id, app_name, message_id)

    elif data.startswith("usr_cnt|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        app_name = parts[1]
        country_key = parts[2] if len(parts) > 2 else "any"
        log(f"[USR_CNT] app={app_name}, country={country_key}")
        try:
            fetch_number_logic(chat_id, app_name, country_key, message_id)
        except Exception as e:
            log(f"[USR_CNT ERROR] {e}")
            safe_send(chat_id, f"❌ Error: {html.escape(str(e))}")

    elif data.startswith("usr_combo|"):
        bot.answer_callback_query(call.id)
        combo_name = data.split("|", 1)[1]
        fetch_combo_number(chat_id, combo_name, message_id)

    elif data.startswith("usr_svc|"):
        bot.answer_callback_query(call.id)
        service_name = data.split("|", 1)[1]
        show_user_service_countries(chat_id, service_name, message_id)

    elif data.startswith("change_num|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        app_name = parts[1] if len(parts) > 1 else ""
        country_key = parts[2] if len(parts) > 2 else "any"
        # Cancel old session - mark old number as used so it's removed from stock
        d = load_data()
        sessions = d.get("number_session", {})
        for sid, sess in list(sessions.items()):
            if sess.get("user_id") == chat_id and sess.get("app", "").upper() == app_name.upper() and sess.get("status") in ("awaiting_otp", "polling"):
                sess["status"] = "changed"
                sessions[sid] = sess
                # Permanently delete old number from stock
                for combo in d.get("combos", []):
                    if combo.get("name", "").upper() == app_name.upper():
                        num = sess.get("number", "")
                        if num in combo.get("used_numbers", []):
                            combo["used_numbers"].remove(num)
                        # Delete from numbers list permanently
                        combo["numbers"] = [n for n in combo.get("numbers", []) if n != num]
                        for cty in combo.get("countries", {}).keys():
                            combo["countries"][cty] = [n for n in combo["countries"][cty] if n != num]
                break
        d["number_session"] = sessions
        save_data(d)
        # Fetch new number instantly
        fetch_number_logic(chat_id, app_name, country_key if country_key != "any" else None, message_id)

    elif data == "back_to_user_services":
        bot.answer_callback_query(call.id)
        show_user_services(chat_id)

    # ============ OTP CHECK & SESSION ============
    elif data.startswith("check_otp|"):
        bot.answer_callback_query(call.id)
        session_id = data.split("|", 1)[1]
        poll_otp_with_status(chat_id, session_id, message_id)

    elif data.startswith("cancel_session|"):
        bot.answer_callback_query(call.id)
        session_id = data.split("|", 1)[1]
        cancel_number_session(chat_id, session_id, message_id)

    # ============ 2FA ============
    elif data == "show_2fa":
        bot.answer_callback_query(call.id)
        show_2fa_menu_display(chat_id)

    # ============ TRAFFIC ============
    elif data == "show_traffic":
        bot.answer_callback_query(call.id)
        show_traffic_info(chat_id)

    elif data == "refresh_traffic":
        bot.answer_callback_query(call.id)
        show_traffic_info(chat_id)

    # ============ STOCK INFO ============
    elif data == "show_stock":
        bot.answer_callback_query(call.id)
        show_stock_info(chat_id, message_id)

    elif data == "refresh_stock":
        bot.answer_callback_query(call.id)
        show_stock_info(chat_id, message_id)

    # ============ LEADERBOARD ============
    elif data == "show_leaderboard":
        bot.answer_callback_query(call.id)
        show_leaderboard(chat_id, message_id)

    elif data == "refresh_leaderboard":
        bot.answer_callback_query(call.id)
        show_leaderboard(chat_id, message_id)

    # ============ SUPPORT ============
    elif data == "show_support":
        bot.answer_callback_query(call.id)
        show_support(chat_id, call.from_user.first_name)

    elif data == "show_support_menu":
        bot.answer_callback_query(call.id)
        show_support_menu(chat_id, message_id)

    elif data == "open_support_ticket":
        bot.answer_callback_query(call.id)
        # Mark user as in support mode
        user_states[chat_id] = {"state": "support_message"}
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"《 📩 <b>SUPPORT TICKET</b> 》\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"<b>TYPE YOUR MESSAGE BELOW</b>\n\n"
            f"📝 <i>Write your question or issue</i>\n"
            f"✅ <b>ADMINS WILL REPLY SOON</b>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            InlineKeyboardMarkup().add(ibtn("❌ CANCEL", callback_data="cancel_support", style="danger")))

    elif data == "cancel_support":
        bot.answer_callback_query(call.id)
        user_states.pop(chat_id, None)
        show_main_menu(chat_id, call.from_user.first_name)

    # ============ REFERRALS ============
    elif data == "show_referrals":
        bot.answer_callback_query(call.id)
        show_referrals(chat_id)

    # ============ BALANCE / WITHDRAW ============
    elif data == "show_balance":
        bot.answer_callback_query(call.id)
        data_obj = load_data()
        bal = data_obj.get("balances", {}).get(str(chat_id), 0.0)
        markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"《 💰 <b>YOUR BALANCE</b> 》\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"💵 <b>CURRENT BALANCE:</b> <b>${bal:.4f}</b>\n\n"
            f"👥 <b>REFER FRIENDS TO EARN!</b>\n"
            f"💲 <b>$0.001 PER REFERRAL</b>\n"
            f"━━━━━━━━━━━━━━━",
            markup, message_id)

    elif data == "show_withdraw":
        bot.answer_callback_query(call.id)
        data_obj = load_data()
        bal = data_obj.get("balances", {}).get(str(chat_id), 0.0)
        if bal < 1.0:
            markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
            safe_edit(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"《 💳 <b>WITHDRAWAL</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"💰 <b>BALANCE:</b> ${bal:.4f}\n"
                f"⚠️ <b>MINIMUM WITHDRAWAL: $1.00</b>\n\n"
                f"<b>EARN MORE VIA REFERRALS!</b>\n"
                f"━━━━━━━━━━━━━━━",
                markup, message_id)
        else:
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(ibtn("💳 REQUEST WITHDRAWAL", callback_data="request_withdraw", style="success"))
            markup.add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
            safe_edit(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"《 💳 <b>WITHDRAWAL</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"💰 <b>YOUR BALANCE:</b> ${bal:.4f}\n"
                f"✅ <b>MINIMUM: ${min_wd:.2f}</b>\n\n"
                f"<b>TAP BELOW TO REQUEST</b>\n"
                f"━━━━━━━━━━━━━━━",
                markup, message_id)

    # ============ 2FA SUB-MENU ============
    elif data == "2fa_generate":
        bot.answer_callback_query(call.id)
        user_states[chat_id] = {"state": "2fa_key"}
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"《 🔐 <b>2FA GENERATE</b> 》\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"<b>ENTER YOUR 2FA SECRET KEY</b>\n\n"
            f"💡 <i>Paste the secret from the service</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            InlineKeyboardMarkup().add(ibtn("❌ CANCEL", callback_data="cancel_2fa", style="danger")))

    elif data == "2fa_back":
        bot.answer_callback_query(call.id)
        show_main_menu(chat_id, call.from_user.first_name)

    elif data == "cancel_2fa":
        bot.answer_callback_query(call.id)
        user_states.pop(chat_id, None)
        show_main_menu(chat_id, call.from_user.first_name)

    # ============ PANEL NAVIGATION ============
    elif data.startswith("panel_view|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        show_panel_detail(chat_id, panel_id, message_id)

    elif data.startswith("panel_ranges|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        show_panel_ranges(chat_id, panel_id, message_id)

    elif data.startswith("view_range|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        parts = data.split("|")
        panel_id = parts[1]
        rng_id = parts[2]
        show_range_detail(chat_id, panel_id, rng_id, message_id)

    elif data.startswith("panel_format|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        show_panel_format_menu(chat_id, panel_id, message_id)

    elif data.startswith("panel_test|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        admin_test_panel_connection(chat_id, panel_id, message_id)

    elif data.startswith("panel_toggle|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        data = load_data()
        panel = data.get("panels", {}).get(panel_id)
        if not panel:
            return
        panel["status"] = "inactive" if panel.get("status") == "active" else "active"
        save_data(data)
        show_panel_detail(chat_id, panel_id, message_id)

    elif data.startswith("panel_delete|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        delete_panel(chat_id, panel_id, message_id)

    elif data.startswith("panel_rename|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        user_states[chat_id] = {"state": "rename_panel", "panel_id": panel_id}
        safe_edit(chat_id, f"✏️ <b>NEW NAME FOR PANEL:</b>\n<i>Send the new name</i>", None, message_id)
        safe_send(chat_id, "📝 <b>TYPE THE NEW PANEL NAME:</b>\n❌ /cancel to cancel")

    elif data.startswith("panel_setcreds|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        user_states[chat_id] = {"state": "set_api_key", "panel_id": panel_id}
        safe_edit(chat_id, f"🔑 <b>ENTER NEW API KEY FOR PANEL:</b>\n<i>Send the API key</i>", None, message_id)
        safe_send(chat_id, "🔑 <b>TYPE THE API KEY:</b>\n❌ /cancel to cancel")

    elif data.startswith("panel_setlogin|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        user_states[chat_id] = {"state": "set_login_url", "panel_id": panel_id}
        safe_edit(chat_id, f"🔐 <b>ENTER LOGIN URL:</b>\n<i>Send the login page URL</i>", None, message_id)
        safe_send(chat_id, "🌐 <b>TYPE THE LOGIN URL:</b>\n❌ /cancel to cancel")

    elif data.startswith("panel_switch|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        switch_panel_type(chat_id, panel_id, message_id)

    elif data.startswith("panel_custom_ep|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        user_states[chat_id] = {"state": "custom_endpoints", "panel_id": panel_id, "ep_step": 0, "endpoints": {}}
        safe_edit(chat_id, "🔧 <b>ENTER CUSTOM FETCH URL:</b>\n<i>Full URL with {api_key}, {country}, {service} placeholders</i>", None, message_id)
        safe_send(chat_id, "🌐 <b>TYPE CUSTOM FETCH URL:</b>\n❌ /cancel to cancel")

    elif data.startswith("set_pfmt|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        parts = data.split("|")
        panel_id = parts[1]
        fmt = parts[2]
        d = load_data()
        panel_obj = d.get("panels", {}).get(panel_id)
        if panel_obj:
            panel_obj["api_format"] = fmt
            save_data(d)
            bot.answer_callback_query(call.id, f"✅ Format set to {fmt.upper()}")
            show_panel_detail(chat_id, panel_id, message_id)

    elif data.startswith("add_nums|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        parts = data.split("|")
        panel_id = parts[1]
        rng_id = parts[2]
        user_states[chat_id] = {"state": "add_numbers_txt", "panel_id": panel_id, "rng_id": rng_id}
        safe_send(chat_id, f"📄 <b>SEND A .TXT FILE</b> containing numbers (one per line)\n<b>OR TYPE numbers separated by newlines</b>\n\n❌ /cancel to cancel")

    elif data.startswith("del_range|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        parts = data.split("|")
        panel_id = parts[1]
        rng_id = parts[2]
        d = load_data()
        if panel_id in d.get("panels", {}):
            d["panels"][panel_id].get("ranges", {}).pop(rng_id, None)
            save_data(d)
            bot.answer_callback_query(call.id, "🗑 Range deleted!")
        show_panel_ranges(chat_id, panel_id, message_id)

    elif data.startswith("add_range|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        panel_id = data.split("|", 1)[1]
        user_states[chat_id] = {"state": "add_range", "panel_id": panel_id, "step": "country"}
        safe_send(chat_id, "🌍 <b>ENTER COUNTRY NAME:</b>\n<i>e.g. United Kingdom, Russia, USA</i>\n\n❌ /cancel to cancel")

    elif data.startswith("del_app|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        app_name = data.split("|", 1)[1]
        d = load_data()
        apps = d.get("apps", [])
        # Remove all instances of this app name (handles both old and new format)
        new_apps = []
        for app in apps:
            if isinstance(app, str):
                if app != app_name:
                    new_apps.append(app)
            elif isinstance(app, dict):
                if app.get("name", "").upper() != app_name.upper():
                    new_apps.append(app)
        d["apps"] = new_apps
        save_data(d)
        bot.answer_callback_query(call.id, f"❌ {app_name} removed!")
        show_app_list(chat_id, message_id)

    elif data.startswith("del_combo|"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        try:
            combo_idx = int(data.split("|", 1)[1])
        except (ValueError, IndexError):
            return
        d = load_data()
        combos = d.get("combos", [])
        if 0 <= combo_idx < len(combos):
            removed_name = combos[combo_idx].get("name", f"Combo {combo_idx}")
            combos.pop(combo_idx)
            d["combos"] = combos
            save_data(d)
            bot.answer_callback_query(call.id, f"\u274c {removed_name} deleted!")
        else:
            bot.answer_callback_query(call.id, "\u274c Combo not found")
        show_app_list(chat_id, message_id)

    elif data == "add_combo":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "add_combo_appname"}
        safe_send(chat_id, "📱 <b>ENTER APP/SERVICE NAME:</b>\n<i>e.g. PayPal, WhatsApp, Telegram</i>\n\n📄 Then send a <b>.txt</b> or <b>.csv</b> file\n<i>Numbers auto-extracted from any format</i>\n\n❌ /cancel to cancel")

    elif data == "add_app":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "add_app_folder"}
        safe_send(chat_id, "📁 <b>ENTER FOLDER NAME:</b>\n<i>e.g. Social Media, Ride Sharing, Banking</i>\n\n❌ /cancel to cancel")

    elif data == "admin_manage_panels":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_panel_list(chat_id, message_id)

    elif data == "admin_manage_apps":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_app_list(chat_id, message_id)

    elif data == "admin_system":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_admin_system(chat_id, message_id)

    elif data == "admin_broadcast":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_broadcast_targeted(chat_id)

    elif data == "admin_group_settings":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        markup = get_group_settings_menu()
        safe_edit(chat_id, "📢 <b>OTP GROUP SETTINGS</b>", markup, message_id)

    elif data == "admin_force_join":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        markup = get_force_join_menu()
        safe_edit(chat_id, "🔗 <b>FORCE JOIN SETTINGS</b>", markup, message_id)

    elif data == "admin_set_watermark":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_watermark"}
        safe_send(chat_id, "📝 <b>ENTER NEW WATERMARK TEXT:</b>\n<i>e.g. NUMBER OTP</i>\n\n❌ /cancel to cancel")

    elif data == "admin_manage_balances":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        balances = d.get("balances", {})
        text = "━━━━━━━━━━━━━━━\n《 💰 <b>BALANCES</b> 》\n━━━━━━━━━━━━━━━\n\n"
        if balances:
            for uid, bal in sorted(balances.items(), key=lambda x: x[1], reverse=True)[:15]:
                text += f"🆔 <code>{uid}</code> — <b>${bal:.4f}</b>\n"
        else:
            text += "<b>No balances found.</b>"
        text += "\n━━━━━━━━━━━━━━━"
        markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
        safe_edit(chat_id, text, markup, message_id)

    elif data == "admin_add_balance":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "admin_add_balance"}
        safe_send(chat_id, "💰 <b>ADD BALANCE TO USER</b>\n\nEnter in format: <code>USER_ID AMOUNT</code>\n<i>e.g. 123456789 5.00</i>\n\n❌ /cancel to cancel")

    elif data == "admin_maintenance":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        current = d.get("maintenance", False)
        d["maintenance"] = not current
        save_data(d)
        status = "🟢 ENABLED" if d["maintenance"] else "🔴 DISABLED"
        bot.answer_callback_query(call.id, f"Maintenance: {status}")
        show_admin_system(chat_id, message_id)

    elif data == "admin_manage_admins":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_manage_admins(chat_id, message_id)

    elif data == "add_panel":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "add_panel_name"}
        safe_send(chat_id, "📋 <b>ENTER PANEL NAME:</b>\n<i>e.g. Main API, Backup Panel</i>\n\n❌ /cancel to cancel")

    # ============ ADMIN USER VIEW ============
    elif data == "admin_user_view":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_user_view(chat_id, message_id)

    elif data == "uv_profile":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "uv_profile_lookup"}
        safe_send(chat_id, "👤 <b>ENTER USER ID OR USERNAME:</b>\n<i>e.g. 123456789 or @username</i>\n\n❌ /cancel to cancel")

    elif data == "uv_ban_menu":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_ban_unban_menu(chat_id, message_id)

    elif data == "uv_ban_do":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "ban_user"}
        safe_send(chat_id, "🔨 <b>ENTER USER ID TO BAN:</b>\n<i>e.g. 123456789</i>\n\n❌ /cancel to cancel")

    elif data == "uv_unban_list":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_unban_list(chat_id, message_id)

    elif data.startswith("unban_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        uid = data.split("_", 1)[1]
        d = load_data()
        banned = d.get("banned_users", [])
        if uid in banned:
            banned.remove(uid)
            d["banned_users"] = banned
            save_data(d)
            bot.answer_callback_query(call.id, f"♻️ User {uid} unbanned!")
        show_unban_list(chat_id, message_id)

    # ============ ADMIN SYSTEM ACTIONS ============
    elif data == "sys_cooldown":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_cooldown"}
        safe_send(chat_id, "⏳ <b>ENTER COOLDOWN (seconds):</b>\n<i>e.g. 30, 60, 120</i>\n\n❌ /cancel to cancel")

    elif data == "sys_num_per_req":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_num_per_req"}
        safe_send(chat_id, "📱 <b>ENTER MAX NUMBERS PER REQUEST:</b>\n<i>e.g. 5, 10, 20</i>\n\n❌ /cancel to cancel")

    elif data == "sys_price":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_price"}
        safe_send(chat_id, "💲 <b>ENTER PRICE PER OTP (USD):</b>\n<i>e.g. 0.001, 0.01, 0.10</i>\n\n❌ /cancel to cancel")

    elif data == "sys_support":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_support_link"}
        safe_send(chat_id, "🔗 <b>ENTER SUPPORT LINK:</b>\n<i>e.g. https://t.me/YOUR_USERNAME</i>\n\n❌ /cancel to cancel")

    elif data == "sys_watermark":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_watermark"}
        safe_send(chat_id, "📝 <b>ENTER NEW WATERMARK TEXT:</b>\n<i>e.g. NUMBER OTP</i>\n\n❌ /cancel to cancel")

    elif data == "sys_force_join":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        fg = d.get("force_join_groups", [])
        text_lines = ["━━━━━━━━━━━━━━━",
                       "《 🔗 <b>FORCE JOIN</b> 》",
                       "━━━━━━━━━━━━━━━"]
        if fg:
            for i, g in enumerate(fg, 1):
                lnk = g.get("link", "N/A")
                title = g.get("title", f"Group {i}")
                text_lines.append(f"{i}. {title}")
                text_lines.append(f"   🔗 {lnk}")
        else:
            text_lines.append("<b>No force-join groups set.</b>")
        text_lines.append("━━━━━━━━━━━━━━━")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(ibtn("➕ ADD GROUP", callback_data="fj_add", style="success"),
                   ibtn("❌ REMOVE GROUP", callback_data="fj_remove_list", style="danger"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_system", style="primary"))
        safe_edit(chat_id, "\n".join(text_lines), markup, message_id)

    elif data == "sys_forward_groups":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        fg = d.get("forward_groups", [])
        text_lines = ["━━━━━━━━━━━━━━━",
                       "《 📢 <b>OTP FORWARD GROUPS</b> 》",
                       "━━━━━━━━━━━━━━━"]
        if fg:
            for i, g in enumerate(fg, 1):
                text_lines.append(f"{i}. CHAT ID: <code>{g}</code>")
        else:
            text_lines.append("<b>No forward groups set.</b>")
        text_lines.append("━━━━━━━━━━━━━━━")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(ibtn("➕ ADD GROUP", callback_data="fg_add", style="success"),
                   ibtn("❌ REMOVE GROUP", callback_data="fg_remove_list", style="danger"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_system", style="primary"))
        safe_edit(chat_id, "\n".join(text_lines), markup, message_id)

    elif data == "sys_broadcast":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "broadcast_msg"}
        safe_send(chat_id, "📢 <b>ENTER MESSAGE TO BROADCAST:</b>\n<i>All users will receive this</i>\n\n❌ /cancel to cancel")

    elif data == "sys_manage_admins":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_manage_admins(chat_id, message_id)

    elif data.startswith("deladm_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        adm_id = data.split("_", 1)[1]
        d = load_data()
        admins = d.get("extra_admins", [])
        try:
            adm_id_int = int(adm_id)
            if adm_id_int in admins:
                admins.remove(adm_id_int)
                d["extra_admins"] = admins
                save_data(d)
                bot.answer_callback_query(call.id, f"👮 Admin {adm_id} removed!")
        except ValueError:
            pass
        show_manage_admins(chat_id, message_id)

    elif data == "add_new_admin":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "add_admin_id"}
        safe_send(chat_id, "👮 <b>ENTER USER ID TO ADD AS ADMIN:</b>\n<i>e.g. 123456789</i>\n\n❌ /cancel to cancel")

    # ============ FORCE JOIN / FORWARD GROUP SUB-MENUS ============
    elif data == "fj_add":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "fj_add_link"}
        safe_send(chat_id, "🔗 <b>ENTER GROUP INVITE LINK:</b>\n<i>e.g. https://t.me/MyGroup</i>\n\n❌ /cancel to cancel")

    elif data == "fj_remove_list":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        fg = d.get("force_join_groups", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for idx, g in enumerate(fg):
            title = g.get("title", f"Group {idx+1}")
            markup.add(ibtn(f"❌ {title}", callback_data=f"fj_del_{idx}", style="danger"))
        markup.add(ibtn("🔙 BACK", callback_data="sys_force_join", style="primary"))
        safe_edit(chat_id, "━━━━━━━━━━━━━━━\n《 ❌ <b>REMOVE FORCE-JOIN GROUP</b> 》\n━━━━━━━━━━━━━━━\n<b>SELECT GROUP TO REMOVE:</b>", markup, message_id)

    elif data.startswith("fj_del_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        idx = int(data.split("_", 2)[2])
        d = load_data()
        fg = d.get("force_join_groups", [])
        if 0 <= idx < len(fg):
            fg.pop(idx)
            d["force_join_groups"] = fg
            save_data(d)
            bot.answer_callback_query(call.id, "✅ Group removed!")
        show_admin_system(chat_id, message_id)

    elif data == "fg_add":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "fg_add_id"}
        safe_send(chat_id, "📢 <b>ENTER GROUP CHAT ID:</b>\n<i>e.g. -1001234567890</i>\n\n❌ /cancel to cancel")

    elif data == "fg_remove_list":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        fg = d.get("forward_groups", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for idx, g in enumerate(fg):
            markup.add(ibtn(f"❌ {g}", callback_data=f"fg_del_{idx}", style="danger"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_system", style="primary"))
        safe_edit(chat_id, "━━━━━━━━━━━━━━━\n《 ❌ <b>REMOVE FORWARD GROUP</b> 》\n━━━━━━━━━━━━━━━\n<b>SELECT GROUP TO REMOVE:</b>", markup, message_id)

    elif data.startswith("fg_del_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        idx = int(data.split("_", 2)[2])
        d = load_data()
        fg = d.get("forward_groups", [])
        if 0 <= idx < len(fg):
            fg.pop(idx)
            d["forward_groups"] = fg
            save_data(d)
            bot.answer_callback_query(call.id, "✅ Group removed!")
        show_admin_system(chat_id, message_id)

    elif data in ["admin_system", "back_to_admin_system"]:
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_admin_system(chat_id, message_id)

    elif data == "admin_services":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_services_menu(chat_id)

    elif data == "admin_blacklist":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_blacklist_menu(chat_id)

    elif data == "admin_anti_spam":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_anti_spam_toggle(chat_id)

    elif data == "admin_stats":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_full_stats(chat_id)

    elif data == "admin_all_users":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_all_users(chat_id)

    elif data == "admin_stock_summary":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_stock_summary(chat_id)

    elif data == "admin_all_numbers":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_all_numbers(chat_id)

    elif data == "admin_withdrawal_history":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_admin_withdrawal_history(chat_id)

    elif data == "admin_total_balances":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_total_balances(chat_id)

    elif data == "admin_add_all_bonus":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_add_all_bonus(chat_id)

    elif data == "admin_deduct_all_fee":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_deduct_all_fee(chat_id)

    elif data == "admin_maint_msg":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_set_maintenance_msg(chat_id)

    elif data == "admin_otp_monitor":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        toggle_otp_monitoring(chat_id)

    elif data == "admin_toggle_otp_mon":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        toggle_otp_monitoring(chat_id)

    elif data == "admin_test_otp_mon":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        test_otp_monitoring(chat_id)

    elif data == "admin_export_numbers":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_export_numbers(chat_id)

    elif data == "admin_expire_numbers":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_expire_numbers(chat_id)

    elif data == "release_all_rented":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        release_all_rented(chat_id)

    elif data.startswith("broadcast_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        if data == "broadcast_all":
            user_states[chat_id] = {"state": "broadcast_msg", "target": "all"}
            safe_send(chat_id, "📢 <b>BROADCAST TO ALL</b>\nEnter message:\n\n❌ /cancel to cancel")
        elif data == "broadcast_active":
            user_states[chat_id] = {"state": "broadcast_msg", "target": "active"}
            safe_send(chat_id, "📢 <b>BROADCAST TO ACTIVE</b>\nEnter message:\n\n❌ /cancel to cancel")
        elif data == "broadcast_specific":
            user_states[chat_id] = {"state": "broadcast_specific"}
            safe_send(chat_id, "💬 <b>SEND TO USER</b>\nEnter: USER_ID Message\n\n❌ /cancel to cancel")
        elif data == "broadcast_by_balance":
            user_states[chat_id] = {"state": "broadcast_by_balance"}
            safe_send(chat_id, "💰 <b>MIN BALANCE (USD):</b>\n\n❌ /cancel to cancel")

    elif data == "back_to_admin":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_admin_panel(chat_id, message_id)

    elif data == "admin_refresh":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_admin_panel(chat_id, message_id)

    # ============ FORCE JOIN MANAGEMENT ============
    elif data == "check_join":
        bot.answer_callback_query(call.id)
        ok, group = check_force_join(chat_id)
        if ok:
            show_main_menu(chat_id, call.from_user.first_name)
        else:
            show_force_join_message(chat_id, message_id)

    elif data == "toggle_force_join":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        d["force_join_enabled"] = not d.get("force_join_enabled", False)
        save_data(d)
        show_force_join_menu(chat_id, message_id)

    elif data == "add_fjc":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "fj_add_link"}
        safe_send(chat_id, "🔗 <b>ENTER CHANNEL/GROUP LINK:</b>\n<i>e.g. https://t.me/MyChannel</i>\n\n❌ /cancel to cancel")

    elif data.startswith("delfjc_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        idx = int(data.split("_", 1)[1])
        d = load_data()
        channels = d.get("force_join_channels", [])
        if 0 <= idx < len(channels):
            channels.pop(idx)
            d["force_join_channels"] = channels
            save_data(d)
            bot.answer_callback_query(call.id, "✅ Channel removed!")
        show_force_join_menu(chat_id, message_id)

    # ============ OTP GROUP MANAGEMENT ============
    elif data == "set_main_otp_link":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "set_main_otp_link"}
        safe_send(chat_id, "🔗 <b>ENTER OTP GROUP LINK:</b>\n<i>e.g. https://t.me/+ invite link</i>\n\n❌ /cancel to cancel")

    elif data == "del_main_otp_link":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        d["main_otp_link"] = ""
        save_data(d)
        bot.answer_callback_query(call.id, "🗑 OTP link removed!")
        get_group_settings_menu()

    elif data == "add_fwd_group":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        user_states[chat_id] = {"state": "fg_add_id"}
        safe_send(chat_id, "📢 <b>ENTER GROUP CHAT ID:</b>\n<i>e.g. -1001234567890</i>\n\n❌ /cancel to cancel")

    # ============ WITHDRAWAL REQUEST ============
    elif data == "request_withdraw":
        bot.answer_callback_query(call.id)
        data_obj = load_data()
        bal = data_obj.get("balances", {}).get(str(chat_id), 0.0)
        if bal < 1.0:
            bot.answer_callback_query(call.id, "❌ Minimum withdrawal is $1.00", show_alert=True)
            return
        user_states[chat_id] = {"state": "withdraw_amount"}
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"《 💳 <b>WITHDRAWAL REQUEST</b> 》\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"💰 <b>BALANCE:</b> ${bal:.4f}\n\n"
            f"<b>ENTER AMOUNT TO WITHDRAW (USD):</b>\n"
            f"<i>e.g. 1.50, 5.00, 10.00</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            InlineKeyboardMarkup().add(ibtn("❌ CANCEL", callback_data="cancel_withdraw", style="danger")),
            message_id)

    elif data == "cancel_withdraw":
        bot.answer_callback_query(call.id)
        user_states.pop(chat_id, None)
        show_main_menu(chat_id, call.from_user.first_name)

    elif data.startswith("approve_wd_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        wd_id = data.split("_", 2)[2]
        d = load_data()
        for wd in d.get("withdrawal_requests", []):
            if wd.get("id") == wd_id and wd.get("status") == "pending":
                wd["status"] = "approved"
                save_data(d)
                try:
                    bot.send_message(wd["user_id"],
                        f"✅ <b>WITHDRAWAL APPROVED!</b>\n\n"
                        f"💰 <b>AMOUNT:</b> ${wd['amount']:.2f}\n"
                        f"🏦 <b>METHOD:</b> {wd.get('payment_method', 'N/A')}\n"
                        f"📱 <b>PHONE:</b> <code>{wd.get('phone', 'N/A')}</code>\n\n"
                        f"<b>CONTACT ADMIN TO RECEIVE FUNDS</b>",
                        parse_mode="HTML")
                except:
                    pass
                bot.answer_callback_query(call.id, "✅ Withdrawal approved!")
                # Update the admin message
                try:
                    bot.edit_message_text(
                        f"✅ <b>WITHDRAWAL APPROVED</b>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"👤 <a href='tg://user?id={wd['user_id']}'>{html.escape(wd.get('full_name', 'User'))}</a>\n"
                        f"💰 <b>${wd['amount']:.2f}</b> → ${wd.get('amount_ngn', 0):.0f} NGN\n"
                        f"🏦 {wd.get('payment_method', 'N/A')} | 📱 <code>{wd.get('phone', '')}</code>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"✅ <b>APPROVED BY ADMIN</b>",
                        chat_id, call.message.message_id, parse_mode="HTML")
                except:
                    pass
                return
        bot.answer_callback_query(call.id, "❌ Withdrawal not found or already processed")

    elif data.startswith("reject_wd_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        wd_id = data.split("_", 2)[2]
        d = load_data()
        for wd in d.get("withdrawal_requests", []):
            if wd.get("id") == wd_id and wd.get("status") == "pending":
                wd["status"] = "rejected"
                # Refund the balance
                uid = str(wd["user_id"])
                d.setdefault("balances", {})[uid] = d.get("balances", {}).get(uid, 0.0) + wd["amount"]
                save_data(d)
                try:
                    bot.send_message(wd["user_id"],
                        f"❌ <b>WITHDRAWAL REJECTED</b>\n\n"
                        f"💰 <b>AMOUNT:</b> ${wd['amount']:.2f}\n"
                        f"<b>Your balance has been refunded.</b>\n"
                        f"<b>Contact support for details.</b>",
                        parse_mode="HTML")
                except:
                    pass
                bot.answer_callback_query(call.id, "❌ Withdrawal rejected & refunded")
                try:
                    bot.edit_message_text(
                        f"❌ <b>WITHDRAWAL REJECTED</b>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"👤 <a href='tg://user?id={wd['user_id']}'>{html.escape(wd.get('full_name', 'User'))}</a>\n"
                        f"💰 <b>${wd['amount']:.2f}</b> refunded\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"❌ <b>REJECTED BY ADMIN</b>",
                        chat_id, call.message.message_id, parse_mode="HTML")
                except:
                    pass
                return
        bot.answer_callback_query(call.id, "❌ Withdrawal not found or already processed")

    # ============ WITHDRAWAL PAYMENT METHOD ============
    elif data.startswith("wdmethod_"):
        bot.answer_callback_query(call.id)
        method = data.split("_", 1)[1]
        state = user_states.get(chat_id)
        if not state or state.get("state") != "withdraw_method":
            return
        amount = state.get("amount", 0)
        user_states[chat_id] = {"state": "withdraw_name", "amount": amount, "payment_method": method}
        method_names = {"opay": "OPay", "palmpay": "PalmPay", "usdt": "USDT BEP20"}
        safe_send(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"💳 <b>WITHDRAWAL: ${amount:.2f}</b>\n"
            f"🏦 <b>METHOD: {method_names.get(method, method)}</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>ENTER YOUR FULL NAME:</b>\n"
            f"<i>As it appears on your account (min 10 chars)</i>\n"
            f"<i>e.g. John Michael Smith</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>")

    # ============ ADMIN REPLY TO USER ============
    elif data.startswith("reply_user_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        target_user_id = int(data.split("_", 2)[2])
        user_states[chat_id] = {"state": "admin_reply", "target_user": target_user_id}
        safe_edit(chat_id,
            f"💬 <b>REPLY TO USER</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🆔 <b>USER ID:</b> <code>{target_user_id}</code>\n\n"
            f"<b>TYPE YOUR MESSAGE BELOW:</b>\n"
            f"❌ <b>Type /cancel to cancel</b>",
            None, message_id)

    # ============ ADMIN SET MIN WITHDRAW ============
    elif data == "admin_set_min_withdraw":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        current = load_data().get("min_withdraw", 1.0)
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"💲 <b>SET MINIMUM WITHDRAWAL</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"📊 <b>Current minimum:</b> ${current:.2f}\n\n"
            f"Enter the new minimum withdrawal amount in USD\n"
            f"<i>e.g. 0.50, 1.00, 2.00</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "set_min_withdraw"}

    # ============ ADMIN VIEW MEMBER BOT ============
    elif data == "admin_view_member_bot":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"🤖 <b>VIEW MEMBER BOT</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"Enter the <b>User ID</b> or <b>@username</b> of the member\n"
            f"to view their bot activity and details.\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "admin_view_member_bot_lookup"}

    # ============ ADMIN CLEAN BALANCES ============
    elif data == "admin_clean_balances":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        clean_date = d.get("balance_clean_date", "")
        total_bal = sum(d.get("balances", {}).values())
        msg = (
            f"━━━━━━━━━━━━━━━\n"
            f"🧹 <b>CLEAN BALANCES</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"💰 <b>Total balances:</b> ${total_bal:.4f}\n"
            f"👥 <b>Members with balance:</b> {len([b for b in d.get('balances', {}).values() if b > 0])}\n"
        )
        if clean_date:
            msg += f"📅 <b>Scheduled clean:</b> {clean_date}\n"
        msg += f"\n⚠️ <b>This will reset ALL member balances to $0.00</b>"
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(ibtn("⚡ CLEAN NOW", callback_data="clean_balances_now", style="danger"),
                   ibtn("📅 SET DATE", callback_data="clean_balances_set_date", style="success"))
        markup.add(ibtn("🗑️ REMOVE SCHEDULE", callback_data="clean_balances_remove", style="primary"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id, msg, markup, message_id)

    # ============ ADMIN WITHDRAW STATS ============
    elif data == "admin_withdraw_stats":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        wds = d.get("withdrawal_requests", [])
        pending = [w for w in wds if w.get("status") == "pending"]
        approved = [w for w in wds if w.get("status") == "approved"]
        rejected = [w for w in wds if w.get("status") == "rejected"]
        total_pending_usd = sum(w.get("amount", 0) for w in pending)
        total_approved_usd = sum(w.get("amount", 0) for w in approved)
        total_rejected_usd = sum(w.get("amount", 0) for w in rejected)
        total_all_usd = total_pending_usd + total_approved_usd + total_rejected_usd
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("📋 VIEW PENDING", callback_data="view_pending_wd", style="primary"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"📊 <b>WITHDRAWAL & PAYMENT STATS</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"⏳ <b>Pending:</b> {len(pending)} requests (${total_pending_usd:.2f})\n"
            f"✅ <b>Approved:</b> {len(approved)} requests (${total_approved_usd:.2f})\n"
            f"❌ <b>Rejected:</b> {len(rejected)} requests (${total_rejected_usd:.2f})\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 <b>Total All:</b> {len(wds)} requests (${total_all_usd:.2f})\n"
            f"━━━━━━━━━━━━━━━",
            markup, message_id)

    # ============ VIEW PENDING WITHDRAWALS ============
    elif data == "view_pending_wd":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        pending = [w for w in d.get("withdrawal_requests", []) if w.get("status") == "pending"]
        if not pending:
            safe_edit(chat_id, "✅ <b>No pending withdrawals!</b>", None, message_id)
            return
        text = "━━━━━━━━━━━━━━━\n⏳ <b>PENDING WITHDRAWALS</b>\n━━━━━━━━━━━━━━━\n\n"
        for w in pending[:15]:
            uid = w.get("user_id", "?")
            amt = w.get("amount", 0)
            method = w.get("payment_method", "opay").upper()
            wd_id = w.get("id", "?")
            text += f"🆔 <code>{wd_id}</code> | 👤 <code>{uid}</code> | 💰 ${amt:.2f} | 🏦 {method}\n"
        if len(pending) > 15:
            text += f"\n... and {len(pending) - 15} more"
        markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="admin_withdraw_stats", style="primary"))
        safe_edit(chat_id, text, markup, message_id)

    # ============ CLEAN BALANCES NOW ============
    elif data == "clean_balances_now":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        user_count = 0
        for uid in d.get("users", []):
            try:
                bot.send_message(uid, "🧹 <b>ALL BALANCES HAVE BEEN CLEANED</b>\n\nAll member balances have been reset to $0.00 by admin.", parse_mode="HTML")
                user_count += 1
                time.sleep(0.05)
            except Exception:
                pass
        d["balances"] = {}
        d["balance_clean_date"] = ""
        d["balance_clean_amount"] = 0.0
        save_data(d)
        safe_edit(chat_id, f"✅ <b>BALANCES CLEANED!</b>\n👥 Notified: {user_count} users\n💰 All balances reset to $0.00", None, message_id)

    # ============ CLEAN BALANCES SET DATE ============
    elif data == "clean_balances_set_date":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_clean_balances", style="primary"))
        safe_edit(chat_id,
            "━━━━━━━━━━━━━━━\n"
            "📅 <b>SET BALANCE CLEAN DATE</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Enter the date for automatic balance clean:\n"
            "<i>Format: YYYY-MM-DD</i>\n"
            "<i>e.g. 2026-09-15</i>\n\n"
            "❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "set_balance_clean_date"}

    # ============ CLEAN BALANCES REMOVE ============
    elif data == "clean_balances_remove":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        d["balance_clean_date"] = ""
        d["balance_clean_amount"] = 0.0
        save_data(d)
        safe_edit(chat_id, "✅ <b>SCHEDULE REMOVED!</b>\nNo automatic balance clean scheduled.", None, message_id)

    # ============ ADMIN BACK ============
    elif data == "admin_back":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        show_admin_panel(chat_id, message_id)

    # ============ ADMIN TOGGLE FORCE JOIN ============
    elif data == "admin_toggle_force_join":
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        d = load_data()
        d["force_join_enabled"] = not d.get("force_join_enabled", False)
        save_data(d)
        status = "✅ ENABLED" if d["force_join_enabled"] else "❌ DISABLED"
        bot.answer_callback_query(call.id, f"Force Join: {status}")
        markup = get_force_join_menu()
        safe_edit(chat_id, "🔗 <b>FORCE JOIN SETTINGS</b>", markup, message_id)

    # ============ DEDUCT BALANCE ============
    elif data.startswith("deduct_bal_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        target_id = int(data.split("_")[2])
        d = load_data()
        current_bal = d.get("balances", {}).get(str(target_id), 0.0)
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"💰 <b>DEDUCT BALANCE</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>User:</b> <code>{target_id}</code>\n"
            f"💰 <b>Current Balance:</b> ${current_bal:.4f}\n\n"
            f"Enter the amount to deduct (in USD):\n"
            f"<i>e.g. 0.50, 1.00</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "deduct_member_balance", "target_user_id": target_id}

    # ============ ADD BALANCE ============
    elif data.startswith("add_bal_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        target_id = int(data.split("_")[2])
        d = load_data()
        current_bal = d.get("balances", {}).get(str(target_id), 0.0)
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"➕ <b>ADD BALANCE</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>User:</b> <code>{target_id}</code>\n"
            f"💰 <b>Current Balance:</b> ${current_bal:.4f}\n\n"
            f"Enter the amount to add (in USD):\n"
            f"<i>e.g. 0.50, 1.00</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "add_member_balance", "target_user_id": target_id}

    # ============ PANEL TYPE PICKER ============
    elif data.startswith("ptype_"):
        bot.answer_callback_query(call.id)
        if not is_admin(chat_id):
            return
        parts = data.split("|")
        if len(parts) < 2:
            return
        ptype = parts[0].replace("ptype_", "")
        pid = parts[1]
        d = load_data()
        p = d.get("panels", {}).get(pid)
        if not p:
            return
        panel_type = "agent" if "agent" in ptype else "client"
        p["type"] = "scraped"
        p["panel_type"] = panel_type
        p["fetch_type"] = "scraped"
        save_data(d)
        bot.answer_callback_query(call.id, f"✅ {panel_type.upper()} Panel")
        user_states[chat_id] = {"state": "scraped_panel_user", "panel_id": pid}
        safe_send(chat_id,
            f"✅ <b>Type:</b> {panel_type.upper()}\n\n"
            f"👤 <b>ENTER USERNAME:</b>\n"
            f"<i>Login username for the panel</i>\n\n"
            f"❌ /cancel to cancel")

    # ============ FALLBACK ============
    else:
        bot.answer_callback_query(call.id, f"Unknown: {data[:20]}")
        log(f"[CALLBACK] Unhandled: {data}")
# ============================================
#  PART 7 (FINAL) - ADMIN CALLBACKS, MESSAGE HANDLERS, MAIN
# ============================================

# -------------------- ADMIN CALLBACK DISPATCH --------------------
def handle_admin_callbacks(chat_id, message_id, data, call):
    if data == "admin_manage_panels":
        show_panel_list(chat_id, message_id)
    elif data == "admin_manage_apps":
        show_app_list(chat_id, message_id)
    elif data == "admin_system":
        show_admin_system(chat_id, message_id)
    elif data == "admin_user_view":
        show_user_view(chat_id, message_id)
    elif data == "admin_refresh":
        show_admin_panel(chat_id, message_id)
    elif data == "admin_broadcast":
        user_states[chat_id] = {"state": "broadcast_msg"}
        safe_send(chat_id, "📢 <b>ENTER MESSAGE TO BROADCAST:</b>\n<i>All users will receive this</i>\n\n❌ /cancel to cancel")
    elif data == "admin_group_settings":
        markup = get_group_settings_menu()
        safe_edit(chat_id, "📢 <b>OTP GROUP SETTINGS</b>", markup, message_id)
    elif data == "admin_force_join":
        markup = get_force_join_menu()
        safe_edit(chat_id, "🔗 <b>FORCE JOIN SETTINGS</b>", markup, message_id)
    elif data == "admin_set_watermark":
        user_states[chat_id] = {"state": "set_watermark"}
        safe_send(chat_id, "📝 <b>ENTER NEW WATERMARK TEXT:</b>\n<i>e.g. VERTEX OTP</i>\n\n❌ /cancel to cancel")
    elif data == "admin_manage_balances":
        d = load_data()
        balances = d.get("balances", {})
        text = "━━━━━━━━━━━━━━━\n《 💰 <b>BALANCES</b> 》\n━━━━━━━━━━━━━━━\n\n"
        if balances:
            for uid, bal in sorted(balances.items(), key=lambda x: x[1], reverse=True)[:15]:
                text += f"🆔 <code>{uid}</code> — <b>${bal:.4f}</b>\n"
        else:
            text += "<b>No balances found.</b>"
        text += "\n━━━━━━━━━━━━━━━"
        markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
        safe_edit(chat_id, text, markup, message_id)
    elif data == "admin_add_balance":
        user_states[chat_id] = {"state": "admin_add_balance"}
        safe_send(chat_id, "💰 <b>ADD BALANCE TO USER</b>\n\nEnter in format: <code>USER_ID AMOUNT</code>\n<i>e.g. 123456789 5.00</i>\n\n❌ /cancel to cancel")
    elif data == "admin_maintenance":
        d = load_data()
        current = d.get("maintenance", False)
        d["maintenance"] = not current
        save_data(d)
        status = "🟢 ENABLED" if d["maintenance"] else "🔴 DISABLED"
        bot.answer_callback_query(call.id, f"Maintenance: {status}")
        show_admin_system(chat_id, message_id)
    elif data == "admin_manage_admins":
        show_manage_admins(chat_id, message_id)
    elif data == "admin_forward_groups":
        d = load_data()
        fg = d.get("forward_groups", [])
        text_lines = ["━━━━━━━━━━━━━━━", "《 📢 FORWARD GROUPS 》", "━━━━━━━━━━━━━━━"]
        if fg:
            for i, g in enumerate(fg, 1):
                text_lines.append(f"{i}. <code>{g}</code>")
        else:
            text_lines.append("<b>No groups set.</b>")
        text_lines.append("━━━━━━━━━━━━━━━")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(ibtn("➕ ADD", callback_data="fg_add", style="success"),
                   ibtn("❌ REMOVE", callback_data="fg_remove_list", style="danger"))
        markup.add(ibtn("🔙 BACK", callback_data="back_to_admin", style="primary"))
        safe_edit(chat_id, "\n".join(text_lines), markup, message_id)
    elif data == "admin_set_min_withdraw":
        current = load_data().get("min_withdraw", 1.0)
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"💲 <b>SET MINIMUM WITHDRAWAL</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"📊 <b>Current minimum:</b> ${current:.2f}\n\n"
            f"Enter the new minimum withdrawal amount in USD\n"
            f"<i>e.g. 0.50, 1.00, 2.00</i>\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "set_min_withdraw"}

    elif data == "admin_view_member_bot":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id,
            f"━━━━━━━━━━━━━━━\n"
            f"🤖 <b>VIEW MEMBER BOT</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"Enter the <b>User ID</b> or <b>@username</b> of the member\n"
            f"to view their bot activity and details.\n\n"
            f"❌ <b>Type /cancel to cancel</b>",
            markup, message_id)
        user_states[chat_id] = {"state": "admin_view_member_bot_lookup"}

    elif data == "admin_clean_balances":
        d = load_data()
        clean_date = d.get("balance_clean_date", "")
        total_bal = sum(d.get("balances", {}).values())
        msg = (
            f"━━━━━━━━━━━━━━━\n"
            f"🧹 <b>CLEAN BALANCES</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"💰 <b>Total balances:</b> ${total_bal:.4f}\n"
            f"👥 <b>Members with balance:</b> {len([b for b in d.get('balances', {}).values() if b > 0])}\n"
        )
        if clean_date:
            msg += f"📅 <b>Scheduled clean:</b> {clean_date}\n"
        msg += f"━━━━━━━━━━━━━━━"
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(ibtn("🧹 CLEAN NOW", callback_data="clean_balances_now", style="danger"))
        markup.add(ibtn("📅 SCHEDULE CLEAN", callback_data="clean_balances_set_date", style="primary"))
        if clean_date:
            markup.add(ibtn("❌ REMOVE SCHEDULE", callback_data="clean_balances_remove", style="danger"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id, msg, markup, message_id)

    elif data == "admin_withdraw_stats":
        d = load_data()
        wds = d.get("withdrawal_requests", [])
        pending = [w for w in wds if w.get("status") == "pending"]
        approved = [w for w in wds if w.get("status") == "approved"]
        rejected = [w for w in wds if w.get("status") == "rejected"]
        total_pending = sum(w.get("amount", 0) for w in pending)
        total_approved = sum(w.get("amount", 0) for w in approved)
        total_rejected = sum(w.get("amount", 0) for w in rejected)
        msg = (
            f"━━━━━━━━━━━━━━━\n"
            f"📊 <b>WITHDRAWAL STATS</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"⏳ <b>Pending:</b> {len(pending)} (${total_pending:.2f})\n"
            f"✅ <b>Approved:</b> {len(approved)} (${total_approved:.2f})\n"
            f"❌ <b>Rejected:</b> {len(rejected)} (${total_rejected:.2f})\n"
            f"━━━━━━━━━━━━━━━"
        )
        markup = InlineKeyboardMarkup(row_width=1)
        if pending:
            markup.add(ibtn(f"⏳ VIEW PENDING ({len(pending)})", callback_data="admin_view_pending_wd", style="primary"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
        safe_edit(chat_id, msg, markup, message_id)

    elif data == "admin_toggle_force_join":
        d = load_data()
        d["force_join_enabled"] = not d.get("force_join_enabled", False)
        save_data(d)
        status = "✅ ENABLED" if d["force_join_enabled"] else "❌ DISABLED"
        bot.answer_callback_query(call.id, f"Force Join: {status}")
        markup = get_force_join_menu()
        safe_edit(chat_id, "🔗 <b>FORCE JOIN SETTINGS</b>", markup, message_id)

    elif data == "admin_back":
        show_admin_panel(chat_id, message_id)

    elif data == "admin_send_test_msg":
        user_states[chat_id] = {"state": "admin_add_balance"}
        safe_send(chat_id, "📝 <b>Enter test message:</b>\n❌ /cancel to cancel")

    elif data == "admin_view_pending_wd":
        d = load_data()
        pending = [w for w in d.get("withdrawal_requests", []) if w.get("status") == "pending"]
        if not pending:
            safe_edit(chat_id, "✅ <b>NO PENDING WITHDRAWALS!</b>", None, message_id)
        else:
            text = "━━━━━━━━━━━━━━━\n⏳ <b>PENDING WITHDRAWALS</b>\n━━━━━━━━━━━━━━━\n\n"
            markup = InlineKeyboardMarkup(row_width=1)
            for w in pending[:10]:
                uid = w.get("user_id", "?")
                amt = w.get("amount", 0)
                method = w.get("payment_method", "?")
                wd_id = w.get("id", "?")
                text += f"🆔 <code>{wd_id}</code> | 💰 ${amt:.2f} | 🏦 {method.upper()}\n"
                markup.add(ibtn(f"✅ APPROVE ${amt:.2f} ({wd_id})", callback_data=f"approve_wd_{wd_id}", style="success"),
                           ibtn(f"❌ REJECT ({wd_id})", callback_data=f"reject_wd_{wd_id}", style="danger"))
            markup.add(ibtn("🔙 BACK", callback_data="admin_withdraw_stats", style="primary"))
            safe_edit(chat_id, text, markup, message_id)

    # ---- NEW ADMIN CALLBACKS (145+ FEATURES) ----
    elif data == "admin_stats":
        show_full_stats(chat_id)
    elif data == "stat_today":
        show_today_stats(chat_id)
    elif data == "stat_weekly":
        safe_send(chat_id, "📊 <b>WEEKLY STATS</b>\n<i>Showing last 7 days</i>")
        show_full_stats(chat_id)
    elif data == "stat_monthly":
        safe_send(chat_id, "📊 <b>MONTHLY STATS</b>\n<i>Showing current month</i>")
        show_full_stats(chat_id)
    elif data == "stat_service":
        show_stock_summary(chat_id)
    elif data == "stat_country":
        show_stock_summary(chat_id)
    elif data == "stat_top":
        show_leaderboard(chat_id)
    elif data == "stat_peak":
        safe_send(chat_id, "⏰ <b>PEAK HOURS</b>\n\n📊 View activity patterns in FULL STATS\n📈 SMS processing is continuous 24/7")
    elif data == "stat_export":
        show_export_stats(chat_id)
    elif data == "admin_all_users":
        show_all_users(chat_id)
    elif data == "admin_user_statistics":
        show_user_statistics(chat_id)
    elif data == "admin_search_user":
        show_search_user(chat_id)
    elif data == "admin_stock_summary":
        show_stock_summary(chat_id)
    elif data == "admin_all_numbers":
        show_all_numbers(chat_id)
    elif data == "admin_available_numbers":
        show_available_numbers(chat_id)
    elif data == "admin_rented_numbers":
        show_rented_numbers(chat_id)
    elif data == "admin_search_numbers":
        show_search_numbers(chat_id)
    elif data == "admin_expire_numbers":
        show_expire_numbers(chat_id)
    elif data == "admin_export_numbers":
        show_export_numbers(chat_id)
    elif data == "release_all_rented":
        release_all_rented(chat_id)
    elif data == "admin_withdrawal_history":
        show_admin_withdrawal_history(chat_id)
    elif data == "admin_total_balances":
        show_total_balances(chat_id)
    elif data == "admin_add_all_bonus":
        show_add_all_bonus(chat_id)
    elif data == "admin_deduct_all_fee":
        show_deduct_all_fee(chat_id)
    elif data == "admin_services":
        show_services_menu(chat_id)
    elif data == "admin_add_service":
        user_states[chat_id] = {"state": "admin_add_service"}
        safe_send(chat_id, "➕ <b>ADD SERVICE</b>\nEnter service name\n<i>e.g. Telegram, WhatsApp</i>\n\n❌ /cancel to cancel")
    elif data == "admin_remove_service":
        user_states[chat_id] = {"state": "admin_remove_service"}
        safe_send(chat_id, "❌ <b>REMOVE SERVICE</b>\nEnter service name to remove\n\n❌ /cancel to cancel")
    elif data == "admin_edit_service_price":
        user_states[chat_id] = {"state": "admin_edit_service_price"}
        safe_send(chat_id, "✏️ <b>EDIT SERVICE PRICE</b>\nEnter format: <code>SERVICE_NAME PRICE</code>\n<i>e.g. Telegram 0.005</i>\n\n❌ /cancel to cancel")
    elif data == "admin_set_price_all":
        user_states[chat_id] = {"state": "admin_set_price_all"}
        safe_send(chat_id, "💲 <b>SET PRICE FOR ALL SERVICES</b>\nEnter price per OTP (USD)\n<i>e.g. 0.001, 0.01</i>\n\n❌ /cancel to cancel")
    elif data == "sys_max_numbers":
        user_states[chat_id] = {"state": "set_max_numbers"}
        safe_send(chat_id, "📱 <b>SET MAX NUMBERS PER USER</b>\nEnter number\n<i>e.g. 5, 10, 20</i>\n\n❌ /cancel to cancel")
    elif data == "admin_maint_msg":
        show_set_maintenance_msg(chat_id)
    elif data == "admin_otp_monitor":
        markup = InlineKeyboardMarkup(row_width=2)
        data_obj = load_data()
        status = "✅ ON" if data_obj.get("otp_monitoring_enabled", True) else "❌ OFF"
        markup.add(ibtn(f"TOGGLE: {status}", callback_data="admin_toggle_otp_mon", style="danger"))
        markup.add(ibtn("🧪 TEST", callback_data="admin_test_otp_mon", style="primary"))
        markup.add(ibtn("🔙 BACK", callback_data="admin_system", style="primary"))
        safe_send(chat_id, "📡 <b>OTP MONITORING</b>\n\nStatus: " + status, markup)
    elif data == "admin_toggle_otp_mon":
        toggle_otp_monitoring(chat_id)
    elif data == "admin_test_otp_mon":
        test_otp_monitoring(chat_id)
    elif data == "admin_blacklist":
        show_blacklist_menu(chat_id)
    elif data == "admin_blacklist_add":
        user_states[chat_id] = {"state": "admin_blacklist_add"}
        safe_send(chat_id, "🚫 <b>BLACKLIST USER</b>\nEnter User ID\n\n❌ /cancel to cancel")
    elif data == "admin_blacklist_remove":
        user_states[chat_id] = {"state": "admin_blacklist_remove"}
        safe_send(chat_id, "♻️ <b>REMOVE FROM BLACKLIST</b>\nEnter User ID\n\n❌ /cancel to cancel")
    elif data == "admin_anti_spam":
        show_anti_spam_toggle(chat_id)
    elif data == "broadcast_all":
        user_states[chat_id] = {"state": "broadcast_msg", "target": "all"}
        safe_send(chat_id, "📢 <b>BROADCAST TO ALL USERS</b>\nEnter message:\n\n❌ /cancel to cancel")
    elif data == "broadcast_active":
        user_states[chat_id] = {"state": "broadcast_msg", "target": "active"}
        safe_send(chat_id, "📢 <b>BROADCAST TO ACTIVE USERS</b>\nEnter message:\n<i>Only non-banned users</i>\n\n❌ /cancel to cancel")
    elif data == "broadcast_specific":
        user_states[chat_id] = {"state": "broadcast_specific"}
        safe_send(chat_id, "💬 <b>SEND TO SPECIFIC USER</b>\nEnter User ID first, then message on next line\n<code>USER_ID Message here</code>\n\n❌ /cancel to cancel")
    elif data == "broadcast_by_balance":
        user_states[chat_id] = {"state": "broadcast_by_balance"}
        safe_send(chat_id, "💰 <b>SEND TO USERS WITH BALANCE ABOVE</b>\nEnter minimum balance (USD)\n<i>e.g. 1.00</i>\n\n❌ /cancel to cancel")

    else:
        log(f"[ADMIN CALLBACK] Unhandled: {data}")

# -------------------- ADMIN PANEL ACTION HELPERS --------------------
def admin_test_panel_connection(chat_id, panel_id, message_id=None):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        safe_edit(chat_id, "⚠️ Panel not found", None, message_id)
        return
    if panel.get("type") == "scraped":
        scraped_panel_test(panel_id, chat_id)
        return
    p_type = panel.get("type", "api")
    if p_type == "login":
        login_url = panel.get("login_url", "")
        login_user = panel.get("login_user", "")
        if not login_url or not login_user:
            safe_edit(chat_id, "❌ <b>LOGIN CREDENTIALS NOT SET</b>", None, message_id)
            return
        try:
            r = requests.get(login_url, timeout=10)
            safe_edit(chat_id, f"✅ <b>LOGIN PAGE REACHABLE</b>\n<b>Status:</b> {r.status_code}\n<b>User:</b> <code>{html.escape(login_user)}</code>", None, message_id)
        except Exception as e:
            safe_edit(chat_id, f"❌ <b>CONNECTION FAILED</b>\n<code>{html.escape(str(e))}</code>", None, message_id)
        return
    api_url = panel.get("api_url", "")
    api_key = panel.get("api_key", "")
    if not api_url or not api_key:
        safe_edit(chat_id, "❌ <b>API CREDENTIALS NOT SET</b>", None, message_id)
        return
    fmt = panel.get("api_format", detect_panel_format(api_url, api_key))
    try:
        if fmt == "smspin":
            params = {"api_key": api_key, "action": "getBalance"}
            r = requests.get(f"{api_url.rstrip('/')}/stubs/handler_api.php", params=params, timeout=12)
            safe_edit(chat_id, f"✅ <b>API CONNECTED</b>\n<b>Format:</b> smspin\n<b>Response:</b> <code>{html.escape(r.text[:120])}</code>", None, message_id)
        elif fmt == "5sim":
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
            r = requests.get(f"{api_url.rstrip('/')}/v1/user/profile", headers=headers, timeout=12)
            safe_edit(chat_id, f"✅ <b>API CONNECTED</b>\n<b>Format:</b> 5sim\n<b>Status:</b> {r.status_code}", None, message_id)
        else:
            params = {"api_key": api_key, "action": "getBalance"}
            r = requests.get(api_url, params=params, timeout=12)
            safe_edit(chat_id, f"✅ <b>API CONNECTED</b>\n<b>Format:</b> {fmt}\n<b>Response:</b> <code>{html.escape(r.text[:120])}</code>", None, message_id)
    except Exception as e:
        safe_edit(chat_id, f"❌ <b>CONNECTION FAILED</b>\n<code>{html.escape(str(e))}</code>", None, message_id)


def delete_panel(chat_id, panel_id, message_id=None):
    data = load_data()
    if panel_id in data.get("panels", {}):
        del data["panels"][panel_id]
        save_data(data)
    show_panel_list(chat_id, message_id)


def switch_panel_type(chat_id, panel_id, message_id=None):
    data = load_data()
    panel = data.get("panels", {}).get(panel_id)
    if not panel:
        return
    panel["type"] = "login" if panel.get("type") == "api" else "api"
    save_data(data)
    show_panel_detail(chat_id, panel_id, message_id)


# -------------------- FORWARD GROUPS --------------------
def forward_to_forward_groups(text):
    data = load_data()
    groups = data.get("forward_groups", [])
    if not groups:
        log("[FORWARD] No forward groups configured!")
        return
    for g in groups:
        # Extract chat_id from dict (forward_groups stores dicts with chat_id key)
        if isinstance(g, dict):
            chat_id = g.get("chat_id")
        else:
            chat_id = g
        if not chat_id:
            continue
        # Convert to int for Telegram API
        try:
            chat_id = int(chat_id)
        except (ValueError, TypeError):
            log(f"[FORWARD] Invalid chat_id: {chat_id}")
            continue
        # Try OTP bot first (it's the one in the OTP group), then main bot
        sent = False
        if otp_bot:
            try:
                otp_bot.send_message(chat_id, text, parse_mode="HTML")
                sent = True
            except Exception as e:
                log(f"[FORWARD] OTP bot failed to {chat_id}: {e}")
        if not sent:
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
                sent = True
            except Exception as e:
                log(f"[FORWARD] Main bot failed to {chat_id}: {e}")


# -------------------- FORCE JOIN CHECK --------------------
def check_force_join(user_id):
    data = load_data()
    groups = data.get("force_join_groups", [])
    if not groups:
        return True, None
    try:
        for g in groups:
            member = bot.get_chat_member(g["chat_id"], user_id)
            if member.status in ("left", "kicked"):
                return False, g
    except Exception:
        return False, groups[0] if groups else None
    return True, None


# -------------------- /START HANDLER --------------------
@bot.message_handler(commands=["start"])
def start_handler(message):
    chat_id = message.chat.id
    first_name = message.from_user.first_name or "User"
    args = message.text.split()
    data = load_data()

    # Register user
    if chat_id not in data.get("users", []):
        data["users"].append(chat_id)
        data.setdefault("balances", {})[str(chat_id)] = data.get("balances", {}).get(str(chat_id), 0.0)

    # Referral handling
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_id = args[1].split("_", 1)[1]
        try:
            referrer_id = int(referrer_id)
        except ValueError:
            referrer_id = None
        if referrer_id and referrer_id != chat_id:
            uid = str(chat_id)
            if uid not in data.get("refers", {}).get(str(referrer_id), []):
                data.setdefault("refers", {}).setdefault(str(referrer_id), []).append(uid)
                data.setdefault("balances", {})[str(referrer_id)] = data["balances"].get(str(referrer_id), 0.0) + 0.001  # CHANGED
                save_data(data)
                try:
                    bot.send_message(referrer_id, f"🎉 <b>NEW REFERRAL!</b>\n👤 <a href='tg://user?id={chat_id}'>{html.escape(first_name)}</a>\n💰 <b>+$0.001 EARNED</b>", parse_mode="HTML")
                except Exception:
                    pass

    # Force join check
    ok, group = check_force_join(chat_id)
    if not ok:
        markup = InlineKeyboardMarkup(row_width=1)
        if group and group.get("link"):
            markup.add(ibtn(f"✅ JOIN {html.escape(group.get('title', 'GROUP'))}", url=group["link"], style="success"))
        markup.add(ibtn("🔄 I'VE JOINED", callback_data="close_menu", style="primary"))
        safe_send(chat_id,
            "━━━━━━━━━━━━━━━\n"
            "《 🔗 <b>JOIN REQUIRED</b> 》\n"
            "━━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>YOU MUST JOIN OUR CHANNEL</b>\n"
            "<b>TO USE THIS BOT</b>\n"
            "━━━━━━━━━━━━━━━",
            markup)
        return

    save_data(data)

    # Admin test command
    if len(args) > 1 and args[1] == "testscrape" and is_admin(chat_id):
        data = load_data()
        scraped = {pid: p for pid, p in data.get("panels", {}).items()
                   if p.get("status") == "active" and p.get("type") == "scraped"}
        fwd = data.get("forward_groups", [])
        safe_send(chat_id,
            f"🧪 <b>SCRAPED PANEL TEST</b>\n\n"
            f"📋 <b>Panels:</b> {len(scraped)}\n"
            f"📢 <b>Forward Groups:</b> {len(fwd)}\n"
            f"━━━━━━━━━━━━━━━")
        for pid, panel in scraped.items():
            safe_send(chat_id, f"🔄 Testing: {html.escape(panel.get('name', pid))}...")
            if scraped_login(pid):
                otps = scraped_fetch_otps(pid)
                safe_send(chat_id,
                    f"✅ <b>{html.escape(panel.get('name', pid))}</b>\n"
                    f"  Type: {panel.get('panel_type', '?')}\n"
                    f"  OTPs: {len(otps)}")
            else:
                safe_send(chat_id, f"❌ <b>{html.escape(panel.get('name', pid))}</b> — Login failed")
        if not fwd:
            safe_send(chat_id, "⚠️ <b>NO FORWARD GROUPS!</b>\nOTP won't be forwarded.\nSet OTP Groups in admin panel.")
        return

    show_main_menu(chat_id, first_name)


# -------------------- .TXT UPLOAD HANDLER (MANUAL NUMBERS) --------------------
@bot.message_handler(content_types=["document"])
def document_handler(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    if not state:
        safe_send(chat_id, "📄 Please send numbers via /admin panel → Panels → Add Numbers.")
        return
    if not is_admin(chat_id):
        return
    
    # Handle combo file upload (CSV or TXT)
    if state.get("state") == "add_combo_file":
        fname = (message.document.file_name or "").lower()
        if not (fname.endswith(".txt") or fname.endswith(".csv")):
            safe_send(chat_id, "❌ <b>PLEASE SEND A .txt OR .csv FILE</b>")
            return
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            text = downloaded.decode("utf-8", errors="ignore")
        except Exception as e:
            safe_send(chat_id, f"❌ <b>FAILED TO READ FILE</b>\n<code>{html.escape(str(e))}</code>")
            return
        # Smart number extraction: pull phone numbers from any format
        raw_lines = text.splitlines()
        numbers = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            # CSV: extract from each cell
            if fname.endswith(".csv"):
                cells = line.split(",")
                for cell in cells:
                    cell = cell.strip().strip('"').strip("'")
                    digits = re.sub(r'[^0-9+]', '', cell)
                    # Strip leading + and common prefixes
                    digits = re.sub(r'^\+0*', '', digits.lstrip('+'))
                    if 8 <= len(digits) <= 15 and digits.isdigit():
                        if digits not in numbers:
                            numbers.append(digits)
            else:
                # TXT: try whole line first
                digits = re.sub(r'[^0-9+]', '', line)
                digits = re.sub(r'^\+0*', '', digits.lstrip('+'))
                if 8 <= len(digits) <= 15 and digits.isdigit():
                    if digits not in numbers:
                        numbers.append(digits)
                else:
                    # Extract all phone-like numbers from the line
                    found = re.findall(r'\b\d{8,15}\b', line)
                    for d in found:
                        if d not in numbers:
                            numbers.append(d)
        if not numbers:
            safe_send(chat_id, "❌ <b>NO PHONE NUMBERS FOUND IN FILE</b>\n\n<i>Supported formats:</i>\n• One number per line\n• CSV with numbers in any column\n• Mixed text with embedded numbers")
            return
        app_name = state.get("app_name", "COMBO")
        # Auto-detect country from numbers
        d = load_data()
        combos = d.get("combos", [])
        exists = False
        for c in combos:
            if c.get("name", "").upper() == app_name.upper():
                c["numbers"] = list(set(c.get("numbers", []) + numbers))
                countries = c.get("countries", {})
                for n in numbers:
                    cty = detect_country_from_phone(n)
                    countries.setdefault(cty, [])
                    if n not in countries[cty]:
                        countries[cty].append(n)
                c["countries"] = countries
                exists = True
                break
        if not exists:
            countries = {}
            for n in numbers:
                cty = detect_country_from_phone(n)
                countries.setdefault(cty, [])
                countries[cty].append(n)
            combos.append({
                "name": app_name,
                "numbers": numbers,
                "used_numbers": [],
                "countries": countries,
                "alloc_per_user": 5
            })
        d["combos"] = combos
        save_data(d)
        user_states.pop(chat_id, None)
        total = len(numbers)
        detected = sorted(set(detect_country_from_phone(n) for n in numbers))
        country_list = ", ".join([f"{get_country_flag(c)} {c}" for c in detected if c != "Unknown"])
        if not country_list:
            country_list = "Unknown"
        safe_send(chat_id,
            f"✅ <b>COMBO CREATED!</b>\n\n"
            f"📱 <b>APP:</b> {html.escape(app_name)}\n"
            f"🌍 <b>COUNTRIES:</b> {country_list}\n"
            f"📱 <b>NUMBERS:</b> {total}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>Users can now find this in GET NUMBER</b>")
        show_app_list(chat_id)
        return
    
    # Handle panel range number upload
    if state.get("state") != "add_numbers_txt":
        safe_send(chat_id, "📄 Please send numbers via /admin panel → Panels → Add Numbers.")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        text = downloaded.decode("utf-8", errors="ignore")
    except Exception as e:
        safe_send(chat_id, f"❌ <b>FAILED TO READ FILE</b>\n<code>{html.escape(str(e))}</code>")
        return
    numbers = [line.strip() for line in text.splitlines() if line.strip()]
    if not numbers:
        safe_send(chat_id, "❌ <b>NO NUMBERS FOUND IN FILE</b>")
        return
    panel_id = state.get("panel_id")
    rng_id = state.get("rng_id")
    data = load_data()
    rng = data.get("panels", {}).get(panel_id, {}).get("ranges", {}).get(rng_id)
    if not rng:
        safe_send(chat_id, "❌ <b>RANGE NOT FOUND</b>")
        user_states.pop(chat_id, None)
        return
    rng.setdefault("numbers", [])
    added = 0
    for n in numbers:
        if n not in rng["numbers"]:
            rng["numbers"].append(n)
            added += 1
    save_data(data)
    user_states.pop(chat_id, None)
    safe_send(chat_id, f"✅ <b>ADDED {added} NUMBERS</b>\n📄 File: <code>{html.escape(message.document.file_name or 'numbers.txt')}</code>\n📊 Total in range: <code>{len(rng['numbers'])}</code>")
    show_range_detail(chat_id, panel_id, rng_id)


# -------------------- COMBO NUMBER FETCHING --------------------
def fetch_combo_number(chat_id, combo_name, message_id=None):
    """Fetch multiple numbers from a combo (admin-set allocation per user)."""
    data = load_data()
    combo = None
    for c in data.get("combos", []):
        if c.get("name", "").upper() == combo_name.upper():
            combo = c
            break
    if not combo:
        safe_send(chat_id, "❌ <b>COMBO NOT FOUND</b>")
        return
    numbers = combo.get("numbers", [])
    used = combo.get("used_numbers", [])
    available = [n for n in numbers if n not in used]
    if not available:
        safe_send(chat_id, "❌ <b>COMBO EMPTY</b>\nAll numbers have been used.")
        return
    alloc = combo.get("alloc_per_user", 5)
    pick_count = min(alloc, len(available))
    import random
    picked = random.sample(available, pick_count)
    for n in picked:
        used.append(n)
    combo["used_numbers"] = used
    save_data(data)
    combo_name_esc = html.escape(combo.get("name", "COMBO"))
    first_num = picked[0]
    first_cty = detect_country_from_phone(first_num)
    first_flag = get_country_flag(first_cty)
    lines = []
    lines.append(f"📞 <b>Number:</b> <code>{html.escape(first_num)}</code>")
    lines.append(f"🌍 <b>Country:</b> {first_flag} {first_cty}")
    lines.append(f"📱 <b>Service:</b> {combo_name_esc}")
    lines.append(f"⏳ <b>Status:</b> Waiting for SMS")
    lines.append("")
    lines.append(f"📋 <b>All Assigned Numbers:</b>")
    for n in picked:
        lines.append(f"• <code>{html.escape(n)}</code>")
    lines.append(f"")
    lines.append(f"📊 <b>Remaining:</b> {len(available) - pick_count}")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(ibtn("👁 View OTP", callback_data=f"check_combo_otp|{combo_name}", style="primary"))
    markup.add(ibtn("🔄 Change Number", callback_data=f"usr_combo|{combo_name}", style="danger"))
    markup.add(ibtn("↩ Back", callback_data="back_to_user_services", style="primary"))
    safe_edit(chat_id, "\n".join(lines), markup, message_id)

# -------------------- TEXT MESSAGE HANDLER (STATE MACHINE + OTP + SUPPORT) --------------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def text_handler(message):
    chat_id = message.chat.id
    text = message.text.strip()
    first_name = message.from_user.first_name or "User"

    if text == "/cancel":
        user_states.pop(chat_id, None)
        safe_send(chat_id, "❌ <b>CANCELLED</b>")
        show_main_menu(chat_id, first_name)
        return

    # ---- ADMIN REPLY TO SUPPORT MESSAGE ----
    if is_main_admin(chat_id) and message.reply_to_message:
        fwd_from = message.reply_to_message.forward_from
        if fwd_from and not fwd_from.is_bot:
            try:
                bot.send_message(fwd_from.id, f"📩 <b>ADMIN REPLY:</b>\n\n{text}", parse_mode="HTML")
                safe_send(chat_id, "✅ <b>REPLY SENT TO USER</b>")
            except Exception as e:
                safe_send(chat_id, f"❌ <b>FAILED:</b> {html.escape(str(e))}")
            return

    # ---- LIVE SUPPORT MESSAGE ----
    state = user_states.get(chat_id)
    if state and state.get("state") == "support_message":
        reply_markup = InlineKeyboardMarkup(row_width=1)
        reply_markup.add(ibtn("💬 REPLY TO USER", callback_data=f"reply_user_{chat_id}", style="primary"))
        notify_all_admins(
            f"📩 <b>SUPPORT MESSAGE</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 <b>FROM:</b> <a href='tg://user?id={chat_id}'>{html.escape(first_name)}</a>\n"
            f"🆔 <b>ID:</b> <code>{chat_id}</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💬 <b>MESSAGE:</b>\n{html.escape(text)}\n"
            f"━━━━━━━━━━━━━━━",
            reply_markup)
        safe_send(chat_id, "✅ <b>MESSAGE SENT TO ADMINS!</b>\n<b>WAIT FOR A REPLY...</b>")
        user_states.pop(chat_id, None)
        return

    # ---- MANUAL OTP CODE ENTRY ----
    data = load_data()
    for sid, sess in list(data.get("number_session", {}).items()):
        if sess.get("user_id") == chat_id and sess.get("status") == "awaiting_manual_otp":
            otp_code = text
            sess["status"] = "completed"
            sess["otp_code"] = otp_code
            save_data(data)
            number = sess.get("number", "?")
            app_name = sess.get("app", "?")
            notify_all_admins(
                f"✅ <b>OTP RECEIVED (MANUAL)</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 <b>USER:</b> <a href='tg://user?id={chat_id}'>User {chat_id}</a>\n"
                f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                f"🔑 <b>OTP:</b> <code>{html.escape(otp_code)}</code>\n"
                f"📦 <b>APP:</b> {emo(app_name)} {app_name.upper()}\n"
                f"🆔 <b>SID:</b> <code>{sid}</code>\n"
                f"━━━━━━━━━━━━━━━")
            forward_to_forward_groups(
                f"✅ <b>OTP (MANUAL)</b>\n"
                f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                f"🔑 <b>CODE:</b> <code>{html.escape(otp_code)}</code>\n"
                f"📦 <b>APP:</b> {emo(app_name)} {app_name.upper()}")
            markup = InlineKeyboardMarkup().add(ibtn("📋 MAIN MENU", callback_data="close_menu", style="success"))
            safe_send(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"《 ✅ <b>OTP CONFIRMED</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                f"🔑 <b>OTP:</b> <code>{html.escape(otp_code)}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"✅ <b>SUCCESS</b> — THANKS FOR USING THE BOT",
                markup)
            return

    # ---- 2FA SECRET ENTRY ----
    if state and state.get("state") == "2fa_key":
        secret = text.strip().replace(" ", "")
        try:
            totp = pyotp.TOTP(secret)
            code = totp.now()
            safe_send(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"《 🔐 <b>YOUR 2FA CODE</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"🔑 <b>CODE:</b> <code>{code}</code>\n\n"
                f"⏳ <b>REFRESHES IN:</b> {30 - int(time.time()) % 30}s\n"
                f"━━━━━━━━━━━━━━━")
        except Exception:
            safe_send(chat_id, "❌ <b>INVALID SECRET KEY</b>\n<i>Check the key and try again</i>")
        user_states.pop(chat_id, None)
        return

    # ---- ADMIN REPLY TO USER ----
    if state and state.get("state") == "admin_reply":
        target_user = state.get("target_user")
        if target_user:
            try:
                bot.send_message(target_user,
                    f"📩 <b>ADMIN REPLY:</b>\n\n{text}",
                    parse_mode="HTML")
                safe_send(chat_id, f"✅ <b>REPLY SENT TO USER</b> <code>{target_user}</code>")
            except Exception as e:
                safe_send(chat_id, f"❌ <b>FAILED:</b> {html.escape(str(e))}")
        user_states.pop(chat_id, None)
        return

    # ---- ADMIN STATE MACHINE ----
    if state and is_admin(chat_id):
        s = state.get("state")

        if s == "add_panel_name":
            d = load_data()
            pid = f"panel_{int(time.time())}"
            d.setdefault("panels", {})[pid] = {
                "name": text, "type": "api", "status": "active",
                "fetch_type": "manual", "api_format": "smspin",
                "api_url": "", "api_key": "", "login_url": "",
                "login_user": "", "login_pass": "", "ranges": {},
                "panel_type": "agent", "panel_url": ""
            }
            save_data(d)
            user_states[chat_id] = {"state": "scraped_panel_url", "panel_id": pid}
            safe_send(chat_id,
                f"📋 <b>PANEL CREATED:</b> <code>{html.escape(text)}</code>\n\n"
                f"🔗 <b>ENTER PANEL URL:</b>\n"
                f"<i>e.g. http://51.77.52.79/ints</i>\n"
                f"<i>Base URL without /login</i>\n\n"
                f"❌ /cancel to cancel")
            return

        if s == "rename_panel":
            d = load_data()
            p = d.get("panels", {}).get(state.get("panel_id"))
            if p:
                p["name"] = text
                save_data(d)
                safe_send(chat_id, f"✅ <b>RENAMED TO:</b> {html.escape(text)}")
            user_states.pop(chat_id, None)
            show_panel_detail(chat_id, state.get("panel_id"))
            return

        if s == "set_api_key":
            d = load_data()
            p = d.get("panels", {}).get(state.get("panel_id"))
            if p:
                p["api_key"] = text
                save_data(d)
                safe_send(chat_id, "✅ <b>API KEY SET</b>")
            user_states.pop(chat_id, None)
            show_panel_detail(chat_id, state.get("panel_id"))
            return

        if s == "set_login_url":
            d = load_data()
            p = d.get("panels", {}).get(state.get("panel_id"))
            if p:
                p["login_url"] = text
                save_data(d)
                user_states[chat_id] = {"state": "set_login_user", "panel_id": state.get("panel_id")}
                safe_send(chat_id, "✅ <b>LOGIN URL SET</b>\n🔐 <b>NOW ENTER LOGIN USERNAME:</b>")
            return

        if s == "set_login_user":
            d = load_data()
            p = d.get("panels", {}).get(state.get("panel_id"))
            if p:
                p["login_user"] = text
                save_data(d)
                user_states[chat_id] = {"state": "set_login_pass", "panel_id": state.get("panel_id")}
                safe_send(chat_id, "✅ <b>USERNAME SET</b>\n🔑 <b>NOW ENTER LOGIN PASSWORD:</b>")
            return

        if s == "set_login_pass":
            d = load_data()
            p = d.get("panels", {}).get(state.get("panel_id"))
            if p:
                p["login_pass"] = text
                save_data(d)
                safe_send(chat_id, "✅ <b>LOGIN CREDENTIALS COMPLETE</b>")
            user_states.pop(chat_id, None)
            show_panel_detail(chat_id, state.get("panel_id"))
            return

        if s == "custom_endpoints":
            d = load_data()
            p = d.get("panels", {}).get(state.get("panel_id"))
            step = state.get("ep_step", 0)
            if p:
                if step == 0:
                    p["custom_fetch_url"] = text
                    user_states[chat_id] = {"state": "custom_endpoints", "panel_id": state.get("panel_id"), "ep_step": 1}
                    safe_send(chat_id, "✅ <b>FETCH URL SET</b>\n🔍 <b>NOW ENTER STATUS/CHECK URL:</b>")
                    return
                elif step == 1:
                    p["custom_status_url"] = text
                    save_data(d)
                    safe_send(chat_id, "✅ <b>ENDPOINTS SAVED</b>")
            user_states.pop(chat_id, None)
            show_panel_detail(chat_id, state.get("panel_id"))
            return

        if s == "add_range":
            d = load_data()
            pid = state.get("panel_id")
            step = state.get("step")
            if step == "country":
                user_states[chat_id] = {"state": "add_range", "panel_id": pid, "step": "app", "country": text}
                safe_send(chat_id, f"🌍 <b>COUNTRY:</b> {html.escape(text)}\n📦 <b>NOW ENTER APP/SERVICE NAME:</b>\n<i>e.g. Telegram, WhatsApp</i>")
                return
            if step == "app":
                user_states[chat_id] = {"state": "add_range", "panel_id": pid, "step": "code", "country": state.get("country"), "app": text}
                safe_send(chat_id, f"📦 <b>APP:</b> {html.escape(text)}\n🔗 <b>NOW ENTER SERVICE CODE:</b>\n<i>e.g. tg, wa, uber</i>")
                return
            if step == "code":
                user_states[chat_id] = {"state": "add_range", "panel_id": pid, "step": "cc", "country": state.get("country"), "app": state.get("app"), "code": text}
                safe_send(chat_id, f"🔗 <b>CODE:</b> {html.escape(text)}\n🌍 <b>NOW ENTER COUNTRY ISO CODE:</b>\n<i>e.g. RU, US, UK</i>")
                return
            if step == "cc":
                rid = f"rng_{int(time.time())}"
                d["panels"][pid].setdefault("ranges", {})[rid] = {
                    "name": state.get("country"), "app": state.get("app"),
                    "range_code": state.get("code"), "country_code": text.upper(),
                    "numbers": [], "used_numbers": []
                }
                save_data(d)
                user_states.pop(chat_id, None)
                safe_send(chat_id, f"✅ <b>RANGE ADDED</b>\n{get_country_flag(state.get('country'))} {html.escape(state.get('country'))} | {html.escape(state.get('app'))} | CC:{text.upper()}")
                show_panel_ranges(chat_id, pid)
            return

        if s == "add_combo_appname":
            app_name = text.strip()
            user_states[chat_id] = {"state": "add_combo_file", "app_name": app_name}
            safe_send(chat_id,
                f"📱 <b>APP:</b> {html.escape(app_name)}\n\n"
                f"📄 <b>SEND THE .TXT FILE WITH NUMBERS</b>\n"
                f"<i>One number per line</i>\n\n"
                f"❌ /cancel to cancel")
            return

        if s == "add_app_folder":
            user_states[chat_id] = {"state": "add_app_name", "folder": text.strip().upper()}
            safe_send(chat_id, f"📁 <b>FOLDER:</b> {html.escape(text.upper())}\n\n📦 <b>ENTER APP/SERVICE NAME:</b>\n<i>e.g. Telegram, WhatsApp, Uber</i>\n\n❌ /cancel to cancel")
            return

        if s == "add_app_name":
            d = load_data()
            folder = state.get("folder", "OTHER")
            apps = d.get("apps", [])
            app_name = text.strip()
            # Check if app already exists in this folder
            exists = False
            for app in apps:
                if isinstance(app, dict) and app.get("name", "").upper() == app_name.upper() and app.get("folder", "").upper() == folder.upper():
                    exists = True
                    break
            if not exists:
                apps.append({"folder": folder, "name": app_name})
                d["apps"] = apps
                save_data(d)
                safe_send(chat_id, f"✅ <b>APP ADDED:</b>\n📁 Folder: {html.escape(folder)}\n📦 App: {emo(app_name)} {html.escape(app_name)}")
            else:
                safe_send(chat_id, f"⚠️ <b>APP ALREADY EXISTS IN {html.escape(folder)}:</b> {html.escape(app_name)}")
            user_states.pop(chat_id, None)
            show_app_list(chat_id)
            return

        if s == "set_cooldown":
            try:
                val = int(text)
                d = load_data()
                d.setdefault("settings", {})["cooldown"] = val
                save_data(d)
                safe_send(chat_id, f"✅ <b>COOLDOWN SET:</b> {val}s")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID NUMBER</b>")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "set_num_per_req":
            try:
                val = int(text)
                d = load_data()
                d.setdefault("settings", {})["num_per_request"] = val
                save_data(d)
                safe_send(chat_id, f"✅ <b>NUM/REQ SET:</b> {val}")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID NUMBER</b>")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "set_price":
            try:
                val = float(text)
                d = load_data()
                d.setdefault("settings", {})["price_per_otp"] = val
                save_data(d)
                safe_send(chat_id, f"✅ <b>PRICE PER OTP SET:</b> ${val:.4f}")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID PRICE</b>")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "set_support_link":
            d = load_data()
            d.setdefault("settings", {})["support_link"] = text
            save_data(d)
            safe_send(chat_id, f"✅ <b>SUPPORT LINK SET:</b> {html.escape(text)}")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "set_watermark":
            d = load_data()
            d["watermark"] = text
            save_data(d)
            safe_send(chat_id, f"✅ <b>WATERMARK SET:</b> {html.escape(text)}")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "admin_add_balance":
            try:
                parts = text.strip().split()
                if len(parts) != 2:
                    safe_send(chat_id, "❌ <b>INVALID FORMAT!</b>\nUse: <code>USER_ID AMOUNT</code>\ne.g. 123456789 5.00")
                    return
                target_id = int(parts[0])
                amount = float(parts[1])
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE POSITIVE!</b>")
                    return
                d = load_data()
                uid = str(target_id)
                d.setdefault("balances", {})[uid] = d.get("balances", {}).get(uid, 0.0) + amount
                save_data(d)
                new_bal = d["balances"][uid]
                safe_send(chat_id, f"✅ <b>BALANCE ADDED!</b>\n\n👤 <code>{target_id}</code>\n💰 +${amount:.4f}\n💰 New balance: <b>${new_bal:.4f}</b>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID INPUT!</b>\nUse: <code>USER_ID AMOUNT</code>")
            user_states.pop(chat_id, None)
            show_admin_panel(chat_id)
            return

        if s == "set_main_otp_link":
            d = load_data()
            d["main_otp_link"] = text.strip()
            save_data(d)
            safe_send(chat_id, f"✅ <b>OTP GROUP LINK SET:</b> {html.escape(text)}")
            user_states.pop(chat_id, None)
            get_group_settings_menu()
            return

        # ---- WITHDRAWAL STATE MACHINE ----
        if s == "withdraw_amount":
            try:
                amount = float(text)
                data_obj = load_data()
                bal = data_obj.get("balances", {}).get(str(chat_id), 0.0)
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE GREATER THAN 0</b>")
                    return
                if amount > bal:
                    safe_send(chat_id, f"❌ <b>INSUFFICIENT BALANCE!</b>\n💰 Your balance: ${bal:.4f}")
                    return
                user_states[chat_id] = {"state": "withdraw_method", "amount": amount}
                markup = InlineKeyboardMarkup(row_width=2)
                markup.add(ibtn("🏦 OPay", callback_data="wdmethod_opay", style="primary"),
                           ibtn("💳 PalmPay", callback_data="wdmethod_palmpay", style="success"))
                markup.add(ibtn("💰 USDT BEP20", callback_data="wdmethod_usdt", style="danger"))
                safe_send(chat_id,
                    f"━━━━━━━━━━━━━━━\n"
                    f"💳 <b>WITHDRAWAL: ${amount:.2f}</b>\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"<b>SELECT PAYMENT METHOD:</b>",
                    markup)
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT!</b>\nEnter a number like: 1.50, 5.00, 10.00")
            return

        if s == "withdraw_name":
            name = text.strip()
            if len(name) < 10:
                safe_send(chat_id, "❌ <b>NAME TOO SHORT!</b>\nEnter your full name (min 10 characters)\n<i>e.g. John Michael Smith</i>")
                return
            state = user_states.get(chat_id)
            amount = state.get("amount", 0)
            method = state.get("payment_method", "opay")
            user_states[chat_id] = {"state": "withdraw_phone", "amount": amount, "payment_method": method, "account_name": name}
            method_names = {"opay": "OPay", "palmpay": "PalmPay", "usdt": "USDT BEP20"}
            if method == "usdt":
                safe_send(chat_id,
                    f"👤 <b>NAME:</b> {html.escape(name)}\n\n"
                    f"💰 <b>ENTER YOUR USDT BEP20 WALLET ADDRESS:</b>\n"
                    f"<i>Must start with 0x and be 42 characters</i>\n"
                    f"<i>e.g. 0x1234567890abcdef1234567890abcdef12345678</i>\n\n"
                    f"❌ <b>Type /cancel to cancel</b>")
            else:
                safe_send(chat_id,
                    f"👤 <b>NAME:</b> {html.escape(name)}\n\n"
                    f"📱 <b>ENTER YOUR {method_names.get(method, method).upper()} ACCOUNT NUMBER:</b>\n"
                    f"<i>Must start with 7, 8, or 9 and be exactly 10 digits</i>\n"
                    f"<i>e.g. 8012345678</i>\n\n"
                    f"❌ <b>Type /cancel to cancel</b>")
            return

        if s == "withdraw_phone":
            state = user_states.get(chat_id)
            amount = state.get("amount", 0)
            method = state.get("payment_method", "opay")
            account_name = state.get("account_name", "")
            method_names = {"opay": "OPay", "palmpay": "PalmPay", "usdt": "USDT BEP20"}
            if method == "usdt":
                wallet = text.strip()
                # Validate USDT BEP20: must start with 0x and be exactly 42 characters (0x + 40 hex)
                import re as re_mod
                if not re_mod.match(r'^0x[0-9a-fA-F]{40}$', wallet):
                    safe_send(chat_id, "❌ <b>INVALID WALLET ADDRESS!</b>\n\nMust be a valid BEP20 address:\n<i>Starts with 0x + 40 hex characters</i>\n<i>e.g. 0x1234567890abcdef1234567890abcdef12345678</i>")
                    return
                phone = wallet
            else:
                phone = text.strip().replace(" ", "").replace("-", "")
                # Validate: must start with 7, 8, or 9 and be exactly 10 digits
                if not phone.isdigit() or len(phone) != 10:
                    safe_send(chat_id, "❌ <b>INVALID ACCOUNT NUMBER!</b>\n\nMust be exactly 10 digits\n<i>e.g. 8012345678</i>")
                    return
                if phone[0] not in ('7', '8', '9'):
                    safe_send(chat_id, "❌ <b>INVALID ACCOUNT NUMBER!</b>\n\nMust start with 7, 8, or 9\n<i>e.g. 8012345678</i>")
                    return
            # Create withdrawal request
            import uuid
            wd_id = uuid.uuid4().hex[:8]
            rate = get_usd_to_ngn()
            amount_ngn = amount * rate
            d = load_data()
            # Get user info
            user_name = first_name
            user_username = "N/A"
            try:
                ch = bot.get_chat(chat_id)
                user_name = ch.first_name or first_name
                user_username = f"@{ch.username}" if ch.username else "N/A"
            except:
                pass
            wd_request = {
                "id": wd_id,
                "user_id": chat_id,
                "amount": amount,
                "amount_ngn": round(amount_ngn, 2),
                "rate_used": round(rate, 2),
                "status": "pending",
                "payment_method": method,
                "phone": phone,
                "full_name": account_name,
                "telegram_name": user_name,
                "timestamp": datetime.now().isoformat()
            }
            d.setdefault("withdrawal_requests", []).append(wd_request)
            # Deduct balance
            uid = str(chat_id)
            d.setdefault("balances", {})[uid] = d.get("balances", {}).get(uid, 0.0) - amount
            save_data(d)
            user_states.pop(chat_id, None)
            # Confirm to user
            method_label = method_names.get(method, method)
            markup = InlineKeyboardMarkup().add(ibtn("🔙 MAIN MENU", callback_data="close_menu", style="success"))
            safe_send(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"✅ <b>WITHDRAWAL REQUEST SENT!</b>\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"🆔 <b>Request ID:</b> <code>{wd_id}</code>\n"
                f"💰 <b>Amount:</b> ${amount:.2f}\n"
                f"💱 <b>Rate:</b> 1 USD = ₦{rate:,.2f}\n"
                f"🇳🇬 <b>NGN:</b> ₦{amount_ngn:,.2f}\n"
                f"👤 <b>Name:</b> {html.escape(account_name)}\n"
                f"🏦 <b>Method:</b> {method_label}\n"
                f"📱 <b>Account:</b> <code>{phone}</code>\n\n"
                f"⏳ <b>WAIT FOR ADMIN APPROVAL</b>\n"
                f"━━━━━━━━━━━━━━━",
                markup)
            # Notify admins with approve/reject buttons
            admin_markup = InlineKeyboardMarkup(row_width=2)
            admin_markup.add(
                ibtn("✅ APPROVE", callback_data=f"approve_wd_{wd_id}", style="success"),
                ibtn("❌ REJECT", callback_data=f"reject_wd_{wd_id}", style="danger"))
            notify_all_admins(
                f"💳 <b>NEW WITHDRAWAL REQUEST</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 <b>Telegram:</b> <a href='tg://user?id={chat_id}'>{html.escape(user_name)}</a> ({user_username})\n"
                f"🆔 <b>User ID:</b> <code>{chat_id}</code>\n"
                f"📛 <b>Account Name:</b> {html.escape(account_name)}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💰 <b>Amount (USD):</b> ${amount:.2f}\n"
                f"💱 <b>Rate:</b> 1 USD = ₦{rate:,.2f}\n"
                f"🇳🇬 <b>Amount (NGN):</b> ₦{amount_ngn:,.2f}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Method:</b> {method_label}\n"
                f"📱 <b>Account No:</b> <code>{phone}</code>\n"
                f"━━━━━━━━━━━━━━━",
                admin_markup)
            return

        if s == "broadcast_msg":
            d = load_data()
            target = state.get("target", "all")
            users = d.get("users", [])
            sent = 0
            skipped = 0
            blacklist = d.get("blacklist", [])
            for uid in users:
                if uid in blacklist:
                    skipped += 1
                    continue
                if target == "active" and uid in d.get("banned_users", []):
                    skipped += 1
                    continue
                if target == "by_balance":
                    min_bal = state.get("min_balance", 0)
                    user_bal = d.get("balances", {}).get(str(uid), 0.0)
                    if user_bal < min_bal:
                        skipped += 1
                        continue
                try:
                    bot.send_message(uid, f"📢 <b>BROADCAST</b>\n━━━━━━━━━━━━━━━\n{text}", parse_mode="HTML")
                    sent += 1
                except Exception:
                    pass
            safe_send(chat_id, f"✅ <b>BROADCAST SENT</b>\n👥 Delivered: <code>{sent}/{len(users)}</code>\n🚫 Skipped: {skipped}")
            user_states.pop(chat_id, None)
            show_admin_panel(chat_id)
            return

        if s == "add_admin_id":
            try:
                aid = int(text)
                d = load_data()
                admins = d.get("extra_admins", [])
                if aid not in admins and aid not in MAIN_ADMINS:
                    admins.append(aid)
                    d["extra_admins"] = admins
                    save_data(d)
                    safe_send(chat_id, f"✅ <b>ADMIN ADDED:</b> <code>{aid}</code>")
                else:
                    safe_send(chat_id, "⚠️ <b>ALREADY AN ADMIN</b>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID USER ID</b>")
            user_states.pop(chat_id, None)
            show_manage_admins(chat_id)
            return

        if s == "ban_user":
            try:
                bid = int(text)
                d = load_data()
                banned = d.get("banned_users", [])
                if bid not in banned:
                    banned.append(bid)
                    d["banned_users"] = banned
                    save_data(d)
                    safe_send(chat_id, f"🔨 <b>USER BANNED:</b> <code>{bid}</code>")
                else:
                    safe_send(chat_id, "⚠️ <b>ALREADY BANNED</b>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID USER ID</b>")
            user_states.pop(chat_id, None)
            show_user_view(chat_id)
            return

        if s == "uv_profile_lookup":
            target = text.strip()
            d = load_data()
            if target.startswith("@"):
                target = target[1:]
                found = None
                for uid in d.get("users", []):
                    try:
                        ch = bot.get_chat(uid)
                        if ch.username and ch.username.lower() == target.lower():
                            found = uid
                            break
                    except Exception:
                        continue
            else:
                try:
                    found = int(target)
                except ValueError:
                    found = None
            if found is None:
                safe_send(chat_id, "❌ <b>USER NOT FOUND</b>")
            else:
                bal = d.get("balances", {}).get(str(found), 0.0)
                otps = d.get("otp_counts", {}).get(str(found), 0)
                banned = "🚫 YES" if found in d.get("banned_users", []) else "✅ NO"
                admin = "👮 YES" if is_admin(found) else "❌ NO"
                try:
                    ch = bot.get_chat(found)
                    name = html.escape(ch.first_name or "User")
                except Exception:
                    name = str(found)
                safe_send(chat_id,
                    f"━━━━━━━━━━━━━━━\n"
                    f"《 👤 <b>USER PROFILE</b> 》\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🆔 <b>ID:</b> <code>{found}</code>\n"
                    f"📛 <b>NAME:</b> {name}\n"
                    f"💰 <b>BALANCE:</b> ${bal:.4f}\n"
                    f"📱 <b>OTPs:</b> {otps}\n"
                    f"🚫 <b>BANNED:</b> {banned}\n"
                    f"👮 <b>ADMIN:</b> {admin}\n"
                    f"━━━━━━━━━━━━━━━")
            user_states.pop(chat_id, None)
            return

        if s == "fj_add_link":
            d = load_data()
            link = text.strip()
            chat_id_part = link.split("/")[-1]
            title = chat_id_part
            try:
                ch = bot.get_chat("@" + chat_id_part)
                title = ch.title or chat_id_part
            except Exception:
                pass
            d.setdefault("force_join_groups", []).append({"title": title, "link": link, "chat_id": "@" + chat_id_part})
            save_data(d)
            safe_send(chat_id, f"✅ <b>FORCE-JOIN GROUP ADDED:</b> {html.escape(title)}")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "fg_add_id":
            try:
                gid = int(text)
                d = load_data()
                groups = d.get("forward_groups", [])
                if gid not in groups:
                    groups.append(gid)
                    d["forward_groups"] = groups
                    save_data(d)
                    safe_send(chat_id, f"✅ <b>FORWARD GROUP ADDED:</b> <code>{gid}</code>")
                else:
                    safe_send(chat_id, "⚠️ <b>ALREADY ADDED</b>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID CHAT ID</b>")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "add_numbers_txt":
            numbers = [line.strip() for line in text.splitlines() if line.strip()]
            d = load_data()
            rng = d.get("panels", {}).get(state.get("panel_id"), {}).get("ranges", {}).get(state.get("rng_id"))
            if rng:
                rng.setdefault("numbers", [])
                added = 0
                for n in numbers:
                    if n not in rng["numbers"]:
                        rng["numbers"].append(n)
                        added += 1
                save_data(d)
                safe_send(chat_id, f"✅ <b>ADDED {added} NUMBERS</b>\n📊 Total: <code>{len(rng['numbers'])}</code>")
                show_range_detail(chat_id, state.get("panel_id"), state.get("rng_id"))
            user_states.pop(chat_id, None)
            return

        # ---- SET MIN WITHDRAW STATE ----
        if s == "set_min_withdraw":
            try:
                amount = float(text)
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE GREATER THAN 0!</b>")
                    return
                d = load_data()
                d["min_withdraw"] = amount
                save_data(d)
                safe_send(chat_id, f"✅ <b>MINIMUM WITHDRAWAL SET TO: ${amount:.2f}</b>")
                user_states.pop(chat_id, None)
                show_admin_panel(chat_id)
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT!</b> Enter a number like: 0.50, 1.00, 2.00")
            return

        # ---- SET BALANCE CLEAN DATE STATE ----
        if s == "set_balance_clean_date":
            clean_date = text.strip()
            try:
                from datetime import datetime as dt
                dt.strptime(clean_date, "%Y-%m-%d")
                d = load_data()
                d["balance_clean_date"] = clean_date
                save_data(d)
                safe_send(chat_id, f"✅ <b>BALANCE CLEAN SCHEDULED!</b>\n📅 Date: {clean_date}\n\nAll balances will be reset to $0.00 on this date.")
                user_states.pop(chat_id, None)
                show_admin_panel(chat_id)
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID DATE FORMAT!</b>\nUse YYYY-MM-DD format\n<i>e.g. 2026-09-15</i>")
            return

        # ---- ADMIN VIEW MEMBER BOT LOOKUP STATE ----
        if s == "admin_view_member_bot_lookup":
            target = text.strip()
            d = load_data()
            found = None
            if target.startswith("@"):
                target = target[1:]
                for uid in d.get("users", []):
                    try:
                        ch = bot.get_chat(uid)
                        if ch.username and ch.username.lower() == target.lower():
                            found = uid
                            break
                    except Exception:
                        continue
            else:
                try:
                    found = int(target)
                except ValueError:
                    found = None

            if found is None:
                safe_send(chat_id, "❌ <b>USER NOT FOUND</b>")
                user_states.pop(chat_id, None)
                return

            bal = d.get("balances", {}).get(str(found), 0.0)
            otps = d.get("otp_counts", {}).get(str(found), 0)
            wd_requests = [w for w in d.get("withdrawal_requests", []) if w.get("user_id") == found]
            pending_wd = [w for w in wd_requests if w.get("status") == "pending"]
            approved_wd = [w for w in wd_requests if w.get("status") == "approved"]
            total_wd = sum(w.get("amount", 0) for w in wd_requests)
            try:
                ch = bot.get_chat(found)
                name = html.escape(ch.first_name or "User")
                username = f"@{ch.username}" if ch.username else "N/A"
            except Exception:
                name = str(found)
                username = "N/A"

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(ibtn(f"💰 DEDUCT BALANCE", callback_data=f"deduct_bal_{found}", style="danger"),
                       ibtn(f"➕ ADD BALANCE", callback_data=f"add_bal_{found}", style="success"))
            markup.add(ibtn("🔙 BACK", callback_data="admin_back", style="primary"))
            safe_send(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"🤖 <b>MEMBER BOT DETAILS</b>\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"🆔 <b>ID:</b> <code>{found}</code>\n"
                f"📛 <b>Name:</b> {name}\n"
                f"👤 <b>Username:</b> {username}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💰 <b>Balance:</b> ${bal:.4f}\n"
                f"📱 <b>OTPs Used:</b> {otps}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💳 <b>Withdrawals:</b> {len(wd_requests)}\n"
                f"⏳ <b>Pending:</b> {len(pending_wd)}\n"
                f"✅ <b>Approved:</b> {len(approved_wd)}\n"
                f"💵 <b>Total withdrawn:</b> ${total_wd:.2f}\n"
                f"━━━━━━━━━━━━━━━",
                markup)
            user_states.pop(chat_id, None)
            return

        # ---- ADD MEMBER BALANCE STATE ----
        if s == "add_member_balance":
            try:
                amount = float(text)
                state_obj = user_states.get(chat_id, {})
                target_uid = state_obj.get("target_user_id")
                if not target_uid:
                    safe_send(chat_id, "❌ <b>ERROR: No target user set</b>")
                    user_states.pop(chat_id, None)
                    return
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE GREATER THAN 0!</b>")
                    return
                d = load_data()
                uid_str = str(target_uid)
                current_bal = d.get("balances", {}).get(uid_str, 0.0)
                d.setdefault("balances", {})[uid_str] = current_bal + amount
                save_data(d)
                try:
                    bot.send_message(target_uid, f"💰 <b>BALANCE ADDED!</b>\n\nAmount: ${amount:.2f}\nNew Balance: ${current_bal + amount:.4f}", parse_mode="HTML")
                except Exception:
                    pass
                safe_send(chat_id, f"✅ <b>BALANCE ADDED!</b>\n👤 User: <code>{target_uid}</code>\n💰 Amount: ${amount:.2f}\n💵 New Balance: ${current_bal + amount:.4f}")
                user_states.pop(chat_id, None)
                show_admin_panel(chat_id)
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT!</b> Enter a number like: 0.50, 1.00, 2.00")
            return

        # ---- DEDUCT MEMBER BALANCE STATE ----
        if s == "deduct_member_balance":
            try:
                amount = float(text)
                state_obj = user_states.get(chat_id, {})
                target_uid = state_obj.get("target_user_id")
                if not target_uid:
                    safe_send(chat_id, "❌ <b>ERROR: No target user set</b>")
                    user_states.pop(chat_id, None)
                    return
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE GREATER THAN 0!</b>")
                    return
                d = load_data()
                uid_str = str(target_uid)
                current_bal = d.get("balances", {}).get(uid_str, 0.0)
                if amount > current_bal:
                    safe_send(chat_id, f"❌ <b>AMOUNT EXCEEDS BALANCE!</b>\n💰 Current: ${current_bal:.4f}")
                    return
                d["balances"][uid_str] = current_bal - amount
                save_data(d)
                try:
                    bot.send_message(target_uid, f"💰 <b>YOUR BALANCE HAS BEEN DEDUCTED</b>\n\nAmount: ${amount:.2f}\nNew Balance: ${current_bal - amount:.4f}", parse_mode="HTML")
                except Exception:
                    pass
                safe_send(chat_id, f"✅ <b>BALANCE DEDUCTED!</b>\n👤 User: <code>{target_uid}</code>\n💰 Amount: ${amount:.2f}\n💵 New Balance: ${current_bal - amount:.4f}")
                user_states.pop(chat_id, None)
                show_admin_panel(chat_id)
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT!</b> Enter a number like: 0.50, 1.00, 2.00")
            return

        # ---- ADMIN: ADD SERVICE ----
        if s == "admin_add_service":
            d = load_data()
            services = d.setdefault("services", [])
            name = text.strip()
            if any(sv.get("name", "").upper() == name.upper() for sv in services):
                safe_send(chat_id, f"⚠️ <b>SERVICE ALREADY EXISTS:</b> {html.escape(name)}")
            else:
                price = d.get("settings", {}).get("price_per_otp", 0.001)
                services.append({"name": name, "price": price})
                save_data(d)
                safe_send(chat_id, f"✅ <b>SERVICE ADDED:</b> {emo(name)} {html.escape(name)} — ${price:.4f}/OTP")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        # ---- ADMIN: REMOVE SERVICE ----
        if s == "admin_remove_service":
            d = load_data()
            services = d.get("services", [])
            name = text.strip()
            new_svcs = [sv for sv in services if sv.get("name", "").upper() != name.upper()]
            if len(new_svcs) == len(services):
                safe_send(chat_id, f"❌ <b>SERVICE NOT FOUND:</b> {html.escape(name)}")
            else:
                d["services"] = new_svcs
                save_data(d)
                safe_send(chat_id, f"✅ <b>SERVICE REMOVED:</b> {html.escape(name)}")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        # ---- ADMIN: EDIT SERVICE PRICE ----
        if s == "admin_edit_service_price":
            try:
                parts = text.strip().split()
                if len(parts) < 2:
                    safe_send(chat_id, "❌ <b>FORMAT:</b> SERVICE_NAME PRICE\n<i>e.g. Telegram 0.005</i>")
                    return
                name = parts[0]
                price = float(parts[1])
                d = load_data()
                found = False
                for sv in d.get("services", []):
                    if sv.get("name", "").upper() == name.upper():
                        sv["price"] = price
                        found = True
                        break
                if found:
                    save_data(d)
                    safe_send(chat_id, f"✅ <b>PRICE UPDATED:</b> {html.escape(name)} — ${price:.4f}/OTP")
                else:
                    safe_send(chat_id, f"❌ <b>SERVICE NOT FOUND:</b> {html.escape(name)}")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID PRICE</b>")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        # ---- ADMIN: SET PRICE ALL ----
        if s == "admin_set_price_all":
            try:
                price = float(text)
                d = load_data()
                d.setdefault("settings", {})["price_per_otp"] = price
                for sv in d.get("services", []):
                    sv["price"] = price
                save_data(d)
                safe_send(chat_id, f"✅ <b>ALL SERVICE PRICES SET TO:</b> ${price:.4f}/OTP")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID PRICE</b>")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        # ---- ADMIN: SET MAX NUMBERS ----
        if s == "set_max_numbers":
            try:
                val = int(text)
                d = load_data()
                d.setdefault("settings", {})["max_numbers"] = val
                save_data(d)
                safe_send(chat_id, f"✅ <b>MAX NUMBERS SET TO:</b> {val}")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID NUMBER</b>")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        # ---- ADMIN: MAINTENANCE MESSAGE ----
        if s == "set_maintenance_msg":
            d = load_data()
            d["maintenance_msg"] = text
            save_data(d)
            safe_send(chat_id, f"✅ <b>MAINTENANCE MSG SET:</b>\n<i>{html.escape(text)}</i>")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        # ---- ADMIN: BLACKLIST ADD ----
        if s == "admin_blacklist_add":
            try:
                bid = int(text)
                d = load_data()
                bl = d.get("blacklist", [])
                if bid not in bl:
                    bl.append(bid)
                    d["blacklist"] = bl
                    save_data(d)
                    safe_send(chat_id, f"🚫 <b>USER BLACKLISTED:</b> <code>{bid}</code>")
                else:
                    safe_send(chat_id, "⚠️ <b>ALREADY BLACKLISTED</b>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID USER ID</b>")
            user_states.pop(chat_id, None)
            show_blacklist_menu(chat_id)
            return

        # ---- ADMIN: BLACKLIST REMOVE ----
        if s == "admin_blacklist_remove":
            try:
                bid = int(text)
                d = load_data()
                bl = d.get("blacklist", [])
                if bid in bl:
                    bl.remove(bid)
                    d["blacklist"] = bl
                    save_data(d)
                    safe_send(chat_id, f"♻️ <b>USER REMOVED FROM BLACKLIST:</b> <code>{bid}</code>")
                else:
                    safe_send(chat_id, "❌ <b>USER NOT IN BLACKLIST</b>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID USER ID</b>")
            user_states.pop(chat_id, None)
            show_blacklist_menu(chat_id)
            return

        # ---- ADMIN: ADD ALL BONUS ----
        if s == "admin_add_all_bonus":
            try:
                amount = float(text)
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE POSITIVE</b>")
                    return
                d = load_data()
                users = d.get("users", [])
                count = 0
                for uid in users:
                    uid_str = str(uid)
                    d.setdefault("balances", {})[uid_str] = d.get("balances", {}).get(uid_str, 0.0) + amount
                    count += 1
                save_data(d)
                safe_send(chat_id, f"✅ <b>BONUS ADDED!</b>\n💰 ${amount:.4f} to {count} users\n📊 Total distributed: ${amount * count:.4f}")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT</b>")
            user_states.pop(chat_id, None)
            show_admin_panel(chat_id)
            return

        # ---- ADMIN: DEDUCT ALL FEE ----
        if s == "admin_deduct_all_fee":
            try:
                amount = float(text)
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMOUNT MUST BE POSITIVE</b>")
                    return
                d = load_data()
                users = d.get("users", [])
                count = 0
                for uid in users:
                    uid_str = str(uid)
                    current = d.get("balances", {}).get(uid_str, 0.0)
                    new_bal = max(0, current - amount)
                    d.setdefault("balances", {})[uid_str] = new_bal
                    count += 1
                save_data(d)
                safe_send(chat_id, f"✅ <b>FEE DEDUCTED!</b>\n💸 ${amount:.4f} from {count} users")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT</b>")
            user_states.pop(chat_id, None)
            show_admin_panel(chat_id)
            return

        # ---- ADMIN: BROADCAST TO SPECIFIC USER ----
        if s == "broadcast_specific":
            try:
                parts = text.strip().split(" ", 1)
                if len(parts) < 2:
                    safe_send(chat_id, "❌ <b>FORMAT:</b> USER_ID Your message here")
                    return
                target_id = int(parts[0])
                msg_text = parts[1]
                bot.send_message(target_id, f"📢 <b>MESSAGE FROM ADMIN:</b>\n\n{msg_text}", parse_mode="HTML")
                safe_send(chat_id, f"✅ <b>MESSAGE SENT TO</b> <code>{target_id}</code>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID USER ID</b>")
            except Exception as e:
                safe_send(chat_id, f"❌ <b>FAILED:</b> {html.escape(str(e))}")
            user_states.pop(chat_id, None)
            show_broadcast_targeted(chat_id)
            return

        # ---- ADMIN: BROADCAST BY BALANCE ----
        if s == "broadcast_by_balance":
            try:
                min_bal = float(text)
                user_states[chat_id] = {"state": "broadcast_msg", "target": "by_balance", "min_balance": min_bal}
                safe_send(chat_id, f"💰 <b>SEND TO USERS WITH BALANCE ≥ ${min_bal:.2f}</b>\nEnter broadcast message:\n\n❌ /cancel to cancel")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID AMOUNT</b>")
            return

        # ---- ADMIN: SEARCH USER ----
        if s == "admin_search_user":
            target = text.strip()
            d = load_data()
            found = None
            if target.startswith("@"):
                uname = target[1:]
                for uid in d.get("users", []):
                    try:
                        ch = bot.get_chat(uid)
                        if ch.username and ch.username.lower() == uname.lower():
                            found = uid
                            break
                    except Exception:
                        continue
            else:
                try:
                    found = int(target)
                except ValueError:
                    found = None
            if found is None:
                safe_send(chat_id, "❌ <b>USER NOT FOUND</b>")
            else:
                bal = d.get("balances", {}).get(str(found), 0.0)
                otps = d.get("otp_counts", {}).get(str(found), 0)
                is_banned = found in d.get("banned_users", [])
                is_bl = found in d.get("blacklist", [])
                try:
                    ch = bot.get_chat(found)
                    name = html.escape(ch.first_name or "?")
                    uname = f"@{ch.username}" if ch.username else "N/A"
                except:
                    name = str(found)
                    uname = "N/A"
                text_out = (
                    f"━━━━━━━━━━━━━━━\n🔍 <b>SEARCH RESULT</b>\n━━━━━━━━━━━━━━━\n\n"
                    f"🆔 <b>ID:</b> <code>{found}</code>\n"
                    f"📛 <b>Name:</b> {name}\n"
                    f"👤 <b>Username:</b> {uname}\n"
                    f"💰 <b>Balance:</b> ${bal:.4f}\n"
                    f"📱 <b>OTPs:</b> {otps}\n"
                    f"🚫 <b>Banned:</b> {'YES' if is_banned else 'NO'}\n"
                    f"黑名单 <b>Blacklisted:</b> {'YES' if is_bl else 'NO'}\n"
                    f"━━━━━━━━━━━━━━━"
                )
                markup = InlineKeyboardMarkup(row_width=2)
                markup.add(ibtn("💰 ADD BAL", callback_data=f"add_bal_{found}", style="success"),
                           ibtn("💸 DEDUCT", callback_data=f"deduct_bal_{found}", style="danger"))
                if is_banned:
                    markup.add(ibtn("♻️ UNBAN", callback_data=f"unban_{found}", style="success"))
                else:
                    markup.add(ibtn("🔨 BAN", callback_data=f"uv_ban_do", style="danger"))
                markup.add(ibtn("🔙 BACK", callback_data="admin_user_view", style="primary"))
                safe_send(chat_id, text_out, markup)
            user_states.pop(chat_id, None)
            return

        # ---- ADMIN: SEARCH NUMBERS ----
        if s == "admin_search_numbers":
            search = text.strip()
            data = load_data()
            results = []
            for pid, panel in data.get("panels", {}).items():
                for rid, rng in panel.get("ranges", {}).items():
                    for n in rng.get("numbers", []):
                        if search in n:
                            status = "✅ Avail" if n not in rng.get("used_numbers", []) else "🔒 Used"
                            results.append((n, rng.get("app", "?"), rng.get("name", "?"), status))
            if not results:
                safe_send(chat_id, f"❌ <b>NO NUMBERS MATCHING:</b> <code>{html.escape(search)}</code>")
            else:
                text_out = f"🔍 <b>SEARCH: {html.escape(search)}</b> ({len(results)} results)\n\n"
                for n, app, country, status in results[:15]:
                    text_out += f"<code>{n}</code> | {emo(app)} {app} | {status}\n"
                safe_send(chat_id, text_out)
            user_states.pop(chat_id, None)
            return

        # ---- ADMIN: BROADCAST MESSAGE (with target filtering) ----
        # This overrides the simple broadcast_msg handler
        # Already handled above in the original code

        # ---- SCRAPED PANEL URL ----
        if s == "scraped_panel_url":
            url = text.strip().rstrip("/")
            state_obj = user_states.get(chat_id, {})
            pid = state_obj.get("panel_id")
            d = load_data()
            p = d.get("panels", {}).get(pid)
            if p:
                p["panel_url"] = url
                save_data(d)
            # Now ask for agent/client type
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(ibtn("🤖 Agent", callback_data=f"ptype_scraped_agent|{pid}", style="success"))
            markup.add(ibtn("👥 Client", callback_data=f"ptype_scraped_client|{pid}", style="danger"))
            safe_send(chat_id,
                f"✅ <b>URL SET:</b> <code>{html.escape(url)}</code>\n\n"
                f"👤 <b>SELECT PANEL TYPE:</b>",
                markup)
            return

        # ---- SCRAPED PANEL USERNAME ----
        if s == "scraped_panel_user":
            state_obj = user_states.get(chat_id, {})
            pid = state_obj.get("panel_id")
            d = load_data()
            p = d.get("panels", {}).get(pid)
            if p:
                p["login_user"] = text.strip()
                save_data(d)
            user_states[chat_id] = {"state": "scraped_panel_pass", "panel_id": pid}
            safe_send(chat_id,
                f"✅ <b>USERNAME SET</b>\n\n"
                f"🔑 <b>ENTER PASSWORD:</b>\n\n"
                f"❌ /cancel to cancel")
            return

        # ---- SCRAPED PANEL PASSWORD ----
        if s == "scraped_panel_pass":
            state_obj = user_states.get(chat_id, {})
            pid = state_obj.get("panel_id")
            d = load_data()
            p = d.get("panels", {}).get(pid)
            if p:
                p["login_pass"] = text.strip()
                p["status"] = "active"
                save_data(d)
            user_states.pop(chat_id, None)
            safe_send(chat_id, "🧪 <b>TESTING CONNECTION...</b>")
            if scraped_login(pid):
                sesskey = _get_sesskey_scraped(pid)
                otps = scraped_fetch_otps(pid)
                safe_send(chat_id,
                    f"━━━━━━━━━━━━━━━\n"
                    f"✅ <b>PANEL SETUP COMPLETE!</b>\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"📋 <b>Name:</b> {html.escape(p.get('name', ''))}\n"
                    f"🔗 <b>URL:</b> <code>{html.escape(p.get('panel_url', ''))}</code>\n"
                    f"👤 <b>Type:</b> {p.get('panel_type', 'agent').upper()}\n"
                    f"🔐 <b>Login:</b> ✅ Success\n"
                    f"🔑 <b>Sesskey:</b> {'✅' if sesskey else '⚠️'}\n"
                    f"📱 <b>OTPs Found:</b> {len(otps)}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📡 <b>OTP monitoring ACTIVE!</b>")
                show_panel_detail(chat_id, pid)
            else:
                safe_send(chat_id,
                    f"━━━━━━━━━━━━━━━\n"
                    f"❌ <b>LOGIN FAILED!</b>\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"Check URL, username, password.\n"
                    f"Panel saved - edit from details.")
                show_panel_detail(chat_id, pid)
            return

        # ---- ADMIN: ADD ALL BONUS ----
        if s == "admin_add_all_bonus":
            try:
                amount = float(text)
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMUST BE POSITIVE</b>")
                    return
                d = load_data()
                count = 0
                for uid in d.get("users", []):
                    uid_str = str(uid)
                    d.setdefault("balances", {})[uid_str] = d.get("balances", {}).get(uid_str, 0.0) + amount
                    count += 1
                save_data(d)
                safe_send(chat_id, f"✅ <b>BONUS SENT!</b> ${amount:.4f} to {count} users")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID</b>")
            user_states.pop(chat_id, None)
            show_admin_panel(chat_id)
            return

        # ---- ADMIN: DEDUCT ALL FEE ----
        if s == "admin_deduct_all_fee":
            try:
                amount = float(text)
                if amount <= 0:
                    safe_send(chat_id, "❌ <b>AMUST BE POSITIVE</b>")
                    return
                d = load_data()
                count = 0
                for uid in d.get("users", []):
                    uid_str = str(uid)
                    cur = d.get("balances", {}).get(uid_str, 0.0)
                    d.setdefault("balances", {})[uid_str] = max(0, cur - amount)
                    count += 1
                save_data(d)
                safe_send(chat_id, f"✅ <b>FEE DEDUCTED!</b> ${amount:.4f} from {count}")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID</b>")
            user_states.pop(chat_id, None)
            show_admin_panel(chat_id)
            return

        # ---- ADMIN: BROADCAST SPECIFIC ----
        if s == "broadcast_specific":
            try:
                parts = text.strip().split(" ", 1)
                if len(parts) < 2:
                    safe_send(chat_id, "❌ <b>FORMAT:</b> USER_ID Message")
                    return
                target_id = int(parts[0])
                bot.send_message(target_id, f"📢 <b>ADMIN:</b>\n\n{parts[1]}", parse_mode="HTML")
                safe_send(chat_id, f"✅ <b>SENT TO</b> <code>{target_id}</code>")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID ID</b>")
            except Exception as e:
                safe_send(chat_id, f"❌ {html.escape(str(e))}")
            user_states.pop(chat_id, None)
            return

        # ---- ADMIN: BROADCAST BY BALANCE ----
        if s == "broadcast_by_balance":
            try:
                min_bal = float(text)
                user_states[chat_id] = {"state": "broadcast_msg", "target": "by_balance", "min_balance": min_bal}
                safe_send(chat_id, f"💰 <b>USERS >= ${min_bal:.2f}</b>\nEnter message:\n\n❌ /cancel")
            except ValueError:
                safe_send(chat_id, "❌ <b>INVALID</b>")
            return

        # ---- ADMIN: SEARCH USER ----
        if s == "admin_search_user":
            target = text.strip()
            d = load_data()
            found = None
            if target.startswith("@"):
                for uid in d.get("users", []):
                    try:
                        ch = bot.get_chat(uid)
                        if ch.username and ch.username.lower() == target[1:].lower():
                            found = uid
                            break
                    except:
                        continue
            else:
                try: found = int(target)
                except: found = None
            if found is None:
                safe_send(chat_id, "❌ <b>NOT FOUND</b>")
            else:
                bal = d.get("balances", {}).get(str(found), 0.0)
                otps = d.get("otp_counts", {}).get(str(found), 0)
                try:
                    ch = bot.get_chat(found)
                    name = html.escape(ch.first_name or "?")
                except:
                    name = str(found)
                safe_send(chat_id, f"🔍 <code>{found}</code> | {name} | ${bal:.4f} | {otps} OTPs")
            user_states.pop(chat_id, None)
            return

        # ---- ADMIN: SEARCH NUMBERS ----
        if s == "admin_search_numbers":
            search = text.strip()
            data = load_data()
            results = []
            for pid_p, panel in data.get("panels", {}).items():
                for rid, rng in panel.get("ranges", {}).items():
                    for n in rng.get("numbers", []):
                        if search in n:
                            s_icon = "✅" if n not in rng.get("used_numbers", []) else "🔒"
                            results.append(f"{s_icon} <code>{n}</code>")
            if results:
                safe_send(chat_id, f"🔍 {len(results)} results:\n" + "\n".join(results[:20]))
            else:
                safe_send(chat_id, f"❌ <b>NO MATCH</b>")
            user_states.pop(chat_id, None)
            return

        # ---- ADMIN: SERVICES ----
        if s == "admin_add_service":
            d = load_data()
            svcs = d.setdefault("services", [])
            name = text.strip()
            if any(sv.get("name","").upper() == name.upper() for sv in svcs):
                safe_send(chat_id, "⚠️ <b>EXISTS</b>")
            else:
                price = d.get("settings",{}).get("price_per_otp", 0.001)
                svcs.append({"name": name, "price": price})
                save_data(d)
                safe_send(chat_id, f"✅ <b>ADDED:</b> {html.escape(name)}")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        if s == "admin_remove_service":
            d = load_data()
            name = text.strip()
            before = len(d.get("services", []))
            d["services"] = [sv for sv in d.get("services", []) if sv.get("name","").upper() != name.upper()]
            save_data(d)
            safe_send(chat_id, f"{'✅ REMOVED' if len(d['services']) < before else '❌ NOT FOUND'}")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        if s == "admin_edit_service_price":
            try:
                parts = text.strip().split()
                name, price = parts[0], float(parts[1])
                d = load_data()
                for sv in d.get("services", []):
                    if sv.get("name","").upper() == name.upper():
                        sv["price"] = price
                        save_data(d)
                        safe_send(chat_id, f"✅ <b>UPDATED:</b> {name} ${price:.4f}")
                        break
                else:
                    safe_send(chat_id, "❌ NOT FOUND")
            except:
                safe_send(chat_id, "❌ FORMAT: NAME PRICE")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        if s == "admin_set_price_all":
            try:
                price = float(text)
                d = load_data()
                d.setdefault("settings", {})["price_per_otp"] = price
                for sv in d.get("services", []):
                    sv["price"] = price
                save_data(d)
                safe_send(chat_id, f"✅ ALL PRICES: ${price:.4f}")
            except:
                safe_send(chat_id, "❌ INVALID")
            user_states.pop(chat_id, None)
            show_services_menu(chat_id)
            return

        if s == "set_max_numbers":
            try:
                d = load_data()
                d.setdefault("settings", {})["max_numbers"] = int(text)
                save_data(d)
                safe_send(chat_id, f"✅ MAX NUMBERS: {text}")
            except:
                safe_send(chat_id, "❌ INVALID")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "set_maintenance_msg":
            d = load_data()
            d["maintenance_msg"] = text
            save_data(d)
            safe_send(chat_id, "✅ MSG SET")
            user_states.pop(chat_id, None)
            show_admin_system(chat_id)
            return

        if s == "admin_blacklist_add":
            try:
                bid = int(text)
                d = load_data()
                bl = d.get("blacklist", [])
                if bid not in bl:
                    bl.append(bid)
                    d["blacklist"] = bl
                    save_data(d)
                safe_send(chat_id, f"🚫 BLACKLISTED: {bid}")
            except:
                safe_send(chat_id, "❌ INVALID")
            user_states.pop(chat_id, None)
            return

        if s == "admin_blacklist_remove":
            try:
                bid = int(text)
                d = load_data()
                bl = d.get("blacklist", [])
                if bid in bl:
                    bl.remove(bid)
                    d["blacklist"] = bl
                    save_data(d)
                safe_send(chat_id, f"♻️ REMOVED: {bid}")
            except:
                safe_send(chat_id, "❌ INVALID")
            user_states.pop(chat_id, None)
            return

        # Unknown state fallback
        user_states.pop(chat_id, None)
        show_main_menu(chat_id, first_name)
        return


    # ---- REPLY KEYBOARD BUTTON HANDLERS ----
    if text == "📱 GET NUMBER":
        show_user_services(chat_id)
        return

    if text == "📊 TRAFFIC":
        show_traffic_info(chat_id)
        return

    if text == "🔐 2FA ONLINE":
        show_2fa_menu_display(chat_id)
        return

    if text == "🏆 LEADERBOARD":
        show_leaderboard(chat_id)
        return

    if text == "📈 STOCK INFO":
        show_stock_info(chat_id)
        return

    if text == "📩 SUPPORT":
        show_support(chat_id, first_name)
        return

    if text == "👥 REFERRALS":
        show_referrals(chat_id)
        return

    if text == "💳 WITHDRAW":
        data_obj = load_data()
        bal = data_obj.get("balances", {}).get(str(chat_id), 0.0)
        min_wd = data_obj.get("min_withdraw", 1.0)
        if bal < min_wd:
            markup = InlineKeyboardMarkup().add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
            safe_send(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"《 💳 <b>WITHDRAWAL</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"💰 <b>BALANCE:</b> ${bal:.4f}\n"
                f"⚠️ <b>MINIMUM WITHDRAWAL: ${min_wd:.2f}</b>\n\n"
                f"<b>EARN MORE VIA REFERRALS!</b>\n"
                f"💰 <b>$0.001 PER REFERRAL</b>\n"
                f"━━━━━━━━━━━━━━━",
                markup)
        else:
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(ibtn("💳 REQUEST WITHDRAWAL", callback_data="request_withdraw", style="success"))
            markup.add(ibtn("🔙 BACK", callback_data="close_menu", style="primary"))
            safe_send(chat_id,
                f"━━━━━━━━━━━━━━━\n"
                f"《 💳 <b>WITHDRAWAL</b> 》\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"💰 <b>YOUR BALANCE:</b> ${bal:.4f}\n"
                f"✅ <b>MINIMUM: $1.00</b>\n\n"
                f"<b>TAP BELOW TO REQUEST</b>\n"
                f"━━━━━━━━━━━━━━━",
                markup)
        return

    if text == "📱 MY NUMBERS":
        show_my_numbers(chat_id)
        return

    if text == "📊 MY STATS":
        show_my_stats(chat_id)
        return

    if text == "💳 WD HISTORY":
        show_withdrawal_history(chat_id)
        return

    if text == "❓ HELP":
        show_help_menu(chat_id)
        return

    if text == "⚙️ ADMIN PANEL":
        if is_admin(chat_id):
            show_admin_panel(chat_id)
        else:
            safe_send(chat_id, "❌ <b>ACCESS DENIED</b>")
        return

    # ---- DEFAULT: MAIN MENU ----
    safe_send(chat_id, "ℹ️ <b>USE THE MENU BUTTONS BELOW</b>", get_main_menu(chat_id))


# -------------------- PANEL TYPE PICKER (inline after creating panel) --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("ptype_"))
def panel_type_picker(call):
    chat_id = call.message.chat.id
    if not is_admin(chat_id):
        return
    parts = call.data.split("|")
    if len(parts) < 2:
        bot.answer_callback_query(call.id, "❌ Invalid callback")
        return
    ptype = parts[0].replace("ptype_", "")
    pid = parts[1]
    d = load_data()
    p = d.get("panels", {}).get(pid)
    if not p:
        bot.answer_callback_query(call.id, "❌ Panel not found")
        return
    panel_type = "agent" if "agent" in ptype else "client"
    p["type"] = "scraped"
    p["panel_type"] = panel_type
    p["fetch_type"] = "scraped"
    save_data(d)
    bot.answer_callback_query(call.id, f"✅ {panel_type.upper()} Panel")
    user_states[chat_id] = {"state": "scraped_panel_user", "panel_id": pid}
    safe_send(chat_id,
        f"✅ <b>Type:</b> {panel_type.upper()}\n\n"
        f"👤 <b>ENTER USERNAME:</b>\n"
        f"<i>Login username for the panel</i>\n\n"
        f"❌ /cancel to cancel")



# -------------------- MAIN --------------------
if __name__ == "__main__":
    log("=" * 50)
    log(f"🤖 BOT STARTED — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"👮 MAIN ADMINS: {MAIN_ADMINS}")
    log("=" * 50)
    notify_all_admins(f"🤖 <b>BOT STARTED</b>\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n👮 <b>ADMINS:</b> {len(MAIN_ADMINS)}")
    # Check and run scheduled balance clean
    def _scheduled_balance_clean():
        try:
            d = load_data()
            clean_date = d.get("balance_clean_date", "")
            if clean_date and datetime.now().strftime("%Y-%m-%d") == clean_date:
                d["balances"] = {}
                d["balance_clean_date"] = ""
                d["balance_clean_amount"] = 0.0
                save_data(d)
                users = d.get("users", [])
                sent = 0
                for uid in users:
                    try:
                        bot.send_message(uid, "🧹 <b>ALL BALANCES HAVE BEEN CLEANED</b>\n\nAll member balances have been reset to $0.00 as scheduled by admin.", parse_mode="HTML")
                        sent += 1
                        time.sleep(0.05)
                    except Exception:
                        pass
                notify_all_admins(f"🧹 <b>BALANCE CLEAN COMPLETED</b>\n👥 Notified: {sent} users")
        except Exception as e:
            log(f"[ERROR] Balance clean scheduler: {e}")
    _scheduled_balance_clean()
    import threading
    def _scraped_monitor():
        while True:
            try:
                scraped_monitor_tick()
            except Exception as e:
                log(f"[SCRAPED MONITOR ERROR] {e}")
            time.sleep(30)
    _mt = threading.Thread(target=_scraped_monitor, daemon=True)
    _mt.start()
    log("[SCRAPED MONITOR] Background started (30s interval)")

    # OTP auto-scan: check scraped panels for matching numbers
    def _otp_scanner():
        while True:
            try:
                data = load_data()
                sessions = data.get("number_session", {})
                price = data.get("settings", {}).get("price_per_otp", 0.001)
                for sid, sess in list(sessions.items()):
                    if sess.get("status") not in ("awaiting_otp", "polling"):
                        continue
                    number = sess.get("number", "")
                    panel_id = sess.get("panel_id", "")
                    # Check this session's panel first
                    panel = data.get("panels", {}).get(panel_id, {})
                    otps = []
                    if panel.get("type") == "scraped":
                        otps = scraped_fetch_otps(panel_id)
                    else:
                        # For combo numbers, check ALL scraped panels
                        for pid, p in data.get("panels", {}).items():
                            if p.get("type") == "scraped" and p.get("status") == "active":
                                otps.extend(scraped_fetch_otps(pid))
                    for sms in otps:
                        sms_phone = re.sub(r'\D', '', sms.get("phone", ""))
                        num_clean = re.sub(r'\D', '', number)
                        if num_clean and (num_clean in sms_phone or sms_phone in num_clean):
                            otp_code = sms.get("otp", "")
                            if not otp_code:
                                continue
                            sess["status"] = "completed"
                            sess["otp_code"] = otp_code
                            data.setdefault("number_session", {})[sid] = sess
                            uid = str(sess.get("user_id"))
                            data.setdefault("balances", {})[uid] = data.get("balances", {}).get(uid, 0.0) + price
                            data.setdefault("otp_counts", {})[uid] = data.get("otp_counts", {}).get(uid, 0) + 1
                            save_data(data)
                            user_id = sess.get("user_id")
                            app_name = sess.get("app", "?")
                            try:
                                bot.send_message(user_id,
                                    f"━━━━━━━━━━━━━━━\n"
                                    f"《 ✅ <b>OTP RECEIVED!</b> 》\n"
                                    f"━━━━━━━━━━━━━━━\n\n"
                                    f"📱 <b>NUMBER:</b> <code>{number}</code>\n"
                                    f"🔑 <b>OTP:</b> <code>{html.escape(otp_code)}</code>\n"
                                    f"💰 <b>EARNED:</b> ${price:.4f}\n"
                                    f"━━━━━━━━━━━━━━━\n"
                                    f"✅ <b>Auto-detected!</b>",
                                    parse_mode="HTML")
                            except Exception as e:
                                log(f"[OTP SCANNER] Notify failed: {e}")
                            # Build Vertex-format message for group
                            country_name = sess.get("country", "Unknown")
                            cflag = get_country_flag(country_name)
                            masked_num = number[:7] + "****" + number[-4:] if len(number) > 11 else number
                            formatted_otp = f"{otp_code[:3]}-{otp_code[3:]}" if len(otp_code) == 6 and otp_code.isdigit() else otp_code
                            svc_emoji = emo(app_name)
                            ts = datetime.now().strftime("%H:%M:%S")
                            wm = load_data().get("watermark", "VERTEX OTP")
                            sep = "\u2501" * 13
                            group_msg = (
                                f"{wm}\n"
                                f"{sep}\n"
                                f"{cflag} {svc_emoji} {app_name.upper()} \U0001f7e2\n"
                                f"\U0001f4f1 {masked_num}\n"
                                f"\U0001f511 OTP: {formatted_otp}\n"
                                f"Don't share this code with others\n"
                                f"\u23f0 {ts}"
                            )
                            forward_to_forward_groups(group_msg)
                            log(f"[OTP SCANNER] Matched: {otp_code} -> {number}")
                            break
                save_data(data)
            except Exception as e:
                log(f"[OTP SCANNER ERROR] {e}")
            time.sleep(15)
    _os = threading.Thread(target=_otp_scanner, daemon=True)
    _os.start()
    log("[OTP SCANNER] Background started (15s)")

    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=["message", "callback_query"]
            )
        except Exception as e:
            err_str = str(e).lower()
            if "409" in err_str or "conflict" in err_str:
                log("[WARN] 409 Conflict - another bot instance is running with this token. Retrying in 10s...")
                log("[HINT] Stop any other bot process using this same token, then this instance will take over.")
                time.sleep(10)
            else:
                log(f"[FATAL] Polling error: {e}")
                time.sleep(5)
            
