from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

MENU_TEXT = (
    "📋 <b>Доступные команды:</b>\n\n"
    "/addtask — добавить задачу\n"
    "/mytasks — мои задачи\n"
    "/schedule — график смен на 7 дней\n"
    "/editschedule — редактор графика на месяц\n"
    "/report day|week|month — HTML-отчёт\n"
    "/settz — сменить таймзону\n"
    "/menu — это меню"
)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MENU_TEXT, parse_mode="HTML")


def get_handlers() -> list:
    return [CommandHandler("menu", cmd_menu)]
