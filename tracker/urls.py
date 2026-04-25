from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/log-task/', views.log_task, name='log_task'),
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/create-server/', views.create_server, name='create_server'),
    path('api/server/<int:server_id>/logs/', views.server_logs_api, name='server_logs_api'),
    path('api/server/<int:server_id>/chart/', views.server_chart_api, name='server_chart_api'),
    path('server/<int:server_id>/', views.server_management, name='server_management'),

    # Entry pages
    path('entries/server-health/', views.server_health_list, name='server_health_list'),
    path('entries/server-health/create/', views.server_health_create, name='server_health_create'),
    path('entries/alerts/', views.alert_check_list, name='alert_check_list'),
    path('entries/alerts/create/', views.alert_check_create, name='alert_check_create'),
    path('entries/pipeline/', views.pipeline_list, name='pipeline_list'),
    path('entries/pipeline/create/', views.pipeline_create, name='pipeline_create'),
    path('entries/deployment/', views.deployment_list, name='deployment_list'),
    path('entries/deployment/create/', views.deployment_create, name='deployment_create'),
]
