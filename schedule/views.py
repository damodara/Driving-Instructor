from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from users.models import User
from .models import LessonTime
from .forms import LessonTimeForm
from django.core.exceptions import ValidationError
import logging
from django.utils import timezone
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@login_required
def index(request):
    # Проверяем, что пользователь одобрен
    if not request.user.is_approved:
        messages.warning(request, 'Ваша учетная запись ожидает одобрения администратором. Вы можете просматривать ограниченную информацию, но не можете записываться на занятия.')
        return render(request, 'schedule/index.html', {'time_slots': [], 'selected_date': timezone.now().date(), 'booked_slots': {}})
    # Получаем дату из GET-параметра или используем сегодняшнюю дату
    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        # Используем текущую дату с учетом часового пояса
        selected_date = timezone.localtime(timezone.now()).date()
    
    # Обработка POST-запроса для изменения статуса посещаемости
    if request.method == 'POST' and request.user.is_authenticated and request.user.role == 'admin':
        lesson_id = request.POST.get('lesson_id')
        attended = request.POST.get('attended')
        
        if lesson_id and attended in ['true', 'false', 'none']:
            try:
                lesson = get_object_or_404(LessonTime, pk=lesson_id)
                
                # Проверяем, что занятие уже прошло
                if lesson.datetime < timezone.now():
                    if attended == 'true':
                        lesson.attended = True
                    elif attended == 'false':
                        lesson.attended = False
                    else:
                        lesson.attended = None
                    
                    lesson.save()
                    messages.success(request, 'Статус посещаемости успешно обновлен.')
                else:
                    messages.error(request, 'Нельзя изменить статус посещаемости для будущих занятий.')
            except Exception as e:
                messages.error(request, f'Ошибка при обновлении статуса посещаемости: {e}')
        
        return redirect('schedule:index')
    
    # Получаем все занятия на выбранную дату
    all_lessons = LessonTime.objects.filter(
        datetime__date=selected_date
    ).order_by('datetime')
    
    # Создаем список занятий с ограниченной информацией о студентах
    lessons = []
    for lesson in all_lessons:
        # Только инструкторы и авторизованные студенты могут видеть информацию о студентах
        if request.user.is_authenticated:
            if request.user.role == 'instructor' and lesson.instructor == request.user:
                # Инструктор видит все детали своего занятия
                lessons.append(lesson)
            elif lesson.student == request.user:
                # Студент видит только свои занятия
                lessons.append(lesson)
            else:
                # Другие авторизованные пользователи видят занятие без информации о студенте
                lesson_copy = LessonTime(
                    id=lesson.id,
                    datetime=lesson.datetime,
                    instructor=lesson.instructor,
                    student=None,
                    is_booked=lesson.is_booked,
                    duration=lesson.duration,
                    attended=lesson.attended
                )
                lessons.append(lesson_copy)
        else:
            # Неавторизованные пользователи видят занятие без информации о студенте
            lesson_copy = LessonTime(
                id=lesson.id,
                datetime=lesson.datetime,
                instructor=lesson.instructor,
                student=None,
                is_booked=lesson.is_booked,
                duration=lesson.duration,
                attended=lesson.attended
            )
            lessons.append(lesson_copy)
    
    # Создаем словарь занятых слотов
    booked_slots = {}
    for lesson in lessons:
        # Используем полный datetime для ключа, чтобы избежать коллизий
        time_key = lesson.datetime.strftime('%H:%M')
        # Если слот уже есть в словаре (дублирование), показываем предупреждение
        if time_key in booked_slots:
            print(f"ПРЕДУПРЕЖДЕНИЕ: Найдено дублирование для времени {time_key}: {lesson.datetime}")
            
        booked_slots[time_key] = {
            'instructor': lesson.instructor,
            'is_booked': lesson.is_booked,
            'student': lesson.student,
            'datetime': lesson.datetime
        }
        print(f"Занятое время: {time_key}, datetime: {lesson.datetime}, is_booked: {lesson.is_booked}")  # Для отладки
    
    print(f"Все занятое время: {list(booked_slots.keys())}")  # Для отладки
    
    # Генерируем временные слоты с 9:00 до 21:00 с шагом в 1 час
    time_slots = []
    # Создаем datetime с учетом часового пояса
    current_time = timezone.make_aware(
        datetime.combine(selected_date, datetime.min.time().replace(hour=9))
    )
    end_time = timezone.make_aware(
        datetime.combine(selected_date, datetime.min.time().replace(hour=21))
    )
    
    while current_time < end_time:
        time_str = current_time.strftime('%H:%M')
        # Перепроверяем в базе данных для каждого слота (на случай, если данные изменились)
        if request.user.is_authenticated and request.user.role == 'instructor':
            # Для инструктора проверяем только его занятия
            lesson = LessonTime.objects.filter(
                instructor=request.user,
                datetime__date=current_time.date(),
                datetime__hour=current_time.hour,
                datetime__minute=current_time.minute
            ).first()
        else:
            # Для студентов и неаутентифицированных пользователей проверяем все занятия
            lesson = LessonTime.objects.filter(
                datetime__date=current_time.date(),
                datetime__hour=current_time.hour,
                datetime__minute=current_time.minute
            ).first()
        
        is_booked = lesson is not None
        # Сравниваем с текущим временем с учетом часового пояса
        is_future = current_time > timezone.localtime(timezone.now())
        is_past = not is_future  # Слот в прошлом
        
        print(f"Проверка слота {time_str}: {'занято' if is_booked else 'свободно'}, {'будущее' if is_future else 'прошлое/настоящее'}")  # Для отладки
        
        # Получаем информацию о слоте из базы данных
        lesson_info = None
        if is_booked and lesson:
            # Показываем информацию о студенте только если текущий пользователь - студент этого занятия
            is_current_user = request.user.is_authenticated and lesson.student == request.user
            
            # Только инструкторы и сам студент могут видеть имя студента
            show_student = False
            if request.user.is_authenticated:
                if request.user.role == 'instructor' and lesson.instructor == request.user:
                    show_student = True
                elif is_current_user:
                    show_student = True
            
            lesson_info = {
                'instructor': lesson.instructor,
                'is_booked': lesson.is_booked,
                'student': lesson.student if show_student else None,
                'datetime': lesson.datetime,
                'is_past': lesson.datetime < timezone.now(),
                'is_current_user': is_current_user,
                'attended': lesson.attended,
                'is_attended': lesson.attended is True,
                'is_absent': lesson.attended is False
            }
        
        time_slots.append({
            'time': current_time,
            'time_str': time_str,
            'is_booked': is_booked,
            'is_future': is_future,
            'is_past': is_past,
            'instructor': lesson_info['instructor'] if lesson_info else None,
            'student': lesson_info['student'] if lesson_info else None,
            'is_current_user': lesson_info['is_current_user'] if lesson_info else False,
            'datetime': lesson_info['datetime'] if lesson_info else current_time
        })
        current_time += timedelta(hours=1)
    
    # Обработка POST-запроса для записи на занятие
    if request.method == 'POST' and request.user.is_authenticated:
        datetime_str = request.POST.get('datetime')
        duration = request.POST.get('duration', '60')
        
        if datetime_str:
            try:
                # Преобразуем строку в datetime
                lesson_datetime = timezone.make_aware(datetime.strptime(datetime_str, '%Y-%m-%d %H:%M'))
                
                # Проверяем, что время в будущем
                if lesson_datetime <= timezone.now():
                    messages.error(request, 'Нельзя записаться на занятие в прошлом или настоящем времени.')
                else:
                    # Проверяем, что слот еще свободен
                    time_key = lesson_datetime.strftime('%H:%M')
                    print(f"Попытка записи на {time_key}, занято: {time_key in booked_slots}")  # Для отладки
                    
                    # Перепроверяем доступность слота в базе данных (защита от гонки условий)
                    existing_lesson = LessonTime.objects.filter(
                        datetime__date=lesson_datetime.date(),
                        datetime__hour=lesson_datetime.hour,
                        datetime__minute=lesson_datetime.minute
                    ).exists()
                    
                    if not existing_lesson:
                        # Создаем новое занятие
                        # Выбираем первого инструктора для простоты, в реальности можно добавить выбор
                        instructor = User.objects.filter(role='instructor').first()
                        
                        if instructor:
                            lesson = LessonTime.objects.create(
                                datetime=lesson_datetime,
                                instructor=instructor,
                                student=request.user,
                                is_booked=True,
                                duration=int(duration)
                            )
                            messages.success(request, f'Вы успешно записались на занятие к {instructor} на {lesson_datetime.strftime("%d.%m.%Y %H:%M")}!')
                            # Обновляем booked_slots после создания нового занятия
                            booked_slots[time_key] = {
                                'instructor': instructor,
                                'is_booked': True,
                                'student': request.user,
                                'datetime': lesson_datetime,
                                'is_past': False,
                                'is_current_user': True
                            }
                        else:
                            messages.error(request, 'Не найдено доступных инструкторов.')
                    else:
                        messages.error(request, 'Извините, этот слот уже занят. Пожалуйста, выберите другое время.')
            except ValueError as e:
                messages.error(request, f'Некорректный формат даты и времени: {e}')
            except Exception as e:
                messages.error(request, f'Ошибка при записи на занятие: {e}')
        
        # Перенаправляем, чтобы избежать повторной отправки формы
        return redirect('schedule:index')
    
    return render(request, 'schedule/index.html', {
        'time_slots': time_slots,
        'selected_date': selected_date,
        'booked_slots': booked_slots
    })


