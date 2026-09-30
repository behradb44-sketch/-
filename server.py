import os
import json
import time
import logging
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS


# ============================================================
# BEHRAD AI
# Streaming Backend
# ============================================================

app = Flask(__name__)

try:
    app.json.ensure_ascii = False
except Exception:
    pass


# ============================================================
# CORS
# ============================================================

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "Accept",
                "Cache-Control",
                "X-Requested-With"
            ],
            "expose_headers": [
                "Content-Type",
                "Cache-Control"
            ]
        }
    }
)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, Accept, Cache-Control, X-Requested-With"
    )

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("BEHRAD_AI")


# ============================================================
# OPENROUTER
# ============================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL = "qwen/qwen3.8-27b:free"

API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    ""
).strip()

SITE_URL = os.environ.get(
    "BEHRAD_AI_SITE_URL",
    "https://k6k83zh1yv.onrender.com"
)

APP_NAME = "BEHRAD AI"


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
تو BEHRAD AI هستی؛ دستیار هوش مصنوعی رسمی پروژه BEHRAD AI.

سازنده پروژه:
بهراد محمدی
Behrad Mohammadi

برند:
BEHRAD M PLAYER

قوانین:

1. فارسی و انگلیسی را به‌خوبی پشتیبانی کن.
2. اگر کاربر فارسی صحبت کرد، فارسی پاسخ بده.
3. لحن دوستانه، طبیعی و حرفه‌ای داشته باش.
4. برای کاربر مبتدی، مفاهیم را از صفر تا صد توضیح بده.
5. اگر کاربر کد خواست، کد واقعی و قابل اجرا بده.
6. اگر پروژه چند فایل دارد، نام فایل‌ها را مشخص کن.
7. برای کدهای بزرگ، پاسخ را منطقی و مرحله‌بندی‌شده ارائه کن.
8. کد ناقص یا pseudo-code را به‌عنوان نسخه نهایی معرفی نکن.
9. قبل از ارائه کد، منطق آن را بررسی کن.
10. اگر چیزی را نمی‌دانی، حدس نزن.
11. درباره قیمت، اخبار، وضعیت محصولات، نسخه نرم‌افزار و اطلاعات لحظه‌ای از Web Search استفاده کن.
12. اگر اطلاعات لحظه‌ای قابل تأیید نیست، آن را به‌عنوان حقیقت فعلی اعلام نکن.
13. لینک و منبع جعلی نساز.
14. اگر از Web Search استفاده کردی، نتایج را با توجه به اطلاعات واقعی وب تفسیر کن.
15. محتوای خانواده‌پسند ارائه کن.
16. در برنامه‌نویسی به Python، JavaScript، HTML، CSS، Unity، بازی‌سازی و توسعه نرم‌افزار کمک کن.
17. اگر پاسخ بسیار طولانی است، آن را با ساختار مناسب و بخش‌بندی‌شده ارائه کن.
18. پاسخ را بی‌دلیل کوتاه نکن.
19. اگر محدودیت فنی برای طول پاسخ وجود دارد، به‌جای قطع ناگهانی، واضح بگو که می‌توان ادامه پاسخ را تولید کرد.
20. هرگز ادعا نکن کاری انجام شده که واقعاً انجام نشده است.

