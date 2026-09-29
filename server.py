import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

app = Flask(__name__, static_folder=".")

MODEL = "stealth/space-bunny-alpha"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

MAX_HISTORY = 20
MAX_VIDEO_MB = 20


def error_json(message, status=500, details=None):
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
        "success": True,
        "service": "BEHRAD AI",
        "status": "ok",
        "api_key_configured": bool(API_KEY),
        "model": MODEL
    })


def openrouter_request(messages):
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
            "Content-Type": "application/json",
            "HTTP-Referer": "https://k6k83zh1yv.onrender.com",
            "X-Title": "BEHRAD AI"
        },
        json=payload,
        timeout=120
    )

    try:
        data = response.json()
    except Exception:
        return None, response.status_code, response.text[:2000]

    return data, response.status_code, None


@app.route("/api/chat", methods=["POST"])
def chat():

    if not API_KEY:
        return error_json(
            "OPENROUTER_API_KEY روی Render تنظیم نشده.",
            500
        )

    try:
        body = request.get_json(silent=True)

        if not body:
            return error_json(
                "درخواست JSON معتبر نیست.",
                400
            )

        messages = body.get("messages")

        if not isinstance(messages, list):
            return error_json(
                "messages نامعتبر است.",
                400
            )

        messages = messages[-MAX_HISTORY:]

        clean_messages = []

        for message in messages:

            if not isinstance(message, dict):
                continue

            role = message.get("role")

            if role not in ("user", "assistant"):
                continue

            content = message.get("content")

            if isinstance(content, str):

                if content.strip():
                    clean_messages.append({
                        "role": role,
                        "content": content
                    })

                continue

            if isinstance(content, list):

                parts = []

                for part in content:

                    if not isinstance(part, dict):
                        continue

                    part_type = part.get("type")

                    if part_type == "text":

                        text = part.get("text", "")

                        if text:
                            parts.append({
                                "type": "text",
                                "text": text
                            })

                    elif part_type == "image_url":

                        image_url = part.get("image_url")

                        if isinstance(image_url, dict):

                            url = image_url.get("url")

                            if isinstance(url, str) and url:
                                parts.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": url
                                    }
                                })

                    elif part_type == "video_url":

                        video_url = part.get("video_url")

                        if isinstance(video_url, dict):

                            url = video_url.get("url")

                            if isinstance(url, str) and url:
                                parts.append({
                                    "type": "video_url",
                                    "video_url": {
                                        "url": url
                                    }
                                })

                if parts:

                    clean_messages.append({
                        "role": role,
                        "content": parts
                    })

        if not clean_messages:
            return error_json(
                "پیامی برای ارسال وجود ندارد.",
                400
            )

        data, status, raw = openrouter_request(
            clean_messages
        )

        if data is None:

            return error_json(
                "OpenRouter پاسخ JSON نداد.",
                status,
                raw
            )

        if status >= 400:

            return error_json(
                "OpenRouter درخواست را قبول نکرد.",
                status,
                data
            )

        choices = data.get("choices", [])

        if not choices:
            return error_json(
                "مدل پاسخی برنگرداند.",
                502,
                data
            )

        message = choices[0].get("message", {})

        answer = message.get("content")

        if answer is None:
            answer = ""

        if not isinstance(answer, str):
            answer = str(answer)

        if not answer.strip():
            answer = "مدل پاسخ متنی برنگرداند."

        return jsonify({
            "success": True,
            "reply": answer,
            "model": MODEL
        })

    except requests.Timeout:

        return error_json(
            "زمان پاسخ مدل تمام شد. دوباره امتحان کن.",
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


if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
                )
