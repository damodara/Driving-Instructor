from django.db import models
from users.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

class LessonTime(models.Model):
    DURATION_CHOICES = [
        (30, '30 минут'),
        (60, '1 час'),
        (90, '1 час 30 минут'),
        (120, '2 часа'),
    ]
    
    datetime = models.DateTimeField()
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='available_lessons')
    student = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='booked_lessons')
    is_booked = models.BooleanField(default=False)
    duration = models.IntegerField(choices=DURATION_CHOICES, default=60, verbose_name='Продолжительность (минуты)')
    attended = models.BooleanField(default=None, null=True, blank=True, verbose_name='Посетил занятие')

    class Meta:
        indexes = [
            models.Index(fields=['instructor', 'datetime']),
        ]

    def clean(self):
        # Эта валидация будет выполняться только при вызове full_clean()
        super().clean()
        
        # Проверяем, что дата и время в будущем
        if self.datetime and self.datetime <= timezone.now():
            raise ValidationError('Дата и время занятия должны быть в будущем.')
        
        # Проверяем пересечение с другими занятиями
        if self.datetime and self.duration and hasattr(self, 'instructor') and self.instructor:
            end_time = self.datetime + timedelta(minutes=self.duration)
            
            # Ищем пересекающиеся занятия
            overlapping_lessons = LessonTime.objects.filter(
                instructor=self.instructor,
                datetime__lt=end_time,
                datetime__gte=self.datetime - timedelta(minutes=1440)  # Проверяем за 24 часа назад для оптимизации
            ).exclude(pk=self.pk if self.pk else None)
            
            for lesson in overlapping_lessons:
                lesson_end = lesson.datetime + timedelta(minutes=lesson.duration)
                if lesson.datetime < end_time and self.datetime < lesson_end:
                    raise ValidationError(
                        f'Занятие пересекается с существующим занятием: '
                        f'{lesson.instructor} - {lesson.datetime.strftime("%d.%m.%Y %H:%M")} '
                        f'(до {lesson_end.strftime("%H:%M")})'
                    )
    
    def save(self, *args, **kwargs):
        # Удаляем full_clean() из save(), так как валидация теперь выполняется в форме
        super().save(*args, **kwargs)
        
        # Автоматически устанавливаем статус "Посетил" для прошедших занятий
        if self.datetime < timezone.now() and self.is_booked and self.attended is None:
            self.attended = True
            # Сохраняем изменения в attended без вызова clean()
            super().save(update_fields=['attended'], force_insert=False, force_update=True)

    def __str__(self):
        return f"{self.instructor} - {self.datetime} ({'занято' if self.is_booked else 'свободно'})"
        
    @property
    def is_past(self):
        return self.datetime < timezone.now()