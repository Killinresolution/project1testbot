import os
import tempfile
from datetime import datetime, timedelta
import pytz
from jinja2 import Environment, FileSystemLoader
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import database as db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

PERIOD_LABELS = {
    "day":   "День",
    "week":  "Неделя",
    "month": "Месяц",
}


def _get_range(period: str, now: datetime):
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = (start + timedelta(days=6)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    else:  # month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (start + timedelta(days=32)).replace(day=1)
        end = (next_month - timedelta(seconds=1))
    return start, end


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Сначала выполни /start для регистрации.")
        return

    args = context.args
    period = args[0].lower() if args else "day"
    if period not in ("day", "week", "month"):
        await update.message.reply_text(
            "Укажи период: /report day, /report week или /report month"
        )
        return

    tz = pytz.timezone(user["timezone"])
    now_local = datetime.now(tz)
    start_local, end_local = _get_range(period, now_local)

    # Переводим в UTC для запроса к БД
    start_utc = start_local.astimezone(pytz.utc)
    end_utc   = end_local.astimezone(pytz.utc)

    raw_tasks = db.get_tasks_for_period(user_id, start_utc, end_utc)

    # Готовим данные для шаблона
    tasks_data = []
    done_count = 0
    overdue_count = 0
    now_utc = datetime.now(pytz.utc)

    for t in raw_tasks:
        deadline_dt = datetime.fromisoformat(t["deadline"])
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=pytz.utc)
        deadline_local = deadline_dt.astimezone(tz)

        completed_fmt = None
        if t["completed_at"]:
            completed_dt = datetime.fromisoformat(t["completed_at"])
            if completed_dt.tzinfo is None:
                completed_dt = completed_dt.replace(tzinfo=pytz.utc)
            completed_fmt = completed_dt.astimezone(tz).strftime("%d.%m.%Y %H:%M")

        is_overdue = not t["is_completed"] and deadline_dt < now_utc

        if t["is_completed"]:
            done_count += 1
        if is_overdue:
            overdue_count += 1

        tasks_data.append({
            "id":            t["id"],
            "title":         t["title"],
            "deadline_fmt":  deadline_local.strftime("%d.%m.%Y %H:%M"),
            "period":        t["period"],
            "is_completed":  bool(t["is_completed"]),
            "overdue":       is_overdue,
            "completed_at_fmt": completed_fmt,
        })

    total = len(tasks_data)
    pending_count = total - done_count
    pct = round(done_count / total * 100) if total > 0 else 0

    template = jinja_env.get_template("report.html")
    html_content = template.render(
        period_label  = PERIOD_LABELS[period],
        date_from     = start_local.strftime("%d.%m.%Y"),
        date_to       = end_local.strftime("%d.%m.%Y"),
        username      = user["username"] or str(user_id),
        total         = total,
        done          = done_count,
        pending       = pending_count,
        overdue       = overdue_count,
        pct           = pct,
        tasks         = tasks_data,
        generated_at  = now_local.strftime("%d.%m.%Y %H:%M"),
    )

    # Сохраняем во временный файл и отправляем
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8", prefix="report_"
    ) as f:
        f.write(html_content)
        tmp_path = f.name

    try:
        await update.message.reply_document(
            document=open(tmp_path, "rb"),
            filename=f"report_{period}_{now_local.strftime('%Y%m%d')}.html",
            caption=(
                f"📊 <b>Отчёт за {PERIOD_LABELS[period].lower()}</b>\n"
                f"✅ Выполнено: {done_count}/{total} ({pct}%)\n"
                f"⚠️ Просрочено: {overdue_count}"
            ),
            parse_mode="HTML",
        )
    finally:
        os.unlink(tmp_path)


def get_handlers() -> list:
    return [CommandHandler("report", cmd_report)]
