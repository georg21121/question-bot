import hashlib
import os
import sqlite3
from typing import Dict, List, Optional, Set

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "questions_memory.db")


def normalize_question(text: str) -> str:
    """Нормализует текст вопроса для точного сравнения дубликатов."""
    cleaned = "".join(ch.lower() for ch in text if ch.isalnum() or ch.isspace())
    cleaned = " ".join(cleaned.split())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def init_db() -> None:
    """Создаёт таблицы базы данных для хранения вопросов, памяти и настроек пользователей."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question_hash TEXT NOT NULL,
                question_text TEXT NOT NULL,
                category TEXT,
                status TEXT DEFAULT 'shown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, question_hash)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cached_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_hash TEXT UNIQUE NOT NULL,
                question_text TEXT NOT NULL,
                category TEXT DEFAULT 'all',
                source TEXT DEFAULT 'Интернет 🌐'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                category TEXT DEFAULT 'all',
                last_question_hash TEXT
            )
        """)
        conn.commit()


def get_user_category(user_id: int) -> str:
    """Возвращает выбранную пользователем категорию вопросов."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT category FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row and row[0] else "all"


def set_user_category(user_id: int, category: str) -> None:
    """Сохраняет выбранную пользователем категорию вопросов в БД."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, category)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET category = excluded.category
            """,
            (user_id, category),
        )
        conn.commit()


def mark_last_question_skipped(user_id: int) -> None:
    """Помечает последний показанный пользователю вопрос как пропущенный ('skipped')."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT last_question_hash FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row and row[0]:
            conn.execute(
                "UPDATE seen_questions SET status = 'skipped' WHERE user_id = ? AND question_hash = ?",
                (user_id, row[0]),
            )
            conn.commit()


def is_question_seen(user_id: int, question_text: str) -> bool:
    """Проверяет, видел ли уже пользователь этот вопрос."""
    q_hash = normalize_question(question_text)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT 1 FROM seen_questions WHERE user_id = ? AND question_hash = ?",
            (user_id, q_hash),
        )
        return cur.fetchone() is not None


def get_seen_hashes(user_id: int) -> Set[str]:
    """Возвращает множество хешей всех вопросов, которые уже видел пользователь."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT question_hash FROM seen_questions WHERE user_id = ?",
            (user_id,),
        )
        return {row[0] for row in cur.fetchall()}


def mark_question_seen(
    user_id: int, question_text: str, category: str = "all", status: str = "shown"
) -> None:
    """Записывает вопрос в память пользователя, чтобы он больше не повторялся."""
    q_hash = normalize_question(question_text)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO seen_questions (user_id, question_hash, question_text, category, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, q_hash, question_text, category, status),
        )
        conn.execute(
            """
            INSERT INTO user_settings (user_id, last_question_hash)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_question_hash = excluded.last_question_hash
            """,
            (user_id, q_hash),
        )
        conn.commit()


def save_cached_questions(questions: List[Dict[str, str]]) -> None:
    """Сохраняет найденные в интернете вопросы в общий кэш БД."""
    with sqlite3.connect(DB_PATH) as conn:
        for q in questions:
            q_hash = normalize_question(q["text"])
            conn.execute(
                """
                INSERT OR IGNORE INTO cached_questions (question_hash, question_text, category, source)
                VALUES (?, ?, ?, ?)
                """,
                (
                    q_hash,
                    q["text"],
                    q.get("category", "all"),
                    q.get("source", "Интернет 🌐"),
                ),
            )
        conn.commit()


def get_unseen_cached_question(
    user_id: int, category: str = "all"
) -> Optional[Dict[str, str]]:
    """Достаёт случайный ещё не показанный пользователю вопрос из кэша."""
    with sqlite3.connect(DB_PATH) as conn:
        if category == "all":
            query = """
                SELECT question_text, category, source FROM cached_questions
                WHERE question_hash NOT IN (
                    SELECT question_hash FROM seen_questions WHERE user_id = ?
                )
                ORDER BY RANDOM() LIMIT 1
            """
            params = (user_id,)
        else:
            query = """
                SELECT question_text, category, source FROM cached_questions
                WHERE (category = ? OR category = 'all')
                AND question_hash NOT IN (
                    SELECT question_hash FROM seen_questions WHERE user_id = ?
                )
                ORDER BY RANDOM() LIMIT 1
            """
            params = (category, user_id)

        cur = conn.execute(query, params)
        row = cur.fetchone()
        if row:
            return {"text": row[0], "category": row[1], "source": row[2]}
        return None


def get_user_stats(user_id: int) -> Dict[str, int]:
    """Возвращает подробную статистику просмотренных и пропущенных вопросов."""
    with sqlite3.connect(DB_PATH) as conn:
        seen_count = conn.execute(
            "SELECT COUNT(*) FROM seen_questions WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        skipped_count = conn.execute(
            "SELECT COUNT(*) FROM seen_questions WHERE user_id = ? AND status = 'skipped'",
            (user_id,),
        ).fetchone()[0]
        total_cached = conn.execute(
            "SELECT COUNT(*) FROM cached_questions"
        ).fetchone()[0]

    return {
        "seen": seen_count,
        "skipped": skipped_count,
        "discussed": seen_count - skipped_count,
        "cached": total_cached,
    }


def reset_user_memory(user_id: int) -> None:
    """Очищает историю просмотренных вопросов для пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM seen_questions WHERE user_id = ?", (user_id,))
        conn.execute(
            "UPDATE user_settings SET last_question_hash = NULL WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
