import os
import sys
import pathlib
import logging
from datetime import datetime, timedelta
import nest_asyncio

from dotenv import load_dotenv
load_dotenv()

from asgiref.sync import sync_to_async
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import django

# Добавляем путь к проекту
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from django.db import connection
from django.contrib.auth import get_user_model
from schedule.models import LessonTime
from telegram_bot.models import TelegramUser

# Получаем модель пользователя
User = get_user_model()
USER_FIELD_NAMES = {f.name for f in User._meta.get_fields()}


def _detect_login_field() -> str:
    candidates = []
    username_field = getattr(User, "USERNAME_FIELD", None)
    if username_field:
        candidates.append(username_field)
    candidates.extend(["username", "email"])
    for field in candidates:
        if field in USER_FIELD_NAMES:
            return field
    raise ValueError("Не найдено подходящее поле для авторизации пользователя")


LOGIN_FIELD = _detect_login_field()

# Диагностика (для отладки, можно убрать после настройки)
print("User model fields:", [f.name for f in User._meta.get_fields()])
print("Database alias:", connection.settings_dict['NAME'])
print("User model:", User)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
token = os.getenv('TELEGRAM_BOT_TOKEN')
if not token:
    raise ValueError('TELEGRAM_BOT_TOKEN не найден в переменных окружения. Проверьте файл .env')

