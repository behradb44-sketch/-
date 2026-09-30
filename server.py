import os
import json
import requests

from flask import Flask, request, jsonify, Response
from flask_cors import CORS


# =========================================================
# APP
# =========================================================

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "OPTIONS"]
)


# =========================================================
# CONFIG
# =========================================================

GAPGPT_API_KEY = os.getenv("GAPGPT_API_KEY", "").strip()

GAPGPT_BASE_URL = os.getenv(
    "GAPGPT_BASE_URL",
    "https://api.gapgpt.app/v1"
).strip().rstrip("/")

GAPGPT_FALLBACK_URL = "https://api.gapapi.com/v1"

GAPGPT_MODEL = os.getenv(
    "GAPGPT_MODEL",
    "gpt-4o"
).strip()

GAPGPT_TIMEOUT = int(
    os.getenv("GAPGPT_TIMEOUT", "180")
)

GAPGPT_MAX_TOKENS = int(
    os.getenv("GAPGPT_MAX_TOKENS", "16384")
)


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی.

نام:
BEHRAD AI

سازنده:
Behrad Mohammadi
بهراد محمدی

برند:
BEHRAD M PLAYER

دستورالعمل:
- با کاربر فارسی و روان صحبت کن مگر اینکه زبان دیگری درخواست شود.
- پاسخ‌ها را واضح، دقیق و کاربردی بده.
- اگر کاربر برنامه‌نویسی خواست، کد کامل و قابل استفاده ارائه کن.
- کدها را داخل code block قرار بده.
- اگر اطلاعاتی را نمی‌دانی، جعل نکن.
- لحن دوستانه و طبیعی داشته باش.
- از Markdown برای مرتب کردن پاسخ‌ها استفاده کن.
"""


# =========================================================
# BASIC HELPERS
# =========================================================

def json_error(message, status=500, details=None):

    result = {
        "ok": False,
        "error": message
    }

    if details is not None:
        result["details"] = details

    return jsonify(result), status


def normalize_content(value):
    """
    تبدیل انواع مختلف content به یک متن ساده.
    """

    if value is None:
        return ""

    # string
    if isinstance(value, str):
        return value.strip()

    # number / bool
    if isinstance(value, (int, float, bool)):
        return str(value)

    # list
    if isinstance(value, list):

        parts = []

        for item in value:

            text = normalize_content(item)

            if text:
                parts.append(text)

        return "\n".join(parts).strip()

    # dict
    if isinstance(value, dict):

        # حالت‌های رایج
        for key in [
            "text",
            "content",
            "value",
            "output",
            "answer",
            "response",
            "message"
        ]:

            if key in value:

                text = normalize_content(
                    value.get(key)
                )

                if text:
                    return text

        # اگر type=text باشد
        if value.get("type") == "text":

            text = normalize_content(
                value.get("text")
            )

            if text:
                return text

        # اگر هیچ کلید مشخصی نبود،
        # مقادیر متنی داخل object را بررسی کن.
        parts = []

        for key, item in value.items():

            if key in [
                "id",
                "type",
                "role",
                "index",
                "finish_reason"
            ]:
                continue

            text = normalize_content(item)

            if text:
                parts.append(text)

        return "\n".join(parts).strip()

    return ""


# =========================================================
# RESPONSE EXTRACTOR
# =========================================================

def extract_answer(payload):

    if payload is None:
        return ""

    # -----------------------------------------------------
    # اگر مستقیم string باشد
    # -----------------------------------------------------

    if isinstance(payload, str):

        text = payload.strip()

        # اگر string در واقع JSON باشد
        if text.startswith("{") or text.startswith("["):

            try:
                decoded = json.loads(text)

                result = extract_answer(decoded)

                if result:
                    return result

            except Exception:
                pass

        return text

    # -----------------------------------------------------
    # list
    # -----------------------------------------------------

    if isinstance(payload, list):

        parts = []

        for item in payload:

            text = extract_answer(item)

            if text:
                parts.append(text)

        return "\n".join(parts).strip()

    # -----------------------------------------------------
    # dict
    # -----------------------------------------------------

    if not isinstance(payload, dict):
        return normalize_content(payload)

    # =====================================================
    # OpenAI:
    #
    # choices[0].message.content
    # =====================================================

    choices = payload.get("choices")

    if isinstance(choices, list):

        all_parts = []

        for choice in choices:

            if not isinstance(choice, dict):
                continue

            # message
            message = choice.get("message")

            if isinstance(message, dict):

                content = message.get("content")

                text = normalize_content(content)

                if text:
                    all_parts.append(text)

                # بعض APIها
                for key in [
                    "text",
                    "output",
                    "answer",
                    "response"
                ]:

                    if not text:

                        value = message.get(key)

                        text = normalize_content(value)

                        if text:
                            all_parts.append(text)

            # delta
            delta = choice.get("delta")

            if isinstance(delta, dict):

                text = normalize_content(
                    delta.get("content")
                )

                if text:
                    all_parts.append(text)

            # text
            text_value = choice.get("text")

            text = normalize_content(text_value)

            if text:
                all_parts.append(text)

            # مستقیم content
            content = choice.get("content")

            text = normalize_content(content)

            if text:
                all_parts.append(text)

        result = "\n".join(
            x for x in all_parts if x
        ).strip()

        if result:
            return result

    # =====================================================
    # Direct fields
    # =====================================================

    for key in [
        "answer",
        "reply",
        "response",
        "content",
        "text",
        "output"
    ]:

        if key in payload:

            text = normalize_content(
                payload.get(key)
            )

            if text:
                return text

    # =====================================================
    # message
    # =====================================================

    message = payload.get("message")

    if message is not None:

        text = normalize_content(message)

        if text:
            return text

    # =====================================================
    # result
    # =====================================================

    result = payload.get("result")

    if result is not None:

        text = extract_answer(result)

        if text:
            return text

    # =====================================================
    # data
    # =====================================================

    data = payload.get("data")

    if data is not None:

        text = extract_answer(data)

        if text:
            return text

    # =====================================================
    # output
    # =====================================================

    output = payload.get("output")

    if output is not None:

        text = extract_answer(output)

        if text:
            return text

    return ""


# =========================================================
# MESSAGES
# =========================================================

def build_messages(data):

    messages = data.get("messages")

    if isinstance(messages, list) and messages:

        cleaned = []

        for message in messages:

            if not isinstance(message, dict):
                continue

            role = message.get(
                "role",
                "user"
            )

            content = message.get(
                "content",
                ""
            )

            if role not in [
                "system",
                "user",
                "assistant"
            ]:
                role = "user"

            cleaned.append({
                "role": role,
                "content": content
            })

        if not any(
            m.get("role") == "system"
            for m in cleaned
        ):

            cleaned.insert(
                0,
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                }
            )

        return cleaned

    message = data.get(
        "message",
        ""
    )

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


# =========================================================
# GAPGPT CALL
# =========================================================

def call_gapgpt(messages):

    if not GAPGPT_API_KEY:

        return {
            "ok": False,
            "status": 500,
            "error": "GAPGPT_API_KEY تنظیم نشده است."
        }

    urls = []

    if GAPGPT_BASE_URL:
        urls.append(GAPGPT_BASE_URL)

    if (
        GAPGPT_FALLBACK_URL
        and GAPGPT_FALLBACK_URL not in urls
    ):
        urls.append(GAPGPT_FALLBACK_URL)

    payload = {
        "model": GAPGPT_MODEL,
        "messages": messages,
        "max_tokens": GAPGPT_MAX_TOKENS,
        "temperature": 0.7,
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {GAPGPT_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "BEHRAD-AI/1.0"
    }

    errors = []

    for base_url in urls:

        endpoint = (
            base_url
            + "/chat/completions"
        )

        try:

            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=(
                    15,
                    GAPGPT_TIMEOUT
                )
            )

        except requests.Timeout as error:

            errors.append({
                "url": endpoint,
                "type": "timeout",
                "message": str(error)
            })

            continue

        except requests.ConnectionError as error:

            errors.append({
                "url": endpoint,
                "type": "connection_error",
                "message": str(error)
            })

            continue

        except Exception as error:

            errors.append({
                "url": endpoint,
                "type": type(error).__name__,
                "message": str(error)
            })

            continue

        # =================================================
        # SUCCESS
        # =================================================

        if 200 <= response.status_code < 300:

            raw_text = response.text

            # ---------------------------------------------
            # JSON
            # ---------------------------------------------

            try:

                response_json = response.json()

            except Exception:

                response_json = None

            # اگر JSON بود
            if response_json is not None:

                answer = extract_answer(
                    response_json
                )

                if answer:

                    return {
                        "ok": True,
                        "answer": answer,
                        "raw": response_json,
                        "url": endpoint,
                        "status": response.status_code
                    }

                # ممکن است پاسخ یک JSON string باشد
                answer = extract_answer(
                    raw_text
                )

                if answer:

                    return {
                        "ok": True,
                        "answer": answer,
                        "raw": response_json,
                        "url": endpoint,
                        "status": response.status_code
                    }

                return {
                    "ok": False,
                    "status": 502,
                    "error": "GapGPT پاسخ داد ولی متن پاسخ قابل استخراج نبود.",
                    "raw": response_json,
                    "url": endpoint
                }

            # ---------------------------------------------
            # plain text
            # ---------------------------------------------

            answer = extract_answer(
                raw_text
            )

            if answer:

                return {
                    "ok": True,
                    "answer": answer,
                    "raw": raw_text,
                    "url": endpoint,
                    "status": response.status_code
                }

            return {
                "ok": False,
                "status": 502,
                "error": "GapGPT پاسخ خالی برگرداند.",
                "raw": raw_text,
                "url": endpoint
            }

        # =================================================
        # AUTH
        # =================================================

        if response.status_code in [
            401,
            403
        ]:

            try:
                raw = response.json()
            except Exception:
                raw = response.text

            return {
                "ok": False,
                "status": response.status_code,
                "error": "API Key یا دسترسی GapGPT مشکل دارد.",
                "raw": raw,
                "url": endpoint
            }

        # =================================================
        # RATE LIMIT
        # =================================================

        if response.status_code == 429:

            try:
                raw = response.json()
            except Exception:
                raw = response.text

            return {
                "ok": False,
                "status": 429,
                "error": "GapGPT درخواست را محدود کرده است.",
                "raw": raw,
                "url": endpoint
            }

        # =================================================
        # FAILOVER
        # =================================================

        if response.status_code in [
            502,
            503,
            504
        ]:

            try:
                raw = response.text[:5000]
            except Exception:
                raw = ""

            errors.append({
                "url": endpoint,
                "status": response.status_code,
                "response": raw
            })

            continue

        # =================================================
        # OTHER ERROR
        # =================================================

        try:
            raw = response.json()
        except Exception:
            raw = response.text[:5000]

        return {
            "ok": False,
            "status": response.status_code,
            "error": f"GapGPT HTTP {response.status_code}",
            "raw": raw,
            "url": endpoint
        }

    return {
        "ok": False,
        "status": 504,
        "error": "هیچ‌کدام از سرورهای GapGPT پاسخ ندادند.",
        "details": errors
    }


# =========================================================
# HOME
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


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "service": "BEHRAD AI",
        "provider": "GapGPT",
        "model": GAPGPT_MODEL,
        "api_key_configured": bool(
            GAPGPT_API_KEY
        ),
        "base_url": GAPGPT_BASE_URL
    })


# =========================================================
# TEST AI
# =========================================================

@app.route(
    "/api/test-ai",
    methods=["GET", "POST"]
)
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
        messages
    )

    if not result.get("ok"):

        return jsonify({
            "ok": False,
            "error": result.get(
                "error",
                "Unknown error"
            ),
            "details": result.get(
                "details"
            ),
            "raw_response": result.get(
                "raw"
            ),
            "provider": "GapGPT",
            "url": result.get(
                "url"
            )
        }), result.get(
            "status",
            500
        )

    answer = result.get(
        "answer",
        ""
    ).strip()

    return jsonify({
        "ok": True,
        "answer": answer,
        "reply": answer,
        "response": answer,
        "provider": "GapGPT",
        "model": GAPGPT_MODEL,
        "url": result.get("url")
    })


# =========================================================
# CHAT OPTIONS
# =========================================================

@app.route(
    "/api/chat",
    methods=["OPTIONS"]
)
def chat_options():

    return Response(
        status=204
    )


# =========================================================
# CHAT GET
# =========================================================

@app.route(
    "/api/chat",
    methods=["GET"]
)
def chat_get():

    return jsonify({
        "ok": True,
        "message": "BEHRAD AI API ONLINE 🚀",
        "provider": "GapGPT",
        "model": GAPGPT_MODEL
    })


# =========================================================
# CHAT POST
# =========================================================

@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    try:

        data = request.get_json(
            force=True
        )

    except Exception as error:

        return json_error(
            "JSON درخواست نامعتبر است.",
            400,
            str(error)
        )

    if not isinstance(
        data,
        dict
    ):

        return json_error(
            "فرمت درخواست اشتباه است.",
            400
        )

    messages = build_messages(
        data
    )

    if not messages:

        return json_error(
            "پیام خالی است.",
            400
        )

    result = call_gapgpt(
        messages
    )

    if not result.get("ok"):

        return jsonify({
            "ok": False,
            "error": result.get(
                "error",
                "خطای ناشناخته"
            ),
            "details": result.get(
                "details"
            ),
            "raw_response": result.get(
                "raw"
            ),
            "provider": "GapGPT",
            "url": result.get(
                "url"
            )
        }), result.get(
            "status",
            500
        )

    answer = result.get(
        "answer",
        ""
    ).strip()

    if not answer:

        return jsonify({
            "ok": False,
            "error": "پاسخ خالی بود.",
            "raw_response": result.get(
                "raw"
            ),
            "provider": "GapGPT",
            "url": result.get(
                "url"
            )
        }), 502

    return jsonify({
        "ok": True,
        "answer": answer,
        "reply": answer,
        "response": answer,
        "provider": "GapGPT",
        "model": GAPGPT_MODEL,
        "url": result.get(
            "url"
        )
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def error_404(error):

    return jsonify({
        "ok": False,
        "error": "مسیر پیدا نشد."
    }), 404


@app.errorhandler(405)
def error_405(error):

    return jsonify({
        "ok": False,
        "error": "Method not allowed."
    }), 405


@app.errorhandler(500)
def error_500(error):

    return jsonify({
        "ok": False,
        "error": "خطای داخلی سرور.",
        "details": str(error)
    }), 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
        )
