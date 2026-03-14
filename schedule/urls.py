from django.contrib import admin
from django.urls import path, include

from schedule.apps import ScheduleConfig

app_name = ScheduleConfig.name

urlpatterns = [
    path("",),
]
