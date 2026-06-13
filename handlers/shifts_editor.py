"""
Редактор графика смен на месяц.
Команда /editschedule открывает интерактивный календарь с кнопками-переключателями.
"""
import calendar as cal_mod
from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
import database as db
from handlers.schedule_h import is_work_day

MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
DAYS_HEADER = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _draft_key(year: int, month: int) -> str:
    return f"se_draft_{year}_{month}"


def _get_draft(context, user_id: int, year: int, month: int) -> dict:
    """
    Возвращает черновик {date_iso: is_working} для месяца.
    Приоритет: context.user_data → БД → расчёт по 3/3.
    """
    key = _draft_key(year, month)
    if key in context.user_data:
        return context.user_data[key]

    existing = db.get_custom_shifts_for_month(user_id, year, month)
    if existing:
        context.user_data[key] = existing
        return existing

    # Предзаполнение по графику 3/3
    user = db.get_user(user_id)
    start_date = (
        date.fromisoformat(user["schedule_start_date"])
        if user else date.today()
    )
    draft = {}
    last_day = cal_mod.monthrange(year, month)[1]
    for d in range(1, last_day + 1):
        day_date = date(year, month, d)
        draft[day_date.isoformat()] = is_work_day(day_date, start_date)
    context.user_data[key] = draft
    return draft


def _build_keyboard(draft: dict, year: int, month: int) -> InlineKeyboardMarkup:
    rows = []

    # Навигация ◀ Месяц Год ▶
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1

    rows.append([
        InlineKeyboardButton("◀️", callback_data=f"se_n_{py}_{pm:02d}"),
        InlineKeyboardButton(f"{MONTH_NAMES[month-1]} {year}", callback_data="se_x"),
        InlineKeyboardButton("▶️", callback_data=f"se_n_{ny}_{nm:02d}"),
    ])

    # Заголовок дней недели
    rows.append([InlineKeyboardButton(d, callback_data="se_x") for d in DAYS_HEADER])

    # Числа месяца
    for week in cal_mod.monthcalendar(year, month):
        row = []
        for d in week:
            if d == 0:
                row.append(InlineKeyboardButton(" ", callback_data="se_x"))
            else:
                day_iso = date(year, month, d).isoformat()
                working = draft.get(day_iso, False)
                label = f"🟢{d}" if working else f"⬜{d}"
                row.append(InlineKeyboardButton(
                    label, callback_data=f"se_t_{year}{month:02d}{d:02d}"
                ))
        rows.append(row)

    # Кнопка сохранения
    rows.append([
        InlineKeyboardButton("✅ Сохранить", callback_data=f"se_s_{year}_{month:02d}")
    ])

    return InlineKeyboardMarkup(rows)


def _editor_text(year: int, month: int) -> str:
    return (
        f"📅 <b>Редактор смен — {MONTH_NAMES[month-1]} {year}</b>\n\n"
        "🟢 — рабочий день   ⬜ — выходной\n"
        "Нажми на день чтобы переключить, затем <b>✅ Сохранить</b>."
    )


# ─── Команда /editschedule ────────────────────────────────────────────────────

async def cmd_editschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Сначала выполни /start для регистрации.")
        return

    today = date.today()
    year, month = today.year, today.month
    draft = _get_draft(context, user_id, year, month)
    keyboard = _build_keyboard(draft, year, month)

    await update.message.reply_text(
        _editor_text(year, month),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ─── Callback-хендлер ────────────────────────────────────────────────────────

async def callback_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # Нет-оп (заголовок, названия дней)
    if data == "se_x":
        return

    # Открыть редактор из уведомления первого числа
    if data.startswith("se_open_"):
        parts = data[8:].split("_")
        year, month = int(parts[0]), int(parts[1])
        draft = _get_draft(context, user_id, year, month)
        keyboard = _build_keyboard(draft, year, month)
        await query.message.reply_text(
            _editor_text(year, month),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # Переключить день: se_t_YYYYMMDD
    if data.startswith("se_t_"):
        compact = data[5:]
        year  = int(compact[:4])
        month = int(compact[4:6])
        day   = int(compact[6:8])
        day_iso = date(year, month, day).isoformat()
        draft = _get_draft(context, user_id, year, month)
        draft[day_iso] = not draft.get(day_iso, False)
        keyboard = _build_keyboard(draft, year, month)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    # Навигация: se_n_YYYY_MM
    if data.startswith("se_n_"):
        parts = data[5:].split("_")
        year, month = int(parts[0]), int(parts[1])
        draft = _get_draft(context, user_id, year, month)
        keyboard = _build_keyboard(draft, year, month)
        await query.edit_message_text(
            _editor_text(year, month),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # Сохранить: se_s_YYYY_MM
    if data.startswith("se_s_"):
        parts = data[5:].split("_")
        year, month = int(parts[0]), int(parts[1])
        key = _draft_key(year, month)
        draft = context.user_data.get(key, {})

        db.set_custom_shifts(user_id, draft)

        work_days = sum(1 for v in draft.values() if v)
        off_days  = sum(1 for v in draft.values() if not v)

        await query.edit_message_text(
            f"✅ <b>Расписание на {MONTH_NAMES[month-1]} {year} сохранено!</b>\n\n"
            f"🟢 Рабочих дней: <b>{work_days}</b>\n"
            f"⬜ Выходных: <b>{off_days}</b>\n\n"
            "Изменить: /editschedule",
            parse_mode="HTML",
        )
        context.user_data.pop(key, None)
        return


# ─── Регистрация ──────────────────────────────────────────────────────────────

def get_handlers() -> list:
    return [
        CommandHandler("editschedule", cmd_editschedule),
        CallbackQueryHandler(callback_editor, pattern=r"^se_"),
    ]
