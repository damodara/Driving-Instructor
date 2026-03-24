from django.contrib import admin
from .models import LessonTime
from django.utils import timezone


@admin.register(LessonTime)
class LessonTimeAdmin(admin.ModelAdmin):
    list_display = ('datetime', 'instructor', 'student', 'is_booked', 'duration', 'get_status_display')
    list_filter = ('is_booked', 'instructor', 'duration', 'datetime')
    search_fields = ('instructor__username', 'student__username', 'datetime')
    date_hierarchy = 'datetime'
    ordering = ('-datetime',)
    
    def get_status_display(self, obj):
        if obj.is_booked:
            if obj.is_past:
                if obj.attended is True:
                    return 'Посещено'
                elif obj.attended is False:
                    return 'Не посетил'
                else:
                    return 'Забронировано'
            return 'Забронировано'
        return 'Свободно'
    get_status_display.short_description = 'Статус'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('datetime', 'instructor', 'student', 'is_booked', 'duration', 'attended')
        }),
        ('Важные даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # редактирование существующего объекта
            return ['created_at', 'updated_at']
        return []
    
    def save_model(self, request, obj, form, change):
        if not change:  # создание нового объекта
            obj.created_at = timezone.now()
        obj.updated_at = timezone.now()
        super().save_model(request, obj, form, change)