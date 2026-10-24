from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('server_management/login/', auth_views.LoginView.as_view(template_name='tracker/login.html'), name='login'),
    path('server_management/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('server_management/', include('tracker.urls')),
]
