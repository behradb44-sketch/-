import os
import json
import time
import requests

from flask import Flask, request, jsonify, Response
from flask_cors import CORS


# =========================================================
# BEHRAD AI
# Backend powered by GapGPT API
# =========================================================

app = Flask(__name__)

# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

GAPGPT_API_KEY = os.getenv("GAPGPT_API_KEY", "").strip()

GAPGPT_BASE_URL = os.getenv(
    "GAPGPT_BASE_URL",
    "https://api.gapgpt.app/v1"
).rstrip("/")

# مدل پیش‌فرض
DEFAULT_MODEL = os.getenv(
    "GAPGPT_MODEL",
    "gpt-4o"
)

# حداکثر توکن خروجی
# مقدار منطقی برای جلوگیری از خطاهای provider
DEFAULT_MAX_TOKENS = int(
    os.getenv("GAPGPT_MAX_TOKENS", "16384")
)

REQUEST_TIMEOUT = int(
    os.getenv("GAPGPT_TIMEOUT", "180")
)


# ---------------------------------------------------------
# System Prompt
# ---------------------------------------------------------

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ دستیار هوش مصنوعی پروژه BEHRAD M PLAYER.

قوانین اصلی:

1. اگر کاربر فارسی صحبت کرد، فارسی روان و طبیعی جواب بده.
2. اگر کاربر انگلیسی صحبت کرد، انگلیسی جواب بده مگر اینکه درخواست دیگری داشته باشد.
3. پاسخ‌ها را واضح، دقیق و کاربردی ارائه کن.
4. برای کدنویسی، تا جای ممکن کد کامل و قابل اجرا ارائه بده.
5. اگر کاربر درباره بهراد محمدی یا BEHRAD M PLAYER پرسید:
   - نام سازنده: بهراد محمدی
   - برند: BEHRAD M PLAYER
   را در صورت مرتبط بودن در نظر بگیر.
6. اطلاعاتی را که از آن مطمئن نیستی به‌عنوان حقیقت قطعی بیان نکن.
7. در پاسخ‌های طولانی ساختار مناسب با تیتر و فهرست ایجاد کن.
8. از Markdown برای خوانایی استفاده کن.
9. پاسخ‌ها خانواده‌پسند باشند.
10. اگر درخواست کاربر به اطلاعات لحظه‌ای نیاز دارد و ابزار جست‌وجوی وب در دسترس نیست،
    ادعا نکن که اطلاعات را به‌صورت زنده بررسی کرده‌ای.
