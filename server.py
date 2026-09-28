import os
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

MODEL = "stealth/space-bunny-alpha"


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


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        if not OPENROUTER_API_KEY:
            return jsonify({
                "error": "OPENROUTER_API_KEY is not configured on Render."
            }), 500

        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "error": "Request body is empty."
            }), 400

        messages = data.get("messages")

        if not messages:
            message = data.get("message")

            if not message:
                return jsonify({
                    "error": "No message provided."
                }), 400

            messages = [
                {
                    "role": "user",
                    "content": message
                }
            ]

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://behrad-ai.onrender.com",
                "X-Title": "BEHRAD AI"
            },
            json={
                "model": MODEL,
                "messages": messages
            },
            timeout=120
        )

        try:
            result = response.json()
        except Exception:
            return jsonify({
                "error": "OpenRouter returned an invalid response.",
                "status_code": response.status_code,
                "raw": response.text[:1000]
            }), 502

        if response.status_code != 200:
            return jsonify({
                "error": "OpenRouter request failed.",
                "status_code": response.status_code,
                "details": result
            }), response.status_code

        if "choices" not in result or not result["choices"]:
            return jsonify({
                "error": "No response was returned by the AI.",
                "details": result
            }), 502

        answer = result["choices"][0]["message"]["content"]

        return jsonify({
            "reply": answer
        })

    except requests.exceptions.Timeout:
        return jsonify({
            "error": "OpenRouter request timed out."
        }), 504

    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Network error while connecting to OpenRouter.",
            "details": str(e)
        }), 502

    except Exception as e:
        return jsonify({
            "error": "Server error.",
            "details": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )
