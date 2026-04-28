from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Server(models.Model):
    STATUS_CHOICES = [
        ('up', 'Operational'),
        ('down', 'Down'),
        ('maint', 'Maintenance'),
    ]
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='up')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_servers')
    last_checked = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Developer(models.Model):
    ROLE_CHOICES = [
        ('manager', 'Manager'),
        ('tl', 'Team Lead'),
        ('developer', 'Developer'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='developer')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='developer')
    job_title = models.CharField(max_length=100, default='DevOps Engineer', blank=True)
    avatar_gradient = models.CharField(max_length=200, default='linear-gradient(135deg,#2563eb,#06b6d4)')
    initials = models.CharField(max_length=4, blank=True)

    def save(self, *args, **kwargs):
        if not self.initials:
            name_parts = self.user.get_full_name().split()
            self.initials = ''.join(p[0] for p in name_parts[:2]).upper() if name_parts else self.user.username[:2].upper()
        super().save(*args, **kwargs)

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def is_tl(self):
        return self.role == 'tl'

    @property
    def is_developer(self):
        return self.role == 'developer'

    @property
    def can_manage_users(self):
        """Manager and TL can create users; developer cannot."""
        return self.role in ('manager', 'tl')

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class TaskDefinition(models.Model):
    CATEGORY_CHOICES = [
        ('d', 'Daily'),
        ('w', 'Weekly'),
        ('m', 'Monthly'),
    ]
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('med', 'Medium'),
        ('low', 'Low'),
    ]
    task_id = models.CharField(max_length=10, unique=True)
    text = models.CharField(max_length=500)
    category = models.CharField(max_length=1, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='med')
    fields_schema = models.JSONField(default=list, blank=True, help_text='List of field names for this task')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.get_category_display()}] {self.task_id} - {self.text[:50]}"


class TaskLog(models.Model):
    """Base task log - tracks which R&R task was done"""
    STATUS_CHOICES = [
        ('done', 'Done'),
        ('wip', 'In Progress'),
        ('blk', 'Blocked'),
        ('miss', 'Missed'),
    ]
    CATEGORY_CHOICES = [
        ('d', 'Daily'),
        ('w', 'Weekly'),
        ('m', 'Monthly'),
    ]
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_logs')
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='task_logs', blank=True, null=True)
    task_id = models.CharField(max_length=10)  # d01, w03, etc.
    task_text = models.CharField(max_length=300)
    category = models.CharField(max_length=1, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    action_taken = models.TextField(blank=True)
    outcome = models.TextField(blank=True)
    logged_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-logged_at']

    def __str__(self):
        return f"{self.developer.username} - {self.task_text[:50]} [{self.status}]"


# ─────────────────────────────────────────────────────────────────
# 1. Server Health Monitor
# ─────────────────────────────────────────────────────────────────
class ServerHealthEntry(models.Model):
    STATUS_CHOICES = [
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='server_health_entries')
    date = models.DateField(default=timezone.now)
    server_name = models.CharField(max_length=100)
    cpu_usage = models.DecimalField(max_digits=5, decimal_places=2, help_text='CPU usage %')
    memory_usage = models.DecimalField(max_digits=5, decimal_places=2, help_text='Memory usage %')
    disk_usage = models.DecimalField(max_digits=5, decimal_places=2, help_text='Disk usage %')
    network_utilization = models.DecimalField(max_digits=5, decimal_places=2, help_text='Network utilization %')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='normal')
    issue_found = models.BooleanField(default=False)
    action_taken = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Server Health Entry'
        verbose_name_plural = 'Server Health Entries'

    def __str__(self):
        return f"{self.server_name} - {self.date} [{self.status}]"


# ─────────────────────────────────────────────────────────────────
# 2. Application & Infrastructure Alerts
# ─────────────────────────────────────────────────────────────────
class AlertCheckEntry(models.Model):
    STATUS_CHOICES = [
        ('resolved', 'Resolved'),
        ('pending', 'Pending'),
    ]
    developer = models.ForeignKey(User, on_delete=models.CASCADE)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='alert_entries', blank=True, null=True)
    date = models.DateField(default=timezone.now)
    tool_name = models.CharField(max_length=100, help_text='e.g. Prometheus, CloudWatch, Grafana')
    total_alerts = models.PositiveIntegerField(default=0)
    critical_alerts = models.PositiveIntegerField(default=0)
    warning_alerts = models.PositiveIntegerField(default=0)
    alert_description = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    action_taken = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Alert Check Entry'
        verbose_name_plural = 'Alert Check Entries'

    def __str__(self):
        return f"{self.tool_name} - {self.date} [{self.status}]"


# ─────────────────────────────────────────────────────────────────
# 3. CI/CD Pipeline Status
# ─────────────────────────────────────────────────────────────────
class PipelineEntry(models.Model):
    BUILD_STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('running', 'Running'),
        ('cancelled', 'Cancelled'),
    ]
    FINAL_STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pipeline_entries')
    date = models.DateField(default=timezone.now)
    pipeline_name = models.CharField(max_length=150)
    build_number = models.CharField(max_length=20, help_text='e.g. #145')
    build_status = models.CharField(max_length=15, choices=BUILD_STATUS_CHOICES)
    failed_stage = models.CharField(max_length=150, blank=True)
    error_message = models.TextField(blank=True)
    fix_applied = models.TextField(blank=True)
    final_status = models.CharField(max_length=15, choices=FINAL_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Pipeline Entry'
        verbose_name_plural = 'Pipeline Entries'

    def __str__(self):
        return f"{self.pipeline_name} {self.build_number} [{self.build_status}]"


# ─────────────────────────────────────────────────────────────────
# 4. Deployment Validation
# ─────────────────────────────────────────────────────────────────
class DeploymentEntry(models.Model):
    DEPLOY_STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
    ]
    ENVIRONMENT_CHOICES = [
        ('dev', 'Development'),
        ('qa', 'QA / Staging'),
        ('prod', 'Production'),
    ]
    VERIFICATION_CHOICES = [
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deployment_entries')
    date = models.DateField(default=timezone.now)
    application_name = models.CharField(max_length=150)
    version_deployed = models.CharField(max_length=50)
    deployment_status = models.CharField(max_length=15, choices=DEPLOY_STATUS_CHOICES)
    environment = models.CharField(max_length=10, choices=ENVIRONMENT_CHOICES)
    errors_found = models.TextField(blank=True)
    rollback_done = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=10, choices=VERIFICATION_CHOICES, default='pending')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Deployment Entry'
        verbose_name_plural = 'Deployment Entries'

    def __str__(self):
        return f"{self.application_name} {self.version_deployed} → {self.environment} [{self.deployment_status}]"


# ─────────────────────────────────────────────────────────────────
# 5. General Task Entry (for all other tasks)
# ─────────────────────────────────────────────────────────────────
class GeneralTaskEntry(models.Model):
    STATUS_CHOICES = [
        ('done', 'Done'),
        ('wip', 'In Progress'),
        ('blk', 'Blocked'),
    ]
    developer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='general_entries')
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='general_entries', blank=True, null=True)
    date = models.DateField(default=timezone.now)
    task_id = models.CharField(max_length=10)
    task_text = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='done')
    fields_data = models.JSONField(default=dict, blank=True)
    observations = models.TextField(blank=True, help_text='What did you see / check?')
    action_taken = models.TextField(blank=True, help_text='What did you do?')
    outcome = models.TextField(blank=True, help_text='What was the result?')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'General Task Entry'
        verbose_name_plural = 'General Task Entries'

    def __str__(self):
        return f"{self.task_id} - {self.date}"
