from html.parser import HTMLParser
import os
import random
import re
import socket
import ssl
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

# Поисковые запросы, ориентированные на Pinterest, TikTok и статьи с вопросами
SEARCH_QUERIES: Dict[str, List[str]] = {
    "couple": [
        "site:pinterest.com вопросы для пар чтобы узнать друг друга лучше",
        "site:pinterest.com глубокие вопросы для парня и девушки",
        "вопросы из тик тока для пар которые сближают список",
        "интересные вопросы для девушки чтобы разговорить",
        "глубокие вопросы для обсуждения с партнером психология",
        "необычные вопросы для свидания чтобы узнать человека",
        "36 вопросов чтобы влюбиться список на русском",
    ],
    "friends": [
        "site:pinterest.com вопросы для друзей на вечеринку",
        "вопросы из тик тока для друзей чтобы узнать правду",
        "интересные вопросы для обсуждения в компании друзей",
        "философские и странные вопросы для друзей на подумать",
        "вопросы с подвохом для обсуждения с друзьями",
        "глубокие вопросы для разговора ночью с друзьями",
    ],
    "all": [
        "site:pinterest.com интересные вопросы для разговора",
        "популярные вопросы из тик тока для обсуждения",
        "100 интересных вопросов чтобы узнать человека",
        "вопросы которые заставят задуматься для компании и пары",
        "глубокие вопросы для разговора по душам",
    ],
}

