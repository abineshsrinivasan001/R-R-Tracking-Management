import sys
from django.core.management.base import BaseCommand
from django.utils import timezone
from tracker.models import Server
from tracker.monitoring import probe_single_server, run_all_server_checks


class Command(BaseCommand):
    help = 'Runs daily automated health checks for all registered servers via SSH & TCP socket'

    def add_arguments(self, parser):
        parser.add_argument(
            '--server-id',
            type=int,
            help='Run check for a specific server by ID',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Check all registered servers instead of only important ones',
        )
        parser.add_argument(
            '--timeout',
            type=float,
            default=6.0,
            help='SSH/TCP timeout in seconds (default: 6.0)',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress standard output except errors',
        )

    def handle(self, *args, **options):
        server_id = options.get('server_id')
        timeout = options.get('timeout')
        quiet = options.get('quiet')
        check_all = options.get('all')

        now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S')

        if server_id:
            server = Server.objects.filter(id=server_id).first()
            if not server:
                self.stderr.write(self.style.ERROR(f"Server with ID {server_id} not found."))
                sys.exit(1)
            servers = [server]
            scope_label = f"Single Server #{server_id}"
        elif check_all:
            servers = list(Server.objects.all().order_by('id'))
            scope_label = "All Registered Servers"
        else:
            servers = list(Server.objects.filter(favorited_by_devs__isnull=False).distinct().order_by('id'))
            scope_label = "Important Servers Only"

        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING("\n========================================================"))
            self.stdout.write(self.style.MIGRATE_HEADING(f"   [*] Daily Server Health Monitor ({scope_label}) - {now_str}"))
            self.stdout.write(self.style.MIGRATE_HEADING("========================================================\n"))

        if not servers:
            if not quiet:
                self.stdout.write(self.style.WARNING("No servers matching criteria found."))
            return

        success_count = 0
        warning_count = 0
        critical_count = 0
        failed_count = 0

        for server in servers:
            if not quiet:
                self.stdout.write(f"Checking [{server.id}] {server.name} ({server.ip_address or 'No IP'})...", ending=' ')

            res = probe_single_server(server, timeout=timeout)

            if res.get('is_up') and res.get('saved'):
                metrics = res.get('metrics', {})
                h_status = res.get('health_status', 'normal')
                latency = f"{res.get('latency_ms')}ms" if res.get('latency_ms') else "N/A"
                cpu = f"{metrics.get('cpu_usage')}%"
                ram = f"{metrics.get('memory_usage')}%"
                disk = f"{metrics.get('disk_usage')}%"
                docker = f"{metrics.get('docker_running', 0)} run"
                if metrics.get('docker_failed', 0) > 0:
                    docker += f", {metrics['docker_failed']} fail"

                if h_status == 'critical':
                    critical_count += 1
                    status_styled = self.style.ERROR(f"CRITICAL ({latency})")
                elif h_status == 'warning':
                    warning_count += 1
                    status_styled = self.style.WARNING(f"WARNING ({latency})")
                else:
                    success_count += 1
                    status_styled = self.style.SUCCESS(f"OK ({latency})")

                if not quiet:
                    self.stdout.write(f"[{status_styled}] CPU: {cpu} | RAM: {ram} | Disk: {disk} | Docker: {docker}")

            elif res.get('is_up'):
                # Up but SSH metrics failed or credentials missing
                warning_count += 1
                err_msg = res.get('error') or 'Metrics incomplete'
                if not quiet:
                    self.stdout.write(self.style.WARNING(f"[UP - NO METRICS] ({res.get('latency_ms')}ms) - {err_msg}"))

            else:
                # Down or unreachable
                failed_count += 1
                err_msg = res.get('error') or 'Unreachable'
                if not quiet:
                    self.stdout.write(self.style.ERROR(f"[DOWN] - {err_msg}"))

        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n--------------------------------------------------------"))
            self.stdout.write(f"Total Servers Checked: {len(servers)}")
            self.stdout.write(self.style.SUCCESS(f"  Operational (Normal): {success_count}"))
            if warning_count:
                self.stdout.write(self.style.WARNING(f"  Warning:              {warning_count}"))
            if critical_count:
                self.stdout.write(self.style.ERROR(f"  Critical:             {critical_count}"))
            if failed_count:
                self.stdout.write(self.style.ERROR(f"  Down / Unreachable:   {failed_count}"))
            self.stdout.write(self.style.MIGRATE_HEADING(f"--------------------------------------------------------\n"))
