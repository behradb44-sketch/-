import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

app = Flask(__name__, static_folder=".")

MODEL = "stealth/space-bunny-alpha"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

MAX_HISTORY = 20


def json_error(message, status=500, details=None):
    data = {
        "success": False,
        "error": message
    }

    if details:
        data["details"] = details

    return jsonify(data), status


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "BEHRAD AI",
        "api_key_configured": bool(API_KEY),
        "model": MODEL
    })


@app.route("/api/test-ai", methods=["GET"])
def test_ai():
    if not API_KEY:
        return json_error("OPENROUTER_API_KEY تنظیم نشده.", 500)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": "سلام! فقط کوتاه جواب بده."
            }
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://k6k83zh1yv.onrender.com",
                "X-Title": "BEHRAD AI"
            },
            json=payload,
            timeout=90
        )

        try:
            data = response.json()
        except Exception:
            return json_error(
                "OpenRouter پاسخ JSON نداد.",
                response.status_code,
                response.text[:1000]
            )

        if not response.ok:
            return json_error(
                "OpenRouter خطا داد.",
                response.status_code,
                data
            )

        answer = ""

        if data.get("choices"):
            answer = (
                data["choices"][0]
                .get("message", {})
                .get("content", "")
            )

        return jsonify({
            "success": True,
            "reply": answer,
            "model": MODEL
        })

    except requests.Timeout:
        return json_error("اتصال به OpenRouter timeout شد.", 504)

    except requests.RequestException as e:
        return json_error(
            "اتصال به OpenRouter برقرار نشد.",
            502,
            str(e)
        )

    except Exception as e:
        return json_error(
            "خطای داخلی سرور.",
            500,
            str(e)
        )


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return json_error(
            "کلید OPENROUTER_API_KEY روی Render تنظیم نشده.",
            500
        )

    try:
        body = request.get_json(silent=True)

        if not body:
            return json_error(
                "بدنه درخواست JSON نیست.",
                400
            )

        messages = body.get("messages")

        if not isinstance(messages, list) or len(messages) == 0:
            return json_error(
                "messages خالی یا نامعتبر است.",
                400
            )

        # فقط آخرین ۲۰ پیام برای جلوگیری از بزرگ‌شدن بیش از حد درخواست
        messages = messages[-MAX_HISTORY:]

        clean_messages = []

        for msg in messages:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")

            if role not in ["user", "assistant"]:
                continue

            content = msg.get("content")

            if isinstance(content, str):
                if content.strip():
                    clean_messages.append({
                        "role": role,
                        "content": content
                    })

            elif isinstance(content, list):
                valid_parts = []

                for part in content:
                    if not isinstance(part, dict):
                        continue

                    part_type = part.get("type")

                    if part_type == "text":
                        text = part.get("text", "")

                        if isinstance(text, str) and text.strip():
                            valid_parts.append({
                                "type": "text",
                                "text": text
                            })

                    elif part_type == "image_url":
                        image_url = part.get("image_url", {})

                        if isinstance(image_url, dict):
                            url = image_url.get("url", "")

                            if isinstance(url, str) and url:
                                valid_parts.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": url
                                    }
                                })

                    elif part_type == "video_url":
                        video_url = part.get("video_url", {})

                        if isinstance(video_url, dict):
                            url = video_url.get("url", "")

                            if isinstance(url, str) and url:
                                valid_parts.append({
                                    "type": "video_url",
                                    "video_url": {
                                        "url": url
                                    }
                                })

                if valid_parts:
                    clean_messages.append({
                        "role": role,
                        "content": valid_parts
                    })

        if not clean_messages:
            return json_error(
                "هیچ پیام قابل پردازشی پیدا نشد.",
                400
            )

        payload = {
            "model": MODEL,
            "messages": clean_messages,
            "temperature": 0.7,
            "max_tokens": 4000,

            # ابزارهای وب اختیاری‌اند و سمت OpenRouter اجرا می‌شوند.
            "tools": [
                {
                    "type": "openrouter:web_search"
                },
                {
                    "type": "openrouter:web_fetch"
                }
            ]
        }

        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://k6k83zh1yv.onrender.com",
                "X-Title": "BEHRAD AI"
            },
            json=payload,
            timeout=120
        )

        # تلاش برای JSON
        try:
            data = response.json()
        except Exception:
            return json_error(
                f"OpenRouter پاسخ قابل‌خواندن نداد. HTTP {response.status_code}",
                response.status_code,
                response.text[:1500]
            )

        if not response.ok:
            return json_error(
                f"OpenRouter خطا داد. HTTP {response.status_code}",
                response.status_code,
                data
            )

        choices = data.get("choices", [])

        if not choices:
            return json_error(
                "OpenRouter هیچ پاسخی برنگرداند.",
                502,
                data
            )

        message = choices[0].get("message", {})

        answer = message.get("content")

        # بعضی مدل‌ها ممکن است content را None برگردانند
        if answer is None:
            answer = ""

        if not isinstance(answer, str):
            answer = str(answer)

        if not answer.strip():
            answer = "مدل پاسخی متنی برنگرداند."

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
            "ارتباط با OpenRouter برقرار نشد.",
            502,
            str(e)
        )

    except Exception as e:
        return json_error(
            "خطای داخلی در /api/chat",
            500,
            str(e)
        )


@app.errorhandler(HTTPException)
def handle_http_error(error):
    return json_error(
        error.description,
        error.code or 500
    )


@app.errorhandler(Exception)
def handle_unknown_error(error):
    return json_error(
        "خطای غیرمنتظره سرور.",
        500,
        str(error)
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