برای اطلاعات به‌روز، در صورت در دسترس بودن ابزار، از Web Search استفاده کن.
"""


# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sse(data):
    """
    ساخت یک Server-Sent Event.
    """
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def sanitize_messages(messages):
    if not isinstance(messages, list):
        return []

    allowed_roles = {
        "system",
        "user",
        "assistant",
        "tool"
    }

    cleaned = []

    for item in messages:
        if not isinstance(item, dict):
            continue

        role = item.get("role")

        if role not in allowed_roles:
            continue

        if "content" not in item:
            continue

        cleaned.append({
            "role": role,
            "content": item["content"]
        })

    return cleaned


def normalize_content(content):
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        result = []

        for item in content:
            if isinstance(item, str):
                result.append(item)
                continue

            if isinstance(item, dict):
                value = item.get("text")

                if isinstance(value, str):
                    result.append(value)

        return "".join(result)

    if isinstance(content, dict):
        value = content.get("text")

        if isinstance(value, str):
            return value

    return str(content)


def is_current_request(messages):
    """
    تشخیص درخواست‌هایی که احتمالاً به وب نیاز دارند.
    """

    chunks = []

    for message in messages:
        content = message.get("content", "")

        if isinstance(content, str):
            chunks.append(content)

        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text")

                    if isinstance(text_value, str):
                        chunks.append(text_value)

    text = " ".join(chunks).lower()

    keywords = [
        "الان",
        "امروز",
        "همین الان",
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
        "در حال حاضر",
        "سرچ",
        "جستجو",
        "وب",
        "سایت",
        "منبع",
        "latest",
        "today",
        "current",
        "right now",
        "price",
        "news",
        "latest news",
        "search",
        "website",
        "stock",
        "exchange rate"
    ]

    return any(word in text for word in keywords)


def build_payload(messages, use_web=True):
    """
    ساخت Payload رسمی OpenRouter.
    """

    payload = {
        "model": MODEL,

        "messages": messages,

        # Streaming واقعی
        "stream": True,

        # Qwen reasoning
        "reasoning": {
            "effort": "high",
            "exclude": True
        },

        "temperature": 0.7,

        "top_p": 0.95,

        # Qwen3.8 27B Free فعلاً تا 262K completion
        # را در صفحه مدل اعلام می‌کند.
        #
        # عمداً 131072 می‌گذاریم تا درخواست‌های بسیار بزرگ
        # قابل مدیریت‌تر باشند.
        "max_tokens": 131072,

        "tool_choice": "auto"
    }

    if use_web:
        payload["tools"] = [
            {
                "type": "openrouter:web_search"
            },
            {
                "type": "openrouter:web_fetch"
            }
        ]

    return payload


def headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",

        "HTTP-Referer": SITE_URL,
        "X-Title": APP_NAME
    }


# ============================================================
# NON-STREAMING TEST
# ============================================================

def normal_request(messages):
    payload = build_payload(
        messages,
        use_web=False
    )

    payload["stream"] = False
    payload["max_tokens"] = 4096

    response = requests.post(
        OPENROUTER_URL,
        headers=headers(),
        json=payload,
        timeout=(20, 180)
    )

    if response.status_code >= 400:
        try:
            details = response.json()
        except Exception:
            details = response.text

        raise RuntimeError(
            f"OpenRouter HTTP {response.status_code}: {details}"
        )

    return response.json()


def extract_normal_answer(data):
    choices = data.get("choices", [])

    if not choices:
        return ""

    message = choices[0].get("message", {})

    return normalize_content(
        message.get("content")
    )


# ============================================================
# ROOT
# ============================================================

@app.route("/", methods=["GET", "OPTIONS"])
def root():

    if request.method == "OPTIONS":
        return ("", 204)

    return jsonify({
        "ok": True,
        "service": APP_NAME,
        "model": MODEL,
        "streaming": True,
        "message": "BEHRAD AI API is online 🚀"
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health", methods=["GET", "OPTIONS"])
def health():

    if request.method == "OPTIONS":
        return ("", 204)

    return jsonify({
        "ok": True,
        "status": "ok",
        "service": APP_NAME,
        "model": MODEL,
        "api_key_configured": bool(API_KEY),

        "streaming": True,

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


# ============================================================
# TEST AI
# ============================================================

@app.route(
    "/api/test-ai",
    methods=["GET", "POST", "OPTIONS"]
)
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
            "content": "فقط بگو: BEHRAD AI فعال است 🚀"
        }
    ]

    try:

        data = normal_request(messages)

        answer = extract_normal_answer(data)

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


# ============================================================
# CHAT STREAM
# ============================================================

@app.route(
    "/api/chat",
    methods=["GET", "POST", "OPTIONS"]
)
def chat():

    if request.method == "OPTIONS":
        return ("", 204)

    if request.method == "GET":
        return jsonify({
            "ok": True,
            "service": APP_NAME,
            "streaming": True,
            "message": "Use POST to stream an AI response.",
            "method_required": "POST"
        })

    if not API_KEY:
        return jsonify({
            "ok": False,
            "success": False,
            "error": "OPENROUTER_API_KEY is not configured."
        }), 500

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

        incoming = body.get("messages")

        if incoming is None:

            single_message = body.get(
                "message"
            )

            if isinstance(single_message, str):
                incoming = [
                    {
                        "role": "user",
                        "content": single_message
                    }
                ]

        messages = sanitize_messages(
            incoming
        )

        if not messages:
            return jsonify({
                "ok": False,
                "success": False,
                "error": "No valid messages were provided."
            }), 400

        # سیستم خودمان همیشه اول باشد
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ] + [
            item
            for item in messages
            if item.get("role") != "system"
        ]

        # جلوگیری از رشد بی‌نهایت history
        # آخرین 40 پیام + system
        if len(messages) > 41:
            messages = [
                messages[0]
            ] + messages[-40:]

        use_web = True

        current_request = is_current_request(
            messages
        )

        logger.info(
            "STREAM CHAT | messages=%s | current=%s",
            len(messages),
            current_request
        )

    except Exception as exc:

        return jsonify({
            "ok": False,
            "success": False,
            "error": str(exc)
        }), 400

    @stream_with_context
    def generate():

        started = time.time()

        payload = build_payload(
            messages,
            use_web=use_web
        )

        response = None

        try:

            response = requests.post(
                OPENROUTER_URL,
                headers=headers(),
                json=payload,

                # مهم:
                # stream=True باعث می‌شود کل پاسخ
                # قبل از تحویل به مرورگر جمع نشود.
                stream=True,

                timeout=(30, 600)
            )

            if response.status_code >= 400:

                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text

                logger.error(
                    "OpenRouter streaming HTTP %s: %s",
                    response.status_code,
                    error_data
                )

                yield sse({
                    "type": "error",
                    "error": (
                        f"OpenRouter HTTP {response.status_code}"
                    ),
                    "details": error_data
                })

                yield sse({
                    "type": "done",
                    "ok": False
                })

                return

            # شروع پاسخ
            yield sse({
                "type": "start",
                "ok": True,
                "model": MODEL,
                "streaming": True,
                "web": use_web
            })

            accumulated_length = 0

            for raw_line in response.iter_lines(
                decode_unicode=True
            ):

                if not raw_line:
                    continue

                line = raw_line.strip()

                if not line:
                    continue

                # SSE معمولاً به شکل:
                # data: {...}
                if line.startswith("data:"):
                    line = line[5:].strip()

                if line == "[DONE]":
                    break

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:

                    # ممکن است بخشی از SSE خراب/غیر JSON باشد.
                    # نادیده می‌گیریم تا stream قطع نشود.
                    continue

                # --------------------------------------------
                # error
                # --------------------------------------------

                if "error" in chunk:

                    yield sse({
                        "type": "error",
                        "error": chunk["error"]
                    })

                    continue

                choices = chunk.get(
                    "choices",
                    []
                )

                if not choices:
                    continue

                choice = choices[0]

                delta = choice.get(
                    "delta",
                    {}
                )

                content = delta.get(
                    "content"
                )

                if content:

                    text = normalize_content(
                        content
                    )

                    if text:

                        accumulated_length += len(
                            text
                        )

                        yield sse({
                            "type": "delta",
                            "text": text,
                            "length": accumulated_length
                        })

                # reasoning را به کاربر نشان نمی‌دهیم.
                #
                # فقط final content ارسال می‌شود.

                finish_reason = choice.get(
                    "finish_reason"
                )

                if finish_reason:

                    yield sse({
                        "type": "finish_reason",
                        "value": finish_reason
                    })

                # usage ممکن است در chunk آخر بیاید
                usage = chunk.get("usage")

                if usage:

                    yield sse({
                        "type": "usage",
                        "usage": usage
                    })

            elapsed = round(
                time.time() - started,
                2
            )

            yield sse({
                "type": "done",
                "ok": True,
                "model": MODEL,
                "elapsed": elapsed
            })

        except requests.Timeout:

            logger.exception(
                "OpenRouter stream timeout"
            )

            yield sse({
                "type": "error",
                "error": (
                    "ارتباط با OpenRouter بیش از حد طول کشید."
                )
            })

            yield sse({
                "type": "done",
                "ok": False
            })

        except requests.RequestException as exc:

            logger.exception(
                "OpenRouter network error"
            )

            yield sse({
                "type": "error",
                "error": (
                    "ارتباط با OpenRouter قطع شد."
                ),
                "details": str(exc)
            })

            yield sse({
                "type": "done",
                "ok": False
            })

        except GeneratorExit:

            logger.info(
                "Client disconnected."
            )

            raise

        except Exception as exc:

            logger.exception(
                "Streaming error"
            )

            yield sse({
                "type": "error",
                "error": str(exc)
            })

            yield sse({
                "type": "done",
                "ok": False
            })

        finally:

            if response is not None:
                response.close()

    return Response(
        generate(),
        status=200,
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True
        )