@login_required
def lesson_create(request):
    # Проверяем, что пользователь является инструктором
    if request.user.role != 'instructor':
        messages.error(request, 'У вас нет прав для создания занятий.')
        return redirect('schedule:index')
    if request.method == 'POST':
        form = LessonTimeForm(request.POST)
        form.current_instructor = request.user  # Передаем текущего пользователя как инструктора
        logger.info(f"Данные формы: {request.POST}")
        logger.info(f"Форма валидна: {form.is_valid()}")
        logger.info(f"Ошибки формы: {form.errors}")
        
        if form.is_valid():
            try:
                lesson = form.save(commit=False)
                lesson.instructor = request.user  # Устанавливаем текущего пользователя как инструктора
                lesson.save()
                messages.success(request, f'Занятие для {lesson.student} успешно создано!')
                logger.info(f"Занятие успешно создано: {lesson}")
                return redirect('schedule:index')
            except Exception as e:
                logger.error(f"Ошибка при сохранении занятия: {e}", exc_info=True)
                messages.error(request, f'Произошла ошибка при сохранении: {e}')
        else:
            logger.warning(f"Форма не валидна. Ошибки: {form.errors}")
            
        # Если форма не валидна или произошла ошибка, возвращаем форму с ошибками
        return render(request, 'schedule/lesson_form.html', {'form': form})
        # Если форма не валидна, ошибки будут отображены в шаблоне автоматически
    else:
        form = LessonTimeForm()
    return render(request, 'schedule/lesson_form.html', {'form': form})


@login_required
def lesson_update(request, pk):
    lesson = get_object_or_404(LessonTime, pk=pk)
    if request.method == 'POST':
        form = LessonTimeForm(request.POST, instance=lesson)
        if form.is_valid():
            form.save()
            messages.success(request, f'Занятие для {lesson.instructor} успешно обновлено!')
            return redirect('schedule:index')
    else:
        form = LessonTimeForm(instance=lesson)
    return render(request, 'schedule/lesson_form.html', {'form': form})


@login_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(LessonTime, pk=pk)
    if request.method == 'POST':
        lesson.delete()
        messages.success(request, 'Занятие успешно удалено!')
        return redirect('schedule:index')
    return render(request, 'schedule/lesson_confirm_delete.html', {'lesson': lesson})
