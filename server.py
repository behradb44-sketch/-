import os
import requests

from flask import Flask, request, jsonify, send_from_directory


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "BEHRAD AI",
        "api_key_configured": bool(OPENROUTER_API_KEY)
    })


# =========================================================
# MAIN CHAT API
# =========================================================

@app.route("/api/chat", methods=["POST"])
def chat():

    try:

        # Check API key
        if not OPENROUTER_API_KEY:
            return jsonify({
                "success": False,
                "error": "OPENROUTER_API_KEY is not configured on Render."
            }), 500


        # Read request
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "success": False,
                "error": "Request body is empty."
            }), 400


        # Get messages
        messages = data.get("messages")


        # Support simple "message"
        if not messages:

            message = data.get("message")

            if not message:
                return jsonify({
                    "success": False,
                    "error": "No message provided."
                }), 400

            messages = [
                {
                    "role": "user",
                    "content": message
                }
            ]


        # OpenRouter request
        payload = {
            "model": MODEL,
            "messages": messages
        }


        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://k6k83zh1yv.onrender.com",
            "X-Title": "BEHRAD AI"
        }


        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=120
        )


        # Debug information in Render logs
        print("======================================")
        print("OPENROUTER STATUS:", response.status_code)
        print("OPENROUTER RESPONSE:", response.text)
        print("======================================")


        # Try JSON
        try:
            result = response.json()

        except Exception:

            return jsonify({
                "success": False,
                "error": "OpenRouter returned a non-JSON response.",
                "status_code": response.status_code,
                "raw_response": response.text[:5000]
            }), 502


        # OpenRouter returned error
        if response.status_code != 200:

            return jsonify({
                "success": False,
                "error": "OpenRouter returned an error.",
                "status_code": response.status_code,
                "details": result
            }), response.status_code


        # Get choices
        choices = result.get("choices")

        if not choices:

            return jsonify({
                "success": False,
                "error": "OpenRouter returned no choices.",
                "openrouter_response": result
            }), 502


        # Get message
        message_data = choices[0].get("message", {})

        answer = message_data.get("content")


        # Empty response
        if not answer:

            return jsonify({
                "success": False,
                "error": "OpenRouter returned empty content.",
                "openrouter_response": result
            }), 502


        # Success
        return jsonify({
            "success": True,
            "reply": answer
        })


    except requests.exceptions.Timeout:

        return jsonify({
            "success": False,
            "error": "OpenRouter request timed out."
        }), 504


    except requests.exceptions.RequestException as e:

        return jsonify({
            "success": False,
            "error": "Network error while connecting to OpenRouter.",
            "details": str(e)
        }), 502


    except Exception as e:

        return jsonify({
            "success": False,
            "error": "Unexpected server error.",
            "details": str(e)
        }), 500


# =========================================================
# DIRECT AI TEST
# =========================================================

@app.route("/api/test-ai")
def test_ai():

    try:

        if not OPENROUTER_API_KEY:

            return jsonify({
                "success": False,
                "error": "OPENROUTER_API_KEY is missing."
            }), 500


        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "سلام! فقط یک جواب کوتاه به فارسی بده."
                }
            ]
        }


        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://k6k83zh1yv.onrender.com",
            "X-Title": "BEHRAD AI"
        }


        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=120
        )


        try:
            result = response.json()

        except Exception:

            return jsonify({
                "success": False,
                "openrouter_status": response.status_code,
                "error": "OpenRouter returned non-JSON data.",
                "raw_response": response.text[:5000]
            }), 502


        # Extract answer if available
        answer = None

        if result.get("choices"):

            answer = (
                result["choices"][0]
                .get("message", {})
                .get("content")
            )


        return jsonify({
            "success": response.status_code == 200,
            "openrouter_status": response.status_code,
            "model": MODEL,
            "answer": answer,
            "openrouter_response": result
        })


    except requests.exceptions.Timeout:

        return jsonify({
            "success": False,
            "error": "OpenRouter timed out."
        }), 504


    except requests.exceptions.RequestException as e:

        return jsonify({
            "success": False,
            "error": "Network error.",
            "details": str(e)
        }), 502


    except Exception as e:

        return jsonify({
            "success": False,
            "error": "Unexpected error.",
            "details": str(e)
        }), 500


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
