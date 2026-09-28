import os
import uuid
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory, abort
from werkzeug.utils import secure_filename


# =========================================================
# BEHRAD AI - SERVER
# =========================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# حداکثر اندازه درخواست
app.config["MAX_CONTENT_LENGTH"] = 55 * 1024 * 1024

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SITE_URL = "https://k6k83zh1yv.onrender.com"


# =========================================================
# ALLOWED FILES
# =========================================================

ALLOWED_IMAGES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

ALLOWED_VIDEOS = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/mpeg",
    "video/x-matroska",
}


# =========================================================
# BASIC HELPERS
# =========================================================

def cleanup_old_uploads():
    """
    فایل‌های قدیمی‌تر از 30 دقیقه حذف می‌شوند.
    """
    now = time.time()

    for file in UPLOAD_DIR.iterdir():
        try:
            if file.is_file():
                age = now - file.stat().st_mtime

                if age > 30 * 60:
                    file.unlink(missing_ok=True)

        except Exception:
            pass


def openrouter_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": SITE_URL,
        "X-Title": "BEHRAD AI",
    }


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "BEHRAD AI",
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "model": MODEL,
        "features": {
            "image_upload": True,
            "video_upload": True,
            "web_search": True,
            "web_fetch": True,
            "code_copy": True
        }
    })


# =========================================================
# UPLOAD MEDIA
# =========================================================

@app.route("/api/upload", methods=["POST"])
def upload_media():

    cleanup_old_uploads()

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "فایلی ارسال نشده."
        }), 400

    file = request.files["file"]

    if not file or not file.filename:
        return jsonify({
            "success": False,
            "error": "نام فایل نامعتبر است."
        }), 400

    content_type = (file.mimetype or "").lower()

    if content_type not in ALLOWED_IMAGES and content_type not in ALLOWED_VIDEOS:
        return jsonify({
            "success": False,
            "error": "این نوع فایل پشتیبانی نمی‌شود."
        }), 400

    # محدودیت جداگانه
    if content_type in ALLOWED_IMAGES:
        max_size = 15 * 1024 * 1024
        media_type = "image"

    else:
        max_size = 40 * 1024 * 1024
        media_type = "video"

    # ذخیره موقت
    extension = Path(secure_filename(file.filename)).suffix.lower()

    if not extension:
        extension = ".bin"

    token = uuid.uuid4().hex

    filename = f"{token}{extension}"

    output_path = UPLOAD_DIR / filename

    file.save(output_path)

    try:
        size = output_path.stat().st_size
    except Exception:
        output_path.unlink(missing_ok=True)

        return jsonify({
            "success": False,
            "error": "ذخیره فایل انجام نشد."
        }), 500

    if size > max_size:
        output_path.unlink(missing_ok=True)

        limit_mb = max_size // (1024 * 1024)

        return jsonify({
            "success": False,
            "error": f"حجم فایل بیشتر از {limit_mb}MB است."
        }), 413

    public_url = f"{request.host_url.rstrip('/')}/media/{filename}"

    return jsonify({
        "success": True,
        "type": media_type,
        "mime": content_type,
        "name": file.filename,
        "size": size,
        "url": public_url
    })


# =========================================================
# SERVE TEMPORARY MEDIA
# =========================================================

@app.route("/media/<filename>")
def serve_media(filename):

    safe_name = secure_filename(filename)

    if not safe_name or safe_name != filename:
        abort(404)

    path = UPLOAD_DIR / safe_name

    if not path.exists():
        abort(404)

    return send_from_directory(
        UPLOAD_DIR,
        safe_name,
        conditional=True
    )


# =========================================================
# CHAT
# =========================================================

