import os
import requests

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException


app = Flask(__name__, static_folder=".")


# =========================================================
# BEHRAD AI CONFIG
# =========================================================

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()

MAX_HISTORY = 20


# =========================================================
# BEHRAD AI IDENTITY
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ دستیار هوش مصنوعی پروژه BEHRAD AI.

هویت پروژه:
- نام پروژه: BEHRAD AI
- سازنده و مالک پروژه: بهراد محمدی
- نام مستعار و برند سازنده: بهراد ام پلیر
- نام انگلیسی برند: BEHRAD M PLAYER
- در صورت سؤال درباره سازنده، مالک یا خالق BEHRAD AI، پاسخ بده:
  «سازنده و مالک BEHRAD AI، بهراد محمدی، ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.»

قوانین هویتی:
- سازنده و مالک را با شخص دیگری اشتباه نگیر.
- اگر کاربر پرسید «تو رو کی ساخته؟»، درباره BEHRAD AI بگو سازنده‌ات بهراد محمدی ملقب به بهراد ام پلیر است.
- اگر کاربر پرسید «مال کی هستی؟»، بگو BEHRAD AI متعلق به بهراد محمدی ملقب به بهراد ام پلیر است.
- این اطلاعات را فقط به عنوان اطلاعات هویتی پروژه استفاده کن.
- درباره چیزهایی که نمی‌دانی، حدس نزن.

رفتار:
- فارسی را روان و طبیعی جواب بده.
- اگر کاربر فارسی حرف زد، فارسی جواب بده.
- در کدنویسی، کد کامل و قابل استفاده ارائه کن.
- اگر مطمئن نیستی، صادقانه بگو.
- پاسخ‌ها را واضح و کاربردی بده.
"""


# =========================================================
# JSON ERROR
# =========================================================

def json_error(message, status=500, details=None):

    data = {
        "success": False,
        "error": message
    }

    if details:
        data["details"] = details

    return jsonify(data), status


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
        "success": True,
        "service": "BEHRAD AI",
        "status": "ok",
        "api_key_configured": bool(API_KEY),
        "model": MODEL
    })


# =========================================================
# OPENROUTER
# =========================================================

def ask_openrouter(messages):

    payload = {
        "model": MODEL,

        "messages": messages,

        "temperature": 0.7,

        "max_tokens": 4000
    }

    response = requests.post(

        OPENROUTER_URL,

        headers={
            "Authorization": f"Bearer {API_KEY}",

            "Content-Type":
                "application/json",

            "HTTP-Referer":
                "https://k6k83zh1yv.onrender.com",

            "X-Title":
                "BEHRAD AI"
        },

        json=payload,

        timeout=120
    )


    try:

        data = response.json()

    except Exception:

        return (
            None,
            response.status_code,
            response.text[:2000]
        )


    return (
        data,
        response.status_code,
        None
    )


# =========================================================
# CHAT
# =========================================================

@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    if not API_KEY:

        return json_error(
            "OPENROUTER_API_KEY تنظیم نشده.",
            500
        )


    try:

        body = request.get_json(
            silent=True
        )


        if not body:

            return json_error(
                "درخواست JSON معتبر نیست.",
                400
            )


        incoming_messages = body.get(
            "messages"
        )


        if not isinstance(
            incoming_messages,
            list
        ):

            return json_error(
                "messages نامعتبر است.",
                400
            )


        incoming_messages = (
            incoming_messages[-MAX_HISTORY:]
        )


        clean_messages = []


        # =================================================
        # SYSTEM PROMPT
        # =================================================

        clean_messages.append({

            "role": "system",

            "content": SYSTEM_PROMPT

        })


        # =================================================
        # USER / ASSISTANT MESSAGES
        # =================================================

        for message in incoming_messages:

            if not isinstance(
                message,
                dict
            ):
                continue


            role = message.get(
                "role"
            )


            if role not in (
                "user",
                "assistant"
            ):
                continue


            content = message.get(
                "content"
            )


            # ---------------------------------------------
            # TEXT
            # ---------------------------------------------

            if isinstance(
                content,
                str
            ):

                if content.strip():

                    clean_messages.append({

                        "role": role,

                        "content": content

                    })

                continue


            # ---------------------------------------------
            # MULTIMODAL
            # ---------------------------------------------

            if isinstance(
                content,
                list
            ):

                parts = []


                for part in content:

                    if not isinstance(
                        part,
                        dict
                    ):
                        continue


                    part_type = part.get(
                        "type"
                    )


                    # TEXT
                    if part_type == "text":

                        text = part.get(
                            "text",
                            ""
                        )


                        if text:

                            parts.append({

                                "type":
                                    "text",

                                "text":
                                    text

                            })


                    # IMAGE
                    elif part_type == "image_url":

                        image_url = part.get(
                            "image_url"
                        )


                        if isinstance(
                            image_url,
                            dict
                        ):

                            url = image_url.get(
                                "url"
                            )


                            if (
                                isinstance(
                                    url,
                                    str
                                )
                                and url
                            ):

                                parts.append({

                                    "type":
                                        "image_url",

                                    "image_url": {

                                        "url":
                                            url

                                    }

                                })


                    # VIDEO
                    elif part_type == "video_url":

                        video_url = part.get(
                            "video_url"
                        )


                        if isinstance(
                            video_url,
                            dict
                        ):

                            url = video_url.get(
                                "url"
                            )


                            if (
                                isinstance(
                                    url,
                                    str
                                )
                                and url
                            ):

                                parts.append({

                                    "type":
                                        "video_url",

                                    "video_url": {

                                        "url":
                                            url

                                    }

                                })


                if parts:

                    clean_messages.append({

                        "role":
                            role,

                        "content":
                            parts

                    })


        # =================================================
        # EMPTY
        # =================================================

        if len(clean_messages) <= 1:

            return json_error(
                "هیچ پیام قابل پردازشی وجود ندارد.",
                400
            )


        # =================================================
        # ASK AI
        # =================================================

        data, status, raw = ask_openrouter(
            clean_messages
        )


        if data is None:

            return json_error(

                "OpenRouter پاسخ JSON نداد.",

                status,

                raw

            )


        if status >= 400:

            return json_error(

                "OpenRouter درخواست را قبول نکرد.",

                status,

                data

            )


        choices = data.get(
            "choices",
            []
        )


        if not choices:

            return json_error(

                "مدل پاسخی برنگرداند.",

                502,

                data

            )


        message = choices[0].get(
            "message",
            {}
        )


        answer = message.get(
            "content"
        )


        if answer is None:

            answer = ""


        if not isinstance(
            answer,
            str
        ):

            answer = str(answer)


        if not answer.strip():

            answer = (
                "مدل پاسخ متنی برنگرداند."
            )


        return jsonify({

            "success":
                True,

            "reply":
                answer,

            "model":
                MODEL

        })


    except requests.Timeout:

        return json_error(

            "زمان پاسخ مدل تمام شد. دوباره امتحان کن.",

            504

        )


    except requests.RequestException as error:

        return json_error(

            "ارتباط با OpenRouter برقرار نشد.",

            502,

            str(error)

        )


    except Exception as error:

        return json_error(

            "خطای داخلی سرور.",

            500,

            str(error)

        )


# =========================================================
# HTTP ERROR
# =========================================================

@app.errorhandler(
    HTTPException
)
def http_error(error):

    return json_error(

        error.description,

        error.code or 500

    )


# =========================================================
# UNKNOWN ERROR
# =========================================================

@app.errorhandler(
    Exception
)
def unknown_error(error):

    return json_error(

        "خطای غیرمنتظره سرور.",

        500,

        str(error)

    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )
