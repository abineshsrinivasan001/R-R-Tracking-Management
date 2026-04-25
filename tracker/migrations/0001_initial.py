# Generated migration for DevOps Tracker models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Developer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(default='DevOps Engineer', max_length=100)),
                ('avatar_gradient', models.CharField(default='linear-gradient(135deg,#2563eb,#06b6d4)', max_length=200)),
                ('initials', models.CharField(blank=True, max_length=4)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='developer', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='TaskLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_id', models.CharField(max_length=10)),
                ('task_text', models.CharField(max_length=300)),
                ('category', models.CharField(choices=[('d', 'Daily'), ('w', 'Weekly'), ('m', 'Monthly')], max_length=1)),
                ('status', models.CharField(choices=[('done', 'Done'), ('wip', 'In Progress'), ('blk', 'Blocked'), ('miss', 'Missed')], max_length=10)),
                ('notes', models.TextField(blank=True)),
                ('logged_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('developer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-logged_at'],
            },
        ),
        migrations.CreateModel(
            name='ServerHealthEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.now)),
                ('server_name', models.CharField(max_length=100)),
                ('cpu_usage', models.DecimalField(decimal_places=2, help_text='CPU usage %', max_digits=5)),
                ('memory_usage', models.DecimalField(decimal_places=2, help_text='Memory usage %', max_digits=5)),
                ('disk_usage', models.DecimalField(decimal_places=2, help_text='Disk usage %', max_digits=5)),
                ('network_utilization', models.DecimalField(decimal_places=2, help_text='Network utilization %', max_digits=5)),
                ('status', models.CharField(choices=[('normal', 'Normal'), ('warning', 'Warning'), ('critical', 'Critical')], default='normal', max_length=10)),
                ('issue_found', models.BooleanField(default=False)),
                ('action_taken', models.TextField(blank=True)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('developer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='server_health_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Server Health Entry',
                'verbose_name_plural': 'Server Health Entries',
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AlertCheckEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.now)),
                ('tool_name', models.CharField(help_text='e.g. Prometheus, CloudWatch, Grafana', max_length=100)),
                ('total_alerts', models.PositiveIntegerField(default=0)),
                ('critical_alerts', models.PositiveIntegerField(default=0)),
                ('warning_alerts', models.PositiveIntegerField(default=0)),
                ('alert_description', models.TextField()),
                ('status', models.CharField(choices=[('resolved', 'Resolved'), ('pending', 'Pending')], default='pending', max_length=10)),
                ('action_taken', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('developer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Alert Check Entry',
                'verbose_name_plural': 'Alert Check Entries',
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PipelineEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.now)),
                ('pipeline_name', models.CharField(max_length=150)),
                ('build_number', models.CharField(help_text='e.g. #145', max_length=20)),
                ('build_status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed'), ('running', 'Running'), ('cancelled', 'Cancelled')], max_length=15)),
                ('failed_stage', models.CharField(blank=True, max_length=150)),
                ('error_message', models.TextField(blank=True)),
                ('fix_applied', models.TextField(blank=True)),
                ('final_status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed'), ('pending', 'Pending')], default='pending', max_length=15)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('developer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pipeline_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Pipeline Entry',
                'verbose_name_plural': 'Pipeline Entries',
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DeploymentEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.now)),
                ('application_name', models.CharField(max_length=150)),
                ('version_deployed', models.CharField(max_length=50)),
                ('deployment_status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed'), ('partial', 'Partial')], max_length=15)),
                ('environment', models.CharField(choices=[('dev', 'Development'), ('qa', 'QA / Staging'), ('prod', 'Production')], max_length=10)),
                ('errors_found', models.TextField(blank=True)),
                ('rollback_done', models.BooleanField(default=False)),
                ('verification_status', models.CharField(choices=[('passed', 'Passed'), ('failed', 'Failed'), ('pending', 'Pending')], default='pending', max_length=10)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('developer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deployment_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Deployment Entry',
                'verbose_name_plural': 'Deployment Entries',
                'ordering': ['-date', '-created_at'],
            },
        ),
    ]
