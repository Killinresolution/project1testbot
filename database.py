import sqlite3
import calendar as _cal_mod
from contextlib import contextmanager
from datetime import datetime, date
from typing import Optional
import config

@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id             INTEGER PRIMARY KEY,
                username            TEXT,
                timezone            TEXT    NOT NULL DEFAULT 'Europe/Moscow',
                schedule_start_date TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                title        TEXT    NOT NULL,
                deadline     TEXT    NOT NULL,
                period       TEXT    NOT NULL DEFAULT 'day',
                is_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                reminded_1h  INTEGER NOT NULL DEFAULT 0,
                reminded_15m INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS shift_log (
                user_id    INTEGER NOT NULL,
                shift_date TEXT    NOT NULL,
                eod_asked  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, shift_date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS custom_shifts (
                user_id    INTEGER NOT NULL,
                shift_date TEXT    NOT NULL,
                is_working INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, shift_date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)


# ─── Users ────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, timezone: str, schedule_start_date: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, timezone, schedule_start_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username            = excluded.username,
                timezone            = excluded.timezone,
                schedule_start_date = excluded.schedule_start_date
        """, (user_id, username, timezone, schedule_start_date))


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def get_all_users() -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users").fetchall()


def update_user_timezone(user_id: int, timezone: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET timezone = ? WHERE user_id = ?", (timezone, user_id)
        )


# ─── Tasks ────────────────────────────────────────────────────────────────────

def add_task(user_id: int, title: str, deadline: str, period: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO tasks (user_id, title, deadline, period)
            VALUES (?, ?, ?, ?)
        """, (user_id, title, deadline, period))
        return cur.lastrowid


def get_active_tasks(user_id: int) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM tasks
            WHERE user_id = ? AND is_completed = 0
            ORDER BY deadline ASC
        """, (user_id,)).fetchall()


def get_all_active_tasks() -> list:
    """Все невыполненные задачи по всем пользователям (для планировщика)."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT t.*, u.timezone FROM tasks t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.is_completed = 0
            ORDER BY t.deadline ASC
        """).fetchall()


def get_tasks_for_period(user_id: int, start: datetime, end: datetime) -> list:
    """
    Возвращает задачи, у которых дедлайн попадает в период,
    ИЛИ которые были выполнены в этот период (даже если дедлайн вне него).
    """
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM tasks
            WHERE user_id = ?
              AND (
                deadline BETWEEN ? AND ?
                OR (is_completed = 1 AND completed_at BETWEEN ? AND ?)
              )
            ORDER BY deadline ASC
        """, (
            user_id,
            start.isoformat(), end.isoformat(),
            start.isoformat(), end.isoformat(),
        )).fetchall()


def get_tasks_for_shift(user_id: int, shift_start: datetime, shift_end: datetime) -> list:
    """Задачи с дедлайном в текущую смену (невыполненные)."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM tasks
            WHERE user_id = ?
              AND is_completed = 0
              AND deadline BETWEEN ? AND ?
        """, (user_id, shift_start.isoformat(), shift_end.isoformat())).fetchall()


def complete_task(task_id: int):
    with get_conn() as conn:
        conn.execute("""
            UPDATE tasks SET is_completed = 1, completed_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), task_id))


def get_task_by_id(task_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def mark_reminded(task_id: int, kind: str):
    """kind: '1h' или '15m'"""
    col = "reminded_1h" if kind == "1h" else "reminded_15m"
    with get_conn() as conn:
        conn.execute(f"UPDATE tasks SET {col} = 1 WHERE id = ?", (task_id,))


# ─── Shift log ────────────────────────────────────────────────────────────────

def is_eod_asked(user_id: int, shift_date: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT eod_asked FROM shift_log
            WHERE user_id = ? AND shift_date = ?
        """, (user_id, shift_date)).fetchone()
        return bool(row and row["eod_asked"])


def mark_eod_asked(user_id: int, shift_date: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO shift_log (user_id, shift_date, eod_asked)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, shift_date) DO UPDATE SET eod_asked = 1
        """, (user_id, shift_date))


# ─── Custom shifts ────────────────────────────────────────────────────────────

def get_custom_shifts_for_month(user_id: int, year: int, month: int) -> dict:
    """Возвращает {date_iso: is_working} для месяца. Пустой dict если нет данных."""
    last_day = _cal_mod.monthrange(year, month)[1]
    first = date(year, month, 1).isoformat()
    last  = date(year, month, last_day).isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT shift_date, is_working FROM custom_shifts
            WHERE user_id = ? AND shift_date BETWEEN ? AND ?
        """, (user_id, first, last)).fetchall()
    return {r["shift_date"]: bool(r["is_working"]) for r in rows}


def set_custom_shifts(user_id: int, shifts: dict):
    """Сохраняет {date_iso: is_working} в таблицу custom_shifts."""
    with get_conn() as conn:
        for date_iso, is_working in shifts.items():
            conn.execute("""
                INSERT INTO custom_shifts (user_id, shift_date, is_working)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, shift_date) DO UPDATE SET
                    is_working = excluded.is_working
            """, (user_id, date_iso, 1 if is_working else 0))


def has_any_custom_shifts(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM custom_shifts WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
    return row is not None


def is_custom_work_day(user_id: int, target_date: date) -> Optional[bool]:
    """True/False если задан кастомный день, None если использовать 3/3."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT is_working FROM custom_shifts
            WHERE user_id = ? AND shift_date = ?
        """, (user_id, target_date.isoformat())).fetchone()
    return bool(row["is_working"]) if row is not None else None
