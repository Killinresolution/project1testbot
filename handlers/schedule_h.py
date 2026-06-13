from datetime import date, timedelta
import pytz
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import database as db
import config


def is_work_day_for_user(user_id: int, target_date: date, start_date: date) -> bool:
    """Проверяет кастомные смены, при отсутствии — график 3/3."""
    custom = db.is_custom_work_day(user_id, target_date)
    if custom is not None:
        return custom
    return is_work_day(target_date, start_date)


def is_work_day(target_date: date, start_date: date) -> bool:
    """Возвращает True, если target_date — рабочий день в графике 3/3."""
    delta = (target_date - start_date).days
    cycle_pos = delta % (config.WORK_DAYS + config.REST_DAYS)
    return 0 <= cycle_pos < config.WORK_DAYS


def get_shift_bounds_utc(shift_date: date):
    """
    Смена: 15:00 МСК shift_date → 03:00 МСК (shift_date + 1).
    Возвращает (start_utc, end_utc) как datetime с UTC.
    """
    from datetime import datetime
    msk = pytz.timezone(config.MSK_TZ)
    shift_start = msk.localize(
        datetime(shift_date.year, shift_date.month, shift_date.day,
                 config.SHIFT_START_HOUR, config.SHIFT_START_MINUTE)
    ).astimezone(pytz.utc)
    next_day = shift_date + timedelta(days=1)
    shift_end = msk.localize(
        datetime(next_day.year, next_day.month, next_day.day,
                 config.SHIFT_END_HOUR, config.SHIFT_END_MINUTE)
    ).astimezone(pytz.utc)
    return shift_start, shift_end


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Сначала выполни /start для регистрации.")
        return

    start_date = date.fromisoformat(user["schedule_start_date"])
    tz_name = user["timezone"]
    tz = pytz.timezone(tz_name)
    today = date.today()

    lines = ["📅 <b>График смен на 7 дней</b>"]
    for i in range(7):
        day = today + timedelta(days=i)
        work = is_work_day_for_user(user_id, day, start_date)
        day_name = _day_name(day.weekday())
        is_today = day == today

        bullet = "👉" if is_today else "▫️"
        date_part = (
            f"<b>{day.strftime('%d.%m')} {day_name}</b>"
            if is_today else
            f"{day.strftime('%d.%m')} {day_name}"
        )

        if work:
            shift_start, shift_end = get_shift_bounds_utc(day)
            start_local = shift_start.astimezone(tz).strftime("%H:%M")
            end_local = shift_end.astimezone(tz).strftime("%H:%M")
            status = f"🟢 Рабочая · ⏰ {start_local}–{end_local}"
        else:
            status = "🔴 Выходной"

        lines.append(f"\n{bullet} {date_part}\n{status}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def _day_name(weekday: int) -> str:
    names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    return names[weekday]


def get_handlers() -> list:
    return [CommandHandler("schedule", cmd_schedule)]
