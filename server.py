import os
import json
import requests

from flask import Flask, request, jsonify, Response, send_from_directory

app = Flask(__name__, static_folder=".")

# =========================================================
# CONFIG
# =========================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 12000
MAX_TOTAL_CHARS = 45000

# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ دستیار هوش مصنوعی اختصاصی پروژه BEHRAD M PLAYER.

اطلاعات مالک و سازنده:
- نام: بهراد محمدی
- نام مستعار و برند: بهراد ام پلیر
- نام انگلیسی برند: BEHRAD M PLAYER
- BEHRAD AI متعلق به بهراد محمدی، ملقب به بهراد ام پلیر است.
- سازنده و مالک پروژه BEHRAD AI، بهراد محمدی است.

اگر کاربر درباره سازنده، مالک، صاحب یا خالق BEHRAD AI پرسید،
پاسخ بده:
«صاحب و سازنده BEHRAD AI، بهراد محمدی، ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.»

رفتار:
- فارسی را کاملاً روان و طبیعی صحبت کن.
- اگر کاربر فارسی صحبت کرد، فارسی جواب بده.
- برای سؤال‌های فنی، دقیق و مرحله‌به‌مرحله توضیح بده.
- اگر کد خواسته شد، کد کامل و قابل استفاده ارائه کن.
- پاسخ‌ها را تا حد لازم کامل بده و بی‌دلیل کوتاه نکن.
- اگر برای پاسخ به اطلاعات جدید اینترنت نیاز است، از Web Search استفاده کن.
- اگر نتیجه جستجو را استفاده کردی، اطلاعات را بر اساس نتایج پیدا شده توضیح بده.
- درباره چیزی که مطمئن نیستی، وانمود نکن که مطمئنی.
"""

# =========================================================
# HELPERS
# =========================================================

def clean_messages(messages):
    """
    تاریخچه را برای ارسال به OpenRouter تمیز و محدود می‌کند.
    """

    if not isinstance(messages, list):
        return []

    cleaned = []

    for message in messages[-MAX_HISTORY:]:
        if not isinstance(message, dict):
            continue

        role = message.get("role")

        if role not in ("user", "assistant"):
            continue

        content = message.get("content", "")

        # رشته معمولی
        if isinstance(content, str):
            content = content[:MAX_MESSAGE_CHARS]

        # محتوای چندبخشی مثل متن + عکس
        elif isinstance(content, list):
            new_parts = []

            for part in content:
                if not isinstance(part, dict):
                    continue

                part_type = part.get("type")

                if part_type == "text":
                    new_parts.append({
                        "type": "text",
                        "text": str(part.get("text", ""))[:MAX_MESSAGE_CHARS]
                    })

                elif part_type == "image_url":
                    image_url = part.get("image_url")

                    if isinstance(image_url, dict):
                        url = image_url.get("url", "")

                        if isinstance(url, str) and url:
                            new_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": url
                                }
                            })

            content = new_parts

        else:
            continue

        cleaned.append({
            "role": role,
            "content": content
        })

    # محدودیت حجم کل
    total = 0
    final_messages = []

    for message in reversed(cleaned):
        content = message.get("content", "")

        try:
            size = len(json.dumps(content, ensure_ascii=False))
        except Exception:
            size = 0

        if total + size > MAX_TOTAL_CHARS:
            break

        total += size
        final_messages.insert(0, message)

    return final_messages


def openrouter_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://behradb44-sketch.github.io/",
        "X-Title": "BEHRAD AI"
    }


def web_search_tool():
    return {
        "type": "openrouter:web_search",
        "parameters": {
            "engine": "auto",
            "max_results": 5,
            "max_total_results": 10
        }
    }


def json_error(message, status=500):
    return jsonify({
        "success": False,
        "error": message
    }), status


# =========================================================
# BASIC ROUTES
# =========================================================

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "BEHRAD AI",
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "model": MODEL
    })


# =========================================================
# NORMAL CHAT
# =========================================================

@app.route("/api/chat", methods=["POST"])
def chat():

    if not OPENROUTER_API_KEY:
        return json_error(
            "OPENROUTER_API_KEY در تنظیمات Render قرار نگرفته است.",
            500
        )

    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return json_error("درخواست JSON معتبر نیست.", 400)

        messages = clean_messages(data.get("messages", []))

        if not messages:
            return json_error("پیامی برای ارسال وجود ندارد.", 400)

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                *messages
            ],
            "tools": [
                web_search_tool()
            ],
            "tool_choice": "auto",
            "temperature": 0.7,
            "max_tokens": 3000
        }

        response = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            timeout=(30, 180)
        )

        try:
            result = response.json()
        except Exception:
            result = {
                "error": response.text[:3000]
            }

        if response.status_code != 200:
            error_message = "خطا از OpenRouter"

            if isinstance(result, dict):
                error_data = result.get("error")

                if isinstance(error_data, dict):
                    error_message = (
                        error_data.get("message")
                        or error_data.get("code")
                        or error_message
                    )
                elif isinstance(error_data, str):
                    error_message = error_data

            return json_error(
                f"OpenRouter: {error_message}",
                response.status_code
            )

        answer = ""

        try:
            answer = result["choices"][0]["message"]["content"] or ""
        except Exception:
            pass

        if not answer:
            answer = "مدل پاسخ متنی برنگرداند."

        return jsonify({
            "success": True,
            "reply": answer,
            "model": MODEL
        })

    except requests.Timeout:
        return json_error(
            "زمان پاسخ OpenRouter تمام شد. دوباره امتحان کن.",
            504
        )

    except requests.RequestException as e:
        return json_error(
            f"خطای اتصال به OpenRouter: {str(e)}",
            502
        )

    except Exception as e:
        print("CHAT ERROR:", repr(e))

        return json_error(
            f"خطای داخلی سرور: {str(e)}",
            500
        )


# =========================================================
# STREAMING CHAT
# =========================================================

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():

    if not OPENROUTER_API_KEY:
        return jsonify({
            "success": False,
            "error": "OPENROUTER_API_KEY تنظیم نشده است."
        }), 500

    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "درخواست JSON معتبر نیست."
            }), 400

        messages = clean_messages(data.get("messages", []))

        if not messages:
            return jsonify({
                "success": False,
                "error": "پیامی برای ارسال وجود ندارد."
            }), 400

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                *messages
            ],

            # Web Search حفظ شده
            "tools": [
                web_search_tool()
            ],

            "tool_choice": "auto",
            "temperature": 0.7,
            "max_tokens": 3000,

            # بسیار مهم برای Streaming
            "stream": True
        }

        upstream = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            stream=True,
            timeout=(30, 180)
        )

        if upstream.status_code != 200:

            try:
                error_data = upstream.json()

                if isinstance(error_data, dict):
                    error_obj = error_data.get("error")

                    if isinstance(error_obj, dict):
                        message = (
                            error_obj.get("message")
                            or error_obj.get("code")
                            or "خطای OpenRouter"
                        )
                    else:
                        message = str(error_obj or "خطای OpenRouter")
                else:
                    message = str(error_data)

            except Exception:
                message = upstream.text[:3000]

            upstream.close()

            def error_generator():
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": f"OpenRouter: {message}"
                        },
                        ensure_ascii=False
                    )
                    + "\n\n"
                )

            return Response(
                error_generator(),
                status=200,
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                    "Content-Encoding": "identity"
                }
            )

        def generate():

            try:
                for raw_line in upstream.iter_lines(
                    chunk_size=1,
                    decode_unicode=True
                ):

                    if raw_line is None:
                        continue

                    line = raw_line.strip()

                    if not line:
                        continue

                    if not line.startswith("data:"):
                        continue

                    raw_data = line[5:].strip()

                    if not raw_data:
                        continue

                    if raw_data == "[DONE]":
                        yield (
                            "data: "
                            + json.dumps(
                                {"type": "done"},
                                ensure_ascii=False
                            )
                            + "\n\n"
                        )
                        continue

                    try:
                        chunk = json.loads(raw_data)
                    except Exception:
                        continue

                    # -----------------------------------------
                    # choices
                    # -----------------------------------------

                    choices = chunk.get("choices") or []

                    if not choices:
                        continue

                    choice = choices[0]

                    delta = choice.get("delta") or {}

                    # -----------------------------------------
                    # TEXT CONTENT
                    # -----------------------------------------

                    content = delta.get("content")

                    if content:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "content",
                                    "text": content
                                },
                                ensure_ascii=False
                            )
                            + "\n\n"
                        )

                    # -----------------------------------------
                    # REASONING
                    # -----------------------------------------

                    reasoning = (
                        delta.get("reasoning")
                        or delta.get("reasoning_content")
                    )

                    if reasoning:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "reasoning",
                                    "text": reasoning
                                },
                                ensure_ascii=False
                            )
                            + "\n\n"
                        )

                    # -----------------------------------------
                    # TOOL CALLS / WEB SEARCH
                    # -----------------------------------------

                    tool_calls = delta.get("tool_calls")

                    if tool_calls:

                        for tool_call in tool_calls:

                            function = (
                                tool_call.get("function")
                                or {}
                            )

                            tool_name = (
                                function.get("name")
                                or ""
                            )

                            arguments = (
                                function.get("arguments")
                                or ""
                            )

                            if (
                                "search" in tool_name.lower()
                                or
                                tool_name
                                == "openrouter:web_search"
                            ):

                                yield (
                                    "data: "
                                    + json.dumps(
                                        {
                                            "type": "search",
                                            "arguments": arguments
                                        },
                                        ensure_ascii=False
                                    )
                                    + "\n\n"
                                )

                yield (
                    "data: "
                    + json.dumps(
                        {"type": "done"},
                        ensure_ascii=False
                    )
                    + "\n\n"
                )

            except Exception as e:

                print("STREAM GENERATOR ERROR:", repr(e))

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": f"خطای Streaming: {str(e)}"
                        },
                        ensure_ascii=False
                    )
                    + "\n\n"
                )

            finally:
                upstream.close()

        return Response(
            generate(),
            status=200,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
                "Content-Encoding": "identity"
            }
        )

    except requests.Timeout:

        return jsonify({
            "success": False,
            "error": "زمان اتصال به OpenRouter تمام شد."
        }), 504

    except requests.RequestException as e:

        return jsonify({
            "success": False,
            "error": f"خطای اتصال: {str(e)}"
        }), 502

    except Exception as e:

        print("STREAM ERROR:", repr(e))

        return jsonify({
            "success": False,
            "error": f"خطای داخلی سرور: {str(e)}"
        }), 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(os.getenv("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True
                        )