# Расширенная стартовая база лучших вопросов из трендов Pinterest, TikTok и психологии общения
SEED_QUESTIONS: List[Dict[str, str]] = [
    {"text": "Какое твоё самое тёплое воспоминание из детства, к которому ты мысленно возвращаешься?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Если бы ты мог(ла) прожить один день из своей жизни заново без права что-то менять, какой день ты бы выбрал(а)?", "category": "all", "source": "TikTok 🎵"},
    {"text": "Какую вещь о себе ты долго не мог(ла) принять, но сейчас считаешь своей суперсилой?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Что для тебя является главным признаком того, что человеку действительно можно доверять?", "category": "all", "source": "Pinterest 📌"},
    {"text": "Если бы мы познакомились в совершенно других обстоятельствах, как думаешь, мы бы подружились?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Какое самое спонтанное или безумное решение в жизни принесло тебе лучший результат?", "category": "friends", "source": "Интернет 🌐"},
    {"text": "О чём ты чаще всего думаешь перед сном, когда откладываешь телефон?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Если бы у тебя была возможность задать один вопрос себе из будущего через 10 лет, что бы ты спросил(а)?", "category": "all", "source": "TikTok 🎵"},
    {"text": "Какой комплимент в своей жизни ты запомнил(а) сильнее всего и почему?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "В какой момент ты впервые почувствовал(а), что мы по-настоящему близкие люди?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Если бы деньги не имели значения, чем бы ты занимался(ась) каждый день?", "category": "friends", "source": "Интернет 🌐"},
    {"text": "Какое непопулярное мнение ты готов(а) защищать в любом споре?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Что в поведении других людей мгновенно отталкивает тебя при первом знакомстве?", "category": "all", "source": "Pinterest 📌"},
    {"text": "Какая песня или фильм лучше всего описывают твоё текущее состояние души?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Если бы ты мог(ла) стереть себе память об одном фильме, книге или событии, чтобы пережить это впервые — что бы это было?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Какое качество в людях ты ценишь больше всего, даже если оно редко встречается?", "category": "all", "source": "Pinterest 📌"},
    {"text": "О каком поступке ты ни капли не жалеешь, хотя окружающие тебя тогда не понимали?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Что для тебя означает идеальный вечер вдвоём без телефонов и суеты?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Какая мелочь способна мгновенно поднять тебе настроение даже в самый тяжёлый день?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Если бы тебе нужно было переехать в любую другую страну завтра утром на год, куда бы ты отправился(ась)?", "category": "friends", "source": "Интернет 🌐"},
    {"text": "Какой совет ты бы дал(а) себе 15-летнему, зная всё то, что знаешь сейчас?", "category": "all", "source": "Pinterest 📌"},
    {"text": "Что ты обычно скрываешь за улыбкой, когда не хочешь никого нагружать своими проблемами?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Какая самая странная привычка есть у тебя, о которой мало кто догадывается?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Веришь ли ты, что случайные встречи в жизни на самом деле не случайны?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Какой момент за последний год заставил тебя смеяться до слёз?", "category": "friends", "source": "Интернет 🌐"},
    {"text": "Что для тебя страшнее: попробовать и потерпеть неудачу или так никогда и не узнать, что могло получиться?", "category": "all", "source": "Pinterest 📌"},
    {"text": "Какое первое впечатление я произвёл(а) на тебя при знакомстве и как оно изменилось?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Если бы твоя жизнь была сериалом, как бы назывался текущий сезон?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "За что в своей жизни ты испытываешь самую большую благодарность прямо сейчас?", "category": "all", "source": "Pinterest 📌"},
    {"text": "О какой мечте ты почти никому не рассказываешь, чтобы не сглазить?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Если бы ты мог(ла) пригласить на ужин любого человека из истории или современности, кто бы это был?", "category": "all", "source": "Pinterest 📌"},
    {"text": "Хотел(а) бы ты стать знаменитым(ой), и если да — то в какой сфере?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Прежде чем сделать важный телефонный звонок, проговариваешь ли ты заранее то, что собираешься сказать?", "category": "all", "source": "Интернет 🌐"},
    {"text": "Если бы ты мог(ла) дожить до 90 лет и сохранить либо разум, либо тело 30-летнего на последние 60 лет жизни — что бы ты выбрал(а)?", "category": "friends", "source": "Pinterest 📌"},
    {"text": "Если бы ты мог(ла) изменить что-то одно в том, как тебя воспитывали, что бы это было?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Если бы завтра ты проснулся(ась) с каким-то новым умением или способностью, что бы ты выбрал(а)?", "category": "all", "source": "TikTok 🎵"},
    {"text": "Если бы магический кристалл мог открыть тебе правду о тебе, твоей жизни или будущем — что бы ты хотел(а) узнать?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Есть ли что-то, о чём ты мечтаешь уже очень давно, но всё ещё не решился(ась) это сделать, и почему?", "category": "all", "source": "TikTok 🎵"},
    {"text": "Какое самое большое достижение в твоей жизни на сегодняшний день вызывает у тебя гордость?", "category": "friends", "source": "Интернет 🌐"},
    {"text": "Что для тебя самое ценное в дружбе, без чего она сразу теряет смысл?", "category": "friends", "source": "Pinterest 📌"},
    {"text": "Какое твоё самое страшное или тревожное воспоминание, которым ты готов(а) поделиться?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Если бы ты знал(а), что через год мир полностью изменится, как бы ты провёл(а) следующие 12 месяцев?", "category": "friends", "source": "TikTok 🎵"},
    {"text": "Насколько тёплыми и близкими были отношения в твоей семье в детстве?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Как ты относишься к своим отношениям с мамой и папой сейчас, во взрослом возрасте?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Когда ты в последний раз плакал(а) при другом человеке, а когда — в полном одиночестве?", "category": "couple", "source": "TikTok 🎵"},
    {"text": "Над чем, по-твоему, слишком серьёзно, чтобы вообще когда-либо шутить?", "category": "friends", "source": "Интернет 🌐"},
    {"text": "Если бы твой дом загорелся, и все близкие и питомцы уже были в безопасности, какую одну вещь ты бы спас(ла)?", "category": "all", "source": "Pinterest 📌"},
    {"text": "Какой человек в твоей жизни повлиял на формирование твоего характера сильнее всего?", "category": "all", "source": "TikTok 🎵"},
    {"text": "В какой момент жизни ты чувствовал(а) себя максимально свободным(ой) и счастливым(ой)?", "category": "couple", "source": "Pinterest 📌"},
    {"text": "Какая привычка или черта в партнёре способна влюбить тебя с первого взгляда?", "category": "couple", "source": "TikTok 🎵"},
]

STOP_PATTERNS = [
    r"как скачат", r"регистрац", r"парол", r"купит", r"цена", r"стоимост",
    r"подписат", r"комментар", r"лайк", r"реклам", r"cookies", r"политик",
    r"что такое", r"как сделат", r"где найти", r"почему не работает",
    r"сколько стоит", r"кто такой", r"какой сайт", r"зачем нужен бот",
]


class TextAndLinksParser(HTMLParser):
    """Извлекает текстовые блоки и ссылки из HTML без сторонних библиотек."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: List[str] = []
        self.links: List[str] = []
        self._current_text: List[str] = []
        self._in_ignored = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "noscript", "head", "nav", "footer"):
            self._in_ignored = True
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "head", "nav", "footer"):
            self._in_ignored = False
        if tag in ("p", "li", "h2", "h3", "h4", "blockquote", "div", "span", "br"):
            chunk = " ".join(self._current_text).strip()
            if chunk:
                self.blocks.append(chunk)
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if not self._in_ignored:
            cleaned = data.strip()
            if cleaned:
                self._current_text.append(cleaned)


def detect_source_label(url_or_query: str) -> str:
    lower = url_or_query.lower()
    if "pinterest" in lower or "pin.it" in lower:
        return "Pinterest 📌"
    if "tiktok" in lower or "тик ток" in lower or "тикток" in lower:
        return "TikTok 🎵"
    return "Интернет 🌐"


def clean_and_validate_question(raw_text: str) -> Optional[str]:
    """Очищает строку и проверяет, является ли она качественным вопросом для обсуждения."""
    text = re.sub(r"^[\s\d\.\)\-\•\—\*✨💬❓📌«»\"]+", "", raw_text).strip()
    text = re.sub(r"[\s«»\"]+$", "", text)
    text = re.sub(r"\s+", " ", text)

    if not text.endswith("?"):
        return None

    if len(text) < 25 or len(text) > 220:
        return None

    if not re.search(r"[а-яА-ЯёЁ]", text):
        return None

    lower = text.lower()
    for pattern in STOP_PATTERNS:
        if re.search(pattern, lower):
            return None

    conversational_markers = [
        "ты ", "тебе", "твой", "твоя", "твоё", "твои", "вы ", "вам", "ваш",
        "мы ", "нам ", "жизн", "люб", "друз", "чувств", "мечт", "боишься",
        "считаешь", "думаешь", "выбрал", "хотел", "мог ", "могла", "если бы",
        "какой", "какая", "какое", "о чем", "о чём", "почему", "что для тебя",
    ]
    if not any(marker in lower for marker in conversational_markers):
        return None

    return text[0].upper() + text[1:]


def extract_questions_from_text(text: str) -> List[str]:
    """Извлекает предложения, заканчивающиеся на '?', из любого текста или сниппета."""
    candidates = re.split(r"(?<=\?)\s+|\n+", text)
    valid_questions: List[str] = []
    for candidate in candidates:
        if "?" in candidate:
            parts = re.split(r"(?<=[\.\!])\s+", candidate)
            for part in parts:
                if "?" in part:
                    q_part = part[: part.rfind("?") + 1]
                    cleaned = clean_and_validate_question(q_part)
                    if cleaned:
                        valid_questions.append(cleaned)
    return valid_questions


def _get_proxy_opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)

    env_proxy = (
        os.environ.get("PROXY_URL")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
    )
    if env_proxy:
        proxy_handler = urllib.request.ProxyHandler({"http": env_proxy, "https": env_proxy})
        return urllib.request.build_opener(proxy_handler, https_handler)

    for port in (2080, 10809, 10808, 7890):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                proxy_url = f"http://127.0.0.1:{port}"
                proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
                return urllib.request.build_opener(proxy_handler, https_handler)
        except Exception:
            continue
    return urllib.request.build_opener(https_handler)


def fetch_html(url: str, timeout: int = 7) -> str:
    """Скачивает HTML страницы с помощью встроенного urllib (с поддержкой прокси/VPN)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        },
    )
    opener = _get_proxy_opener()
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
        return raw.decode("utf-8", errors="ignore")


