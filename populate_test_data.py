import os
import django
import datetime
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'devops_tracker.settings')
django.setup()

from django.contrib.auth.models import User
from tracker.models import Server, TaskLog, ServerHealthEntry, AlertCheckEntry

def populate():
    try:
        user = User.objects.get(username='admin')
    except User.DoesNotExist:
        print("User 'admin' not found. Please adjust username in script.")
        return

    # 1. Create Server
    server, created = Server.objects.get_or_create(
        name='PROD_SERVER_01',
        defaults={
            'ip_address': '10.0.0.45',
            'status': 'up',
            'owner': user
        }
    )
    if created:
        print(f"Created server: {server.name}")
    else:
        print(f"Server {server.name} already exists.")

    # 2. Create Health Entries (for trend)
    for i in range(5):
        d = timezone.now() - datetime.timedelta(days=i)
        ServerHealthEntry.objects.create(
            developer=user,
            server_name=server.name,
            date=d.date(),
            cpu_usage=40 + (i * 8),
            memory_usage=55 + (i * 4),
            disk_usage=32,
            network_utilization=12,
            status='normal' if i < 3 else 'warning',
            issue_found=(i >= 3),
            remarks=f"Historical record for {d.date()}"
        )
    print("Created 5 health entries.")

    # 3. Create Task Logs (for Audit History)
    tasks = [
        ('d01', 'Monitor server health', 'High CPU load observed on production node. Investigated logs and found leaking process.', 'Terminated zombie process and optimized heap memory.', 'CPU stabilized at 40%.', 2),
        ('d02', 'Verify Backup Status', 'Backup job took 5 hours (2 hours over threshold).', 'Cleaned up old staging logs and adjusted backup compression level.', 'Backup completed in 2.2 hours.', 24),
        ('d03', 'Security Patch Review', 'CVE-2024-XXXX vulnerability reported for kernel.', 'Applied latest security patches via yum update.', 'Node patched and rebooted.', 48),
        ('d01', 'Monitor server health', 'Memory usage at 85% steady.', 'No action needed - within peak threshold.', 'Performance stable.', 72),
    ]

    for tid, text, obs, action, out, hours_ago in tasks:
        log_time = timezone.now() - datetime.timedelta(hours=hours_ago)
        TaskLog.objects.create(
            developer=user,
            server=server,
            task_id=tid,
            task_text=text,
            category=tid[0],
            status='done',
            observations=obs,
            action_taken=action,
            outcome=out,
            logged_at=log_time
        )
    print(f"Created {len(tasks)} task logs.")

    # 4. Create Alert Entries
    AlertCheckEntry.objects.create(
        developer=user,
        server=server,
        tool_name='CloudWatch',
        total_alerts=3,
        critical_alerts=1,
        warning_alerts=2,
        alert_description='5xx error spike on web application endpoint.',
        status='resolved',
        action_taken='Restarted Nginx and cleared cache.',
        date=(timezone.now() - datetime.timedelta(days=1)).date()
    )
    print("Created alert entry.")

    print("\n--- TEST DATA POPULATED SUCCESSFULLY ---")
    print(f"Go to your dashboard and look for '{server.name}'")

if __name__ == "__main__":
    populate()
