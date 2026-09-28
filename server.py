import os
import uuid
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory, abort
from werkzeug.utils import secure_filename


# =========================================================
# BEHRAD AI SERVER
# =========================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# حداکثر حجم کل درخواست
app.config["MAX_CONTENT_LENGTH"] = 55 * 1024 * 1024

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()

MODEL = "stealth/space-bunny-alpha"

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

SITE_URL = "https://k6k83zh1yv.onrender.com"


# =========================================================
# FILE TYPES
# =========================================================

ALLOWED_IMAGES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif"
}

ALLOWED_VIDEOS = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/mpeg",
    "video/x-matroska"
}


# =========================================================
# JSON ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def too_large(error):

    return jsonify({
        "success": False,
        "error": "حجم فایل یا درخواست بیش از حد مجاز است. حداکثر 55MB."
    }), 413


@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "success": False,
        "error": "مسیر موردنظر پیدا نشد."
    }), 404


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "success": False,
        "error": "خطای داخلی سرور."
    }), 500


# =========================================================
# CLEANUP
# =========================================================

def cleanup_old_uploads():

    now = time.time()

    try:

        for file in UPLOAD_DIR.iterdir():

            if not file.is_file():
                continue

            try:

                age = now - file.stat().st_mtime

                if age > 30 * 60:
                    file.unlink(missing_ok=True)

            except Exception:
                pass

    except Exception:
        pass


# =========================================================
# HEADERS
# =========================================================