def search_internet_questions(category: str = "all") -> List[Dict[str, str]]:
    """
    Ищет свежие вопросы в интернете через DuckDuckGo HTML (Pinterest, TikTok-подборки, статьи)
    и парсит найденные страницы.
    """
    queries = SEARCH_QUERIES.get(category, SEARCH_QUERIES["all"])
    query = random.choice(queries)
    source_hint = detect_source_label(query)

    discovered: List[Dict[str, str]] = []
    try:
        encoded_q = urllib.parse.quote_plus(query)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}&kl=ru-ru"
        html = fetch_html(search_url, timeout=8)

        parser = TextAndLinksParser()
        parser.feed(html)

        # Извлекаем вопросы прямо из сниппетов поисковой выдачи
        for block in parser.blocks:
            for q_text in extract_questions_from_text(block):
                discovered.append({
                    "text": q_text,
                    "category": category,
                    "source": source_hint,
                })

        # Собираем внешние ссылки для глубокого парсинга статей с вопросами
        external_urls: List[str] = []
        for link in parser.links:
            if "uddg=" in link:
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                if "uddg" in parsed_qs:
                    real_url = parsed_qs["uddg"][0]
                    if real_url.startswith("http") and not any(
                        skip in real_url for skip in ["youtube.com", "duckduckgo.com", "vk.com/video"]
                    ):
                        external_urls.append(real_url)

        random.shuffle(external_urls)
        for target_url in external_urls[:3]:
            try:
                page_html = fetch_html(target_url, timeout=6)
                page_parser = TextAndLinksParser()
                page_parser.feed(page_html)
                page_src = detect_source_label(target_url)
                if page_src == "Интернет 🌐" and source_hint != "Интернет 🌐":
                    page_src = source_hint

                for block in page_parser.blocks:
                    if "?" in block and len(block) < 350:
                        for q_text in extract_questions_from_text(block):
                            discovered.append({
                                "text": q_text,
                                "category": category,
                                "source": page_src,
                            })
            except Exception:
                continue
    except Exception:
        pass

    random.shuffle(discovered)
    return discovered
