from django.db import models
from users.models import User

class LessonTime(models.Model):
    datetime = models.DateTimeField()
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='available_lessons')
    student = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='booked_lessons')
    is_booked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.instructor} - {self.datetime} ({'занято' if self.is_booked else 'свободно'})"