@app.route("/api/chat", methods=["POST"])
def chat():

    if not OPENROUTER_API_KEY:
        return jsonify({
            "success": False,
            "error": "OPENROUTER_API_KEY is not configured on Render."
        }), 500

    try:

        data = request.get_json(silent=True) or {}

        messages = data.get("messages")

        if not isinstance(messages, list) or not messages:
            return jsonify({
                "success": False,
                "error": "messages نامعتبر است."
            }), 400

        # -------------------------------------------------
        # System prompt
        # -------------------------------------------------

        system_message = {
            "role": "system",
            "content": """
تو BEHRAD AI هستی.

قوانین و قابلیت‌ها:

1. پاسخ‌ها را واضح، کاربردی و تا حد ممکن دقیق بده.

2. اگر سؤال به اطلاعات جدید، قیمت، اخبار، سایت‌ها، محصولات،
   قوانین، تکنولوژی جدید یا هر اطلاعات آنلاین نیاز دارد،
   از web search استفاده کن.

3. اگر کاربر یک URL داد یا خواست یک سایت را باز/بررسی کنی،
   از web fetch استفاده کن.

4. می‌توانی سایت‌های مختلف و منابع معتبر و غیرمعتبر را بررسی کنی،
   اما اعتبار منبع را از روی شواهد و مشخصات آن توضیح بده و
   ادعاهای تأییدنشده را قطعی بیان نکن.

5. اگر چند منبع وجود دارد، اطلاعات مهم را با مقایسه منابع بررسی کن.

6. اگر کاربر عکس یا ویدیو فرستاد، محتوای آن را بررسی کن و
   مستقیماً درباره همان فایل پاسخ بده.

7. برای برنامه‌نویسی:
   - کد کامل و قابل اجرا بده.
   - زبان کد را مشخص کن.
   - توضیح را خارج از code block قرار بده.
   - کد را داخل triple backtick قرار بده.

8. هیچ‌وقت reasoning داخلی یا chain-of-thought خودت را نمایش نده.
   فقط نتیجه و توضیح مفید را ارائه کن.

9. اگر اطلاعات کافی نیست، واضح بگو چه چیزی مشخص نیست.

10. اگر لینک یا منبعی از وب پیدا کردی، تا حد امکان URL یا نام منبع
    را در پاسخ نهایی قابل تشخیص نگه دار.

تو یک دستیار چندرسانه‌ای و وب‌محور هستی.
"""
        }

        final_messages = [system_message] + messages

        payload = {
            "model": MODEL,
            "messages": final_messages,

            # -------------------------------------------------
            # WEB TOOLS
            # -------------------------------------------------

            "tools": [
                {
                    "type": "openrouter:web_search",
                    "parameters": {
                        "max_results": 6,
                        "max_total_results": 12,
                        "search_context_size": "medium"
                    }
                },
                {
                    "type": "openrouter:web_fetch",
                    "parameters": {
                        "engine": "openrouter",
                        "max_content_tokens": 30000
                    }
                }
            ],

            "temperature": 0.7,

            "max_tokens": 8000
        }

        response = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            timeout=180
        )

        try:
            result = response.json()
        except Exception:
            result = {
                "error": response.text
            }

        if response.status_code != 200:

            error_message = (
                result.get("error", {}).get("message")
                if isinstance(result.get("error"), dict)
                else None
            )

            return jsonify({
                "success": False,
                "error": error_message or "OpenRouter request failed.",
                "status": response.status_code,
                "details": result
            }), response.status_code

        choices = result.get("choices", [])

        if not choices:
            return jsonify({
                "success": False,
                "error": "OpenRouter پاسخ خالی برگرداند.",
                "details": result
            }), 502

        message = choices[0].get("message", {})

        answer = message.get("content")

        if isinstance(answer, list):

            parts = []

            for item in answer:

                if isinstance(item, dict):

                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))

                    elif "text" in item:
                        parts.append(item.get("text", ""))

            answer = "\n".join(parts)

        if not answer:
            answer = "پاسخ متنی از مدل دریافت نشد."

        return jsonify({
            "success": True,
            "reply": answer,
            "model": result.get("model", MODEL),
            "usage": result.get("usage", {}),
            "web_enabled": True
        })

    except requests.Timeout:

        return jsonify({
            "success": False,
            "error": "زمان پاسخ OpenRouter تمام شد. دوباره امتحان کن."
        }), 504

    except requests.RequestException as e:

        return jsonify({
            "success": False,
            "error": f"خطای ارتباط با OpenRouter: {str(e)}"
        }), 502

    except Exception as e:

        return jsonify({
            "success": False,
            "error": f"Server error: {str(e)}"
        }), 500


# =========================================================
# TEST AI
# =========================================================

@app.route("/api/test-ai")
def test_ai():

    if not OPENROUTER_API_KEY:
        return jsonify({
            "success": False,
            "error": "OPENROUTER_API_KEY is not configured."
        }), 500

    try:

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "سلام! فقط یک پاسخ کوتاه بده و بگو BEHRAD AI آنلاین است."
                }
            ]
        }

        response = requests.post(
            OPENROUTER_URL,
            headers=openrouter_headers(),
            json=payload,
            timeout=60
        )

        result = response.json()

        answer = (
            result
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )

        return jsonify({
            "success": response.status_code == 200,
            "openrouter_status": response.status_code,
            "model": MODEL,
            "پاسخ": answer,
            "openrouter_response": result
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(os.getenv("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
