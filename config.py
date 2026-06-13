import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN не задан. "
        "Локально: создай файл .env и добавь BOT_TOKEN=твой_токен. "
        "На Railway: добавь переменную BOT_TOKEN в разделе Variables."
    )

# Часовой пояс МСК для планировщика
MSK_TZ = "Europe/Moscow"

# Начало смены МСК (15:00)
SHIFT_START_HOUR = 15
SHIFT_START_MINUTE = 0

# Конец смены МСК (03:00 следующего дня)
SHIFT_END_HOUR = 3
SHIFT_END_MINUTE = 0

# Длина рабочего блока и блока отдыха в графике 3/3
WORK_DAYS = 3
REST_DAYS = 3

# За сколько часов/минут до дедлайна слать напоминание
REMIND_HOURS = 1
REMIND_MINUTES = 15

# На Railway: задай DB_PATH=/data/ezra_bot.db и примонтируй Volume к /data
# Локально: файл создаётся в папке проекта
DB_PATH = os.getenv("DB_PATH", "ezra_bot.db")
