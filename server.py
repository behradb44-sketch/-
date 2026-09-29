import os
import json
import requests

from flask import Flask, request, jsonify, Response, send_from_directory


app = Flask(__name__, static_folder=".", static_url_path="")


# =========================================================
# CONFIG
# =========================================================

OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    ""
).strip()

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

MAX_HISTORY = 14
MAX_MESSAGE_CHARS = 12000
MAX_TOTAL_CHARS = 50000


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ یک دستیار هوش مصنوعی فارسی‌زبان حرفه‌ای.

اطلاعات پروژه:

صاحب و سازنده BEHRAD AI:
بهراد محمدی

نام مستعار:
بهراد ام پلیر

نام برند:
BEHRAD M PLAYER

اگر کاربر درباره صاحب، سازنده، مالک یا خالق BEHRAD AI پرسید،
پاسخ بده:

«صاحب و سازنده BEHRAD AI، بهراد محمدی ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.»

قوانین پاسخ:

1. اگر کاربر فارسی صحبت کرد، فارسی روان و خوانا پاسخ بده.
2. اگر کاربر انگلیسی صحبت کرد، انگلیسی پاسخ بده.
3. پاسخ‌ها طبیعی، دوستانه و دقیق باشند.
4. برای اطلاعات جدید و به‌روز، در صورت نیاز از Web Search استفاده کن.
5. اگر کاربر درباره اخبار، قیمت، وضعیت فعلی، افراد یا سایت‌های امروزی پرسید، در صورت نیاز جستجو کن.
6. در برنامه‌نویسی، تا جای ممکن کد کامل و قابل استفاده بده.
7. از Markdown برای خوانایی استفاده کن.
8. اگر پاسخ شامل کد است، از code fence استفاده کن.
9. فارسی را با UTF-8 صحیح تولید کن.
10. اگر اطلاعات کافی نداری، حدس بی‌پایه نزن.
"""


# =========================================================
# HELPERS
# =========================================================

def error_response(message, status=500, details=None):
    data = {
        "success": False,
        "error": message
    }

    if details is not None:
        data["details"] = details

    return jsonify(data), status


def normalize_content(content):
    """
    متن ساده یا محتوای multimodal را تمیز می‌کند.
    """

    if isinstance(content, str):
        return content[:MAX_MESSAGE_CHARS]

    if isinstance(content, list):

        result = []

        for part in content:

            if not isinstance(part, dict):
                continue

            part_type = part.get("type")

            if part_type == "text":

                result.append({
                    "type": "text",
                    "text": str(
                        part.get("text", "")
                    )[:MAX_MESSAGE_CHARS]
                })

            elif part_type == "image_url":

                image_url = part.get(
                    "image_url"
                )

                if isinstance(image_url, dict):

                    url = image_url.get(
                        "url",
                        ""
                    )

                else:

                    url = str(
                        image_url or ""
                    )

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

    cleaned = []

    total_chars = 0

    for msg in messages:

        if not isinstance(msg, dict):
            continue

        role = msg.get("role")

        if role not in (
            "user",
            "assistant"
        ):
            continue

        content = normalize_content(
            msg.get(
                "content",
                ""
            )
        )

        if isinstance(content, str):

            total_chars += len(content)

        else:

            for part in content:

                if part.get("type") == "text":

                    total_chars += len(
                        part.get(
                            "text",
                            ""
                        )
                    )

        if total_chars > MAX_TOTAL_CHARS:
            break

        cleaned.append({
            "role": role,
            "content": content
        })

    return cleaned


def openrouter_headers():

    return {
        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json; charset=utf-8",

        "Accept":
            "application/json",

        "HTTP-Referer":
            "https://behradb44-sketch.github.io/behrad-m-player/",

        "X-Title":
            "BEHRAD AI"
    }


def create_payload(messages):

    return {

        "model":
            MODEL,

        "messages": [
            {
                "role":
                    "system",

                "content":
                    SYSTEM_PROMPT
            },

            *messages
        ],

        "temperature":
            0.7,

        "max_tokens":
            4000,

        "stream":
            False,

        # =================================================
        # OPENROUTER WEB SEARCH
        # =================================================

        "tools": [
            {
                "type":
                    "openrouter:web_search",

                "parameters": {
                    "engine":
                        "auto",

                    "max_results":
                        5,

                    "max_total_results":
                        10
                }
            }
        ]
    }


def extract_answer(result):

    choices = result.get(
        "choices",
        []
    )

    if not choices:
        return None

    message = choices[0].get(
        "message",
        {}
    )

    if not isinstance(message, dict):
        return None

    content = message.get(
        "content"
    )

    # معمول‌ترین حالت
    if isinstance(content, str) and content.strip():
        return content.strip()

    # بعضی پاسخ‌ها ممکن است content را به شکل list برگردانند
    if isinstance(content, list):

        text_parts = []

        for part in content:

            if isinstance(part, dict):

                text = part.get(
                    "text"
                )

                if text:
                    text_parts.append(
                        str(text)
                    )

        joined = "".join(
            text_parts
        ).strip()

        if joined:
            return joined

    return None


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "status":
            "ok",

        "service":
            "BEHRAD AI",

        "model":
            MODEL,

        "api_key_configured":
            bool(
                OPENROUTER_API_KEY
            )
    })


# =========================================================
# CHAT
# =========================================================

@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    if not OPENROUTER_API_KEY:

        return error_response(
            "OPENROUTER_API_KEY تنظیم نشده است.",
            500
        )

    try:

        # ---------------------------------------------
        # READ JSON
        # ---------------------------------------------

        data = request.get_json(
            force=True,
            silent=False
        )

        if not isinstance(data, dict):

            return error_response(
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

            return error_response(
                "پیامی دریافت نشد.",
                400
            )

        # ---------------------------------------------
        # REQUEST
        # ---------------------------------------------

        payload = create_payload(
            messages
        )

        response = requests.post(

            OPENROUTER_URL,

            headers=
                openrouter_headers(),

            json=
                payload,

            timeout=
                (30, 180)
        )

        # ---------------------------------------------
        # OPENROUTER ERROR
        # ---------------------------------------------

        if response.status_code != 200:

            try:

                details = response.json()

            except Exception:

                details = response.text[
                    :5000
                ]

            return error_response(
                "OpenRouter خطا داد.",
                response.status_code,
                details
            )

        # ---------------------------------------------
        # JSON
        # ---------------------------------------------

        try:

            result = response.json()

        except Exception as e:

            return error_response(
                "پاسخ OpenRouter JSON معتبر نبود.",
                502,
                str(e)
            )

        # ---------------------------------------------
        # ANSWER
        # ---------------------------------------------

        answer = extract_answer(
            result
        )

        if answer:

            return jsonify({

                "success":
                    True,

                "reply":
                    answer,

                "model":
                    MODEL

            })

        # ---------------------------------------------
        # NO TEXT
        # ---------------------------------------------

        choices = result.get(
            "choices",
            []
        )

        if choices:

            message = choices[0].get(
                "message",
                {}
            )

            tool_calls = message.get(
                "tool_calls"
            )

            refusal = message.get(
                "refusal"
            )

            reasoning = (
                message.get(
                    "reasoning"
                )
                or
                message.get(
                    "reasoning_content"
                )
            )

            details = {
                "has_tool_calls":
                    bool(tool_calls),

                "refusal":
                    refusal,

                "has_reasoning":
                    bool(reasoning),

                "finish_reason":
                    choices[0].get(
                        "finish_reason"
                    )
            }

            return error_response(
                "مدل پاسخ متنی قابل نمایش برنگرداند.",
                502,
                details
            )

        return error_response(
            "OpenRouter پاسخ خالی برگرداند.",
            502,
            result
        )

    except requests.exceptions.Timeout:

        return error_response(
            "زمان پاسخ OpenRouter تمام شد.",
            504
        )

    except requests.exceptions.RequestException as e:

        return error_response(
            "ارتباط با OpenRouter برقرار نشد.",
            502,
            str(e)
        )

    except Exception as e:

        return error_response(
            f"خطای سرور: {str(e)}",
            500
        )


# =========================================================
# TEST AI
# =========================================================

@app.route("/api/test-ai")
def test_ai():

    if not OPENROUTER_API_KEY:

        return error_response(
            "OPENROUTER_API_KEY تنظیم نشده است.",
            500
        )

    try:

        payload = create_payload([
            {
                "role":
                    "user",

                "content":
                    "سلام رفیق، فقط بگو سلام!"
            }
        ])

        response = requests.post(

            OPENROUTER_URL,

            headers=
                openrouter_headers(),

            json=
                payload,

            timeout=
                (30, 180)
        )

        return Response(

            response.content,

            status=
                response.status_code,

            content_type=
                "application/json; charset=utf-8"
        )

    except Exception as e:

        return error_response(
            str(e),
            500
        )


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

        host=
            "0.0.0.0",

        port=
            port,

        debug=
            False
        )
