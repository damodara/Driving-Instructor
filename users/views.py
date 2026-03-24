from django.shortcuts import render
from django.contrib.auth import login, authenticate
from django.shortcuts import render, redirect
from django.contrib import messages

from .forms import CustomUserCreationForm


def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            
            # Проверяем статус одобрения
            if not user.is_approved:
                messages.warning(request, 'Ваша учетная запись ожидает одобрения администратором. Вы можете просматривать ограниченную информацию, но не можете записываться на занятия.')
                return redirect('users:home')
            
            return redirect('users:home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def home(request):
    return render(request, 'home.html')