def openrouter_headers():

    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": SITE_URL,
        "X-Title": "BEHRAD AI"
    }


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return jsonify({

        "success": True,

        "status": "ok",

        "service": "BEHRAD AI",

        "api_key_configured":
            bool(OPENROUTER_API_KEY),

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
# UPLOAD
# =========================================================

@app.route(
    "/api/upload",
    methods=["POST"]
)
def upload():

    cleanup_old_uploads()

    try:

        if "file" not in request.files:

            return jsonify({

                "success": False,

                "error":
                    "هیچ فایلی ارسال نشده."

            }), 400


        file = request.files["file"]


        if not file:

            return jsonify({

                "success": False,

                "error":
                    "فایل نامعتبر است."

            }), 400


        if not file.filename:

            return jsonify({

                "success": False,

                "error":
                    "نام فایل خالی است."

            }), 400


        original_name = file.filename

        content_type = (
            file.mimetype or ""
        ).lower()


        # -----------------------------------------------
        # نوع فایل
        # -----------------------------------------------

        if content_type in ALLOWED_IMAGES:

            media_type = "image"

            max_size = (
                15 * 1024 * 1024
            )

        elif content_type in ALLOWED_VIDEOS:

            media_type = "video"

            max_size = (
                40 * 1024 * 1024
            )

        else:

            return jsonify({

                "success": False,

                "error":
                    "فقط عکس و ویدیو پشتیبانی می‌شود."

            }), 400


        # -----------------------------------------------
        # ذخیره موقت
        # -----------------------------------------------

        safe_name = secure_filename(
            original_name
        )

        extension = (
            Path(safe_name).suffix.lower()
        )

        if not extension:

            extension = ".bin"


        filename = (
            f"{uuid.uuid4().hex}"
            f"{extension}"
        )

        output_path = (
            UPLOAD_DIR / filename
        )


        file.save(output_path)


        if not output_path.exists():

            return jsonify({

                "success": False,

                "error":
                    "ذخیره فایل انجام نشد."

            }), 500


        file_size = (
            output_path.stat().st_size
        )


        # -----------------------------------------------
        # حجم
        # -----------------------------------------------

        if file_size > max_size:

            output_path.unlink(
                missing_ok=True
            )

            limit_mb = (
                max_size //
                (1024 * 1024)
            )

            return jsonify({

                "success": False,

                "error":
                    f"حجم {media_type} بیشتر "
                    f"از {limit_mb}MB است."

            }), 413


        # -----------------------------------------------
        # URL
        # -----------------------------------------------

        public_url = (
            request.host_url.rstrip("/")
            + "/media/"
            + filename
        )


        return jsonify({

            "success": True,

            "type": media_type,

            "mime": content_type,

            "name": original_name,

            "size": file_size,

            "url": public_url

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                f"خطا در آپلود: {str(e)}"

        }), 500


# =========================================================
# MEDIA
# =========================================================

@app.route(
    "/media/<filename>"
)
def media(filename):

    safe_name = secure_filename(
        filename
    )

    if not safe_name:

        abort(404)


    path = (
        UPLOAD_DIR /
        safe_name
    )


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

@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    if not OPENROUTER_API_KEY:

        return jsonify({

            "success": False,

            "error":
                "OPENROUTER_API_KEY is not configured on Render."

        }), 500


    try:

        data = request.get_json(
            silent=True
        ) or {}


        messages = data.get(
            "messages"
        )


        if not isinstance(
            messages,
            list
        ) or not messages:

            return jsonify({

                "success": False,

                "error":
                    "messages نامعتبر است."

            }), 400


        system_message = {

            "role": "system",

            "content": """
تو BEHRAD AI هستی.

قوانین:

- پاسخ دقیق، واضح و کاربردی بده.
- اگر سؤال نیاز به اطلاعات جدید اینترنتی دارد، از web search استفاده کن.
- اگر کاربر URL داد یا خواست سایت را بررسی کنی، از web fetch استفاده کن.
- منابع مختلف را در صورت نیاز با هم مقایسه کن.
- ادعاهای تأییدنشده را قطعی بیان نکن.
- اگر عکس یا ویدیو دریافت کردی، محتوای آن را بررسی کن.
- برای برنامه‌نویسی کد کامل و قابل اجرا ارائه کن.
- کدها را داخل code block قرار بده.
- chain-of-thought یا reasoning داخلی را نمایش نده.
"""
        }


        final_messages = [
            system_message
        ] + messages


        payload = {

            "model": MODEL,

            "messages":
                final_messages,

            "tools": [

                {
                    "type":
                        "openrouter:web_search",

                    "parameters": {

                        "max_results": 6,

                        "max_total_results": 12,

                        "search_context_size":
                            "medium"

                    }

                },

                {
                    "type":
                        "openrouter:web_fetch",

                    "parameters": {

                        "engine":
                            "openrouter",

                        "max_content_tokens":
                            30000

                    }

                }

            ],

            "temperature": 0.7,

            "max_tokens": 8000

        }


        response = requests.post(

            OPENROUTER_URL,

            headers=
                openrouter_headers(),

            json=payload,

            timeout=180

        )


        try:

            result = response.json()

        except Exception:

            return jsonify({

                "success": False,

                "error":
                    "OpenRouter پاسخ JSON معتبر نداد.",

                "status":
                    response.status_code,

                "raw":
                    response.text[:1000]

            }), 502


        if response.status_code != 200:

            error_obj = result.get(
                "error"
            )

            if isinstance(
                error_obj,
                dict
            ):

                error_message = (
                    error_obj.get(
                        "message"
                    )
                    or
                    "OpenRouter error"
                )

            else:

                error_message = (
                    "OpenRouter request failed."
                )


            return jsonify({

                "success": False,

                "error":
                    error_message,

                "status":
                    response.status_code,

                "details":
                    result

            }), response.status_code


        choices = result.get(
            "choices",
            []
        )


        if not choices:

            return jsonify({

                "success": False,

                "error":
                    "OpenRouter پاسخ خالی برگرداند.",

                "details":
                    result

            }), 502


        message = choices[0].get(
            "message",
            {}
        )


        answer = message.get(
            "content"
        )


        if isinstance(
            answer,
            list
        ):

            parts = []

            for item in answer:

                if isinstance(
                    item,
                    dict
                ):

                    if item.get(
                        "type"
                    ) == "text":

                        parts.append(
                            item.get(
                                "text",
                                ""
                            )
                        )

                    elif "text" in item:

                        parts.append(
                            item.get(
                                "text",
                                ""
                            )
                        )

            answer = "\n".join(
                parts
            )


        if not answer:

            answer = (
                "پاسخ متنی دریافت نشد."
            )


        return jsonify({

            "success": True,

            "reply": answer,

            "model":
                result.get(
                    "model",
                    MODEL
                ),

            "usage":
                result.get(
                    "usage",
                    {}
                )

        })


    except requests.Timeout:

        return jsonify({

            "success": False,

            "error":
                "زمان پاسخ تمام شد."

        }), 504


    except requests.RequestException as e:

        return jsonify({

            "success": False,

            "error":
                f"خطای ارتباطی: {str(e)}"

        }), 502


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                f"Server error: {str(e)}"

        }), 500


# =========================================================
# TEST
# =========================================================

@app.route("/api/test-ai")
def test_ai():

    if not OPENROUTER_API_KEY:

        return jsonify({

            "success": False,

            "error":
                "OPENROUTER_API_KEY is not configured."

        }), 500


    try:

        payload = {

            "model": MODEL,

            "messages": [

                {

                    "role": "user",

                    "content":
                        "سلام! فقط بگو BEHRAD AI آنلاین است."

                }

            ]

        }


        response = requests.post(

            OPENROUTER_URL,

            headers=
                openrouter_headers(),

            json=payload,

            timeout=60

        )


        result = response.json()


        answer = (
            result
            .get(
                "choices",
                [{}]
            )[0]
            .get(
                "message",
                {}
            )
            .get(
                "content"
            )
        )


        return jsonify({

            "success":
                response.status_code == 200,

            "openrouter_status":
                response.status_code,

            "model":
                MODEL,

            "پاسخ":
                answer

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