# --- Асинхронные обёртки для ORM ---
get_telegram_user = sync_to_async(TelegramUser.objects.get)
create_telegram_user = sync_to_async(TelegramUser.objects.create)
save_telegram_user = sync_to_async(lambda obj: obj.save())
get_lesson_by_id = sync_to_async(LessonTime.objects.get)
save_lesson = sync_to_async(lambda obj: obj.save())

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user = update.effective_user
    try:
        user = await get_telegram_user(telegram_id=telegram_user.id)
        await update.message.reply_text(f'Добро пожаловать обратно, {user.first_name}!')
    except TelegramUser.DoesNotExist:
        user = await create_telegram_user(
            telegram_id=telegram_user.id,
            username=telegram_user.username or '',
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name or '',
            is_registered=False
        )
        await update.message.reply_text(f'Добро пожаловать, {user.first_name}! Используйте /help для просмотра доступных команд.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Доступные команды:\n"
        "/schedule - Просмотреть расписание\n"
        "/book - Записаться на занятие\n"
        "/mybookings - Мои записи\n"
        "/register - Привязать учетную запись сайта\n"
        "/help - Помощь"
    )

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = timezone.now()
    end_date = now + timedelta(days=7)
    lessons_qs = LessonTime.objects.filter(
        datetime__gte=now,
        datetime__lt=end_date
    ).order_by('datetime')
    lessons = await sync_to_async(list)(lessons_qs)

    if not lessons:
        await update.message.reply_text('На ближайшую неделю нет доступных занятий.')
        return

    schedule_text = "Расписание на ближайшую неделю:\n\n"
    current_date = None
    for lesson in lessons:
        lesson_date = lesson.datetime.date()
        if lesson_date != current_date:
            schedule_text += f"\n<b>{lesson_date.strftime('%d.%m.%Y')} ({lesson_date.strftime('%A')})</b>:\n"
            current_date = lesson_date
        time_str = lesson.datetime.strftime('%H:%M')
        status = "Занято" if lesson.is_booked else "Свободно"
        booked_by = f" (забронировано {lesson.student.first_name})" if lesson.is_booked and lesson.student else ""
        schedule_text += f"• {time_str} - {status}{booked_by}\n"

    await update.message.reply_html(schedule_text)

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        telegram_user = await get_telegram_user(telegram_id=update.effective_user.id)
        if not telegram_user.is_registered or not telegram_user.user_id:
            await update.message.reply_text('Для записи на занятие необходимо привязать учетную запись сайта. Используйте команду /register')
            return

        now = timezone.now()
        end_date = now + timedelta(days=7)
        free_lessons_qs = LessonTime.objects.filter(
            datetime__gte=now,
            datetime__lt=end_date,
            is_booked=False
        ).order_by('datetime')
        free_lessons = await sync_to_async(list)(free_lessons_qs)

        if not free_lessons:
            await update.message.reply_text('На ближайшую неделю нет свободных слотов.')
            return

        keyboard = []
        for lesson in free_lessons:
            time_str = lesson.datetime.strftime('%d.%m.%Y %H:%M')
            keyboard.append([
                InlineKeyboardButton(
                    f"{time_str} - {lesson.instructor.first_name}",
                    callback_data=f"book_{lesson.id}"
                )
            ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Выберите свободный слот для записи:', reply_markup=reply_markup)

    except TelegramUser.DoesNotExist:
        await update.message.reply_text('Сначала используйте команду /start')

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    login_label = "email" if LOGIN_FIELD == "email" else "логин"
    example_login = "user@example.com" if LOGIN_FIELD == "email" else "johndoe"
    await update.message.reply_text(
        f'Для привязки учетной записи сайта отправьте ваш {login_label} и пароль в формате:\n\n'
        f'<{login_label}> <пароль>\n\nНапример:\n\n{example_login} mysecretpassword'
    )
    context.user_data['waiting_for_registration'] = True

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data.startswith('book_'):
        lesson_id = int(query.data.split('_')[1])
        try:
            lesson = await get_lesson_by_id(id=lesson_id)
            if lesson.is_booked:
                await query.edit_message_text('Извините, этот слот уже занят.')
                return

            telegram_user = await get_telegram_user(telegram_id=query.from_user.id)
            if not telegram_user.user_id:
                await query.edit_message_text('Для записи на занятие необходимо привязать учетную запись сайта. Используйте команду /register')
                return

            lesson.student_id = telegram_user.user_id
            lesson.is_booked = True
            await save_lesson(lesson)

            await query.edit_message_text(
                f'Вы успешно записаны на занятие к {lesson.instructor.first_name} '
                f'на {lesson.datetime.strftime("%d.%m.%Y %H:%M")}!'
            )
        except LessonTime.DoesNotExist:
            await query.edit_message_text('Занятие не найдено.')
        except TelegramUser.DoesNotExist:
            await query.edit_message_text('Пользователь не найден.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('waiting_for_registration'):
        message_text = update.message.text.strip()
        parts = message_text.split(' ', 1)
        if len(parts) != 2:
            await update.message.reply_text('Неверный формат. Отправьте логин и пароль через пробел.')
            return

        username, password = parts

        def _get_user_by_login(login_value: str):
            return User.objects.filter(**{LOGIN_FIELD: login_value}).first()

        user_obj = await sync_to_async(_get_user_by_login)(username)
        logger.info("Найден пользователь по %s: %s", LOGIN_FIELD, user_obj)

        if user_obj:
            logger.info(f"Проверка пароля: {user_obj.check_password(password)}")
            if user_obj.check_password(password):
                user = user_obj
            else:
                user = None
        else:
            user = None

        if user is not None:
            try:
                telegram_user = await get_telegram_user(telegram_id=update.effective_user.id)
                telegram_user.user = user
                telegram_user.is_registered = True
                await save_telegram_user(telegram_user)
                await update.message.reply_text(f'Учетная запись {username} успешно привязана!')
            except TelegramUser.DoesNotExist:
                await update.message.reply_text('Сначала используйте команду /start')
        else:
            await update.message.reply_text('Неверный логин или пароль. Попробуйте еще раз.')

        context.user_data['waiting_for_registration'] = False

async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        telegram_user = await get_telegram_user(telegram_id=update.effective_user.id)
        if not telegram_user.user_id:
            await update.message.reply_text('Сначала привяжите учетную запись сайта с помощью команды /register')
            return

        bookings_qs = LessonTime.objects.filter(
            student_id=telegram_user.user_id,
            datetime__gte=timezone.now()
        ).order_by('datetime')
        bookings = await sync_to_async(list)(bookings_qs)

        if not bookings:
            await update.message.reply_text('У вас нет предстоящих занятий.')
            return

        text = 'Ваши предстоящие занятия:\n\n'
        for booking in bookings:
            text += f'• {booking.datetime.strftime("%d.%m.%Y %H:%M")} - {booking.instructor.first_name}\n'
        await update.message.reply_text(text)

    except TelegramUser.DoesNotExist:
        await update.message.reply_text('Сначала используйте команду /start')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main() -> None:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schedule", schedule))
    application.add_handler(CommandHandler("book", book))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("mybookings", mybookings))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    import asyncio
    if sys.platform == 'darwin':
        nest_asyncio.apply()
    main()