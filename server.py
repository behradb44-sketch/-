import os
import json
import time
import re

import requests
from flask import Flask, request, jsonify, send_from_directory


# =========================================================
# BEHRAD AI - SERVER
# =========================================================

app = Flask(__name__, static_folder=".", static_url_path="")

MODEL = "stealth/space-bunny-alpha"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

# ---------------------------------------------------------
# Limits
# ---------------------------------------------------------

MAX_HISTORY = 10
MAX_MESSAGE_CHARS = 9000
MAX_TOTAL_CHARS = 30000

# فقط یک Retry برای درخواست‌های موقتی
MAX_RETRIES = 1

REQUEST_TIMEOUT = (15, 75)


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ یک دستیار هوش مصنوعی فارسی‌زبان سریع، دقیق، دوستانه و حرفه‌ای.

هویت پروژه:
- صاحب و سازنده BEHRAD AI: بهراد محمدی
- نام مستعار/برند سازنده: بهراد ام پلیر
- برند انگلیسی: BEHRAD M PLAYER

اگر کاربر درباره صاحب، سازنده یا مالک BEHRAD AI سؤال کرد:
بگو صاحب و سازنده BEHRAD AI، بهراد محمدی ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.

قوانین پاسخ:
- فارسی را طبیعی و روان بنویس.
- اگر کاربر فارسی صحبت کرد، فارسی جواب بده.
- جواب‌ها واضح و مستقیم باشند.
- برای سؤال ساده، پاسخ کوتاه و سریع بده.
- برای مسائل فنی، مرحله‌به‌مرحله و دقیق توضیح بده.
- اگر اطلاعاتی به‌روز لازم است، از ابزار جستجوی وب استفاده کن.
- اگر ابزار وب در دسترس نبود، اطلاعات را حدس نزن.
- هیچ‌وقت درباره نتیجه جستجو دروغ نساز.
"""


# =========================================================
# SEARCH DETECTION
# =========================================================

SEARCH_PATTERNS = [
    # فارسی
    r"\bامروز\b",
    r"\bالان\b",
    r"\bجدیدترین\b",
    r"\bآخرین\b",
    r"\bاخبار\b",
    r"\bقیمت\b",
    r"\bقیمت امروز\b",
    r"\bقیمت فعلی\b",
    r"\bموجوده\b",
    r"\bموجود است\b",
    r"\bاومده\b",
    r"\bآمده\b",
    r"\bعرضه شده\b",
    r"\bمنتشر شده\b",
    r"\bتازه\b",
    r"\bسال ۲۰۲۶\b",
    r"\b2026\b",
    r"\bاین هفته\b",
    r"\bاین ماه\b",
    r"\bامسال\b",
    r"\bبه‌روز\b",
    r"\bبروز\b",
    r"\bزنده\b",
    r"\bلینک\b",
    r"\bسایت\b",
    r"\bوب\b",
    r"\bسرچ\b",
    r"\bجستجو\b",
    r"\bبررسی کن\b",
    r"\bبگرد\b",
    r"\bپیدا کن\b",

    # انگلیسی
    r"\btoday\b",
    r"\bnow\b",
    r"\blatest\b",
    r"\bnews\b",
    r"\bprice\b",
    r"\bcurrent\b",
    r"\breleased\b",
    r"\bavailable\b",
    r"\b2026\b",
    r"\bsearch\b",
    r"\bwebsite\b",
]


def needs_web_search(messages):
    """
    فقط آخرین پیام کاربر بررسی می‌شود.
    """

    if not messages:
        return False

    last_user = None

    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = msg
            break

    if not last_user:
        return False

    content = last_user.get("content", "")

    if isinstance(content, list):
        text_parts = []

        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))

        content = " ".join(text_parts)

    text = str(content).lower().strip()

    if not text:
        return False

    for pattern in SEARCH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


# =========================================================
# MESSAGE CLEANING
# =========================================================

def normalize_content(content):

    if isinstance(content, str):
        return content[:MAX_MESSAGE_CHARS]

    if not isinstance(content, list):
        return str(content)[:MAX_MESSAGE_CHARS]

    cleaned = []

    for item in content:

        if not isinstance(item, dict):
            continue

        item_type = item.get("type")

        # Text
        if item_type == "text":

            text = str(item.get("text", ""))

            if text:
                cleaned.append({
                    "type": "text",
                    "text": text[:MAX_MESSAGE_CHARS]
                })

        # Image
        elif item_type == "image_url":

            image_url = item.get("image_url")

            if isinstance(image_url, dict):
                url = image_url.get("url")

                if url:
                    cleaned.append({
                        "type": "image_url",
                        "image_url": {
                            "url": url
                        }
                    })

    if not cleaned:
        return ""

    return cleaned


def clean_messages(messages):

    if not isinstance(messages, list):
        return []

    result = []

    for msg in messages:

        if not isinstance(msg, dict):
            continue

        role = msg.get("role")

        if role not in ("user", "assistant"):
            continue

        content = normalize_content(msg.get("content", ""))

        if not content:
            continue

        result.append({
            "role": role,
            "content": content
        })

    # فقط آخرین پیام‌ها
    result = result[-MAX_HISTORY:]

    # محدودیت حجم کل
    total = 0
    final = []

    for msg in reversed(result):

        content = msg.get("content", "")

        if isinstance(content, str):
            size = len(content)
        else:
            try:
                size = len(json.dumps(content, ensure_ascii=False))
            except Exception:
                size = 1000

        if total + size > MAX_TOTAL_CHARS:
            break

        final.append(msg)
        total += size

    final.reverse()

    return final


# =========================================================
# HEADERS
# =========================================================

def openrouter_headers():

    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": "https://behradb44-sketch.github.io/",
        "X-Title": "BEHRAD AI"
    }


# =========================================================
# PAYLOAD
# =========================================================

def build_payload(messages, use_search=False):

    payload = {
        "model": MODEL,

        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            *messages
        ],

        "temperature": 0.65,

        # کمتر = سریع‌تر
        "max_tokens": 2200,

        "stream": False
    }

    # فقط وقتی واقعاً لازم است Search فعال می‌شود
    if use_search:

        payload["tools"] = [
            {
                "type": "openrouter:web_search",
                "parameters": {
                    "engine": "auto",
                    "max_results": 5,
                    "max_total_results": 8
                }
            }
        ]

    return payload


# =========================================================
# EXTRACT ANSWER
# =========================================================

def extract_text(data):

    try:

        choices = data.get("choices")

        if not choices:
            return None

        message = choices[0].get("message", {})

        content = message.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):

            parts = []

            for item in content:

                if isinstance(item, dict):

                    if item.get("type") == "text":
                        text = item.get("text", "")

                        if text:
                            parts.append(text)

            answer = "".join(parts).strip()

            if answer:
                return answer

        return None

    except Exception:
        return None


# =========================================================
# OPENROUTER REQUEST
# =========================================================

def call_openrouter(payload):

    last_error = None

    for attempt in range(MAX_RETRIES + 1):

        try:

            response = requests.post(
                OPENROUTER_URL,
                headers=openrouter_headers(),
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            raw = response.text

            # ---------------------------------------------
            # Success
            # ---------------------------------------------

            if response.status_code == 200:

                try:
                    data = response.json()
                except Exception:

                    print("OPENROUTER INVALID JSON:")
                    print(raw[:3000])

                    return {
                        "ok": False,
                        "status": 502,
                        "error": "OpenRouter پاسخ JSON معتبر نداد."
                    }

                return {
                    "ok": True,
                    "data": data
                }

            # ---------------------------------------------
            # Error
            # ---------------------------------------------

            print(
                f"OpenRouter HTTP {response.status_code}: "
                f"{raw[:3000]}"
            )

            last_error = {
                "status": response.status_code,
                "body": raw[:3000]
            }

            # خطاهای قابل Retry
            if response.status_code in (
                408,
                429,
                500,
                502,
                503,
                504
            ):

                if attempt < MAX_RETRIES:
                    time.sleep(0.7)
                    continue

            return {
                "ok": False,
                "status": response.status_code,
                "error": (
                    f"OpenRouter HTTP {response.status_code}"
                )
            }

        except requests.Timeout:

            print("OpenRouter TIMEOUT")

            last_error = {
                "status": 504,
                "body": "Request timed out"
            }

            if attempt < MAX_RETRIES:
                time.sleep(0.7)
                continue

            return {
                "ok": False,
                "status": 504,
                "error": "زمان پاسخ OpenRouter تمام شد."
            }

        except requests.RequestException as e:

            print("OpenRouter REQUEST ERROR:", repr(e))

            last_error = {
                "status": 502,
                "body": str(e)
            }

            if attempt < MAX_RETRIES:
                time.sleep(0.7)
                continue

            return {
                "ok": False,
                "status": 502,
                "error": "ارتباط با OpenRouter برقرار نشد."
            }

    return {
        "ok": False,
        "status": 502,
        "error": "خطای ناشناخته در OpenRouter"
    }


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def home():

    return send_from_directory(".", "index.html")


@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "BEHRAD AI",
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "model": MODEL
    })


@app.route("/api/chat", methods=["POST"])
def chat():

    # ---------------------------------------------
    # API KEY
    # ---------------------------------------------

    if not OPENROUTER_API_KEY:

        return jsonify({
            "success": False,
            "error": "OPENROUTER_API_KEY تنظیم نشده است."
        }), 500

    # ---------------------------------------------
    # JSON
    # ---------------------------------------------

    try:

        body = request.get_json(
            silent=True
        )

    except Exception:

        body = None

    if not isinstance(body, dict):

        return jsonify({
            "success": False,
            "error": "درخواست JSON معتبر نیست."
        }), 400

    messages = clean_messages(
        body.get("messages", [])
    )

    if not messages:

        return jsonify({
            "success": False,
            "error": "پیامی برای ارسال وجود ندارد."
        }), 400

    # ---------------------------------------------
    # آیا Search لازم است؟
    # ---------------------------------------------

    use_search = needs_web_search(messages)

    print(
        f"BEHRAD AI | SEARCH={use_search} | "
        f"MESSAGES={len(messages)}"
    )

    # ---------------------------------------------
    # درخواست اول
    # ---------------------------------------------

    payload = build_payload(
        messages,
        use_search=use_search
    )

    result = call_openrouter(payload)

    # ---------------------------------------------
    # اگر Search خراب شد:
    # یک بار بدون Search امتحان کن
    # ---------------------------------------------

    if (
        not result["ok"]
        and use_search
    ):

        print(
            "Web Search request failed. "
            "Retrying without Web Search..."
        )

        fallback_payload = build_payload(
            messages,
            use_search=False
        )

        result = call_openrouter(
            fallback_payload
        )

    # ---------------------------------------------
    # هنوز خطاست
    # ---------------------------------------------

    if not result["ok"]:

        return jsonify({
            "success": False,
            "error": result.get(
                "error",
                "OpenRouter خطای ناشناخته داد."
            )
        }), result.get("status", 500)

    # ---------------------------------------------
    # استخراج متن
    # ---------------------------------------------

    answer = extract_text(
        result["data"]
    )

    if not answer:

        print(
            "OpenRouter returned no text:"
        )

        try:
            print(
                json.dumps(
                    result["data"],
                    ensure_ascii=False
                )[:5000]
            )
        except Exception:
            pass

        return jsonify({
            "success": False,
            "error": (
                "مدل پاسخ متنی قابل نمایش "
                "برنگرداند. دوباره تلاش کن."
            )
        }), 502

    # ---------------------------------------------
    # موفق
    # ---------------------------------------------

    return jsonify({
        "success": True,
        "reply": answer,
        "searched": use_search,
        "model": MODEL
    })


# =========================================================
# TEST
# =========================================================

@app.route("/api/test-ai")
def test_ai():

    test_messages = [
        {
            "role": "user",
            "content": "سلام! فقط یک پاسخ کوتاه بده."
        }
    ]

    payload = build_payload(
        test_messages,
        use_search=False
    )

    result = call_openrouter(payload)

    if not result["ok"]:

        return jsonify({
            "success": False,
            "error": result.get("error")
        }), result.get("status", 500)

    answer = extract_text(
        result["data"]
    )

    return jsonify({
        "success": bool(answer),
        "reply": answer
    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
            )
