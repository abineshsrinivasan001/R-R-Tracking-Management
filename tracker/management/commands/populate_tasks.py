from django.core.management.base import BaseCommand
from tracker.models import TaskDefinition

class Command(BaseCommand):
    help = 'Populates the TaskDefinition table with DevOps tasks and fields'

    def handle(self, *args, **options):
        # 🟢 DAILY TASKS
        daily = [
            ("d01", "Monitor Server Health", ["Server Name", "CPU %", "Memory %", "Disk %", "Network %", "Status (Normal/Warning/Critical)", "Issue Found", "Action Taken", "Remarks"]),
            ("d02", "Check Alerts (App + Infra)", ["Tool Name", "Total Alerts", "Critical Alerts", "Warning Alerts", "Alert Description", "Status", "Action Taken"]),
            ("d03", "CI/CD Pipeline Status", ["Pipeline Name", "Build Number", "Build Status", "Failed Stage", "Error Message", "Fix Applied"]),
            ("d04", "Deployment Validation", ["App Name", "Version", "Environment", "Deployment Status", "Errors Found", "Rollback (Yes/No)", "Verification Status"]),
            ("d05", "Log Monitoring", ["Log Source", "Error Count", "Warning Count", "Critical Issues", "Action Taken"]),
            ("d06", "Backup Status", ["Backup Job Name", "Status (Success/Failed)", "Backup Time", "Storage Location"]),
            ("d07", "Security Alerts", ["Alerts Count", "Severity", "Issue Description", "Action Taken"]),
            ("d08", "Kubernetes / Docker Health", ["Cluster Name", "Pods Running / Failed", "Restart Count", "Status"]),
            ("d09", "Service/API Availability", ["Service Name", "Status (Up/Down)", "Response Time", "Issue Found"]),
            ("d10", "Incident Handling", ["Incident ID", "Issue Description", "Severity", "Resolution Time", "Status"]),
            ("d11", "Disk Cleanup", ["Server Name", "Disk Usage Before", "Disk Usage After", "Action Taken"]),
            ("d12", "SSL Certificate Check", ["Domain Name", "Expiry Date", "Status (Valid/Expiring Soon)", "Action"]),
        ]

        # 🟡 WEEKLY TASKS
        weekly = [
            ("w01", "Server Capacity Review", ["Avg CPU", "Peak CPU", "Memory Trend", "Storage Growth", "Recommendation"]),
            ("w02", "Patch Updates", ["Patch Type", "Systems Updated", "Status", "Downtime"]),
            ("w03", "CI/CD Optimization", ["Pipeline Name", "Build Time Before", "Build Time After", "Improvement Done"]),
            ("w04", "Backup Restore Test", ["Backup Name", "Restore Tested (Yes/No)", "Result", "Time Taken"]),
            ("w05", "User Access Audit", ["Total Users Reviewed", "Removed Users", "Suspicious Accounts"]),
            ("w06", "Security Review", ["Vulnerabilities Found", "Severity", "Fixed Count"]),
            ("w07", "Container Maintenance", ["Images Updated", "Containers Removed", "Cleanup Done"]),
            ("w08", "DB Performance Check", ["Query Time", "Slow Queries", "Optimization Done"]),
            ("w09", "Monitoring Dashboard Review", ["Alerts Tuned", "Changes Made"]),
            ("w10", "Cost Review", ["Total Cost", "Increase/Decrease", "Optimization"]),
        ]

        # 🔴 MONTHLY TASKS
        monthly = [
            ("m01", "Disaster Recovery Drill", ["DR Tested", "Recovery Time", "Result"]),
            ("m02", "Architecture Review", ["Bottlenecks", "Scaling Needed", "Suggestions"]),
            ("m03", "Security Patching", ["Patches Applied", "Systems Covered", "Status"]),
            ("m04", "Secrets & Keys Rotation", ["Keys Rotated", "Expiry Updated", "Status"]),
            ("m05", "Server Audit", ["Config Checked", "Issues Found", "Compliance Status"]),
            ("m06", "Backup Policy Review", ["Retention Days", "Changes Made"]),
            ("m07", "Capacity Planning", ["Future Load", "Resources Needed"]),
            ("m08", "Cloud Cost Optimization", ["Total Cost", "Savings Achieved"]),
            ("m09", "Documentation Update", ["Docs Updated", "Sections Changed"]),
            ("m10", "Tool Evaluation", ["Tool Name", "Purpose", "Decision (Use/Reject)"]),
            ("m11", "Team Review Meeting", ["Meeting Date", "Topics Discussed", "Action Items"]),
        ]

        self.stdout.write("Populating tasks...")
        
        def populate(tasks, cat):
            for tid, txt, fields in tasks:
                obj, created = TaskDefinition.objects.update_or_create(
                    task_id=tid,
                    defaults={
                        'text': txt,
                        'category': cat,
                        'fields_schema': fields,
                        'priority': 'high' if cat == 'd' else 'med'
                    }
                )
                status = "Created" if created else "Updated"
                self.stdout.write(f"  {status}: {tid} - {txt}")

        populate(daily, 'd')
        populate(weekly, 'w')
        populate(monthly, 'm')
        
        self.stdout.write(self.style.SUCCESS("Successfully populated all tasks!"))
