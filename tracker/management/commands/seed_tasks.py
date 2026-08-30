# tracker/management/commands/seed_tasks.py
# 
# Run with: python manage.py seed_tasks
#
# This seeds all 33 TaskDefinitions (Daily/Weekly/Monthly) with
# their field schemas so developers see the right input fields
# when they verify a task on a server.

from django.core.management.base import BaseCommand
from tracker.models import TaskDefinition


TASK_DEFINITIONS = [

    # ══════════════════════════════════════════════════════════════
    # DAILY TASKS (d01 – d12)
    # ══════════════════════════════════════════════════════════════
    {
        'task_id': 'd01',
        'category': 'd',
        'priority': 'high',
        'text': 'Monitor server health (CPU, memory, disk usage, network utilization)',
        'fields_schema': [
            'cpu_usage',           # number, %
            'memory_usage',        # number, %
            'disk_usage',          # number, %
            'network_utilization', # number, %
            'status|Normal,Warning,Critical',
            'issue_found|Yes,No',
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'd02',
        'category': 'd',
        'priority': 'high',
        'text': 'Check application and infrastructure alerts from monitoring tools',
        'fields_schema': [
            'monitoring_tool',       # text: Prometheus, Grafana, CloudWatch etc.
            'total_alerts',          # number
            'critical_alerts',       # number
            'warning_alerts',        # number
            'alert_description',     # textarea
            'status|Resolved,Pending,Escalated',
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'd03',
        'category': 'd',
        'priority': 'high',
        'text': 'Review CI/CD pipeline status and failed builds',
        'fields_schema': [
            'pipeline_name',
            'build_number',
            'build_status|Success,Failed,Running,Cancelled',
            'failed_stage',
            'error_message',
            'fix_applied',
            'final_status|Success,Failed,Pending',
            'remarks',
        ]
    },
    {
        'task_id': 'd04',
        'category': 'd',
        'priority': 'high',
        'text': 'Validate successful deployment of scheduled releases',
        'fields_schema': [
            'application_name',
            'version_deployed',
            'environment|Development,QA/Staging,Production',
            'deployment_status|Success,Failed,Partial',
            'errors_found',
            'rollback_done|Yes,No',
            'verification_status|Passed,Failed,Pending',
            'remarks',
        ]
    },
    {
        'task_id': 'd05',
        'category': 'd',
        'priority': 'med',
        'text': 'Monitor log files for errors or unusual activities',
        'fields_schema': [
            'log_source',           # text: Application / System / Security / Nginx etc.
            'error_count',          # number
            'warning_count',        # number
            'critical_errors',      # text: brief desc
            'unusual_activity',     # text: any anomaly
            'status|Clean,Issues Found,Escalated',
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'd06',
        'category': 'd',
        'priority': 'high',
        'text': 'Check backup job status and confirm completion',
        'fields_schema': [
            'backup_job_name',
            'backup_type|Full,Incremental,Differential',
            'backup_status|Success,Failed,Partial',
            'backup_size_gb',          # number
            'duration_minutes',        # number
            'failure_reason',          # text (blank if success)
            'recovery_action',         # text
            'remarks',
        ]
    },
    {
        'task_id': 'd07',
        'category': 'd',
        'priority': 'high',
        'text': 'Review system security alerts and vulnerability notifications',
        'fields_schema': [
            'alert_source',            # text: SIEM, IDS, WAF etc.
            'vulnerability_count',     # number
            'severity|Low,Medium,High,Critical',
            'affected_service',        # text
            'cve_ids',                 # text (comma-separated if multiple)
            'action_taken',
            'status|Resolved,Pending,Escalated',
            'remarks',
        ]
    },
    {
        'task_id': 'd08',
        'category': 'd',
        'priority': 'med',
        'text': 'Verify container orchestration health (Kubernetes/Docker)',
        'fields_schema': [
            'platform|Kubernetes,Docker,Both',
            'total_pods_containers',   # number
            'running_count',           # number
            'failed_count',            # number
            'restarting_count',        # number
            'namespace',               # text
            'issue_description',
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'd09',
        'category': 'd',
        'priority': 'high',
        'text': 'Ensure availability of critical services and APIs',
        'fields_schema': [
            'services_checked',        # text: list of services / API names
            'all_services_up|Yes,No',
            'down_services',           # text (blank if all up)
            'avg_response_time_ms',    # number
            'uptime_pct',              # number
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'd10',
        'category': 'd',
        'priority': 'high',
        'text': 'Respond to incidents and perform initial troubleshooting',
        'fields_schema': [
            'incident_id',             # text
            'severity|P1,P2,P3,P4',
            'description',
            'root_cause',
            'action_taken',
            'status|Resolved,In Progress,Escalated',
            'resolution_time_minutes', # number (0 if not resolved)
            'remarks',
        ]
    },
    {
        'task_id': 'd11',
        'category': 'd',
        'priority': 'low',
        'text': 'Check disk usage and clean temporary / log files if required',
        'fields_schema': [
            'partition_path',          # text: / or /var etc.
            'usage_before_pct',        # number
            'usage_after_pct',         # number
            'space_freed_gb',          # number
            'files_cleaned',           # text: brief description
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'd12',
        'category': 'd',
        'priority': 'med',
        'text': 'Verify SSL certificate validity for services',
        'fields_schema': [
            'domain_name',
            'expiry_date',             # date
            'days_remaining',          # number
            'certificate_issuer',
            'status|Valid,Expiring Soon,Expired',
            'action_taken',
            'remarks',
        ]
    },

    # ══════════════════════════════════════════════════════════════
    # WEEKLY TASKS (w01 – w11)
    # ══════════════════════════════════════════════════════════════
    {
        'task_id': 'w01',
        'category': 'w',
        'priority': 'med',
        'text': 'Review server capacity (CPU, RAM, storage trends)',
        'fields_schema': [
            'cpu_avg_pct',             # number
            'memory_avg_pct',          # number
            'storage_used_pct',        # number
            'storage_used_gb',         # number
            'storage_total_gb',        # number
            'trend|Stable,Growing,Declining,Critical',
            'recommendation',
            'remarks',
        ]
    },
    {
        'task_id': 'w02',
        'category': 'w',
        'priority': 'high',
        'text': 'Perform patch updates for OS, packages, and middleware (if scheduled)',
        'fields_schema': [
            'os_name',
            'os_version_before',
            'os_version_after',
            'packages_updated',        # number
            'patch_level',
            'reboot_required|Yes,No',
            'reboot_done|Yes,No,Scheduled',
            'issues_found',
            'rollback_needed|Yes,No',
            'remarks',
        ]
    },
    {
        'task_id': 'w03',
        'category': 'w',
        'priority': 'med',
        'text': 'Review CI/CD pipeline improvements and optimize build times',
        'fields_schema': [
            'pipelines_reviewed',      # number
            'avg_build_time_before_min', # number
            'avg_build_time_after_min',  # number
            'improvements_made',
            'build_time_saved_pct',    # number
            'recommendation',
            'remarks',
        ]
    },
    {
        'task_id': 'w04',
        'category': 'w',
        'priority': 'high',
        'text': 'Validate backup restoration process (test restore)',
        'fields_schema': [
            'backup_date_tested',
            'restore_type|Full,Partial,File-Level',
            'restore_status|Success,Failed,Partial',
            'time_taken_minutes',      # number
            'data_integrity|Verified,Failed,Not Checked',
            'issues_found',
            'recovery_point_objective', # text
            'remarks',
        ]
    },
    {
        'task_id': 'w05',
        'category': 'w',
        'priority': 'high',
        'text': 'Audit user access and remove inactive accounts',
        'fields_schema': [
            'total_accounts_reviewed', # number
            'inactive_accounts_found', # number
            'accounts_removed',        # number
            'privileged_access_reviewed|Yes,No',
            'mfa_compliance_pct',      # number
            'policy_violations',       # text
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'w06',
        'category': 'w',
        'priority': 'high',
        'text': 'Review security logs and vulnerability scan results',
        'fields_schema': [
            'scan_tool',               # text: Nessus, OpenVAS, Qualys etc.
            'total_vulnerabilities',   # number
            'critical_count',          # number
            'high_count',              # number
            'medium_count',            # number
            'low_count',               # number
            'patched_count',           # number
            'pending_remediation_count', # number
            'report_summary',
            'remarks',
        ]
    },
    {
        'task_id': 'w07',
        'category': 'w',
        'priority': 'med',
        'text': 'Check container image updates and rebuild if necessary',
        'fields_schema': [
            'total_images_checked',    # number
            'outdated_images',         # number
            'images_rebuilt',          # number
            'images_removed',          # number
            'container_registry',      # text: DockerHub, ECR, GCR etc.
            'rebuild_reason',
            'remarks',
        ]
    },
    {
        'task_id': 'w08',
        'category': 'w',
        'priority': 'med',
        'text': 'Optimize database performance with DB teams if required',
        'fields_schema': [
            'database_name',
            'db_type',                 # text: PostgreSQL / MySQL / Oracle etc.
            'slow_queries_found',      # number
            'indexes_optimized',       # number
            'avg_query_time_before_ms', # number
            'avg_query_time_after_ms',  # number
            'db_size_gb',              # number
            'action_taken',
            'remarks',
        ]
    },
    {
        'task_id': 'w09',
        'category': 'w',
        'priority': 'low',
        'text': 'Clean unused Docker images, containers, and artifacts',
        'fields_schema': [
            'images_removed',          # number
            'containers_removed',      # number
            'volumes_removed',         # number
            'space_freed_gb',          # number
            'artifact_registry_cleaned|Yes,No',
            'remarks',
        ]
    },
    {
        'task_id': 'w10',
        'category': 'w',
        'priority': 'med',
        'text': 'Review monitoring dashboards and tune alert thresholds',
        'fields_schema': [
            'dashboards_reviewed',     # number
            'alert_rules_tuned',       # number
            'false_positives_reduced', # number
            'new_alerts_added',        # number
            'monitoring_tools',        # text: Grafana / Prometheus / Datadog
            'changes_summary',
            'remarks',
        ]
    },
    {
        'task_id': 'w11',
        'category': 'w',
        'priority': 'med',
        'text': 'Review infrastructure costs and resource utilization',
        'fields_schema': [
            'cloud_provider',          # text: AWS / GCP / Azure / On-Prem
            'monthly_cost_usd',        # number
            'cost_vs_last_month_pct',  # number (positive = increase)
            'top_cost_services',       # text
            'unused_resources_found',
            'optimization_actions',
            'estimated_savings_usd',   # number
            'remarks',
        ]
    },

    # ══════════════════════════════════════════════════════════════
    # MONTHLY TASKS (m01 – m11)
    # ══════════════════════════════════════════════════════════════
    {
        'task_id': 'm01',
        'category': 'm',
        'priority': 'high',
        'text': 'Perform full disaster recovery (DR) drill or validation',
        'fields_schema': [
            'drill_type|Full DR,Partial DR,Tabletop Exercise',
            'rto_target_minutes',      # number
            'rto_achieved_minutes',    # number
            'rpo_target_hours',        # number
            'rpo_achieved_hours',      # number
            'drill_result|Pass,Fail,Partial Pass',
            'gaps_identified',
            'action_plan',
            'next_drill_date',
            'remarks',
        ]
    },
    {
        'task_id': 'm02',
        'category': 'm',
        'priority': 'high',
        'text': 'Review infrastructure architecture and scalability planning',
        'fields_schema': [
            'components_reviewed',     # text: list of services reviewed
            'bottlenecks_identified',
            'single_points_of_failure',
            'scaling_recommendations',
            'architecture_changes_proposed',
            'priority|High,Medium,Low',
            'next_review_date',
            'remarks',
        ]
    },
    {
        'task_id': 'm03',
        'category': 'm',
        'priority': 'high',
        'text': 'Conduct security patching and vulnerability remediation',
        'fields_schema': [
            'patches_applied',         # number
            'cves_addressed',          # text
            'systems_patched',         # number
            'pending_patches',         # number
            'reboot_count',            # number
            'exceptions_granted',      # number
            'compliance_status|Compliant,Non-Compliant,Partial',
            'summary',
            'remarks',
        ]
    },
    {
        'task_id': 'm04',
        'category': 'm',
        'priority': 'high',
        'text': 'Review and rotate secrets, API keys, and credentials',
        'fields_schema': [
            'secrets_rotated',         # number
            'api_keys_rotated',        # number
            'certificates_renewed',    # number
            'rotation_tool|HashiCorp Vault,AWS Secrets Manager,Manual,Azure Key Vault',
            'pending_rotations',       # number
            'next_rotation_date',
            'remarks',
        ]
    },
    {
        'task_id': 'm05',
        'category': 'm',
        'priority': 'high',
        'text': 'Audit server configurations and compliance requirements',
        'fields_schema': [
            'servers_audited',         # number
            'compliance_standard|CIS Benchmark,NIST,ISO 27001,SOC2,Internal Policy',
            'pass_count',              # number
            'fail_count',              # number
            'critical_findings',
            'remediation_deadline',
            'remediation_plan',
            'remarks',
        ]
    },
    {
        'task_id': 'm06',
        'category': 'm',
        'priority': 'med',
        'text': 'Review backup policies and retention configurations',
        'fields_schema': [
            'policies_reviewed',       # number
            'retention_period_days',   # number
            'policy_changes_made',     # text
            'backup_storage_used_tb',  # number
            'storage_cost_monthly_usd', # number
            'compliance_status|Compliant,Non-Compliant,Needs Update',
            'next_policy_review_date',
            'remarks',
        ]
    },
    {
        'task_id': 'm07',
        'category': 'm',
        'priority': 'high',
        'text': 'Capacity planning and forecasting for upcoming workloads',
        'fields_schema': [
            'forecast_period_months',  # number
            'expected_growth_pct',     # number
            'cpu_forecast_pct',        # number (projected avg)
            'memory_forecast_gb',      # number
            'storage_forecast_tb',     # number
            'new_servers_needed',      # number
            'scaling_action_needed|Yes,No,Under Review',
            'recommendation',
            'remarks',
        ]
    },
    {
        'task_id': 'm08',
        'category': 'm',
        'priority': 'med',
        'text': 'Review cloud usage and optimize costs',
        'fields_schema': [
            'cloud_provider',
            'current_monthly_cost_usd', # number
            'previous_month_cost_usd',  # number
            'cost_change_pct',          # number
            'unused_resources_terminated', # text
            'reserved_instances_reviewed|Yes,No',
            'savings_achieved_usd',     # number
            'rightsizing_done|Yes,No',
            'recommendations',
            'remarks',
        ]
    },
    {
        'task_id': 'm09',
        'category': 'm',
        'priority': 'med',
        'text': 'Update infrastructure documentation and runbooks',
        'fields_schema': [
            'documents_updated',       # number
            'runbooks_updated',        # number
            'new_documents_created',   # number
            'documentation_platform',  # text: Confluence / Notion / SharePoint
            'sections_covered',        # text
            'review_done_by',          # text (reviewer name)
            'remarks',
        ]
    },
    {
        'task_id': 'm10',
        'category': 'm',
        'priority': 'low',
        'text': 'Evaluate new tools or improvements for DevOps pipelines',
        'fields_schema': [
            'tools_evaluated',         # number
            'tool_names',              # text
            'poc_conducted|Yes,No',
            'poc_result',              # text
            'recommendation|Adopt,Trial Period,Reject,On Hold',
            'estimated_cost_usd',      # number
            'justification',
            'remarks',
        ]
    },
    {
        'task_id': 'm11',
        'category': 'm',
        'priority': 'med',
        'text': 'Conduct internal review meetings with development and operations teams',
        'fields_schema': [
            'meeting_date',
            'attendees_count',         # number
            'agenda_items',            # text
            'action_items',            # text
            'decisions_made',          # text
            'blockers_raised',         # text
            'next_meeting_date',
            'remarks',
        ]
    },
]


class Command(BaseCommand):
    help = 'Seed all TaskDefinitions (Daily/Weekly/Monthly) with field schemas'

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for task_def in TASK_DEFINITIONS:
            obj, was_created = TaskDefinition.objects.update_or_create(
                task_id=task_def['task_id'],
                defaults={
                    'text': task_def['text'],
                    'category': task_def['category'],
                    'priority': task_def['priority'],
                    'fields_schema': task_def['fields_schema'],
                    'is_active': True,
                }
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  [CREATED] [{obj.task_id}] {obj.text[:60]}'))
            else:
                updated += 1
                self.stdout.write(self.style.WARNING(f'  [UPDATED] [{obj.task_id}] {obj.text[:60]}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done! {created} created, {updated} updated. '
            f'Total: {created + updated} task definitions.'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Daily: {sum(1 for t in TASK_DEFINITIONS if t["category"] == "d")} tasks | '
            f'Weekly: {sum(1 for t in TASK_DEFINITIONS if t["category"] == "w")} tasks | '
            f'Monthly: {sum(1 for t in TASK_DEFINITIONS if t["category"] == "m")} tasks'
        ))