11. هدف تو کمک دقیق، دوستانه و کاربردی به کاربر است.
"""


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def api_error(message, status=500, extra=None):
    data = {
        "ok": False,
        "error": message,
    }

    if extra:
        data.update(extra)

    return jsonify(data), status


def clean_messages(messages):
    """
    پیام‌های ورودی را برای ارسال به GapGPT آماده می‌کند.
    """

    if not isinstance(messages, list):
        return []

    cleaned = []

    for msg in messages:

        if not isinstance(msg, dict):
            continue

        role = msg.get("role")

        if role not in ("system", "user", "assistant"):
            continue

        content = msg.get("content")

        if content is None:
            continue

        # رشته ساده
        if isinstance(content, str):

            cleaned.append({
                "role": role,
                "content": content
            })

            continue

        # محتوای چندبخشی OpenAI-style
        if isinstance(content, list):

            valid_parts = []

            for part in content:

                if not isinstance(part, dict):
                    continue

                part_type = part.get("type")

                # متن
                if part_type == "text":

                    text = part.get("text", "")

                    if text:
                        valid_parts.append({
                            "type": "text",
                            "text": str(text)
                        })

                # تصویر
                elif part_type == "image_url":

                    image_url = part.get("image_url")

                    if isinstance(image_url, dict):
                        url = image_url.get("url")

                        if url:
                            valid_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": url
                                }
                            })

            if valid_parts:

                cleaned.append({
                    "role": role,
                    "content": valid_parts
                })

    return cleaned


def build_messages(user_messages):
    """
    System prompt را به ابتدای conversation اضافه می‌کند.
    """

    messages = []

    messages.append({
        "role": "system",
        "content": SYSTEM_PROMPT
    })

    messages.extend(clean_messages(user_messages))

    return messages


def extract_error(response):

    try:
        data = response.json()

        if isinstance(data, dict):

            error = data.get("error")

            if isinstance(error, dict):

                message = (
                    error.get("message")
                    or error.get("error")
                    or error.get("type")
                )

                if message:
                    return str(message)

            if isinstance(error, str):
                return error

            message = data.get("message")

            if message:
                return str(message)

    except Exception:
        pass

    try:
        text = response.text.strip()

        if text:
            return text[:2000]

    except Exception:
        pass

    return "خطای ناشناخته از GapGPT دریافت شد."


def extract_answer(data):

    if not isinstance(data, dict):
        return None

    # OpenAI Chat Completions
    choices = data.get("choices")

    if isinstance(choices, list) and choices:

        first = choices[0]

        if isinstance(first, dict):

            message = first.get("message")

            if isinstance(message, dict):

                content = message.get("content")

                if isinstance(content, str):
                    return content

            # بعضی providerها
            text = first.get("text")

            if isinstance(text, str):
                return text

    # fallback
    for key in ("answer", "reply", "response", "output"):

        value = data.get(key)

        if isinstance(value, str):
            return value

    return None


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "service": "BEHRAD AI",
        "status": "online",
        "provider": "GapGPT",
        "api_configured": bool(GAPGPT_API_KEY),
        "model": DEFAULT_MODEL,
        "message": "BEHRAD AI backend is running 🚀"
    })


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "status": "ok",
        "service": "BEHRAD AI",
        "provider": "GapGPT",
        "api_key_configured": bool(GAPGPT_API_KEY),
        "base_url": GAPGPT_BASE_URL,
        "model": DEFAULT_MODEL,
        "features": {
            "text": True,
            "multilingual": True,
            "reasoning": True,
            "image": True,
            "streaming": True
        }
    })


# ---------------------------------------------------------
# OPTIONS
# ---------------------------------------------------------

@app.route("/api/chat", methods=["OPTIONS"])
def chat_options():

    return Response(status=204)


# ---------------------------------------------------------
# GET /api/chat
# ---------------------------------------------------------

@app.route("/api/chat", methods=["GET"])
def chat_get():

    return jsonify({
        "ok": True,
        "service": "BEHRAD AI",
        "provider": "GapGPT",
        "method_required": "POST",
        "message": "BEHRAD AI chat endpoint is online. Use POST to send messages."
    })


# ---------------------------------------------------------
# Test API
# ---------------------------------------------------------

@app.route("/api/test-ai", methods=["GET"])
def test_ai():

    if not GAPGPT_API_KEY:

        return api_error(
            "GAPGPT_API_KEY در Environment Variables تنظیم نشده است.",
            500
        )

    url = f"{GAPGPT_BASE_URL}/chat/completions"

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": "سلام! فقط یک جمله کوتاه برای تست بگو."
            }
        ],
        "temperature": 0.7,
        "max_tokens": 256
    }

    headers = {
        "Authorization": f"Bearer {GAPGPT_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code >= 400:

            return api_error(
                f"GapGPT HTTP {response.status_code}",
                response.status_code,
                {
                    "details": extract_error(response)
                }
            )

        try:
            data = response.json()

        except Exception:

            return api_error(
                "پاسخ GapGPT JSON معتبر نبود.",
                502,
                {
                    "raw": response.text[:2000]
                }
            )

        answer = extract_answer(data)

        if not answer:

            return api_error(
                "GapGPT پاسخ متنی معتبری برنگرداند.",
                502,
                {
                    "raw_response": data
                }
            )

        return jsonify({
            "ok": True,
            "answer": answer,
            "model": data.get("model", DEFAULT_MODEL),
            "provider": "GapGPT"
        })

    except requests.Timeout:

        return api_error(
            "زمان پاسخ GapGPT تمام شد.",
            504
        )

    except requests.RequestException as e:

        return api_error(
            "ارتباط با GapGPT برقرار نشد.",
            502,
            {
                "details": str(e)
            }
        )

    except Exception as e:

        return api_error(
            "خطای داخلی هنگام تست GapGPT.",
            500,
            {
                "details": str(e)
            }
        )


# ---------------------------------------------------------
# Main Chat Endpoint
# ---------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def chat():

    # -----------------------------------------------------
    # API Key
    # -----------------------------------------------------

    if not GAPGPT_API_KEY:

        return api_error(
            "کلید GAPGPT_API_KEY روی سرور تنظیم نشده است.",
            500
        )

    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------

    try:

        body = request.get_json(
            force=False,
            silent=False
        )

    except Exception:

        return api_error(
            "بدنه درخواست JSON معتبر نیست.",
            400
        )

    if not isinstance(body, dict):

        return api_error(
            "بدنه درخواست باید JSON باشد.",
            400
        )

    # -----------------------------------------------------
    # Messages
    # -----------------------------------------------------

    incoming_messages = body.get("messages")

    # پشتیبانی از فرمت ساده:
    #
    # {
    #   "message": "سلام"
    # }

    if not incoming_messages:

        simple_message = body.get("message")

        if isinstance(simple_message, str) and simple_message.strip():

            incoming_messages = [
                {
                    "role": "user",
                    "content": simple_message.strip()
                }
            ]

    if not incoming_messages:

        return api_error(
            "هیچ پیامی دریافت نشد.",
            400
        )

    messages = build_messages(incoming_messages)

    if len(messages) <= 1:

        return api_error(
            "پیام قابل پردازشی وجود ندارد.",
            400
        )

    # -----------------------------------------------------
    # Model
    # -----------------------------------------------------

    model = body.get("model")

    if not isinstance(model, str) or not model.strip():

        model = DEFAULT_MODEL

    # -----------------------------------------------------
    # Parameters
    # -----------------------------------------------------

    temperature = body.get("temperature", 0.7)

    try:
        temperature = float(temperature)

    except Exception:
        temperature = 0.7

    temperature = max(
        0.0,
        min(temperature, 2.0)
    )

    max_tokens = body.get(
        "max_tokens",
        DEFAULT_MAX_TOKENS
    )

    try:
        max_tokens = int(max_tokens)

    except Exception:
        max_tokens = DEFAULT_MAX_TOKENS

    max_tokens = max(
        256,
        min(max_tokens, 16384)
    )

    # -----------------------------------------------------
    # Streaming
    # -----------------------------------------------------

    stream = body.get("stream", True)

    if isinstance(stream, str):

        stream = stream.lower() == "true"

    stream = bool(stream)

    # -----------------------------------------------------
    # GapGPT URL
    # -----------------------------------------------------

    url = f"{GAPGPT_BASE_URL}/chat/completions"

    # -----------------------------------------------------
    # Request
    # -----------------------------------------------------

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream
    }

    headers = {
        "Authorization": f"Bearer {GAPGPT_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json"
    }

    # =====================================================
    # STREAMING MODE
    # =====================================================

    if stream:

        try:

            upstream = requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=REQUEST_TIMEOUT
            )

        except requests.Timeout:

            return api_error(
                "زمان پاسخ GapGPT تمام شد.",
                504
            )

        except requests.RequestException as e:

            return api_error(
                "ارتباط با GapGPT برقرار نشد.",
                502,
                {
                    "details": str(e)
                }
            )

        if upstream.status_code >= 400:

            error_message = extract_error(upstream)

            retry_after = upstream.headers.get(
                "Retry-After"
            )

            extra = {
                "details": error_message,
                "provider": "GapGPT"
            }

            if retry_after:
                extra["retry_after"] = retry_after

            return api_error(
                f"GapGPT HTTP {upstream.status_code}",
                upstream.status_code,
                extra
            )

        def generate():

            try:

                for raw_line in upstream.iter_lines(
                    decode_unicode=False
                ):

                    if not raw_line:
                        continue

                    # UTF-8 واقعی
                    try:

                        line = raw_line.decode(
                            "utf-8",
                            errors="replace"
                        )

                    except Exception:

                        line = str(raw_line)

                    # SSE
                    if line.startswith("data:"):

                        data_part = line[5:].strip()

                        if data_part == "[DONE]":

                            yield "data: [DONE]\n\n"
                            break

                        try:

                            chunk = json.loads(
                                data_part
                            )

                            yield (
                                "data: "
                                + json.dumps(
                                    chunk,
                                    ensure_ascii=False
                                )
                                + "\n\n"
                            )

                        except Exception:

                            # اگر provider خط را JSON نکرده بود
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "text": data_part
                                    },
                                    ensure_ascii=False
                                )
                                + "\n\n"
                            )

            finally:

                try:
                    upstream.close()

                except Exception:
                    pass

        return Response(
            generate(),
            status=200,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*"
            }
        )

    # =====================================================
    # NORMAL JSON MODE
    # =====================================================

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )

    except requests.Timeout:

        return api_error(
            "زمان پاسخ GapGPT تمام شد.",
            504
        )

    except requests.RequestException as e:

        return api_error(
            "ارتباط با GapGPT برقرار نشد.",
            502,
            {
                "details": str(e)
            }
        )

    # -----------------------------------------------------
    # Provider error
    # -----------------------------------------------------

    if response.status_code >= 400:

        error_message = extract_error(response)

        extra = {
            "details": error_message,
            "provider": "GapGPT"
        }

        retry_after = response.headers.get(
            "Retry-After"
        )

        if retry_after:
            extra["retry_after"] = retry_after

        return api_error(
            f"GapGPT HTTP {response.status_code}",
            response.status_code,
            extra
        )

    # -----------------------------------------------------
    # JSON
    # -----------------------------------------------------

    try:

        data = response.json()

    except Exception:

        return api_error(
            "GapGPT پاسخ JSON معتبر برنگرداند.",
            502,
            {
                "raw": response.text[:3000]
            }
        )

    # -----------------------------------------------------
    # Extract answer
    # -----------------------------------------------------

    answer = extract_answer(data)

    if not answer:

        return api_error(
            "GapGPT پاسخ متنی قابل استفاده‌ای برنگرداند.",
            502,
            {
                "raw_response": data
            }
        )

    # -----------------------------------------------------
    # Final response
    # -----------------------------------------------------

    return jsonify({
        "ok": True,
        "answer": answer,
        "reply": answer,
        "response": answer,
        "model": data.get("model", model),
        "provider": "GapGPT",
        "usage": data.get("usage")
    })


# ---------------------------------------------------------
# Global error handler
# ---------------------------------------------------------

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "ok": False,
        "error": "مسیر موردنظر پیدا نشد.",
        "service": "BEHRAD AI"
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "ok": False,
        "error": "Method برای این مسیر مجاز نیست.",
        "service": "BEHRAD AI"
    }), 405


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "ok": False,
        "error": "خطای داخلی سرور BEHRAD AI.",
        "service": "BEHRAD AI"
    }), 500


# ---------------------------------------------------------
# Local development
# ---------------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "5000")
    )

    print("=" * 60)
    print("BEHRAD AI")
    print("Provider: GapGPT")
    print(f"Model: {DEFAULT_MODEL}")
    print(f"API configured: {bool(GAPGPT_API_KEY)}")
    print(f"Base URL: {GAPGPT_BASE_URL}")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
        )
