import os
import json
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# =========================================================
# CONFIG
# =========================================================

GAPGPT_API_KEY = os.getenv("GAPGPT_API_KEY", "").strip()

PRIMARY_BASE_URL = os.getenv(
    "GAPGPT_BASE_URL",
    "https://api.gapgpt.app/v1"
).rstrip("/")

FALLBACK_BASE_URL = "https://api.gapapi.com/v1"

GAPGPT_MODEL = os.getenv(
    "GAPGPT_MODEL",
    "gpt-4o"
).strip()

REQUEST_TIMEOUT = int(
    os.getenv("GAPGPT_TIMEOUT", "180")
)

MAX_TOKENS = int(
    os.getenv("GAPGPT_MAX_TOKENS", "16384")
)

# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی، یک دستیار هوش مصنوعی فارسی‌زبان.

سازنده:
Behrad Mohammadi
بهراد محمدی

برند:
BEHRAD M PLAYER

قوانین:
- به فارسی روان پاسخ بده، مگر کاربر زبان دیگری بخواهد.
- پاسخ‌ها را واضح، دقیق و کاربردی بده.
- در برنامه‌نویسی کد کامل و قابل استفاده ارائه کن.
- اگر کاربر درخواست کد کرد، کد را داخل Markdown code block قرار بده.
- از جعل اطلاعات یا ادعای دسترسی به اطلاعات زنده بدون ابزار مناسب خودداری کن.
- لحن دوستانه و طبیعی داشته باش.
- از Markdown برای مرتب‌سازی پاسخ استفاده کن.
"""

# =========================================================
# HELPERS
# =========================================================

def api_error(message, status=500, details=None, provider=None):
    data = {
        "ok": False,
        "error": message
    }

    if details:
        data["details"] = details

    if provider:
        data["provider"] = provider

    return jsonify(data), status


def clean_messages(messages):
    if not isinstance(messages, list):
        return []

    cleaned = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role not in ["system", "user", "assistant"]:
            role = "user"

        cleaned.append({
            "role": role,
            "content": content
        })

    return cleaned


def build_messages(data):
    messages = data.get("messages")

    if isinstance(messages, list) and messages:
        messages = clean_messages(messages)

        # اگر system prompt وجود نداشت، اضافه شود
        has_system = any(
            m.get("role") == "system"
            for m in messages
        )

        if not has_system:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                }
            )

        return messages

    message = data.get("message", "")

    if not isinstance(message, str):
        message = str(message)

    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": message
        }
    ]


def extract_error(data):
    if not isinstance(data, dict):
        return None

    error = data.get("error")

    if isinstance(error, dict):
        return (
            error.get("message")
            or error.get("detail")
            or error.get("code")
            or str(error)
        )

    if isinstance(error, str):
        return error

    return (
        data.get("message")
        or data.get("detail")
        or data.get("details")
    )


def extract_answer(data):
    """
    تلاش برای استخراج پاسخ از چند ساختار مختلف.
    """

    if data is None:
        return None

    # -----------------------------------------------------
    # حالت معمول OpenAI
    # -----------------------------------------------------

    if isinstance(data, dict):

        choices = data.get("choices")

        if isinstance(choices, list) and choices:

            first = choices[0]

            if isinstance(first, dict):

                message = first.get("message")

                if isinstance(message, dict):

                    content = message.get("content")

                    if isinstance(content, str) and content.strip():
                        return content.strip()

                    # بعضی APIها ممکن است content را لیست بدهند
                    if isinstance(content, list):

                        parts = []

                        for item in content:

                            if isinstance(item, dict):

                                text = item.get("text")

                                if isinstance(text, str):
                                    parts.append(text)

                        result = "".join(parts).strip()

                        if result:
                            return result

                # بعضی ساختارها
                text = first.get("text")

                if isinstance(text, str) and text.strip():
                    return text.strip()

        # -------------------------------------------------
        # ساختارهای جایگزین
        # -------------------------------------------------

        for key in [
            "answer",
            "reply",
            "response",
            "content",
            "text"
        ]:

            value = data.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

        # -------------------------------------------------
        # message مستقیم
        # -------------------------------------------------

        message = data.get("message")

        if isinstance(message, str) and message.strip():
            return message.strip()

        if isinstance(message, dict):

            content = message.get("content")

            if isinstance(content, str) and content.strip():
                return content.strip()

    # -----------------------------------------------------
    # اگر پاسخ مستقیماً string بود
    # -----------------------------------------------------

    if isinstance(data, str):

        text = data.strip()

        if text:
            return text

    return None


def get_base_urls():
    urls = []

    for url in [
        PRIMARY_BASE_URL,
        FALLBACK_BASE_URL
    ]:
        if url and url not in urls:
            urls.append(url)

    return urls


# =========================================================
# GAPGPT REQUEST
# =========================================================

def call_gapgpt(messages, stream=False):

    if not GAPGPT_API_KEY:
        return {
            "ok": False,
            "status": 500,
            "error": "GAPGPT_API_KEY تنظیم نشده است."
        }

    payload = {
        "model": GAPGPT_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.7,
        "stream": stream
    }

    headers = {
        "Authorization": f"Bearer {GAPGPT_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    errors = []

    for base_url in get_base_urls():

        endpoint = f"{base_url}/chat/completions"

        try:

            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=(15, REQUEST_TIMEOUT),
                stream=stream
            )

            # -------------------------------------------------
            # موفق
            # -------------------------------------------------

            if 200 <= response.status_code < 300:

                if stream:
                    return {
                        "ok": True,
                        "stream": True,
                        "response": response,
                        "base_url": base_url
                    }

                try:
                    data = response.json()
                except Exception:
                    raw = response.text

                    return {
                        "ok": True,
                        "data": raw,
                        "base_url": base_url
                    }

                return {
                    "ok": True,
                    "data": data,
                    "base_url": base_url
                }

            # -------------------------------------------------
            # احراز هویت اشتباه
            # -------------------------------------------------

            if response.status_code in [401, 403]:

                try:
                    error_data = response.json()
                    detail = extract_error(error_data)
                except Exception:
                    detail = response.text[:2000]

                return {
                    "ok": False,
                    "status": response.status_code,
                    "error": "خطا در API Key یا دسترسی GapGPT",
                    "details": detail,
                    "base_url": base_url
                }

            # -------------------------------------------------
            # محدودیت
            # -------------------------------------------------

            if response.status_code == 429:

                try:
                    error_data = response.json()
                    detail = extract_error(error_data)
                except Exception:
                    detail = response.text[:2000]

                return {
                    "ok": False,
                    "status": 429,
                    "error": "GapGPT درخواست را محدود کرده است.",
                    "details": detail,
                    "base_url": base_url
                }

            # -------------------------------------------------
            # خطاهای قابل Failover
            # -------------------------------------------------

            if response.status_code in [502, 503, 504]:

                try:
                    detail = response.text[:3000]
                except Exception:
                    detail = "No response body"

                errors.append({
                    "url": base_url,
                    "status": response.status_code,
                    "details": detail
                })

                continue

            # -------------------------------------------------
            # سایر خطاها
            # -------------------------------------------------

            try:
                detail = response.text[:3000]
            except Exception:
                detail = "Unknown error"

            return {
                "ok": False,
                "status": response.status_code,
                "error": f"GapGPT HTTP {response.status_code}",
                "details": detail,
                "base_url": base_url
            }

        except requests.Timeout as e:

            errors.append({
                "url": base_url,
                "error": "Timeout",
                "details": str(e)
            })

            continue

        except requests.ConnectionError as e:

            errors.append({
                "url": base_url,
                "error": "ConnectionError",
                "details": str(e)
            })

            continue

        except Exception as e:

            errors.append({
                "url": base_url,
                "error": type(e).__name__,
                "details": str(e)
            })

            continue

    return {
        "ok": False,
        "status": 504,
        "error": "هر دو مسیر GapGPT پاسخ ندادند.",
        "details": errors
    }


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def home():

    return jsonify({
        "ok": True,
        "name": "BEHRAD AI",
        "status": "online",
        "provider": "GapGPT",
        "model": GAPGPT_MODEL
    })


@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "service": "BEHRAD AI",
        "provider": "GapGPT",
        "model": GAPGPT_MODEL,
        "api_key_configured": bool(GAPGPT_API_KEY)
    })


# =========================================================
# TEST AI
# =========================================================

@app.route("/api/test-ai", methods=["GET", "POST"])
def test_ai():

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": "فقط بنویس: BEHRAD AI ONLINE"
        }
    ]

    result = call_gapgpt(
        messages,
        stream=False
    )

    if not result.get("ok"):

        return api_error(
            result.get("error", "خطای ناشناخته"),
            result.get("status", 500),
            result.get("details"),
            "GapGPT"
        )

    data = result.get("data")

    answer = extract_answer(data)

    if not answer:

        return api_error(
            "پاسخ از GapGPT دریافت شد اما متن پاسخ پیدا نشد.",
            502,
            {
                "raw_response": data
            },
            "GapGPT"
        )

    return jsonify({
        "ok": True,
        "answer": answer,
        "reply": answer,
        "response": answer,
        "provider": "GapGPT",
        "model": GAPGPT_MODEL,
        "base_url": result.get("base_url")
    })


# =========================================================
# CHAT
# =========================================================

@app.route("/api/chat", methods=["OPTIONS"])
def chat_options():

    return Response(status=204)


@app.route("/api/chat", methods=["GET"])
def chat_get():

    return jsonify({
        "ok": True,
        "message": "BEHRAD AI chat API is online 🚀",
        "provider": "GapGPT",
        "model": GAPGPT_MODEL
    })


@app.route("/api/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json(
            force=True,
            silent=False
        )

    except Exception:

        return api_error(
            "بدنه درخواست JSON معتبر نیست.",
            400
        )

    if not isinstance(data, dict):

        return api_error(
            "فرمت درخواست اشتباه است.",
            400
        )

    messages = build_messages(data)

    if not messages:

        return api_error(
            "پیام خالی است.",
            400
        )

    # برای پایداری، فعلاً پاسخ عادی می‌گیریم
    # و فرانت‌اند خودش آن را نرم نمایش می‌دهد.
    result = call_gapgpt(
        messages,
        stream=False
    )

    if not result.get("ok"):

        return api_error(
            result.get("error", "خطای ناشناخته"),
            result.get("status", 500),
            result.get("details"),
            "GapGPT"
        )

    raw_data = result.get("data")

    answer = extract_answer(raw_data)

    if not answer:

        return api_error(
            "پاسخ خالی بود یا ساختار پاسخ GapGPT قابل شناسایی نبود.",
            502,
            {
                "raw_response": raw_data
            },
            "GapGPT"
        )

    return jsonify({
        "ok": True,
        "answer": answer,
        "reply": answer,
        "response": answer,
        "provider": "GapGPT",
        "model": GAPGPT_MODEL,
        "base_url": result.get("base_url")
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "ok": False,
        "error": "مسیر مورد نظر پیدا نشد."
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "ok": False,
        "error": "Method not allowed."
    }), 405


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "ok": False,
        "error": "خطای داخلی سرور.",
        "details": str(error)
    }), 500


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
                        )
