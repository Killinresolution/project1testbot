# EzraTest1Bot — Telegram-бот для планирования рабочего дня

Бот помогает планировать рабочие смены по графику 3/3 (15:00–03:00 МСК),
управлять задачами с дедлайнами и получать напоминания.

## Функции

- Учёт таймзоны, график работы 3/3 (15:00–03:00 МСК)
- Добавление задач через интерактивный пикер даты и времени
- Напоминания за 1 час и 15 минут до дедлайна
- Отметка выполненных задач прямо из списка (кнопками)
- Редактор графика смен на месяц
- HTML-отчёт о прогрессе за день / неделю / месяц
- Вопрос конца смены в 03:00 МСК о закрытых задачах
- Ежемесячное напоминание о настройке расписания

## Требования

- **Python 3.9+**
- Токен бота от [@BotFather](https://t.me/BotFather)

## Установка

```bash
# 1. Клонировать репозиторий
git clone <url репозитория>
cd "telegramm bot"

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Создать файл .env
cp .env.example .env
# Открыть .env и вставить свой токен
```

## Запуск

### Windows

```bash
python bot.py
```

Или двойным кликом по `start_bot.bat`.

### Linux / сервер

```bash
# Одноразовый запуск в фоне
nohup python bot.py > bot.log 2>&1 &

# Или через systemd (рекомендуется для продакшена)
sudo cp ezrabot.service /etc/systemd/system/
sudo systemctl enable ezrabot
sudo systemctl start ezrabot
sudo systemctl status ezrabot
```

### Railway (облако)

1. Создай новый проект на [railway.app](https://railway.app)
2. Подключи GitHub-репозиторий (или загрузи через Railway CLI)
3. В настройках сервиса выбери тип **Worker** (не Web)
4. Добавь переменную окружения:
   - `BOT_TOKEN` = твой токен от @BotFather
5. Настрой Persistent Volume (чтобы база данных не удалялась при деплое):
   - Dashboard → твой сервис → **Volumes** → Add Volume
   - Mount Path: `/data`
   - Добавь переменную: `DB_PATH` = `/data/ezra_bot.db`
6. Деплой запустится автоматически — Railway найдёт `Procfile` и выполнит `python bot.py`

## Структура файлов

| Файл | Назначение |
|---|---|
| `bot.py` | Точка входа — запускает бота |
| `config.py` | Загрузка токена и настроек из `.env` |
| `database.py` | SQLite: пользователи, задачи, смены |
| `scheduler.py` | APScheduler: напоминания, конец смены, ежемесячный дайджест |
| `handlers/start.py` | `/start`, выбор и смена таймзоны |
| `handlers/tasks.py` | `/addtask`, `/mytasks`, `/done` |
| `handlers/schedule_h.py` | `/schedule` — график смен на 7 дней |
| `handlers/shifts_editor.py` | `/editschedule` — редактор графика на месяц |
| `handlers/report.py` | `/report` — HTML-отчёт |
| `handlers/menu.py` | `/menu` — список команд |
| `templates/report.html` | Jinja2-шаблон HTML-отчёта |
| `.env.example` | Шаблон для создания `.env` |
| `ezrabot.service` | Systemd-сервис для Linux |

## Переменные окружения (`.env`)

```
BOT_TOKEN=ваш_токен_от_botfather
```

Файл `.env` **не загружается на GitHub** — он указан в `.gitignore`.

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Регистрация и выбор таймзоны |
| `/menu` | Список всех команд |
| `/addtask` | Добавить задачу (интерактивный пикер даты/времени) |
| `/mytasks` | Список активных задач с кнопками выполнения |
| `/done <id>` | Отметить задачу выполненной по ID |
| `/schedule` | График смен на 7 дней |
| `/editschedule` | Редактор графика смен на месяц |
| `/report day` | HTML-отчёт за сегодня |
| `/report week` | HTML-отчёт за неделю |
| `/report month` | HTML-отчёт за месяц |
| `/settz` | Сменить таймзону |
