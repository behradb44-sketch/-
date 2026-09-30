import os
import time
import logging
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS


# =========================================================
# BEHRAD AI
# Stable Backend
# =========================================================

app = Flask(__name__)

# JSON فارسی را خواناتر برگردان
try:
    app.json.ensure_ascii = False
except Exception:
    pass


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Type"],
        }
    },
)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("BEHRAD_AI")


# ---------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    ""
).strip()

MODEL = "qwen/qwen3.8-27b:free"

SITE_URL = os.environ.get(
    "BEHRAD_AI_SITE_URL",
    "https://behrad-ai.onrender.com"
)

APP_NAME = "BEHRAD AI"


# ---------------------------------------------------------
# System Prompt
# ---------------------------------------------------------

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ دستیار هوش مصنوعی رسمی پروژه BEHRAD AI.

سازنده و صاحب پروژه:
بهراد محمدی
نام انگلیسی: Behrad Mohammadi
برند: BEHRAD M PLAYER

قوانین اصلی:

1. همیشه دقیق، مفید و طبیعی پاسخ بده.
2. فارسی را کاملاً پشتیبانی کن.
3. اگر کاربر فارسی صحبت کرد، فارسی پاسخ بده.
4. اگر کاربر انگلیسی صحبت کرد، انگلیسی پاسخ بده؛ مگر اینکه درخواست دیگری داشته باشد.
5. لحن دوستانه، حرفه‌ای و قابل فهم داشته باش.
6. برای کاربر مبتدی، از صفر تا صد توضیح بده.
7. اگر کاربر درخواست کد کامل کرد، کد کامل و قابل اجرا بده، نه تکه‌کد ناقص.
8. اگر پروژه چند فایل دارد، نام تمام فایل‌ها و محتوای کامل هر فایل را ارائه کن.
9. قبل از ارائه کدهای بزرگ، معماری و منطق لازم را بررسی کن.
10. کد را تا حد ممکن قابل اجرا و بدون وابستگی غیرضروری بنویس.
11. اگر چیزی را نمی‌دانی، حدس نزن.
12. درباره اطلاعات لحظه‌ای مثل قیمت، اخبار، نسخه نرم‌افزار، وضعیت سرویس‌ها، محصولات و مشخصات جدید، از Web Search استفاده کن.
13. اگر اطلاعات لحظه‌ای را با Web Search نتوانستی تأیید کنی، صریح بگو که نتوانستی آن را تأیید کنی و اطلاعات قدیمی را به‌عنوان اطلاعات فعلی ارائه نکن.
14. هنگام استفاده از نتایج وب، اطلاعات را با منبع و تاریخ مرتبط بیان کن.
15. تاریخ فعلی را از محیط/ابزارهای موجود در نظر بگیر و درباره «امروز»، «الان»، «جدیدترین» و موارد مشابه دقت کن.
16. از ساختن لینک، قیمت، خبر یا منبع جعلی خودداری کن.
17. برای درخواست‌های برنامه‌نویسی طولانی، پاسخ را منظم و مرحله‌بندی‌شده ارائه کن.
18. محتوای خانواده‌پسند ارائه کن.
19. اطلاعات شخصی سازنده را فقط در حد اطلاعاتی که همین System Prompt مشخص کرده استفاده کن.
20. هیچ‌وقت ادعا نکن کاری را انجام داده‌ای اگر واقعاً انجام نشده است.

اگر ابزار Web Search یا Web Fetch در دسترس باشد، برای اطلاعاتی که به‌روز بودنشان مهم است از آن‌ها استفاده کن.

تو یک دستیار عمومی هستی و می‌توانی در برنامه‌نویسی، بازی‌سازی، وب، Python، JavaScript، HTML/CSS، Unity، تکنولوژی، سخت‌افزار، آموزش و موضوعات عمومی کمک کنی.
"""


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_content(content):
    """
    تبدیل خروجی‌های مختلف OpenRouter به متن ساده.
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)

            elif isinstance(item, dict):
                text_value = item.get("text")

                if isinstance(text_value, str):
                    parts.append(text_value)

                elif item.get("type") == "text":
                    value = item.get("text", "")
                    if isinstance(value, str):
                        parts.append(value)

        return "\n".join(parts).strip()

    if isinstance(content, dict):
        value = content.get("text")

        if isinstance(value, str):
            return value.strip()

        return str(content)

    return str(content)


def sanitize_messages(messages):
    """
    فقط پیام‌های معتبر را نگه می‌دارد.
    """

    if not isinstance(messages, list):
        return []

    cleaned = []

    allowed_roles = {
        "system",
        "user",
        "assistant",
        "tool"
    }

    for message in messages:

        if not isinstance(message, dict):
            continue

        role = message.get("role")

        if role not in allowed_roles:
            continue

        content = message.get("content")

        if content is None:
            continue

        cleaned.append({
            "role": role,
            "content": content
        })

    return cleaned


