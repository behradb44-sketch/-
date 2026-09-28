import os
import requests

from flask import Flask, request, jsonify, send_from_directory


app = Flask(__name__)


# ==========================================
# CONFIG
# ==========================================

OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY"
)

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health():

    return jsonify({
        "status": "online",
        "name": "BEHRAD AI",
        "model": MODEL,
        "api_key_configured":
            bool(OPENROUTER_API_KEY)
    })


# ==========================================
# CHAT
# ==========================================

@app.post("/api/chat")
def chat():

    try:

        if not OPENROUTER_API_KEY:

            return jsonify({
                "error":
                "OPENROUTER_API_KEY تنظیم نشده است."
            }), 500


        data = request.get_json(
            silent=True
        )


        if not data:

            return jsonify({
                "error":
                "داده‌ای دریافت نشد."
            }), 400


        messages = data.get(
            "messages",
            []
        )


        if not isinstance(
            messages,
            list
        ):

            return jsonify({
                "error":
                "messages باید یک لیست باشد."
            }), 400


        if len(messages) == 0:

            return jsonify({
                "error":
                "پیامی برای ارسال وجود ندارد."
            }), 400


        payload = {

            "model": MODEL,

            "messages": messages,

            "temperature": 0.7

        }


        headers = {

            "Authorization":
                f"Bearer {OPENROUTER_API_KEY}",

            "Content-Type":
                "application/json",

            "HTTP-Referer":
                request.host_url,

            "X-Title":
                "BEHRAD AI"

        }


        response = requests.post(

            OPENROUTER_URL,

            headers=headers,

            json=payload,

            timeout=120

        )


        # ----------------------------------
        # OpenRouter error
        # ----------------------------------

        if not response.ok:

            try:

                error_data =
                    response.json()

            except Exception:

                error_data = {
                    "error": response.text
                }


            return jsonify({

                "error":
                    "OpenRouter Error",

                "details":
                    error_data

            }), response.status_code


        # ----------------------------------
        # Success
        # ----------------------------------

        result =
            response.json()


        return jsonify(result)


    except requests.exceptions.Timeout:

        return jsonify({

            "error":
            "زمان پاسخ OpenRouter تمام شد."

        }), 504


    except requests.exceptions.RequestException as error:

        return jsonify({

            "error":
            "خطا در اتصال به OpenRouter.",

            "details":
            str(error)

        }), 502


    except Exception as error:

        return jsonify({

            "error":
            "خطای داخلی سرور.",

            "details":
            str(error)

        }), 500


# ==========================================
# START SERVER
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(

        host="0.0.0.0",

        port=port

      )
