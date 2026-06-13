"""
Редактор графика смен на месяц.
Команда /editschedule открывает интерактивный календарь с кнопками-переключателями.
"""
import calendar as cal_mod
from datetime import date, timedelta
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
    Приоритет: context.user_data → (3/3 base + кастомные override из БД).
    Весь месяц всегда предзаполнен по 3/3; кастомные записи из БД
    перекрывают только те дни, которые пользователь менял вручную.
    """
    key = _draft_key(year, month)
    if key in context.user_data:
        return context.user_data[key]

    user = db.get_user(user_id)
    start_date = (
        date.fromisoformat(user["schedule_start_date"])
        if user else date.today()
    )

    # Базовое расписание 3/3 на весь месяц
    last_day = cal_mod.monthrange(year, month)[1]
    draft = {
        date(year, month, d).isoformat(): is_work_day(date(year, month, d), start_date)
        for d in range(1, last_day + 1)
    }

    # Поверх накладываем кастомные дни пользователя (переопределения)
    custom = db.get_custom_shifts_for_month(user_id, year, month)
    draft.update(custom)

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
        await update.message.reply_text(
            "Ты ещё не зарегистрирован. Нажми /start — это займёт 10 секунд 👇",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 Начать", callback_data="go_start"),
            ]]),
        )
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

        # Сохраняем только отклонения от 3/3, чтобы не засорять БД
        user_row = db.get_user(user_id)
        start_date = (
            date.fromisoformat(user_row["schedule_start_date"])
            if user_row else date.today()
        )
        overrides = {
            day_iso: val
            for day_iso, val in draft.items()
            if val != is_work_day(date.fromisoformat(day_iso), start_date)
        }
        db.set_custom_shifts(user_id, overrides)

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


# ─── Week setup (онбординг после выбора таймзоны) ────────────────────────────

_WS_KEY = "ws_week_draft"
_DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _build_week_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = []
    for day_iso in sorted(draft):
        d = date.fromisoformat(day_iso)
        name = _DAYS_RU[d.weekday()]
        icon = "🟢" if draft[day_iso] else "⬜"
        label = f"{icon} {d.strftime('%d.%m')} {name}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ws_t_{day_iso}")])
    rows.append([
        InlineKeyboardButton("✅ Сохранить", callback_data="ws_save"),
        InlineKeyboardButton("⏭ Пропустить", callback_data="ws_skip"),
    ])
    return InlineKeyboardMarkup(rows)


async def show_week_setup(chat_id: int, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Отправляет mini-форму настройки смен на ближайшие 7 дней."""
    today = date.today()
    user = db.get_user(user_id)
    start_date = date.fromisoformat(user["schedule_start_date"]) if user else today

    draft = {
        (today + timedelta(days=i)).isoformat(): is_work_day(today + timedelta(days=i), start_date)
        for i in range(7)
    }
    context.user_data[_WS_KEY] = draft

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "📅 <b>Настрой график на ближайшую неделю</b>\n\n"
            "🟢 — рабочая смена   ⬜ — выходной\n"
            "Нажми на день чтобы переключить, затем <b>✅ Сохранить</b>.\n\n"
            "Нажми <b>⏭ Пропустить</b> — буду считать по графику 3/3 автоматически."
        ),
        reply_markup=_build_week_keyboard(draft),
        parse_mode="HTML",
    )


def _rebuild_week_draft(user_id: int) -> dict:
    """Пересобирает 7-дневный черновик из 3/3, если user_data был потерян."""
    today = date.today()
    user_row = db.get_user(user_id)
    start_date = (
        date.fromisoformat(user_row["schedule_start_date"])
        if user_row else today
    )
    return {
        (today + timedelta(days=i)).isoformat(): is_work_day(today + timedelta(days=i), start_date)
        for i in range(7)
    }


async def callback_week_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("ws_t_"):
        day_iso = data[5:]
        # Если черновик потерялся (перезапуск бота) — пересобираем из 3/3
        if _WS_KEY not in context.user_data:
            context.user_data[_WS_KEY] = _rebuild_week_draft(user_id)
        draft = context.user_data[_WS_KEY]
        draft[day_iso] = not draft.get(day_iso, False)
        await query.edit_message_reply_markup(reply_markup=_build_week_keyboard(draft))
        return

    if data == "ws_save":
        # Если черновик потерялся — пересобираем из 3/3 (сохранять нечего, только считаем)
        draft = context.user_data.pop(_WS_KEY, None)
        user_row = db.get_user(user_id)

        if not user_row:
            await query.edit_message_text(
                "⚠️ Сессия устарела. Пожалуйста, выполни /start заново.",
            )
            return

        start_date = date.fromisoformat(user_row["schedule_start_date"])

        if draft is None:
            draft = _rebuild_week_draft(user_id)

        # Сохраняем только отклонения от 3/3
        overrides = {
            day_iso: val
            for day_iso, val in draft.items()
            if val != is_work_day(date.fromisoformat(day_iso), start_date)
        }
        if overrides:
            db.set_custom_shifts(user_id, overrides)

        work = sum(1 for v in draft.values() if v)
        off = len(draft) - work
        await query.edit_message_text(
            f"✅ <b>График на неделю сохранён!</b>\n\n"
            f"🟢 Рабочих: <b>{work}</b>   ⬜ Выходных: <b>{off}</b>\n\n"
            "Команды:\n"
            "/schedule — график смен\n"
            "/editschedule — редактировать расписание\n"
            "/addtask — добавить задачу\n"
            "/mytasks — мои задачи\n"
            "/report day|week|month — HTML-отчёт",
            parse_mode="HTML",
        )
        return

    if data == "ws_skip":
        context.user_data.pop(_WS_KEY, None)
        await query.edit_message_text(
            "Хорошо! Буду автоматически считать по графику 3/3 🔄\n\n"
            "Команды:\n"
            "/schedule — график смен\n"
            "/editschedule — настроить расписание вручную\n"
            "/addtask — добавить задачу\n"
            "/mytasks — мои задачи\n"
            "/report day|week|month — HTML-отчёт",
            parse_mode="HTML",
        )
        return


async def _callback_go_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from handlers.start import build_tz_keyboard
    await query.edit_message_text(
        "Выбери свою таймзону:",
        reply_markup=build_tz_keyboard(),
    )


# ─── Регистрация ──────────────────────────────────────────────────────────────

def get_handlers() -> list:
    return [
        CommandHandler("editschedule", cmd_editschedule),
        CallbackQueryHandler(callback_editor, pattern=r"^se_"),
        CallbackQueryHandler(callback_week_setup, pattern=r"^ws_"),
        CallbackQueryHandler(_callback_go_start, pattern=r"^go_start$"),
    ]
