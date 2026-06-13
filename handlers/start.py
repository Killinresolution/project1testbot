from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
)
import database as db
from handlers.menu import cmd_menu

# Список таймзон: (label, pytz_name)
TIMEZONES = [
    ("Москва (UTC+3)",          "Europe/Moscow"),
    ("Екатеринбург (UTC+5)",    "Asia/Yekaterinburg"),
    ("Омск (UTC+6)",            "Asia/Omsk"),
    ("Красноярск (UTC+7)",      "Asia/Krasnoyarsk"),
    ("Иркутск (UTC+8)",         "Asia/Irkutsk"),
    ("Якутск (UTC+9)",          "Asia/Yakutsk"),
    ("Владивосток (UTC+10)",    "Asia/Vladivostok"),
    ("Магадан (UTC+11)",        "Asia/Magadan"),
    ("Камчатка (UTC+12)",       "Asia/Kamchatka"),
    ("Калининград (UTC+2)",     "Europe/Kaliningrad"),
    ("Самара (UTC+4)",          "Europe/Samara"),
    ("Лондон (UTC+0)",          "Europe/London"),
    ("Берлин (UTC+1/2)",        "Europe/Berlin"),
    ("Дубай (UTC+4)",           "Asia/Dubai"),
    ("Минск (UTC+3)",           "Europe/Minsk"),
]

SELECT_TZ = 0


def build_tz_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, (label, tz_name) in enumerate(TIMEZONES):
        row.append(InlineKeyboardButton(label, callback_data=f"tz:{tz_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = db.get_user(user.id)

    if existing:
        await update.message.reply_text(
            f"👋 С возвращением, {user.first_name}!\n"
            f"Твоя таймзона: <b>{existing['timezone']}</b>\n\n"
            "Команды:\n"
            "/addtask — добавить задачу\n"
            "/mytasks — мои задачи\n"
            "/schedule — график смен\n"
            "/report day|week|month — HTML-отчёт\n"
            "/settz — сменить таймзону",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"👋 Привет, {user.first_name}! Я EzraTest1Bot.\n\n"
        "Помогу планировать рабочий день, напоминать о задачах и отслеживать прогресс.\n\n"
        "Для начала выбери свою таймзону:",
        reply_markup=build_tz_keyboard(),
    )
    return SELECT_TZ


async def cmd_settz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери новую таймзону:", reply_markup=build_tz_keyboard()
    )
    return SELECT_TZ


async def callback_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tz_name = query.data.replace("tz:", "")
    user = query.from_user
    today = date.today().isoformat()

    db.upsert_user(user.id, user.username or user.first_name, tz_name, today)

    label = next((l for l, t in TIMEZONES if t == tz_name), tz_name)
    await query.edit_message_text(
        f"✅ Таймзона установлена: <b>{label}</b>\n\n"
        f"График работы 3/3 считается от сегодня ({today}).\n"
        f"Смены: 15:00 → 03:00 МСК.\n\n"
        "Команды:\n"
        "/addtask — добавить задачу\n"
        "/mytasks — мои задачи\n"
        "/schedule — график смен на 7 дней\n"
        "/report day|week|month — HTML-отчёт",
        parse_mode="HTML",
    )
    return ConversationHandler.END


def get_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("settz", cmd_settz),
        ],
        states={
            SELECT_TZ: [CallbackQueryHandler(callback_tz, pattern=r"^tz:")],
        },
        fallbacks=[CommandHandler("menu", cmd_menu)],
    )
    return [conv]
