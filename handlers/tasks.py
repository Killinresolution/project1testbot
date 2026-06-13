import html
from datetime import datetime, date, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
import database as db
from handlers.menu import cmd_menu

# ConversationHandler states
ASK_TITLE, ASK_DATE, ASK_HOUR, ASK_MINUTE = range(4)

DEADLINE_FORMAT = "%d.%m.%Y %H:%M"


def _auto_period(deadline_utc: datetime, tz_name: str) -> str:
    tz = pytz.timezone(tz_name)
    deadline_local = deadline_utc.astimezone(tz).date()
    today = datetime.now(tz).date()
    if deadline_local <= today:
        return "day"
    if deadline_local <= today + timedelta(days=7):
        return "week"
    return "month"


def _fmt_deadline(deadline_iso: str, tz_name: str) -> str:
    try:
        dt = datetime.fromisoformat(deadline_iso)
        tz = pytz.timezone(tz_name)
        dt_local = dt.replace(tzinfo=pytz.utc).astimezone(tz)
        return dt_local.strftime(DEADLINE_FORMAT)
    except Exception:
        return deadline_iso


def _date_keyboard(tz) -> InlineKeyboardMarkup:
    today = datetime.now(tz).date()
    options = [
        ("Сегодня",   0), ("Завтра",    1),
        ("+2 дня",    2), ("+3 дня",    3),
        ("+5 дней",   5), ("+7 дней",   7),
        ("+14 дней", 14), ("+30 дней", 30),
    ]
    buttons = []
    row = []
    for label, delta in options:
        d = today + timedelta(days=delta)
        row.append(InlineKeyboardButton(
            f"{label}  {d.strftime('%d.%m')}",
            callback_data=f"dt_date:{d.isoformat()}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def _hour_keyboard() -> InlineKeyboardMarkup:
    buttons, row = [], []
    for h in range(24):
        row.append(InlineKeyboardButton(f"{h:02d}", callback_data=f"dt_hour:{h:02d}"))
        if len(row) == 6:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)


def _minute_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(":00", callback_data="dt_min:00"),
        InlineKeyboardButton(":15", callback_data="dt_min:15"),
        InlineKeyboardButton(":30", callback_data="dt_min:30"),
        InlineKeyboardButton(":45", callback_data="dt_min:45"),
    ]])


# ─── /addtask ─────────────────────────────────────────────────────────────────

async def cmd_addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Сначала выполни /start для регистрации."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 <b>Новая задача</b>\n\nВведи название задачи:",
        parse_mode="HTML",
    )
    return ASK_TITLE


async def got_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task_title"] = update.message.text.strip()
    user = db.get_user(update.effective_user.id)
    tz_name = user["timezone"] if user else "Europe/Moscow"
    tz = pytz.timezone(tz_name)
    await update.message.reply_text(
        "📅 <b>Выбери дату дедлайна:</b>",
        parse_mode="HTML",
        reply_markup=_date_keyboard(tz),
    )
    return ASK_DATE


async def got_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["task_date"] = query.data.replace("dt_date:", "")
    d = date.fromisoformat(context.user_data["task_date"])
    await query.edit_message_text(
        f"📅 Дата: <b>{d.strftime('%d.%m.%Y')}</b>\n\n"
        "🕐 <b>Выбери час:</b>",
        parse_mode="HTML",
        reply_markup=_hour_keyboard(),
    )
    return ASK_HOUR


async def got_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["task_hour"] = query.data.replace("dt_hour:", "")
    d = date.fromisoformat(context.user_data["task_date"])
    h = context.user_data["task_hour"]
    await query.edit_message_text(
        f"📅 Дата: <b>{d.strftime('%d.%m.%Y')}</b>\n"
        f"🕐 Час: <b>{h}:??</b>\n\n"
        "⏱ <b>Выбери минуты:</b>",
        parse_mode="HTML",
        reply_markup=_minute_keyboard(),
    )
    return ASK_MINUTE


