#!/bin/sh
set -e
python manage.py migrate --noinput
exec python telegram_bot/bot.py
