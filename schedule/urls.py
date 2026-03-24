from django.contrib import admin
from django.urls import path, include
from . import views

app_name = 'schedule'

urlpatterns = [
    path("", views.index, name='index'),
    path("lessons/create/", views.lesson_create, name='lesson_create'),
    path("lessons/<int:pk>/edit/", views.lesson_update, name='lesson_update'),
    path("lessons/<int:pk>/delete/", views.lesson_delete, name='lesson_delete'),
]
