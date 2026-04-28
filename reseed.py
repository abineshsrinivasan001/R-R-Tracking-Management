import django, os, sys, random, datetime
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'devops_tracker.settings')
django.setup()

from tracker.models import TaskLog, GeneralTaskEntry, ServerHealthEntry, TaskDefinition, Server
from django.contrib.auth.models import User
from django.utils import timezone

GeneralTaskEntry.objects.all().delete()
TaskLog.objects.all().delete()
ServerHealthEntry.objects.all().delete()

manager = User.objects.filter(is_superuser=True).first() or User.objects.first()
servers = list(Server.objects.all())
print("Servers:", [s.name for s in servers])
today = timezone.now().date()

TASK_FIELDS = {
    'd01': lambda: {'cpu_usage': str(random.randint(25,65)), 'memory_usage': str(random.randint(30,70)), 'disk_usage': str(random.randint(20,55)), 'network_utilization': str(random.randint(5,25)), 'status': 'Normal', 'issue_found': 'No', 'action_taken': 'Routine check completed', 'remarks': 'All systems healthy'},
    'd02': lambda: {'monitoring_tool': 'Prometheus', 'total_alerts': str(random.randint(0,4)), 'critical_alerts': '0', 'warning_alerts': str(random.randint(0,2)), 'alert_description': 'Minor CPU spike resolved', 'status': 'Resolved', 'action_taken': 'Alerts reviewed and cleared', 'remarks': 'No escalation needed'},
    'd03': lambda: {'pipeline_name': 'main-ci', 'build_number': str(random.randint(100,999)), 'build_status': 'Success', 'failed_stage': '', 'error_message': '', 'fix_applied': 'None', 'final_status': 'Success', 'remarks': 'Pipeline healthy'},
    'd04': lambda: {'application_name': 'WebApp', 'version_deployed': 'v1.5.0', 'environment': 'Production', 'deployment_status': 'Success', 'errors_found': 'None', 'rollback_done': 'No', 'verification_status': 'Passed', 'remarks': 'Deployment verified'},
    'd05': lambda: {'log_source': 'Application/System', 'error_count': str(random.randint(0,3)), 'warning_count': str(random.randint(0,5)), 'critical_errors': 'None', 'unusual_activity': 'None detected', 'status': 'Clean', 'action_taken': 'Logs reviewed', 'remarks': 'No anomalies found'},
    'd06': lambda: {'backup_job_name': 'nightly-full', 'backup_type': 'Full', 'backup_status': 'Success', 'backup_size_gb': str(random.randint(10,50)), 'duration_minutes': str(random.randint(15,45)), 'failure_reason': '', 'recovery_action': 'None', 'remarks': 'Backup completed successfully'},
    'd07': lambda: {'alert_source': 'SIEM', 'vulnerability_count': '0', 'severity': 'Low', 'affected_service': 'None', 'cve_ids': '', 'action_taken': 'Security alerts reviewed', 'status': 'Resolved', 'remarks': 'No new vulnerabilities'},
    'd08': lambda: {'platform': 'Kubernetes', 'total_pods_containers': str(random.randint(8,20)), 'running_count': str(random.randint(8,15)), 'failed_count': '0', 'restarting_count': '0', 'namespace': 'production', 'issue_description': 'None', 'action_taken': 'All pods healthy', 'remarks': 'Cluster stable'},
    'd09': lambda: {'services_checked': 'API Gateway, Auth Service, DB', 'all_services_up': 'Yes', 'down_services': '', 'avg_response_time_ms': str(random.randint(50,200)), 'uptime_pct': '99.9', 'action_taken': 'Services verified', 'remarks': 'All critical services operational'},
    'd10': lambda: {'incident_id': 'INC-0000', 'severity': 'P4', 'description': 'Minor service hiccup resolved', 'root_cause': 'Memory leak in background job', 'action_taken': 'Restarted background service', 'status': 'Resolved', 'resolution_time_minutes': str(random.randint(5,30)), 'remarks': 'No impact to users'},
    'd11': lambda: {'partition_path': '/var', 'usage_before_pct': str(random.randint(60,80)), 'usage_after_pct': str(random.randint(30,55)), 'space_freed_gb': str(random.randint(2,15)), 'files_cleaned': 'Old log files older than 30 days', 'action_taken': 'Log rotation applied', 'remarks': 'Disk space recovered'},
    'd12': lambda: {'domain_name': 'app.company.com', 'expiry_date': '2026-12-31', 'days_remaining': '247', 'certificate_issuer': "Let's Encrypt", 'status': 'Valid', 'action_taken': 'SSL verified', 'remarks': 'Certificate valid'},
    'w01': lambda: {'cpu_avg_pct': str(random.randint(30,55)), 'memory_avg_pct': str(random.randint(40,65)), 'storage_used_pct': str(random.randint(35,60)), 'storage_used_gb': str(random.randint(100,400)), 'storage_total_gb': '1000', 'trend': 'Stable', 'recommendation': 'No action needed', 'remarks': 'Capacity within normal range'},
    'w02': lambda: {'os_name': 'Ubuntu', 'os_version_before': '22.04.3', 'os_version_after': '22.04.4', 'packages_updated': str(random.randint(5,30)), 'patch_level': 'Current', 'reboot_required': 'No', 'reboot_done': 'No', 'issues_found': 'None', 'rollback_needed': 'No', 'remarks': 'Patch successful'},
    'w03': lambda: {'pipelines_reviewed': str(random.randint(3,8)), 'avg_build_time_before_min': str(random.randint(8,15)), 'avg_build_time_after_min': str(random.randint(5,10)), 'improvements_made': 'Parallel builds enabled', 'build_time_saved_pct': str(random.randint(15,40)), 'recommendation': 'Continue caching', 'remarks': 'Build time improved'},
    'w04': lambda: {'tests_run': str(random.randint(200,800)), 'passed': str(random.randint(180,760)), 'failed': '0', 'skipped': str(random.randint(0,20)), 'coverage_pct': str(random.randint(75,92)), 'failures_fixed': 'None', 'recommendation': 'Increase coverage', 'remarks': 'Testing complete'},
    'w05': lambda: {'total_accounts_reviewed': str(random.randint(10,30)), 'inactive_accounts_found': str(random.randint(0,3)), 'accounts_removed': '0', 'mfa_compliance_pct': str(random.randint(88,100)), 'action_taken': 'Access audit complete', 'remarks': 'No unauthorized access found'},
}