async def got_minute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = db.get_user(user_id)
    tz_name = user["timezone"] if user else "Europe/Moscow"
    tz = pytz.timezone(tz_name)

    d = date.fromisoformat(context.user_data["task_date"])
    h = int(context.user_data["task_hour"])
    m = int(query.data.replace("dt_min:", ""))
    title = context.user_data.get("task_title", "Без названия")

    dt_local = datetime(d.year, d.month, d.day, h, m)
    dt_utc = tz.localize(dt_local).astimezone(pytz.utc)
    deadline_iso = dt_utc.isoformat()
    period = _auto_period(dt_utc, tz_name)

    task_id = db.add_task(user_id, title, deadline_iso, period)
    deadline_fmt = dt_local.strftime(DEADLINE_FORMAT)

    context.user_data.clear()
    await query.edit_message_text(
        f"✅ Задача добавлена!\n\n"
        f"🆔 ID: <b>{task_id}</b>\n"
        f"📝 Название: <b>{html.escape(title)}</b>\n"
        f"📅 Дедлайн: <b>{deadline_fmt}</b>",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel_addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Добавление задачи отменено.")
    return ConversationHandler.END


# ─── /mytasks ─────────────────────────────────────────────────────────────────

def _build_tasks_message(tasks: list, tz_name: str) -> tuple[str, InlineKeyboardMarkup]:
    """Возвращает (текст, клавиатура) для списка активных задач."""
    lines = ["📋 <b>Активные задачи:</b>\n"]
    buttons = []
    for t in tasks:
        deadline_fmt = _fmt_deadline(t["deadline"], tz_name)
        lines.append(
            f"🆔 <b>{t['id']}</b> — {html.escape(t['title'])}\n"
            f"   📅 {deadline_fmt}"
        )
        label = t["title"][:22] + "…" if len(t["title"]) > 22 else t["title"]
        buttons.append([InlineKeyboardButton(
            f"☑️ {label}", callback_data=f"task_done:{t['id']}"
        )])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Сначала выполни /start для регистрации.")
        return

    tasks = db.get_active_tasks(user_id)
    if not tasks:
        await update.message.reply_text("✅ Активных задач нет!")
        return

    text, keyboard = _build_tasks_message(tasks, user["timezone"])
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def callback_task_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    task_id = int(query.data.replace("task_done:", ""))

    task = db.get_task_by_id(task_id)
    if not task or task["user_id"] != user_id:
        await query.answer("❌ Задача не найдена.", show_alert=True)
        return
    if task["is_completed"]:
        await query.answer("ℹ️ Уже выполнена.", show_alert=True)
        return

    db.complete_task(task_id)
    await query.answer(f"✅ «{task['title'][:30]}» выполнена!")

    user = db.get_user(user_id)
    tz_name = user["timezone"] if user else "Europe/Moscow"
    remaining = db.get_active_tasks(user_id)

    if not remaining:
        await query.edit_message_text("✅ Все задачи выполнены!")
        return

    text, keyboard = _build_tasks_message(remaining, tz_name)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


# ─── /done ────────────────────────────────────────────────────────────────────

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Укажи ID задачи: /done <номер>\n\nСписок задач: /mytasks"
        )
        return

    task_id = int(args[0])
    task = db.get_task_by_id(task_id)

    if not task:
        await update.message.reply_text(f"❌ Задача #{task_id} не найдена.")
        return

    if task["user_id"] != user_id:
        await update.message.reply_text("❌ Это не твоя задача.")
        return

    if task["is_completed"]:
        await update.message.reply_text(f"ℹ️ Задача #{task_id} уже выполнена.")
        return

    db.complete_task(task_id)
    await update.message.reply_text(
        f"✅ Задача <b>#{task_id} — {html.escape(task['title'])}</b> отмечена выполненной!",
        parse_mode="HTML",
    )


# ─── Callback: ответ на вопрос конца смены ────────────────────────────────────

async def callback_eod_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # eod_yes:<task_id> или eod_no:<task_id>
    parts = data.split(":")
    action, task_id_str = parts[0], parts[1]
    task_id = int(task_id_str)

    task = db.get_task_by_id(task_id)
    if not task:
        await query.edit_message_text("❌ Задача не найдена.")
        return

    if action == "eod_yes":
        db.complete_task(task_id)
        await query.edit_message_text(
            f"✅ Задача <b>{html.escape(task['title'])}</b> отмечена выполненной!",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            f"📌 Задача <b>{html.escape(task['title'])}</b> перенесена — не забудь закрыть её позже!",
            parse_mode="HTML",
        )


def get_handlers() -> list:
    addtask_conv = ConversationHandler(
        entry_points=[CommandHandler("addtask", cmd_addtask)],
        states={
            ASK_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_title)],
            ASK_DATE:   [CallbackQueryHandler(got_date,   pattern=r"^dt_date:")],
            ASK_HOUR:   [CallbackQueryHandler(got_hour,   pattern=r"^dt_hour:")],
            ASK_MINUTE: [CallbackQueryHandler(got_minute, pattern=r"^dt_min:")],
        },
        fallbacks=[CommandHandler("cancel", cancel_addtask), CommandHandler("menu", cmd_menu)],
    )
    return [
        addtask_conv,
        CommandHandler("mytasks", cmd_mytasks),
        CommandHandler("done", cmd_done),
        CallbackQueryHandler(callback_task_done, pattern=r"^task_done:\d+$"),
        CallbackQueryHandler(callback_eod_answer, pattern=r"^eod_(yes|no):"),
    ]