def is_current_information_request(messages):
    """
    تشخیص تقریبی درخواست‌هایی که احتمالاً نیاز به Web Search دارند.
    """

    text_parts = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        content = message.get("content", "")

        if isinstance(content, str):
            text_parts.append(content)

        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text")
                    if isinstance(value, str):
                        text_parts.append(value)

    text = " ".join(text_parts).lower()

    keywords = [
        "الان",
        "امروز",
        "فعلی",
        "لحظه‌ای",
        "لحظه ای",
        "جدیدترین",
        "آخرین",
        "اخبار",
        "خبر",
        "قیمت",
        "نرخ",
        "دلار",
        "یورو",
        "طلا",
        "سکه",
        "بورس",
        "سهام",
        "موجودی",
        "موجوده",
        "چنده",
        "چند است",
        "چقدر است",
        "در حال حاضر",
        "همین الان",
        "سرچ",
        "جستجو",
        "وب",
        "سایت",
        "منبع",
        "latest",
        "today",
        "current",
        "now",
        "price",
        "news",
        "latest news",
        "search",
        "website",
        "stock",
        "exchange rate"
    ]

    return any(keyword in text for keyword in keywords)


def build_tools(use_web=False):
    """
    ابزارهای Server-side رسمی OpenRouter.
    """

    tools = []

    if use_web:
        tools.append({
            "type": "openrouter:web_search"
        })

        tools.append({
            "type": "openrouter:web_fetch"
        })

    return tools


def make_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": SITE_URL,
        "X-Title": APP_NAME,
        "Accept": "application/json",
    }


def openrouter_request(messages, use_web=True):
    """
    یک درخواست پایدار به OpenRouter.
    """

    payload = {
        "model": MODEL,

        "messages": messages,

        "temperature": 0.7,

        "top_p": 0.95,

        # برای پاسخ‌های کدنویسی طولانی
        "max_tokens": 12000,

        "reasoning": {
            "effort": "high",
            "exclude": True
        },

        "tool_choice": "auto",
    }

    tools = build_tools(use_web)

    if tools:
        payload["tools"] = tools

    logger.info(
        "OpenRouter request | model=%s | web=%s | messages=%d",
        MODEL,
        use_web,
        len(messages)
    )

    response = requests.post(
        OPENROUTER_URL,
        headers=make_headers(),
        json=payload,
        timeout=(20, 300)
    )

    logger.info(
        "OpenRouter response | status=%s",
        response.status_code
    )

    if response.status_code >= 400:
        try:
            error_data = response.json()
        except Exception:
            error_data = response.text

        raise RuntimeError(
            f"OpenRouter HTTP {response.status_code}: {error_data}"
        )

    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(
            f"OpenRouter returned invalid JSON: {exc}"
        )


def extract_answer(data):
    """
    استخراج پاسخ از ساختار OpenRouter.
    """

    choices = data.get("choices")

    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]

    if not isinstance(first, dict):
        return ""

    message = first.get("message", {})

    if not isinstance(message, dict):
        return ""

    content = message.get("content")

    answer = normalize_content(content)

    if answer:
        return answer

    # بعضی پاسخ‌ها ممکن است text داشته باشند
    text_value = message.get("text")

    if isinstance(text_value, str):
        return text_value.strip()

    return ""


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.route("/health", methods=["GET", "OPTIONS"])
def health():

    return jsonify({
        "ok": True,
        "status": "ok",
        "service": APP_NAME,
        "model": MODEL,
        "api_key_configured": bool(API_KEY),

        "features": {
            "text": True,
            "multilingual": True,
            "reasoning": True,
            "tool_calling": True,
            "web_search": True,
            "web_fetch": True,
            "image": True,
            "video": True
        },

        "time": now_iso()
    })


# ---------------------------------------------------------
# Root
# ---------------------------------------------------------

@app.route("/", methods=["GET", "OPTIONS"])
def root():

    return jsonify({
        "ok": True,
        "service": APP_NAME,
        "model": MODEL,
        "message": "BEHRAD AI API is online 🚀"
    })


# ---------------------------------------------------------
# Test AI
# ---------------------------------------------------------

