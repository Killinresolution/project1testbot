"""
EzraTest1Bot — точка входа.
Запуск: python bot.py
"""
import asyncio
import logging
from telegram import Update, BotCommand
from telegram.ext import Application, ContextTypes
import config
import database as db
from scheduler import create_scheduler
from handlers import start, tasks, schedule_h, report, shifts_editor, menu

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Логирует все ошибки в хендлерах — без этого ошибки молча глотаются."""
    logger.error("Ошибка при обработке обновления:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text("⚠️ Произошла внутренняя ошибка.")
        except Exception:
            pass


async def run_bot():
    db.init_db()
    logger.info("База данных инициализирована.")

    app = Application.builder().token(config.BOT_TOKEN).build()

    # Error handler — обязательно первым
    app.add_error_handler(error_handler)

    # Регистрируем хендлеры
    for handler in start.get_handlers():
        app.add_handler(handler)
    for handler in tasks.get_handlers():
        app.add_handler(handler)
    for handler in schedule_h.get_handlers():
        app.add_handler(handler)
    for handler in report.get_handlers():
        app.add_handler(handler)
    for handler in shifts_editor.get_handlers():
        app.add_handler(handler)
    for handler in menu.get_handlers():
        app.add_handler(handler)

    scheduler = create_scheduler(app)

    # Один вызов initialize — НЕ используем async with чтобы не дублировать
    await app.initialize()
    await app.bot.set_my_commands([
        BotCommand("addtask",      "Добавить задачу"),
        BotCommand("mytasks",      "Мои задачи"),
        BotCommand("schedule",     "График смен на 7 дней"),
        BotCommand("editschedule", "Редактор графика на месяц"),
        BotCommand("report",       "HTML-отчёт (day/week/month)"),
        BotCommand("settz",        "Сменить таймзону"),
        BotCommand("menu",         "Список команд"),
    ])
    await app.start()
    scheduler.start()
    logger.info("Планировщик запущен.")

    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Бот запущен. Нажми Ctrl+C для остановки.")

    # Ждём вечно (пока не придёт CancelledError от Ctrl+C)
    try:
        await asyncio.Event().wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass

    # Завершение
    logger.info("Остановка бота...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await app.updater.stop()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_bot())
