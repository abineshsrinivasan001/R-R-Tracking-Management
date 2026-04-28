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

def populate_as_devops():
    # 1. Get a user
    user = User.objects.first()
    if not user:
        print("No user found. Creating one.")
        user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')

    # 2. Create the server
    server_name = "K8S-PROD-CLUSTER-01"
    server, created = Server.objects.get_or_create(
        name=server_name,
        defaults={
            'ip_address': '10.0.5.21',
            'status': 'up',
            'owner': user
        }
    )
    if created:
        print(f"Created server: {server_name}")
    else:
        print(f"Server {server_name} already exists.")

    # 3. Fill Daily Task: d01 (Monitor server health)
    # Proper devops filling: Checking metrics, noting specific utilization
    d01_def = TaskDefinition.objects.get(task_id='d01')
    fields_d01 = {
        'cpu_usage_pct': 42.5,
        'memory_usage_pct': 68.2,
        'disk_usage_pct': 55.0,
        'network_utilization_pct': 12.5,
        'status': 'normal'
    }
    notes_d01 = "All metrics within operational thresholds. Node cluster looks stable after the recent memory pressure incident. No CPU spikes observed during peak hours."
    
    # Log it
    TaskLog.objects.create(
        developer=user,
        server=server,
        task_id='d01',
        task_text=d01_def.text,
        category='d',
        status='done',
        notes=notes_d01
    )
    GeneralTaskEntry.objects.create(
        developer=user,
        server=server,
        task_id='d01',
        task_text=d01_def.text,
        status='done',
        fields_data=fields_d01,
        remarks=notes_d01
    )
    print("Logged Daily Task d01.")

    # 4. Fill Weekly Task: w01 (Review server capacity)
    # Proper devops filling: Analyzing trends, forecasting
    w01_def = TaskDefinition.objects.get(task_id='w01')
    fields_w01 = {
        'cpu_trend': 'Stable',
        'ram_trend': 'Increasing (3% WoW)',
        'storage_forecast_days': 120,
        'action_plan': 'Monitor memory leak in microservice-api. Plan for node upgrade next month if ram usage hits 85%.'
    }
    notes_w01 = "Weekly capacity review completed. Storage is healthy but RAM usage is slowly creeping up. Likely due to the new caching strategy in the API service."

    TaskLog.objects.create(
        developer=user,
        server=server,
        task_id='w01',
        task_text=w01_def.text,
        category='w',
        status='done',
        notes=notes_w01
    )
    GeneralTaskEntry.objects.create(
        developer=user,
        server=server,
        task_id='w01',
        task_text=w01_def.text,
        status='done',
        fields_data=fields_w01,
        remarks=notes_w01
    )
    print("Logged Weekly Task w01.")

    # 5. Fill Monthly Task: m01 (Perform full disaster recovery drill)
    # Proper devops filling: Drills, recovery times, outcome
    m01_def = TaskDefinition.objects.get(task_id='m01')
    fields_m01 = {
        'drill_date': '2026-04-25',
        'rto_achieved_minutes': 14.5,
        'rpo_achieved_minutes': 5.0,
        'drill_outcome': 'Success',
        'drill_summary': 'Successfully failed over to the DR region (US-West) and back to Primary (US-East). All DB replication syncs were within SLA.'
    }
    notes_m01 = "April DR Drill successful. Achieve RTO of 14.5 mins (target was 30 mins). Automation scripts performed flawlessly."

    TaskLog.objects.create(
        developer=user,
        server=server,
        task_id='m01',
        task_text=m01_def.text,
        category='m',
        status='done',
        notes=notes_m01
    )
    GeneralTaskEntry.objects.create(
        developer=user,
        server=server,
        task_id='m01',
        task_text=m01_def.text,
        status='done',
        fields_data=fields_m01,
        remarks=notes_m01
    )
    print("Logged Monthly Task m01.")

if __name__ == '__main__':
    populate_as_devops()
