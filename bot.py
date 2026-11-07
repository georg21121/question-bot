from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from database import (
    get_unseen_cached_question,
    get_user_category,
    get_user_stats,
    init_db,
    is_question_seen,
    mark_last_question_skipped,
    mark_question_seen,
    reset_user_memory,
    save_cached_questions,
    set_user_category,
)
from searcher import SEED_QUESTIONS, search_internet_questions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")


def load_env_dict() -> Dict[str, str]:
    """Читает настройки из файла .env."""
    env_vars: Dict[str, str] = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars


ENV_VARS = load_env_dict()
BOT_TOKEN = ENV_VARS.get("BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
CUSTOM_PROXY = (
    ENV_VARS.get("PROXY_URL")
    or os.environ.get("PROXY_URL")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("http_proxy")
    or os.environ.get("HTTP_PROXY")
    or ""
)
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

CATEGORY_NAMES = {
    "all": "🎲 Все темы",
    "couple": "❤️ Для пары / девушки",
    "friends": "🍻 Для друзей",
}


def is_local_port_open(host: str, port: int) -> bool:
    """Проверяет, запущен ли локальный прокси/VPN-клиент (например, порт 2080 или 10809)."""
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except Exception:
        return False


def build_opener(use_proxy: Optional[str] = None) -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    if use_proxy:
        proxy_handler = urllib.request.ProxyHandler({"http": use_proxy, "https": use_proxy})
        return urllib.request.build_opener(proxy_handler, https_handler)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), https_handler)


def get_active_proxy() -> Optional[str]:
    if CUSTOM_PROXY:
        return CUSTOM_PROXY
    for port in (2080, 10809, 10808, 7890):
        if is_local_port_open("127.0.0.1", port):
            return f"http://127.0.0.1:{port}"
    return None


