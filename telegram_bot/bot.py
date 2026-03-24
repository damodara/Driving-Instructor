from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import os
import logging
from datetime import datetime, timedelta
import django
import sys
import pathlib
import nest_asyncio
from telegram.request import HTTPXRequest

# Добавляем путь к проекту
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Теперь можно импортировать модели
from django.utils import timezone
from users.models import User
from schedule.models import LessonTime
from telegram_bot.models import TelegramUser

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
token = os.getenv('TELEGRAM_BOT_TOKEN')

# Проверяем, что токен загружен
if not token:
    raise ValueError('TELEGRAM_BOT_TOKEN не найден в переменных окружения. Проверьте файл .env')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /start"""
    telegram_user = update.effective_user
    
    # Проверяем, существует ли уже пользователь
    try:
        user = TelegramUser.objects.get(telegram_id=telegram_user.id)
        await update.message.reply_text(f'Добро пожаловать обратно, {user.first_name}!')
    except TelegramUser.DoesNotExist:
        # Создаем нового пользователя
        user = TelegramUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username or '',
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name or '',
            is_registered=False
        )
        user.save()
        await update.message.reply_text(f'Добро пожаловать, {user.first_name}! Используйте /help для просмотра доступных команд.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /help"""
    help_text = """
Доступные команды:
/schedule - Просмотреть расписание
/book - Записаться на занятие
/mybookings - Мои записи
/register - Привязать учетную запись сайта
/help - Помощь
    """
    await update.message.reply_text(help_text)

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать расписание на ближайшие дни"""
    # Получаем текущую дату
    now = timezone.now()
    # Показываем расписание на 7 дней вперед
    end_date = now + timedelta(days=7)
    
    # Получаем все занятия в этом диапазоне
    lessons = LessonTime.objects.filter(
        datetime__gte=now,
        datetime__lt=end_date
    ).order_by('datetime')
    
    if not lessons:
        await update.message.reply_text('На ближайшую неделю нет доступных занятий.')
        return
    
    # Группируем занятия по датам
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
    """Начать процесс записи на занятие"""
    # Проверяем, привязан ли пользователь к учетной записи сайта
    try:
        telegram_user = TelegramUser.objects.get(telegram_id=update.effective_user.id)
        
        if not telegram_user.is_registered or not telegram_user.user:
            await update.message.reply_text('Для записи на занятие необходимо привязать учетную запись сайта. Используйте команду /register')
            return
        
        # Показываем свободные слоты для выбора
        now = timezone.now()
        end_date = now + timedelta(days=7)
        
        # Получаем свободные слоты
        free_lessons = LessonTime.objects.filter(
            datetime__gte=now,
            datetime__lt=end_date,
            is_booked=False
        ).order_by('datetime')
        
        if not free_lessons:
            await update.message.reply_text('На ближайшую неделю нет свободных слотов.')
            return
        
        # Создаем клавиатуру с выбором слотов
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
    """Начать процесс привязки учетной записи сайта"""
    await update.message.reply_text('Для привязки учетной записи сайта отправьте ваш логин и пароль в формате:\n\n<логин> <пароль>\n\nНапример:\n\njohndoe mysecretpassword')
    # Устанавливаем флаг ожидания регистрации
    context.user_data['waiting_for_registration'] = True

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия на кнопку"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('book_'):
        lesson_id = int(query.data.split('_')[1])
        
        try:
            lesson = LessonTime.objects.get(id=lesson_id)
            
            # Проверяем, что слот все еще свободен
            if lesson.is_booked:
                await query.edit_message_text('Извините, этот слот уже занят.')
                return
            
            # Проверяем, что пользователь привязан к учетной записи
            telegram_user = TelegramUser.objects.get(telegram_id=query.from_user.id)
            if not telegram_user.user:
                await query.edit_message_text('Для записи на занятие необходимо привязать учетную запись сайта. Используйте команду /register')
                return
            
            # Записываем пользователя на занятие
            lesson.student = telegram_user.user
            lesson.is_booked = True
            lesson.save()
            
            await query.edit_message_text(
                f'Вы успешно записаны на занятие к {lesson.instructor.first_name} ' +
                f'на {lesson.datetime.strftime("%d.%m.%Y %H:%M")}!'
            )
            
        except LessonTime.DoesNotExist:
            await query.edit_message_text('Занятие не найдено.')
        except TelegramUser.DoesNotExist:
            await query.edit_message_text('Пользователь не найден.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений"""
    # Проверяем, ожидаем ли данные для регистрации
    if context.user_data.get('waiting_for_registration'):
        message_text = update.message.text.strip()
        
        # Ожидаем формат "логин пароль"
        parts = message_text.split(' ', 1)
        if len(parts) != 2:
            await update.message.reply_text('Неверный формат. Отправьте логин и пароль через пробел.')
            return
        
        username, password = parts
        
        # Проверяем учетные данные
        from django.contrib.auth import authenticate
        user = authenticate(username=username, password=password)
        
        if user is not None:
            # Привязываем учетную запись
            try:
                telegram_user = TelegramUser.objects.get(telegram_id=update.effective_user.id)
                telegram_user.user = user
                telegram_user.is_registered = True
                telegram_user.save()
                
                await update.message.reply_text(f'Учетная запись {username} успешно привязана!')
                
            except TelegramUser.DoesNotExist:
                await update.message.reply_text('Сначала используйте команду /start')
        else:
            await update.message.reply_text('Неверный логин или пароль. Попробуйте еще раз.')
        
        # Сбрасываем флаг
        context.user_data['waiting_for_registration'] = False

async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать мои записи на занятия"""
    try:
        telegram_user = TelegramUser.objects.get(telegram_id=update.effective_user.id)
        
        if not telegram_user.user:
            await update.message.reply_text('Сначала привяжите учетную запись сайта с помощью команды /register')
            return
        
        # Получаем записи пользователя
        bookings = LessonTime.objects.filter(
            student=telegram_user.user,
            datetime__gte=timezone.now()
        ).order_by('datetime')
        
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
    """Обработка ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schedule", schedule))
    application.add_handler(CommandHandler("book", book))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("mybookings", mybookings))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    import asyncio
    # Устанавливаем правильный event loop для macOS
    if sys.platform == 'darwin':
        import nest_asyncio
        nest_asyncio.apply()
    main()