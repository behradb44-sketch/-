import os
import json
import requests

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from werkzeug.exceptions import HTTPException


app = Flask(__name__, static_folder=".")


# =========================================================
# CONFIG
# =========================================================

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 12000
MAX_TOTAL_CHARS = 45000


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ دستیار هوش مصنوعی پروژه BEHRAD AI.

اطلاعات هویتی پروژه:

صاحب:
بهراد محمدی

مالک:
بهراد محمدی

سازنده:
بهراد محمدی

نام مستعار و برند:
بهراد ام پلیر (BEHRAD M PLAYER)

اگر کاربر درباره صاحب، مالک یا سازنده BEHRAD AI پرسید،
بگو صاحب، مالک و سازنده BEHRAD AI، بهراد محمدی
ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.

به زبان کاربر پاسخ بده.

اگر سؤال نیاز به اطلاعات جدید یا اینترنتی دارد،
از Web Search استفاده کن.

اگر جستجو انجام شد، اطلاعات جستجو را در پاسخ نهایی لحاظ کن.

پاسخ‌ها طبیعی، دقیق و مفید باشند.
اگر چیزی را نمی‌دانی، حدس بی‌دلیل نزن.
"""


# =========================================================
# ERROR
# =========================================================

def error_json(message, status=500, details=None):

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
        "model": MODEL,
        "streaming": True,
        "web_search": True
    })


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    if not isinstance(text, str):
        return ""

    text = text.strip()

    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS]

    return text


# =========================================================
# CLEAN MESSAGES
# =========================================================

def clean_messages(messages):

    if not isinstance(messages, list):
        return []

    messages = messages[-MAX_HISTORY:]

    cleaned = []

    total_chars = 0

    for message in messages:

        if not isinstance(message, dict):
            continue

        role = message.get("role")

        if role not in ("user", "assistant"):
            continue

        content = message.get("content")


        # =============================================
        # TEXT
        # =============================================

        if isinstance(content, str):

            content = clean_text(content)

            if not content:
                continue

            remaining = (
                MAX_TOTAL_CHARS -
                total_chars
            )

            if remaining <= 0:
                break

            content = content[:remaining]

            cleaned.append({
                "role": role,
                "content": content
            })

            total_chars += len(content)

            continue


        # =============================================
        # MULTIMODAL
        # =============================================

        if isinstance(content, list):

            parts = []

            for part in content:

                if not isinstance(part, dict):
                    continue

                part_type = part.get("type")


                # TEXT
                if part_type == "text":

                    text = clean_text(
                        part.get("text", "")
                    )

                    if not text:
                        continue

                    remaining = (
                        MAX_TOTAL_CHARS -
                        total_chars
                    )

                    if remaining <= 0:
                        break

                    text = text[:remaining]

                    parts.append({
                        "type": "text",
                        "text": text
                    })

                    total_chars += len(text)


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
                            isinstance(url, str)
                            and url
                        ):

                            parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": url
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
                            isinstance(url, str)
                            and url
                        ):

                            parts.append({
                                "type": "video_url",
                                "video_url": {
                                    "url": url
                                }
                            })


            if parts:

                cleaned.append({
                    "role": role,
                    "content": parts
                })


    return cleaned


# =========================================================
# HEADERS
# =========================================================

def openrouter_headers():

    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://k6k83zh1yv.onrender.com",
        "X-Title": "BEHRAD AI"
    }


# =========================================================
# NORMAL CHAT
# =========================================================

@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    try:

        if not API_KEY:

            return error_json(
                "OPENROUTER_API_KEY تنظیم نشده.",
                500
            )


        body = request.get_json(
            silent=True
        )

        if not body:

            return error_json(
                "JSON معتبر نیست.",
                400
            )


        messages = clean_messages(
            body.get("messages")
        )


        if not messages:

            return error_json(
                "پیامی برای ارسال وجود ندارد.",
                400
            )


        final_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        final_messages.extend(
            messages
        )


        payload = {
            "model": MODEL,
            "messages": final_messages,
            "temperature": 0.7,
            "max_tokens": 3000,

            # Web Search
            "tools": [
                {
                    "type": "openrouter:web_search"
                }
            ]
        }


        response = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            timeout=120
        )


        try:

            data = response.json()

        except Exception:

            return error_json(
                "OpenRouter پاسخ JSON نداد.",
                502,
                response.text[:2000]
            )


        if response.status_code >= 400:

            error_message = (
                "OpenRouter خطا داد."
            )

            error_obj = (
                data.get("error")
                if isinstance(data, dict)
                else None
            )

            if isinstance(
                error_obj,
                dict
            ):

                error_message = (
                    error_obj.get(
                        "message",
                        error_message
                    )
                )

            elif isinstance(
                error_obj,
                str
            ):

                error_message = error_obj


            return error_json(
                error_message,
                502,
                data
            )


        choices = data.get(
            "choices",
            []
        )


        if not choices:

            return error_json(
                "مدل پاسخی برنگرداند.",
                502,
                data
            )


        answer = choices[0].get(
            "message",
            {}
        ).get(
            "content",
            ""
        )


        if not isinstance(
            answer,
            str
        ):

            answer = str(answer)


        if not answer.strip():

            return error_json(
                "مدل پاسخ متنی برنگرداند.",
                502
            )


        return jsonify({
            "success": True,
            "reply": answer,
            "model": MODEL
        })


    except requests.Timeout:

        return error_json(
            "زمان پاسخ مدل تمام شد.",
            504
        )


    except requests.RequestException as e:

        return error_json(
            "ارتباط با OpenRouter برقرار نشد.",
            502,
            str(e)
        )


    except Exception as e:

        return error_json(
            "خطای داخلی سرور.",
            500,
            str(e)
        )


# =========================================================
# STREAMING CHAT + WEB SEARCH
# =========================================================

@app.route(
    "/api/chat/stream",
    methods=["POST"]
)
def chat_stream():

    if not API_KEY:

        return error_json(
            "OPENROUTER_API_KEY تنظیم نشده.",
            500
        )


    body = request.get_json(
        silent=True
    )

    if not body:

        return error_json(
            "JSON معتبر نیست.",
            400
        )


    messages = clean_messages(
        body.get("messages")
    )


    if not messages:

        return error_json(
            "پیامی برای ارسال وجود ندارد.",
            400
        )


    final_messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    final_messages.extend(
        messages
    )


    payload = {

        "model": MODEL,

        "messages": final_messages,

        "stream": True,

        "temperature": 0.7,

        "max_tokens": 3000,

        # ==============================
        # KEEP WEB SEARCH
        # ==============================

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


    def generate():

        try:

            response = requests.post(

                OPENROUTER_URL,

                headers=openrouter_headers(),

                json=payload,

                stream=True,

                timeout=(
                    30,
                    180
                )
            )


            # =========================================
            # OPENROUTER ERROR
            # =========================================

            if response.status_code >= 400:

                try:

                    data = response.json()

                    message = (
                        "OpenRouter خطا داد."
                    )

                    if isinstance(
                        data,
                        dict
                    ):

                        error_obj = data.get(
                            "error"
                        )

                        if isinstance(
                            error_obj,
                            dict
                        ):

                            message = (
                                error_obj.get(
                                    "message",
                                    message
                                )
                            )

                        elif isinstance(
                            error_obj,
                            str
                        ):

                            message = error_obj

                except Exception:

                    message = (
                        response.text[:2000]
                    )


                yield (
                    "data: " +
                    json.dumps(
                        {
                            "type": "error",
                            "message": message
                        },
                        ensure_ascii=False
                    ) +
                    "\n\n"
                )

                return


            # =========================================
            # STREAM
            #
            # chunk_size=1 مهمه
            # =========================================

            for line in response.iter_lines(
                chunk_size=1,
                decode_unicode=True
            ):

                if not line:
                    continue


                line = line.strip()


                if not line.startswith(
                    "data:"
                ):

                    continue


                raw = line[
                    5:
                ].strip()


                if not raw:
                    continue


                if raw == "[DONE]":

                    yield (
                        "data: " +
                        json.dumps(
                            {
                                "type": "done"
                            },
                            ensure_ascii=False
                        ) +
                        "\n\n"
                    )

                    break


                try:

                    chunk = json.loads(
                        raw
                    )

                except Exception:

                    continue


                # =====================================
                # SEARCH / TOOL INFORMATION
                # =====================================

                choices = chunk.get(
                    "choices",
                    []
                )


                if not choices:
                    continue


                choice = choices[0]

                delta = choice.get(
                    "delta",
                    {}
                )


                # =====================================
                # TEXT
                # =====================================

                content = delta.get(
                    "content"
                )


                if content:

                    yield (
                        "data: " +
                        json.dumps(
                            {
                                "type": "content",
                                "text": content
                            },
                            ensure_ascii=False
                        ) +
                        "\n\n"
                    )


                # =====================================
                # TOOL CALL
                # =====================================

                tool_calls = delta.get(
                    "tool_calls"
                )


                if tool_calls:

                    for tool in tool_calls:

                        function = tool.get(
                            "function",
                            {}
                        )

                        tool_name = (
                            function.get(
                                "name",
                                ""
                            )
                        )

                        arguments = (
                            function.get(
                                "arguments",
                                ""
                            )
                        )


                        yield (
                            "data: " +
                            json.dumps(
                                {
                                    "type": "search",
                                    "name": tool_name,
                                    "arguments": arguments
                                },
                                ensure_ascii=False
                            ) +
                            "\n\n"
                        )


                # =====================================
                # SOME PROVIDERS MAY SEND REASONING
                # =====================================

                reasoning = delta.get(
                    "reasoning"
                )


                if reasoning:

                    yield (
                        "data: " +
                        json.dumps(
                            {
                                "type": "reasoning",
                                "text": reasoning
                            },
                            ensure_ascii=False
                        ) +
                        "\n\n"
                    )


            # =========================================
            # FINISHED
            # =========================================

            yield (
                "data: " +
                json.dumps(
                    {
                        "type": "done"
                    },
                    ensure_ascii=False
                ) +
                "\n\n"
            )


        except requests.Timeout:

            yield (
                "data: " +
                json.dumps(
                    {
                        "type": "error",
                        "message":
                            "زمان پاسخ مدل تمام شد."
                    },
                    ensure_ascii=False
                ) +
                "\n\n"
            )


        except requests.RequestException as e:

            yield (
                "data: " +
                json.dumps(
                    {
                        "type": "error",
                        "message":
                            "ارتباط با OpenRouter قطع شد.",
                        "details": str(e)
                    },
                    ensure_ascii=False
                ) +
                "\n\n"
            )


        except Exception as e:

            yield (
                "data: " +
                json.dumps(
                    {
                        "type": "error",
                        "message":
                            "خطای Streaming سرور.",
                        "details": str(e)
                    },
                    ensure_ascii=False
                ) +
                "\n\n"
            )


    return Response(

        stream_with_context(
            generate()
        ),

        status=200,

        mimetype="text/event-stream",

        headers={

            "Cache-Control":
                "no-cache, no-transform",

            "X-Accel-Buffering":
                "no",

            "Connection":
                "keep-alive",

            "Content-Encoding":
                "identity"
        }
    )


# =========================================================
# FLASK ERRORS
# =========================================================

@app.errorhandler(HTTPException)
def http_error(error):

    return error_json(
        error.description,
        error.code or 500
    )


@app.errorhandler(Exception)
def unknown_error(error):

    return error_json(
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