def tg_request(method: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    """Выполняет запрос к Telegram Bot API (с автоподхватом прокси при необходимости)."""
    url = f"{API_BASE}/{method}"
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    proxy_url = get_active_proxy()
    candidates = [proxy_url, None] if proxy_url else [None]

    last_err = ""
    for proxy in candidates:
        req = urllib.request.Request(url, data=data, headers=headers)
        opener = build_opener(proxy)
        try:
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logging.warning(f"Telegram API HTTP error ({method}): {e.code} {err_body}")
            return {"ok": False, "error_code": e.code, "description": err_body}
        except Exception as e:
            last_err = str(e)
            continue

    logging.warning(f"Network error ({method}): {last_err}")
    return {"ok": False, "description": last_err}


def get_main_reply_keyboard() -> Dict[str, Any]:
    """Постоянная клавиатура внизу экрана."""
    return {
        "keyboard": [
            [{"text": "🎲 Вопрос"}, {"text": "⏭ Пропустить вопрос"}],
            [
                {"text": "❤️ Для девушки / пары"},
                {"text": "🍻 Для друзей"},
                {"text": "🌐 Все темы"},
            ],
            [{"text": "📊 Моя память"}, {"text": "🔄 Сбросить память"}],
        ],
        "resize_keyboard": True,
    }


def get_question_inline_keyboard() -> Dict[str, Any]:
    """Инлайн-кнопки прямо под сообщением с вопросом."""
    return {
        "inline_keyboard": [
            [
                {"text": "🎲 Ещё вопрос", "callback_data": "next_question"},
                {"text": "⏭ Пропустить вопрос", "callback_data": "skip_question"},
            ],
            [
                {"text": "🔎 Найти свежие в сети (Pinterest / TikTok)", "callback_data": "force_search"},
            ],
        ]
    }


def background_replenish(category: str) -> None:
    """Фоновое пополнение базы вопросов из интернета."""
    def _worker() -> None:
        try:
            found = search_internet_questions(category)
            if found:
                save_cached_questions(found)
                logging.info(f"Фоновый поиск: добавлено {len(found)} вопросов (категория {category})")
        except Exception as e:
            logging.debug(f"Background search error: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def fetch_unique_question(user_id: int, category: str, force_web: bool = False) -> Optional[Dict[str, str]]:
    """
    Находит уникальный вопрос, который пользователь ещё не видел.
    Если force_web=True или в кэше закончились вопросы — запускает живой поиск по Pinterest/TikTok/Интернету.
    """
    if not force_web:
        cached = get_unseen_cached_question(user_id, category)
        if cached:
            background_replenish(category)
            return cached

    found_questions = search_internet_questions(category)
    if found_questions:
        save_cached_questions(found_questions)
        for q in found_questions:
            if not is_question_seen(user_id, q["text"]):
                return q

    return get_unseen_cached_question(user_id, "all")


def format_question_message(q_data: Dict[str, str], category: str, skipped: bool = False) -> str:
    prefix = "⏭ <i>Вопрос пропущен! Вот другой:</i>\n\n" if skipped else ""
    cat_label = CATEGORY_NAMES.get(category, "🎲 Все темы")
    source_label = q_data.get("source", "Интернет 🌐")
    return (
        f"{prefix}"
        f"💬 <b>{q_data['text']}</b>\n\n"
        f"🏷 <i>Тема: {cat_label}</i>\n"
        f"🌐 <i>Источник: {source_label}</i>"
    )


def send_or_update_question(
    user_id: int,
    chat_id: int,
    skipped: bool = False,
    force_web: bool = False,
    edit_message_id: Optional[int] = None,
) -> None:
    category = get_user_category(user_id)

    if skipped:
        mark_last_question_skipped(user_id)

    status_msg_id = None
    if force_web:
        res = tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "🔎 Ищу свежие вопросы в Pinterest 📌, TikTok 🎵 и по всему интернету...",
            },
        )
        if res.get("ok"):
            status_msg_id = res["result"]["message_id"]

    q_data = fetch_unique_question(user_id, category, force_web=force_web)

    if status_msg_id:
        tg_request("deleteMessage", {"chat_id": chat_id, "message_id": status_msg_id})

    if not q_data:
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "🎉 Ого! Ты просмотрел все доступные вопросы в текущей теме.\n"
                    "Нажми <b>«🔄 Сбросить память»</b> или переключи тему!"
                ),
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
        return

    mark_question_seen(user_id, q_data["text"], category=category, status="shown")
    text = format_question_message(q_data, category, skipped=skipped)

    if edit_message_id is not None:
        edit_res = tg_request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": edit_message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": get_question_inline_keyboard(),
            },
        )
        if edit_res.get("ok"):
            return

    tg_request(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": get_question_inline_keyboard(),
        },
    )


def handle_message(message: Dict[str, Any]) -> None:
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id", chat_id)
    text = message.get("text", "").strip()

    if text.startswith("/start"):
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "👋 <b>Привет! Я бот для интересных разговоров с девушкой или друзьями.</b>\n\n"
                    "Я сам ищу крутые вопросы в <b>Pinterest 📌, TikTok 🎵 и на просторах интернета 🌐</b>.\n\n"
                    "🧠 <b>У меня есть память:</b> я запоминаю каждый показанный и пропущенный вопрос, "
                    "поэтому вопросы <u>не повторяются</u>.\n\n"
                    "Жми <b>«🎲 Вопрос»</b> внизу экрана, чтобы начать!"
                ),
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
    elif text in ("🎲 Вопрос", "/question"):
        send_or_update_question(user_id, chat_id, skipped=False)
    elif text == "⏭ Пропустить вопрос":
        send_or_update_question(user_id, chat_id, skipped=True)
    elif text == "❤️ Для девушки / пары":
        set_user_category(user_id, "couple")
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "❤️ Выбран режим: <b>Вопросы для девушки / пары</b>.\nИщу глубокие и сближающие вопросы!",
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
        send_or_update_question(user_id, chat_id, skipped=False)
    elif text == "🍻 Для друзей":
        set_user_category(user_id, "friends")
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "🍻 Выбран режим: <b>Вопросы для компании друзей</b>.\nИщу интересные темы для обсуждения!",
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
        send_or_update_question(user_id, chat_id, skipped=False)
    elif text == "🌐 Все темы":
        set_user_category(user_id, "all")
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "🎲 Выбран режим: <b>Все темы</b>!",
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
        send_or_update_question(user_id, chat_id, skipped=False)
    elif text == "📊 Моя память":
        stats = get_user_stats(user_id)
        cat = CATEGORY_NAMES.get(get_user_category(user_id), "🎲 Все темы")
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    f"🧠 <b>Память бота для тебя:</b>\n\n"
                    f"✅ Всего просмотрено: <b>{stats['seen']}</b> вопр.\n"
                    f"💬 Оставлено для обсуждения: <b>{stats['discussed']}</b> вопр.\n"
                    f"⏭ Пропущено: <b>{stats['skipped']}</b> вопр.\n"
                    f"📦 Всего вопросов в базе бота: <b>{stats['cached']}</b> вопр.\n"
                    f"🏷 Текущая тема: <b>{cat}</b>\n\n"
                    f"<i>Все показанные вопросы сохранены в базе SQLite и не повторяются.</i>"
                ),
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
    elif text == "🔄 Сбросить память":
        reset_user_memory(user_id)
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "♻️ <b>Память очищена!</b>\nТеперь все вопросы снова доступны для показа.",
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )
    else:
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Нажми <b>«🎲 Вопрос»</b> на клавиатуре внизу, чтобы получить интересный вопрос 👇",
                "parse_mode": "HTML",
                "reply_markup": get_main_reply_keyboard(),
            },
        )


