from django.contrib import admin
from .models import Developer, TaskLog, ServerHealthEntry, AlertCheckEntry, PipelineEntry, DeploymentEntry, Server, GeneralTaskEntry, TaskDefinition

@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'job_title', 'initials']
    list_filter = ['role']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']

@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip_address', 'status', 'owner', 'last_checked']
    list_filter = ['status']

@admin.register(TaskLog)
class TaskLogAdmin(admin.ModelAdmin):
    list_display = ['developer', 'task_text', 'category', 'status', 'logged_at']
    list_filter = ['status', 'category', 'logged_at']
    search_fields = ['task_text', 'developer__username']

@admin.register(ServerHealthEntry)
class ServerHealthAdmin(admin.ModelAdmin):
    list_display = ['server_name', 'developer', 'date', 'cpu_usage', 'memory_usage', 'disk_usage', 'status']
    list_filter = ['status', 'date', 'issue_found']

@admin.register(AlertCheckEntry)
class AlertCheckAdmin(admin.ModelAdmin):
    list_display = ['tool_name', 'developer', 'date', 'total_alerts', 'critical_alerts', 'status']
    list_filter = ['status', 'date']

@admin.register(PipelineEntry)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ['pipeline_name', 'build_number', 'developer', 'date', 'build_status', 'final_status']
    list_filter = ['build_status', 'final_status', 'date']

@admin.register(DeploymentEntry)
class DeploymentAdmin(admin.ModelAdmin):
    list_display = ['application_name', 'version_deployed', 'developer', 'date', 'environment', 'deployment_status']
    list_filter = ['deployment_status', 'environment', 'date']
