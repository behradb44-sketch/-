import os
import json
import time
import requests

from flask import Flask, request, jsonify, send_from_directory


app = Flask(__name__, static_folder=".", static_url_path="")

OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    ""
).strip()

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 10000
MAX_TOTAL_CHARS = 40000

REQUEST_TIMEOUT = (20, 120)

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ یک دستیار هوش مصنوعی فارسی‌زبان حرفه‌ای.

اطلاعات پروژه:

صاحب BEHRAD AI:
بهراد محمدی

سازنده BEHRAD AI:
بهراد محمدی

نام مستعار سازنده:
بهراد ام پلیر

نام برند:
BEHRAD M PLAYER

اگر کاربر درباره صاحب، سازنده، مالک یا خالق BEHRAD AI پرسید، بگو:

«صاحب و سازنده BEHRAD AI، بهراد محمدی ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.»

قوانین:

- اگر کاربر فارسی صحبت کرد، فارسی روان پاسخ بده.
- اگر کاربر انگلیسی صحبت کرد، انگلیسی پاسخ بده.
- پاسخ طبیعی و دوستانه باشد.
- اطلاعات جدید را در صورت نیاز با Web Search بررسی کن.
- برای برنامه‌نویسی، کد کامل و قابل استفاده بده.
- از Markdown استفاده کن.
- اطلاعات را بدون دلیل حدس نزن.
- پاسخ را واضح و کاربردی بنویس.
"""


def make_error(message, status=500, details=None):

    result = {
        "success": False,
        "error": message
    }

    if details is not None:
        result["details"] = details

    return jsonify(result), status


def normalize_content(content):

    if isinstance(content, str):
        return content[:MAX_MESSAGE_CHARS]

    if isinstance(content, list):

        result = []

        for part in content:

            if not isinstance(part, dict):
                continue

            kind = part.get("type")

            if kind == "text":

                result.append({
                    "type": "text",
                    "text": str(
                        part.get("text", "")
                    )[:MAX_MESSAGE_CHARS]
                })

            elif kind == "image_url":

                image = part.get("image_url")

                if isinstance(image, dict):
                    url = image.get("url", "")
                else:
                    url = str(image or "")

                result.append({
                    "type": "image_url",
                    "image_url": {
                        "url": url
                    }
                })

        return result

    return ""


def clean_messages(messages):

    if not isinstance(messages, list):
        return []

    messages = messages[-MAX_HISTORY:]

    result = []
    total = 0

    for msg in messages:

        if not isinstance(msg, dict):
            continue

        role = msg.get("role")

        if role not in ("user", "assistant"):
            continue

        content = normalize_content(
            msg.get("content", "")
        )

        if isinstance(content, str):

            total += len(content)

        else:

            for part in content:

                if part.get("type") == "text":

                    total += len(
                        part.get(
                            "text",
                            ""
                        )
                    )

        if total > MAX_TOTAL_CHARS:
            break

        result.append({
            "role": role,
            "content": content
        })

    return result


def headers():

    return {
        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "HTTP-Referer":
            "https://behradb44-sketch.github.io/behrad-m-player/",

        "X-Title":
            "BEHRAD AI"
    }


def build_payload(messages):

    return {
        "model": MODEL,

        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            *messages
        ],

        "temperature": 0.7,

        "max_tokens": 3000,

        "stream": False,

        "tools": [
            {
                "type": "openrouter:web_search",

                "parameters": {
                    "engine": "auto",
                    "max_results": 5,
                    "max_total_results": 10
                }
            }
        ]
    }


def extract_answer(data):

    choices = data.get("choices")

    if not isinstance(choices, list):
        return None

    if not choices:
        return None

    message = choices[0].get(
        "message",
        {}
    )

    if not isinstance(message, dict):
        return None

    content = message.get("content")

    if isinstance(content, str):

        text = content.strip()

        if text:
            return text

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(item, dict):

                text = item.get("text")

                if text:
                    parts.append(
                        str(text)
                    )

        text = "".join(parts).strip()

        if text:
            return text

    return None


def call_openrouter(payload):

    last_error = None

    for attempt in range(3):

        try:

            response = requests.post(
                OPENROUTER_URL,
                headers=headers(),
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            # موقتاً دوباره امتحان کن
            if response.status_code in (
                408,
                429,
                500,
                502,
                503,
                504
            ):

                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:1000]}"
                )

                if attempt < 2:

                    time.sleep(
                        1.5 * (attempt + 1)
                    )

                    continue

            return response

        except requests.exceptions.Timeout as e:

            last_error = str(e)

            if attempt < 2:

                time.sleep(
                    1.5 * (attempt + 1)
                )

                continue

        except requests.exceptions.RequestException as e:

            last_error = str(e)

            if attempt < 2:

                time.sleep(
                    1.5 * (attempt + 1)
                )

                continue

    raise RuntimeError(
        last_error or
        "ارتباط با OpenRouter برقرار نشد."
    )


@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


@app.route("/health")
def health():

    return jsonify({
        "success": True,
        "status": "ok",
        "service": "BEHRAD AI",
        "model": MODEL,
        "api_key_configured":
            bool(OPENROUTER_API_KEY)
    })


@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    if not OPENROUTER_API_KEY:

        return make_error(
            "OPENROUTER_API_KEY تنظیم نشده است.",
            500
        )

    try:

        data = request.get_json(
            force=True,
            silent=False
        )

        if not isinstance(data, dict):

            return make_error(
                "درخواست JSON معتبر نیست.",
                400
            )

        messages = clean_messages(
            data.get(
                "messages",
                []
            )
        )

        if not messages:

            return make_error(
                "پیامی دریافت نشد.",
                400
            )

        payload = build_payload(
            messages
        )

        response = call_openrouter(
            payload
        )

        # -----------------------------------------
        # OPENROUTER ERROR
        # -----------------------------------------

        if response.status_code != 200:

            raw = response.text[:5000]

            try:
                details = response.json()
            except Exception:
                details = raw

            return make_error(
                f"OpenRouter خطا داد "
                f"(HTTP {response.status_code})",
                response.status_code,
                details
            )

        # -----------------------------------------
        # JSON
        # -----------------------------------------

        try:

            result = response.json()

        except ValueError:

            return make_error(
                "OpenRouter پاسخ JSON معتبر نداد.",
                502,
                response.text[:3000]
            )

        # -----------------------------------------
        # ANSWER
        # -----------------------------------------

        answer = extract_answer(
            result
        )

        if answer:

            return jsonify({
                "success": True,
                "reply": answer,
                "model": MODEL
            })

        # -----------------------------------------
        # EMPTY CONTENT
        # -----------------------------------------

        choices = result.get(
            "choices",
            []
        )

        details = {}

        if choices:

            message = choices[0].get(
                "message",
                {}
            )

            details = {
                "finish_reason":
                    choices[0].get(
                        "finish_reason"
                    ),

                "has_tool_calls":
                    bool(
                        message.get(
                            "tool_calls"
                        )
                    ),

                "refusal":
                    message.get(
                        "refusal"
                    )
            }

        return make_error(
            "مدل پاسخ متنی قابل نمایش برنگرداند.",
            502,
            details
        )

    except RuntimeError as e:

        return make_error(
            str(e),
            502
        )

    except Exception as e:

        return make_error(
            f"خطای سرور: {str(e)}",
            500
        )


@app.route("/api/test-ai")
def test_ai():

    if not OPENROUTER_API_KEY:

        return make_error(
            "OPENROUTER_API_KEY تنظیم نشده است.",
            500
        )

    try:

        payload = build_payload([
            {
                "role": "user",
                "content":
                    "سلام. فقط کوتاه جواب بده."
            }
        ])

        response = call_openrouter(
            payload
        )

        return (
            response.text,
            response.status_code,
            {
                "Content-Type":
                    "application/json; charset=utf-8"
            }
        )

    except Exception as e:

        return make_error(
            str(e),
            502
        )


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
