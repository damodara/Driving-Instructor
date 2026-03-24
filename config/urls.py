from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("schedule.urls", namespace="schedule")),
    path("users/", include("users.urls", namespace="users")),
    path("", include("django.contrib.auth.urls")),
]
