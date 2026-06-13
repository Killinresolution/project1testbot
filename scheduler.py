"""
APScheduler: уведомления о дедлайнах + вопрос конца смены (03:00 МСК).
"""
import html
import logging
from datetime import datetime, timedelta, date
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
import database as db
import config
from handlers.schedule_h import is_work_day, is_work_day_for_user, get_shift_bounds_utc

MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

logger = logging.getLogger(__name__)

MSK = pytz.timezone(config.MSK_TZ)


# ─── Напоминания о дедлайнах ──────────────────────────────────────────────────

async def check_deadlines(app: Application):
    """Запускается каждые 5 минут. Шлёт напоминание за 1ч и за 15 минут."""
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    tasks = db.get_all_active_tasks()

    for task in tasks:
        try:
            deadline = datetime.fromisoformat(task["deadline"])
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=pytz.utc)

            delta = (deadline - now_utc).total_seconds()

            # За 1 час (от 65 до 55 минут до дедлайна)
            if 3300 < delta <= 3900 and not task["reminded_1h"]:
                await _send_reminder(app, task, "1h", deadline)
                db.mark_reminded(task["id"], "1h")

            # За 15 минут (от 20 до 10 минут до дедлайна)
            elif 600 < delta <= 1200 and not task["reminded_15m"]:
                await _send_reminder(app, task, "15m", deadline)
                db.mark_reminded(task["id"], "15m")

        except Exception as e:
            logger.warning(f"check_deadlines task {task['id']}: {e}")


async def _send_reminder(app: Application, task, kind: str, deadline: datetime):
    user = db.get_user(task["user_id"])
    if not user:
        return
    tz = pytz.timezone(user["timezone"])
    deadline_local = deadline.astimezone(tz).strftime("%d.%m.%Y %H:%M")

    emoji = "⏰" if kind == "1h" else "🔔"
    time_label = "1 час" if kind == "1h" else "15 минут"

    text = (
        f"{emoji} <b>Напоминание!</b>\n\n"
        f"До дедлайна задачи «<b>{html.escape(task['title'])}</b>» осталось <b>{time_label}</b>.\n"
        f"📅 Дедлайн: {deadline_local}"
    )
    try:
        await app.bot.send_message(
            chat_id=task["user_id"], text=text, parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить напоминание {task['user_id']}: {e}")


# ─── Вопрос конца смены ───────────────────────────────────────────────────────

async def end_of_shift_check(app: Application):
    """
    Запускается каждые 5 минут.
    Если текущее время МСК от 03:00 до 03:10 И сегодня рабочий день →
    задаём вопрос по задачам смены.
    """
    now_msk = datetime.now(MSK)

    # Окно: 03:00–03:10 МСК
    if not (3 == now_msk.hour and 0 <= now_msk.minute < 10):
        return

    # Смена относится ко вчерашнему дню (смена 15:00 вчера → 03:00 сегодня)
    shift_date = (now_msk - timedelta(hours=3)).date()

    users = db.get_all_users()
    for user in users:
        try:
            start_date = date.fromisoformat(user["schedule_start_date"])
            if not is_work_day_for_user(user["user_id"], shift_date, start_date):
                continue

            shift_date_str = shift_date.isoformat()
            if db.is_eod_asked(user["user_id"], shift_date_str):
                continue

            shift_start, shift_end = get_shift_bounds_utc(shift_date)
            tasks = db.get_tasks_for_shift(user["user_id"], shift_start, shift_end)

            if not tasks:
                db.mark_eod_asked(user["user_id"], shift_date_str)
                continue

            await app.bot.send_message(
                chat_id=user["user_id"],
                text=(
                    "🌙 <b>Конец смены!</b>\n\n"
                    "Отметь статус задач этой смены:"
                ),
                parse_mode="HTML",
            )

            for task in tasks:
                buttons = [
                    [
                        InlineKeyboardButton(
                            "✅ Выполнена", callback_data=f"eod_yes:{task['id']}"
                        ),
                        InlineKeyboardButton(
                            "❌ Не выполнена", callback_data=f"eod_no:{task['id']}"
                        ),
                    ]
                ]
                await app.bot.send_message(
                    chat_id=user["user_id"],
                    text=f"📝 <b>{html.escape(task['title'])}</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

            db.mark_eod_asked(user["user_id"], shift_date_str)

        except Exception as e:
            logger.warning(f"end_of_shift user {user['user_id']}: {e}")


# ─── Ежемесячное напоминание (1-е число) ─────────────────────────────────────

async def monthly_schedule_reminder(app: Application):
    """1-го числа в 12:00 МСК — предложить настроить смены на новый месяц."""
    today = date.today()
    year, month = today.year, today.month
    month_name = MONTH_NAMES[month - 1]

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📅 Настроить смены",
            callback_data=f"se_open_{year}_{month:02d}",
        )
    ]])

    users = db.get_all_users()
    for user in users:
        try:
            await app.bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"🗓 <b>Новый месяц — {month_name} {year}!</b>\n\n"
                    "Не забудь настроить расписание рабочих смен.\n"
                    "Нажми кнопку ниже или используй /editschedule"
                ),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning(f"monthly_reminder user {user['user_id']}: {e}")


# ─── Инициализация планировщика ───────────────────────────────────────────────

def create_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=MSK)

    # Каждые 5 минут — проверка дедлайнов
    scheduler.add_job(
        check_deadlines,
        trigger="interval",
        minutes=5,
        args=[app],
        id="deadline_check",
        replace_existing=True,
    )

    # Каждые 5 минут — проверка конца смены
    scheduler.add_job(
        end_of_shift_check,
        trigger="interval",
        minutes=5,
        args=[app],
        id="eod_check",
        replace_existing=True,
    )

    # 1-го числа каждого месяца в 12:00 МСК — напоминание о расписании
    scheduler.add_job(
        monthly_schedule_reminder,
        trigger="cron",
        day=1,
        hour=12,
        minute=0,
        args=[app],
        id="monthly_schedule",
        replace_existing=True,
    )

    return scheduler