daily_tasks = list(TaskDefinition.objects.filter(category='d', is_active=True).values_list('task_id', 'text'))
weekly_tasks = list(TaskDefinition.objects.filter(category='w', is_active=True).values_list('task_id', 'text'))

for server in servers:
    for day_offset in range(3):
        day = today - datetime.timedelta(days=day_offset)
        for tid, ttext in daily_tasks:
            fget = TASK_FIELDS.get(tid)
            fdata = fget() if fget else {'status': 'Normal', 'action_taken': 'Completed', 'remarks': 'Done'}
            TaskLog.objects.create(
                developer=manager, server=server, task_id=tid, task_text=ttext,
                category='d', status='done', notes='[DONE] ' + ttext,
                logged_at=timezone.make_aware(datetime.datetime.combine(day, datetime.time(10, day_offset * 5)))
            )
            GeneralTaskEntry.objects.create(
                developer=manager, server=server, task_id=tid, task_text=ttext,
                date=day, status='done', fields_data=fdata, remarks='Completed on schedule'
            )
        ServerHealthEntry.objects.create(
            developer=manager, server_name=server.name, date=day,
            cpu_usage=random.randint(25,65), memory_usage=random.randint(30,70),
            disk_usage=random.randint(20,55), network_utilization=random.randint(5,25),
            status='normal', issue_found=False, action_taken='', remarks='All clear'
        )
    print(server.name + ": 3 days x " + str(len(daily_tasks)) + " daily tasks seeded with correct fields")

s1 = servers[0]
for tid, ttext in weekly_tasks[:5]:
    fget = TASK_FIELDS.get(tid)
    fdata = fget() if fget else {'status': 'Completed', 'recommendation': 'Continue', 'remarks': 'Done'}
    TaskLog.objects.create(
        developer=manager, server=s1, task_id=tid, task_text=ttext,
        category='w', status='done', notes='[DONE] ' + ttext,
        logged_at=timezone.make_aware(datetime.datetime.combine(today, datetime.time(14, 0)))
    )
    GeneralTaskEntry.objects.create(
        developer=manager, server=s1, task_id=tid, task_text=ttext,
        date=today, status='done', fields_data=fdata, remarks='Weekly review completed'
    )

print(s1.name + ": 5 weekly tasks seeded")
print("TOTAL: " + str(TaskLog.objects.count()) + " logs, " + str(GeneralTaskEntry.objects.count()) + " entries")
print("SUCCESS")
