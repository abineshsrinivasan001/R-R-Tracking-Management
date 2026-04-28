import os
import django
import json
from django.utils import timezone

import sys
from pathlib import Path

# Add the project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.append(str(root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'devops_tracker.settings')
django.setup()

from django.contrib.auth.models import User
from tracker.models import Server, TaskLog, TaskDefinition, GeneralTaskEntry

def populate_for_all_users():
    users = User.objects.all()
    if not users:
        print("No users found.")
        return

    server_name = "K8S-PROD-CLUSTER-01"
    # Task Definitions
    d01_def = TaskDefinition.objects.get(task_id='d01')
    w01_def = TaskDefinition.objects.get(task_id='w01')
    m01_def = TaskDefinition.objects.get(task_id='m01')

    for user in users:
        print(f"Processing for user: {user.username}")
        
        # Create/Get Server for this user
        server, created = Server.objects.get_or_create(
            name=server_name,
            owner=user,
            defaults={
                'ip_address': '10.0.5.21',
                'status': 'up'
            }
        )
        
        # Log Daily Task
        fields_d01 = {'cpu_usage_pct': 42.5, 'memory_usage_pct': 68.2, 'disk_usage_pct': 55.0, 'status': 'normal'}
        notes_d01 = "Node cluster stable. Monitoring metrics normal."
        
        TaskLog.objects.get_or_create(
            developer=user, server=server, task_id='d01',
            defaults={'task_text': d01_def.text, 'category': 'd', 'status': 'done', 'notes': notes_d01}
        )
        GeneralTaskEntry.objects.get_or_create(
            developer=user, server=server, task_id='d01',
            defaults={'task_text': d01_def.text, 'status': 'done', 'fields_data': fields_d01, 'remarks': notes_d01}
        )

        # Log Weekly Task
        fields_w01 = {'cpu_trend': 'Stable', 'ram_trend': 'Increasing', 'storage_forecast_days': 120}
        notes_w01 = "Weekly capacity review completed."
        
        TaskLog.objects.get_or_create(
            developer=user, server=server, task_id='w01',
            defaults={'task_text': w01_def.text, 'category': 'w', 'status': 'done', 'notes': notes_w01}
        )
        GeneralTaskEntry.objects.get_or_create(
            developer=user, server=server, task_id='w01',
            defaults={'task_text': w01_def.text, 'status': 'done', 'fields_data': fields_w01, 'remarks': notes_w01}
        )

        # Log Monthly Task
        fields_m01 = {'drill_outcome': 'Success', 'rto_achieved_minutes': 14.5}
        notes_m01 = "Monthly DR drill successful."
        
        TaskLog.objects.get_or_create(
            developer=user, server=server, task_id='m01',
            defaults={'task_text': m01_def.text, 'category': 'm', 'status': 'done', 'notes': notes_m01}
        )
        GeneralTaskEntry.objects.get_or_create(
            developer=user, server=server, task_id='m01',
            defaults={'task_text': m01_def.text, 'status': 'done', 'fields_data': fields_m01, 'remarks': notes_m01}
        )

    print("Done! Data populated for all users.")

if __name__ == '__main__':
    populate_for_all_users()