def handle_callback(callback: Dict[str, Any]) -> None:
    cb_id = callback["id"]
    user_id = callback["from"]["id"]
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id", user_id)
    message_id = message.get("message_id")
    data = callback.get("data", "")

    if data == "next_question":
        tg_request("answerCallbackQuery", {"callback_query_id": cb_id})
        send_or_update_question(user_id, chat_id, skipped=False)
    elif data == "skip_question":
        tg_request("answerCallbackQuery", {"callback_query_id": cb_id, "text": "Вопрос пропущен ⏭"})
        send_or_update_question(user_id, chat_id, skipped=True, edit_message_id=message_id)
    elif data == "force_search":
        tg_request("answerCallbackQuery", {"callback_query_id": cb_id, "text": "Запускаю поиск в сети 🔎"})
        send_or_update_question(user_id, chat_id, skipped=False, force_web=True)


def start_healthcheck_server_if_needed() -> None:
    """Если переменная PORT задана (например, на облачных хостингах Render/Koyeb), поднимает мини HTTP-сервер."""
    port_str = os.environ.get("PORT")
    if not port_str:
        return

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - Question Bot is running")

        def log_message(self, format: str, *args: Any) -> None:
            return

    def _serve() -> None:
        server = HTTPServer(("0.0.0.0", int(port_str)), HealthHandler)
        logging.info(f"Health-check HTTP сервер запущен на порту {port_str}")
        server.serve_forever()

    threading.Thread(target=_serve, daemon=True).start()


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
        logging.error("Не указан BOT_TOKEN в .env или переменных окружения!")
        return

    init_db()
    save_cached_questions(SEED_QUESTIONS)
    start_healthcheck_server_if_needed()

    logging.info("Подключение к Telegram Bot API...")
    while True:
        me = tg_request("getMe", timeout=10)
        if me.get("ok"):
            bot_info = me["result"]
            logging.info(f"Бот @{bot_info.get('username')} успешно запущен и готов к работе!")
            break
        logging.warning(
            "Не удалось достучаться до api.telegram.org (возможно, нужен включенный VPN/прокси). "
            "Повторная попытка через 5 секунд..."
        )
        time.sleep(5)

    background_replenish("all")

    offset = 0
    while True:
        try:
            updates_resp = tg_request(
                "getUpdates",
                {"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]},
                timeout=35,
            )
            if not updates_resp.get("ok"):
                time.sleep(3)
                continue

            for update in updates_resp.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
        except KeyboardInterrupt:
            logging.info("Бот остановлен пользователем.")
            break
        except Exception as e:
            logging.error(f"Ошибка в цикле опроса: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
