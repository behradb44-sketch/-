import os
import json
import requests

from flask import Flask, request, jsonify, Response, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

MODEL = "stealth/space-bunny-alpha"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 12000
MAX_TOTAL_CHARS = 45000


SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ یک دستیار هوش مصنوعی فارسی‌زبان قدرتمند.

اطلاعات هویتی پروژه:
- صاحب BEHRAD AI: بهراد محمدی
- سازنده BEHRAD AI: بهراد محمدی
- نام مستعار و برند سازنده: بهراد ام پلیر
- نام انگلیسی برند: BEHRAD M PLAYER

اگر کاربر درباره صاحب، سازنده یا مالک BEHRAD AI پرسید،
با اطمینان بگو:
«صاحب و سازنده BEHRAD AI، بهراد محمدی ملقب به بهراد ام پلیر (BEHRAD M PLAYER) است.»

قوانین:
- فارسی را کاملاً طبیعی و خوانا بنویس.
- پاسخ‌ها را با UTF-8 صحیح تولید کن.
- اگر کاربر فارسی حرف زد، فارسی جواب بده.
- اگر کاربر انگلیسی حرف زد، می‌توانی انگلیسی پاسخ بدهی.
- در برنامه‌نویسی کد کامل و قابل استفاده ارائه کن.
- لحن دوستانه، طبیعی و مفید داشته باش.
- از پاسخ‌های بی‌دلیل خیلی طولانی خودداری کن.
"""


def error_response(message, status=500):
    return jsonify({
        "success": False,
        "error": message
    }), status


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "BEHRAD AI",
        "api_key_configured": bool(OPENROUTER_API_KEY)
    })


def normalize_content(content):
    if isinstance(content, str):
        return content[:MAX_MESSAGE_CHARS]

    if isinstance(content, list):
        result = []

        for part in content:
            if not isinstance(part, dict):
                continue

            ptype = part.get("type")

            if ptype == "text":
                result.append({
                    "type": "text",
                    "text": str(part.get("text", ""))[:MAX_MESSAGE_CHARS]
                })

            elif ptype == "image_url":
                image_url = part.get("image_url")

                if isinstance(image_url, dict):
                    url = image_url.get("url", "")
                else:
                    url = str(image_url or "")

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

    cleaned = []

    # فقط آخرین 12 پیام
    messages = messages[-MAX_HISTORY:]

    total_chars = 0

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role")

        if role not in ("user", "assistant"):
            continue

        content = normalize_content(msg.get("content", ""))

        if isinstance(content, str):
            total_chars += len(content)
        else:
            for part in content:
                if part.get("type") == "text":
                    total_chars += len(part.get("text", ""))

        if total_chars > MAX_TOTAL_CHARS:
            break

        cleaned.append({
            "role": role,
            "content": content
        })

    return cleaned


def openrouter_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "HTTP-Referer": "https://behradb44-sketch.github.io/behrad-m-player/",
        "X-Title": "BEHRAD AI"
    }


def openrouter_payload(messages, stream=False):
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
        "stream": stream,

        # جستجوی وب حذف نشده
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


@app.route("/api/chat", methods=["POST"])
def chat():
    if not OPENROUTER_API_KEY:
        return error_response("OPENROUTER_API_KEY تنظیم نشده است.", 500)

    try:
        data = request.get_json(force=True, silent=False)

        messages = clean_messages(
            data.get("messages", [])
        )

        if not messages:
            return error_response("پیامی دریافت نشد.", 400)

        payload = openrouter_payload(messages, stream=False)

        response = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            timeout=(30, 180)
        )

        if response.status_code != 200:
            try:
                details = response.json()
            except Exception:
                details = response.text[:2000]

            return jsonify({
                "success": False,
                "error": "OpenRouter error",
                "details": details
            }), response.status_code

        result = response.json()

        answer = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        if not answer:
            answer = "مدل پاسخ متنی برنگرداند."

        return jsonify({
            "success": True,
            "reply": answer,
            "model": MODEL
        })

    except Exception as e:
        return error_response(
            f"خطای سرور: {str(e)}",
            500
        )


def sse_bytes(event, data):
    """
    مهم‌ترین بخش رفع مشکل فارسی:
    خروجی SSE مستقیماً به UTF-8 bytes تبدیل می‌شود.
    """
    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    )

    text = (
        f"event: {event}\n"
        f"data: {payload}\n\n"
    )

    return text.encode("utf-8")


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    if not OPENROUTER_API_KEY:
        return Response(
            sse_bytes(
                "error",
                {"message": "OPENROUTER_API_KEY تنظیم نشده است."}
            ),
            status=500,
            content_type="text/event-stream; charset=utf-8"
        )

    try:
        data = request.get_json(force=True, silent=False)

        messages = clean_messages(
            data.get("messages", [])
        )

        if not messages:
            return Response(
                sse_bytes(
                    "error",
                    {"message": "پیامی دریافت نشد."}
                ),
                status=400,
                content_type="text/event-stream; charset=utf-8"
            )

        payload = openrouter_payload(messages, stream=True)

        upstream = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            stream=True,
            timeout=(30, 180)
        )

        if upstream.status_code != 200:

            try:
                raw_error = upstream.content

                error_text = raw_error.decode(
                    "utf-8",
                    errors="replace"
                )

                try:
                    error_data = json.loads(error_text)
                except Exception:
                    error_data = error_text[:3000]

            except Exception as e:
                error_data = str(e)

            yield sse_bytes(
                "error",
                {
                    "message": "OpenRouter خطا داد.",
                    "details": error_data
                }
            )

            yield sse_bytes(
                "done",
                {}
            )

            return

        # اعلام شروع پاسخ
        yield sse_bytes(
            "start",
            {
                "model": MODEL
            }
        )

        buffer = b""

        for raw_chunk in upstream.iter_content(
            chunk_size=1024
        ):
            if not raw_chunk:
                continue

            buffer += raw_chunk

            while b"\n\n" in buffer:

                raw_event, buffer = buffer.split(
                    b"\n\n",
                    1
                )

                # UTF-8 دقیق
                event_text = raw_event.decode(
                    "utf-8",
                    errors="replace"
                )

                for line in event_text.splitlines():

                    if not line.startswith("data:"):
                        continue

                    data_text = line[5:].strip()

                    if not data_text:
                        continue

                    if data_text == "[DONE]":
                        yield sse_bytes(
                            "done",
                            {}
                        )
                        continue

                    try:
                        chunk = json.loads(data_text)

                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])

                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # متن پاسخ
                    content = delta.get("content")

                    if content:
                        yield sse_bytes(
                            "token",
                            {
                                "text": content
                            }
                        )

                    # reasoning
                    reasoning = (
                        delta.get("reasoning")
                        or delta.get("reasoning_content")
                    )

                    if reasoning:
                        yield sse_bytes(
                            "reasoning",
                            {
                                "text": reasoning
                            }
                        )

                    # Tool / search
                    tool_calls = delta.get("tool_calls")

                    if tool_calls:
                        yield sse_bytes(
                            "search",
                            {
                                "status": "در حال جستجو در وب..."
                            }
                        )

        if buffer.strip():

            event_text = buffer.decode(
                "utf-8",
                errors="replace"
            )

            for line in event_text.splitlines():

                if not line.startswith("data:"):
                    continue

                data_text = line[5:].strip()

                if data_text == "[DONE]":
                    continue

                try:
                    chunk = json.loads(data_text)
                except Exception:
                    continue

                choices = chunk.get("choices", [])

                if not choices:
                    continue

                content = (
                    choices[0]
                    .get("delta", {})
                    .get("content")
                )

                if content:
                    yield sse_bytes(
                        "token",
                        {
                            "text": content
                        }
                    )

        yield sse_bytes(
            "done",
            {}
        )

    except requests.exceptions.Timeout:
        yield sse_bytes(
            "error",
            {
                "message": "زمان پاسخ سرور تمام شد."
            }
        )

    except Exception as e:
        yield sse_bytes(
            "error",
            {
                "message": f"خطای سرور: {str(e)}"
            }
        )


@app.route("/api/test-ai")
def test_ai():
    if not OPENROUTER_API_KEY:
        return error_response(
            "OPENROUTER_API_KEY تنظیم نشده است.",
            500
        )

    try:
        payload = openrouter_payload(
            [
                {
                    "role": "user",
                    "content": "سلام رفیق"
                }
            ],
            stream=False
        )

        response = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            timeout=(30, 180)
        )

        return Response(
            response.content,
            status=response.status_code,
            content_type="application/json; charset=utf-8"
        )

    except Exception as e:
        return error_response(
            str(e),
            500
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
