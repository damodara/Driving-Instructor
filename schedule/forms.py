from django import forms
from .models import LessonTime
from users.models import User


class LessonTimeForm(forms.ModelForm):
    class Meta:
        model = LessonTime
        fields = ['datetime', 'student', 'duration']
        widgets = {
            'datetime': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '300'}),  # шаг 5 минут
            'student': forms.Select(attrs={'class': 'form-control'}),
            'duration': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Фильтруем пользователей, оставляя только тех, у кого роль 'student'
        self.fields['student'].queryset = User.objects.filter(role='student')
        
        # Ограничиваем выбор времени с шагом 5 минут
        if 'datetime' in self.fields:
            self.fields['datetime'].widget.attrs['step'] = '300'  # 300 секунд = 5 минут
        
        # Инициализируем инструктора как текущего пользователя
        self.current_instructor = None  # Будет установлен в представлении

    def clean(self):
        cleaned_data = super().clean()
        datetime = cleaned_data.get('datetime')
        student = cleaned_data.get('student')
        duration = cleaned_data.get('duration')
        
        # Логируем данные для отладки
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Проверка валидации: datetime={datetime}, student={student}, duration={duration}")
        
        if datetime and student and duration:
            from datetime import timedelta
            from django.utils import timezone
            
            # Проверяем, что дата и время в будущем
            if datetime <= timezone.now():
                self.add_error('datetime', 'Дата и время занятия должны быть в будущем.')
            
            # Проверяем, что инструктор доступен
            # Ищем инструктора (предполагаем, что инструктор - это текущий пользователь или выбирается другим способом)
            instructor = self.instance.instructor if self.instance.pk else None
            if not instructor:
                # Инструктор - это текущий пользователь (передается в представлении)
                instructor = self.current_instructor
            if instructor:
                # Проверяем пересечение с другими занятиями инструктора
                end_time = datetime + timedelta(minutes=duration)
                overlapping_lessons = LessonTime.objects.filter(
                    instructor=instructor,
                    datetime__lt=end_time,
                    datetime__gte=datetime - timedelta(minutes=1440)
                ).exclude(pk=self.instance.pk if self.instance.pk else None)
                
                logger.info(f"Найдено пересекающихся занятий: {overlapping_lessons.count()}")
                
                for lesson in overlapping_lessons:
                    lesson_end = lesson.datetime + timedelta(minutes=lesson.duration)
                    if lesson.datetime < end_time and datetime < lesson_end:
                        self.add_error(None, 
                            f'Занятие пересекается с существующим занятием: '
                            f'{lesson.instructor} - {lesson.datetime.strftime("%d.%m.%Y %H:%M")} '
                            f'(до {lesson_end.strftime("%H:%M")})'
                        )
            else:
                self.add_error(None, 'Не удалось определить инструктора для проверки доступности времени.')
        
        return cleaned_data