@app.route("/api/test-ai", methods=["GET", "POST", "OPTIONS"])
def test_ai():

    if request.method == "OPTIONS":
        return ("", 204)

    if not API_KEY:
        return jsonify({
            "ok": False,
            "success": False,
            "error": "OPENROUTER_API_KEY is not configured."
        }), 500

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": "یک جمله کوتاه بگو که BEHRAD AI فعال است."
        }
    ]

    try:

        data = openrouter_request(
            messages,
            use_web=False
        )

        answer = extract_answer(data)

        if not answer:
            raise RuntimeError(
                "OpenRouter returned an empty answer."
            )

        return jsonify({
            "ok": True,
            "success": True,
            "model": MODEL,
            "answer": answer,
            "reply": answer,
            "response": answer
        })

    except Exception as exc:

        logger.exception("Test AI failed")

        return jsonify({
            "ok": False,
            "success": False,
            "error": str(exc)
        }), 502


# ---------------------------------------------------------
# Chat
# ---------------------------------------------------------

@app.route(
    "/api/chat",
    methods=["GET", "POST", "OPTIONS"]
)
def chat():

    # مهم برای جلوگیری از 405 در CORS preflight
    if request.method == "OPTIONS":
        return ("", 204)

    # اگر کسی URL را مستقیم باز کرد
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "service": APP_NAME,
            "message": "BEHRAD AI chat endpoint is online. Use POST to send messages.",
            "method_required": "POST"
        })

    if not API_KEY:
        return jsonify({
            "ok": False,
            "success": False,
            "error": "OPENROUTER_API_KEY is not configured."
        }), 500

    start_time = time.time()

    try:

        body = request.get_json(
            silent=True
        )

        if not isinstance(body, dict):
            return jsonify({
                "ok": False,
                "success": False,
                "error": "Invalid JSON body."
            }), 400

        incoming_messages = body.get("messages")

        # پشتیبانی از نسخه‌های قدیمی
        if incoming_messages is None:
            single_message = body.get("message")

            if isinstance(single_message, str):
                incoming_messages = [
                    {
                        "role": "user",
                        "content": single_message
                    }
                ]

        messages = sanitize_messages(
            incoming_messages
        )

        if not messages:
            return jsonify({
                "ok": False,
                "success": False,
                "error": "No valid messages were provided."
            }), 400

        # سیستم را همیشه اول قرار می‌دهیم
        user_messages = [
            message
            for message in messages
            if message.get("role") != "system"
        ]

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ] + user_messages

        # جلوگیری از ارسال تاریخچه‌ی بی‌نهایت
        #
        # سیستم + حداکثر 30 پیام اخیر
        if len(messages) > 31:
            messages = [
                messages[0]
            ] + messages[-30:]

        current_request = is_current_information_request(
            messages
        )

        # اگر درخواست فعلی/قیمت/خبر است:
        # web را فعال کن.
        #
        # برای بقیه هم Web Search در دسترس است،
        # اما مدل خودش می‌تواند تصمیم بگیرد.
        use_web = True

        logger.info(
            "Chat request | current_info=%s | messages=%d",
            current_request,
            len(messages)
        )

        try:

            data = openrouter_request(
                messages,
                use_web=use_web
            )

            answer = extract_answer(data)

        except Exception as first_error:

            logger.warning(
                "Primary OpenRouter request failed: %s",
                first_error
            )

            # اگر ابزار وب مشکل داشت، یک بار بدون ابزار
            # دوباره مدل را امتحان می‌کنیم.
            #
            # برای درخواست‌هایی که به اطلاعات لحظه‌ای
            # نیاز دارند، این fallback نباید به عنوان
            # اطلاعات تأییدشده‌ی فعلی نمایش داده شود.
            data = openrouter_request(
                messages,
                use_web=False
            )

            answer = extract_answer(data)

            if not answer:
                raise first_error

        if not answer:
            raise RuntimeError(
                "AI returned an empty response."
            )

        elapsed = round(
            time.time() - start_time,
            2
        )

        usage = data.get(
            "usage",
            {}
        )

        return jsonify({
            "ok": True,
            "success": True,

            "model": MODEL,

            "answer": answer,
            "reply": answer,
            "response": answer,

            "elapsed": elapsed,

            "usage": usage,

            "web_available": use_web,

            "time": now_iso()
        })

    except requests.Timeout:

        logger.exception(
            "OpenRouter timeout"
        )

        return jsonify({
            "ok": False,
            "success": False,
            "error": (
                "ارتباط با سرویس هوش مصنوعی بیش از حد طول کشید. "
                "لطفاً دوباره تلاش کن."
            )
        }), 504

    except requests.RequestException as exc:

        logger.exception(
            "Network error"
        )

        return jsonify({
            "ok": False,
            "success": False,
            "error": (
                "ارتباط با OpenRouter برقرار نشد."
            ),
            "details": str(exc)
        }), 502

    except Exception as exc:

        logger.exception(
            "Chat failed"
        )

        return jsonify({
            "ok": False,
            "success": False,
            "error": str(exc)
        }), 500


# ---------------------------------------------------------
# Run
# ---------------------------------------------------------

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
