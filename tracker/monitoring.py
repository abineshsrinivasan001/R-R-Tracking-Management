"""
Server Monitoring Service
Handles TCP reachability, SSH-based metric collection via Paramiko,
database persistence into ServerHealthEntry, and automated TaskLog completion.
"""

import socket
import time
import re
import paramiko
from django.utils import timezone
from django.contrib.auth.models import User
from .models import (
    Server, ServerStatusHistory, ServerHealthEntry,
    TaskLog, GeneralTaskEntry, TaskDefinition, AlertCheckEntry
)


def check_tcp_liveness(ip_address, port=22, timeout=3.0):
    """
    Performs a fast TCP socket connection check.
    Returns: (is_up: bool, latency_ms: int or None, error_message: str or None)
    """
    if not ip_address:
        return False, None, "No IP address provided"

    start_time = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip_address, int(port or 22)))
        latency_ms = max(1, round((time.time() - start_time) * 1000))
        sock.close()
        return True, latency_ms, None
    except socket.timeout:
        return False, None, "Connection timed out"
    except ConnectionRefusedError:
        return False, None, "Connection refused (Port closed or firewalled)"
    except Exception as e:
        return False, None, str(e)
    finally:
        sock.close()


DIAGNOSTIC_COMMAND = r"""
# Take initial snapshot of /proc/stat and network interfaces
C1=$(grep "^cpu " /proc/stat 2>/dev/null)
IFACE=$(ls /sys/class/net 2>/dev/null | grep -E '^(ens|eth|enp|eno)[0-9]' | head -1)
if [ -n "$IFACE" ]; then
  R1=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
  T1=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
fi

# Sleep 1 second for true delta sampling
sleep 1

# Take second snapshot of /proc/stat and network
C2=$(grep "^cpu " /proc/stat 2>/dev/null)
if [ -n "$IFACE" ]; then
  R2=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
  T2=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
fi

echo "===CPU==="
# Calculate CPU % from /proc/stat jiffies delta (Total - Idle) / Total
(echo "$C1 $C2" | awk '{
  u1=$2; n1=$3; s1=$4; i1=$5; w1=$6; q1=$7; sq1=$8; st1=$9;
  u2=$13; n2=$14; s2=$15; i2=$16; w2=$17; q2=$18; sq2=$19; st2=$20;
  idle1 = i1 + w1;
  idle2 = i2 + w2;
  total1 = u1 + n1 + s1 + i1 + w1 + q1 + sq1 + st1;
  total2 = u2 + n2 + s2 + i2 + w2 + q2 + sq2 + st2;
  dt = total2 - total1;
  di = idle2 - idle1;
  if (dt > 0) {
    pct = ((dt - di) / dt) * 100;
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    printf "%.1f\n", pct;
  } else {
    exit 1;
  }
}') 2>/dev/null || (top -bn1 | grep -i "Cpu(s)" | awk -F',' '{for(i=1;i<=NF;i++) if($i ~ /id/) {gsub(/[^0-9.]/,"",$i); print 100 - $i; exit}}') 2>/dev/null || echo "0"

echo "===MEM==="
# Free memory in MB
free -m 2>/dev/null | awk '
  /^Mem:/ {print $2, $7, $3, $4}
  /^Swap:/ {print $2, $3}
'

echo "===DISK==="
# Root disk usage
df -m / 2>/dev/null | awk 'NR==2 {print $2, $3, $5}'

echo "===LOAD==="
cat /proc/loadavg 2>/dev/null | awk '{print $1, $2, $3}'

echo "===UPTIME==="
(uptime -p 2>/dev/null || uptime) 2>/dev/null

echo "===DOCKER==="
(docker ps -q 2>/dev/null | wc -l) || echo "0"
(docker ps -a --filter "status=exited" -q 2>/dev/null | wc -l) || echo "0"

echo "===FAILCONTAINERS==="
(docker ps -a --filter "status=exited" --format "{{.Names}}" 2>/dev/null | head -5) || echo ""

echo "===TOPPROC==="
(ps -eo comm,%cpu --sort=-%cpu 2>/dev/null | head -2 | tail -1) || echo ""

echo "===NET==="
cat /proc/net/dev 2>/dev/null

echo "===NETRATE==="
if [ -n "$IFACE" ]; then
  echo "$R1 $T1 $R2 $T2" | awk '{
    rx_b = $3 - $1;
    tx_b = $4 - $2;
    total_bps = (rx_b + tx_b) * 8;
    mbps = total_bps / 1000000;
    pct = (mbps / 1000) * 100;
    if (pct > 100) pct = 100;
    if (pct < 0.01 && mbps > 0) pct = 0.01;
    printf "%.2f %.2f\n", pct, mbps;
  }' 2>/dev/null || echo "0.0 0.0"
else
  echo "0.0 0.0"
fi

echo "===HW==="
nproc 2>/dev/null || echo ""
uname -sr 2>/dev/null || echo ""
"""


def parse_telemetry_output(raw_output):
    """
    Parses the combined diagnostic shell output into structured metrics.
    """
    sections = {}
    current_key = None
    lines = raw_output.splitlines()

    for line in lines:
        line_stripped = line.strip()
        match = re.match(r"^===([A-Z0-9_]+)===$", line_stripped)
        if match:
            current_key = match.group(1)
            sections[current_key] = []
        elif current_key:
            sections[current_key].append(line_stripped)

    metrics = {
        'cpu_usage': 0.0,
        'memory_usage': 0.0,
        'disk_usage': 0.0,
        'swap_usage': '0 MB / 0 MB (0%)',
        'load_average': '0.00 0.00 0.00',
        'uptime': 'N/A',
        'network_rx_tx': 'RX: 0.0 MB | TX: 0.0 MB',
        'network_utilization': 0.0,
        'network_mbps': 0.0,
        'docker_running': 0,
        'docker_failed': 0,
        'docker_failed_names': '',
        'top_process': '',
        'cpu_cores': None,
        'total_ram': None,
        'total_disk': None,
        'os_version': None,
    }

    # 1. CPU
    if 'CPU' in sections and sections['CPU']:
        for val in sections['CPU']:
            try:
                cpu_val = float(val)
                if 0 <= cpu_val <= 100:
                    metrics['cpu_usage'] = round(cpu_val, 1)
                    break
            except (ValueError, TypeError):
                continue

    # 2. Memory
    if 'MEM' in sections and sections['MEM']:
        mem_lines = [l for l in sections['MEM'] if l]
        if len(mem_lines) >= 1:
            try:
                parts = mem_lines[0].split()
                if len(parts) >= 2:
                    total_mb = float(parts[0])
                    avail_mb = float(parts[1]) if len(parts) >= 2 else (total_mb - float(parts[2]))
                    if total_mb > 0:
                        used_pct = ((total_mb - avail_mb) / total_mb) * 100
                        metrics['memory_usage'] = round(max(0.0, min(100.0, used_pct)), 1)
                        if total_mb >= 1024:
                            metrics['total_ram'] = f"{round(total_mb / 1024, 1)} GB"
                        else:
                            metrics['total_ram'] = f"{int(total_mb)} MB"
            except (ValueError, TypeError, IndexError):
                pass

        if len(mem_lines) >= 2:
            try:
                parts = mem_lines[1].split()
                if len(parts) >= 2:
                    swap_total = float(parts[0])
                    swap_used = float(parts[1])
                    if swap_total > 0:
                        pct = round((swap_used / swap_total) * 100)
                        metrics['swap_usage'] = f"{int(swap_used)} MB / {int(swap_total)} MB ({pct}%)"
                    else:
                        metrics['swap_usage'] = "Disabled / None"
            except (ValueError, TypeError, IndexError):
                pass

    # 3. Disk
    if 'DISK' in sections and sections['DISK']:
        for l in sections['DISK']:
            parts = l.split()
            if len(parts) >= 3:
                try:
                    total_m = float(parts[0])
                    pct_str = parts[2].replace('%', '')
                    metrics['disk_usage'] = round(float(pct_str), 1)
                    if total_m >= 1024:
                        metrics['total_disk'] = f"{round(total_m / 1024, 1)} GB"
                    else:
                        metrics['total_disk'] = f"{int(total_m)} MB"
                    break
                except (ValueError, TypeError):
                    continue

    # 4. Load Average
    if 'LOAD' in sections and sections['LOAD']:
        load_line = ' '.join(sections['LOAD']).strip()
        if load_line:
            metrics['load_average'] = load_line

    # 5. Uptime
    if 'UPTIME' in sections and sections['UPTIME']:
        uptime_line = ' '.join(sections['UPTIME']).strip()
        if uptime_line:
            # Clean up uptime string
            cleaned = uptime_line.replace('up ', '').strip()
            metrics['uptime'] = cleaned if cleaned else uptime_line

    # 6. Docker
    if 'DOCKER' in sections and sections['DOCKER']:
        docker_lines = [l for l in sections['DOCKER'] if l.isdigit()]
        if len(docker_lines) >= 1:
            metrics['docker_running'] = int(docker_lines[0])
        if len(docker_lines) >= 2:
            metrics['docker_failed'] = int(docker_lines[1])

    # 7. Network
    if 'NET' in sections and sections['NET']:
        rx_total = 0
        tx_total = 0
        for l in sections['NET']:
            if ':' in l and 'lo:' not in l:
                try:
                    _, data = l.split(':', 1)
                    cols = data.split()
                    if len(cols) >= 9:
                        rx_total += int(cols[0])
                        tx_total += int(cols[8])
                except (ValueError, IndexError):
                    continue
        if rx_total > 0 or tx_total > 0:
            rx_mb = rx_total / (1024 * 1024)
            tx_mb = tx_total / (1024 * 1024)
            metrics['network_rx_tx'] = f"RX: {rx_mb:.1f} MB | TX: {tx_mb:.1f} MB"

    # 7b. Network Rate & Utilization
    if 'NETRATE' in sections and sections['NETRATE']:
        for l in sections['NETRATE']:
            parts = l.strip().split()
            if len(parts) >= 2:
                try:
                    pct = float(parts[0].replace('%', ''))
                    mbps = float(parts[1])
                    metrics['network_utilization'] = round(pct, 2)
                    metrics['network_mbps'] = round(mbps, 2)
                    if mbps > 0:
                        metrics['network_rx_tx'] = f"{mbps:.2f} Mbps · " + metrics['network_rx_tx']
                    break
                except (ValueError, TypeError):
                    continue

    # 8. Hardware details
    if 'HW' in sections and sections['HW']:
        hw_lines = [l for l in sections['HW'] if l]
        if len(hw_lines) >= 1 and hw_lines[0].isdigit():
            metrics['cpu_cores'] = int(hw_lines[0])
        if len(hw_lines) >= 2:
            metrics['os_version'] = hw_lines[1]

    # 9. Failed Container Names
    if 'FAILCONTAINERS' in sections and sections['FAILCONTAINERS']:
        names = [n.strip() for n in sections['FAILCONTAINERS'] if n.strip() and not n.startswith('===')]
        if names:
            metrics['docker_failed_names'] = ', '.join(names[:3])

    # 10. Top CPU Process
    if 'TOPPROC' in sections and sections['TOPPROC']:
        for l in sections['TOPPROC']:
            l_clean = l.strip()
            if l_clean and not l_clean.startswith('==='):
                metrics['top_process'] = l_clean
                break

    return metrics


def probe_single_server(server, timeout=6.0, user=None):
    """
    Probes an individual server via TCP and SSH, parses metrics,
    and updates the database.
    
    Returns: dict with probe results
    """
    result = {
        'server_id': server.id,
        'server_name': server.name,
        'ip_address': server.ip_address,
        'is_up': False,
        'latency_ms': None,
        'error': None,
        'metrics': None,
        'saved': False,
    }

    if not server.ip_address:
        result['error'] = "Server has no IP address configured"
        return result

    port = server.port_number or 22

    # Step 1: TCP Port Liveness Check
    is_up, latency_ms, tcp_error = check_tcp_liveness(server.ip_address, port=port, timeout=min(timeout, 3.0))
    result['latency_ms'] = latency_ms

    if not is_up:
        result['error'] = f"TCP reachability failed: {tcp_error}"
        # Update server status to down
        old_status = server.status
        server.status = 'down'
        server.last_checked = timezone.now()
        server.save()
        if old_status != 'down':
            ServerStatusHistory.objects.create(server=server, status='down', changed_by=user)
        return result

    result['is_up'] = True

    # Step 2: Check if credentials are present for SSH probe
    if not server.username or not server.server_password:
        # We can confirm it is UP via TCP, but cannot collect full OS metrics without credentials
        old_status = server.status
        server.status = 'up'
        server.last_checked = timezone.now()
        server.save()
        if old_status != 'up':
            ServerStatusHistory.objects.create(server=server, status='up', changed_by=user)
        result['error'] = "TCP is UP, but username or password missing for detailed metrics"
        return result

    # Step 3: Paramiko SSH Connection
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=server.ip_address,
            port=port,
            username=server.username,
            password=server.server_password,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout
        )

        stdin, stdout, stderr = client.exec_command(DIAGNOSTIC_COMMAND, timeout=timeout)
        raw_output = stdout.read().decode('utf-8', errors='replace')
        client.close()

        # Step 4: Parse Telemetry
        metrics = parse_telemetry_output(raw_output)
        result['metrics'] = metrics

        # Step 5: Save to Database
        save_result = save_telemetry_to_db(server, metrics, latency_ms=latency_ms, user=user)
        result['saved'] = save_result.get('success', False)
        result['health_status'] = save_result.get('health_status', 'normal')

    except paramiko.AuthenticationException:
        result['error'] = "SSH Authentication failed: Invalid username or password"
        server.status = 'up'  # Reachable, but auth failed
        server.last_checked = timezone.now()
        server.save()
    except paramiko.SSHException as e:
        result['error'] = f"SSH error: {e}"
    except socket.timeout:
        result['error'] = "SSH command execution timed out"
    except Exception as e:
        result['error'] = f"Unexpected error during probe: {e}"
    finally:
        try:
            client.close()
        except Exception:
            pass

    return result


def save_telemetry_to_db(server, metrics, latency_ms=None, user=None):
    """
    Saves parsed metrics into Server, ServerHealthEntry, and auto-completes TaskLog for d01.
    """
    today = timezone.now().date()
    target_user = user or server.owner or User.objects.filter(is_superuser=True).first()

    # 1. Enrich static hardware info if missing
    updated_fields = ['last_checked', 'status']
    server.last_checked = timezone.now()

    if metrics.get('cpu_cores') and not server.cpu_cores:
        server.cpu_cores = metrics['cpu_cores']
        updated_fields.append('cpu_cores')
    if metrics.get('total_ram') and not server.total_ram:
        server.total_ram = metrics['total_ram']
        updated_fields.append('total_ram')
    if metrics.get('total_disk') and not server.total_disk:
        server.total_disk = metrics['total_disk']
        updated_fields.append('total_disk')
    if metrics.get('os_version') and not server.os_version:
        server.os_version = metrics['os_version']
        updated_fields.append('os_version')

    # Determine Health Status based on thresholds
    cpu = metrics.get('cpu_usage', 0.0)
    mem = metrics.get('memory_usage', 0.0)
    disk = metrics.get('disk_usage', 0.0)
    docker_failed = metrics.get('docker_failed', 0)
    docker_running = metrics.get('docker_running', 0)

    if cpu >= 90.0 or disk >= 90.0 or mem >= 95.0:
        health_status = 'critical'
    elif cpu >= 75.0 or disk >= 80.0 or mem >= 85.0 or docker_failed > 0:
        health_status = 'warning'
    else:
        health_status = 'normal'

    old_status = server.status
    server.status = 'up'
    server.save(update_fields=list(set(updated_fields)))

    if old_status != 'up':
        ServerStatusHistory.objects.create(server=server, status='up', changed_by=target_user)

    # 2. Update or Create ServerHealthEntry
    issue_found = (health_status != 'normal')
    failed_names = metrics.get('docker_failed_names', '')
    top_proc = metrics.get('top_process', '')

    action_taken = "Automated daily monitoring probe completed successfully."
    if issue_found:
        details_list = []
        if cpu >= 75: details_list.append(f"CPU: {cpu}%")
        if mem >= 85: details_list.append(f"RAM: {mem}%")
        if disk >= 80: details_list.append(f"Disk: {disk}%")
        if docker_failed > 0: details_list.append(f"Failed Containers: {docker_failed} ({failed_names})" if failed_names else f"Failed Containers: {docker_failed}")
        action_taken = f"Automated Alert: {', '.join(details_list)}."

    remarks = f"Automated probe at {timezone.now().strftime('%H:%M:%S')}"
    if latency_ms:
        remarks += f" (Latency: {latency_ms}ms)"
    if failed_names:
        remarks += f" | Crashed: {failed_names}"
    if top_proc:
        remarks += f" | Top CPU: {top_proc}"

    health_entry, _ = ServerHealthEntry.objects.update_or_create(
        server_name=server.name,
        date=today,
        defaults={
            'developer': target_user,
            'cpu_usage': cpu,
            'memory_usage': mem,
            'disk_usage': disk,
            'network_utilization': metrics.get('network_utilization', 0.0),
            'status': health_status,
            'issue_found': issue_found,
            'action_taken': action_taken,
            'remarks': remarks,
            'network_rx_tx': metrics.get('network_rx_tx', ''),
            'load_average': metrics.get('load_average', ''),
            'uptime': metrics.get('uptime', ''),
            'swap_usage': metrics.get('swap_usage', ''),
            'docker_running': metrics.get('docker_running', 0),
            'docker_failed': docker_failed,
        }
    )

    # 3. Auto-complete Tasks in TaskLog & GeneralTaskEntry for all assigned developers
    users_to_log = set()
    if target_user:
        users_to_log.add(target_user)
    if server.owner:
        users_to_log.add(server.owner)
    for u in server.assigned_users.all():
        users_to_log.add(u)

    now_time_str = timezone.now().strftime('%H:%M:%S')

    # 3a. Auto-log 'd01' ("Monitor Server Health")
    task_d01_text = TaskDefinition.objects.filter(task_id='d01').values_list('text', flat=True).first() or 'Monitor Server Health'
    for u in users_to_log:
        TaskLog.objects.update_or_create(
            developer=u,
            server=server,
            task_id='d01',
            logged_at__date=today,
            defaults={
                'task_text': task_d01_text,
                'category': 'd',
                'status': 'done',
                'notes': f"Auto-checked: CPU {cpu}%, RAM {mem}%, Disk {disk}%, Net {metrics.get('network_utilization', 0.0)}%, Uptime: {metrics.get('uptime', 'N/A')}",
                'observations': f"Load: {metrics.get('load_average', 'N/A')}, Docker: {metrics.get('docker_running', 0)} run" + (f", Top: {top_proc}" if top_proc else ""),
                'action_taken': action_taken,
                'outcome': f"Server status: {health_status.upper()}",
                'logged_at': timezone.now()
            }
        )
        GeneralTaskEntry.objects.update_or_create(
            developer=u,
            server=server,
            task_id='d01',
            date=today,
            defaults={
                'task_text': task_d01_text,
                'status': 'done',
                'fields_data': {
                    'cpu_usage': f"{cpu}%",
                    'memory_usage': f"{mem}%",
                    'disk_usage': f"{disk}%",
                    'network_utilization': f"{metrics.get('network_utilization', 0.0)}%",
                    'status': health_status.capitalize(),
                    'issue_found': 'Yes' if issue_found else 'No',
                    'load_average': metrics.get('load_average', ''),
                    'uptime': metrics.get('uptime', ''),
                    'swap_usage': metrics.get('swap_usage', ''),
                    'docker_running': metrics.get('docker_running', 0),
                    'docker_failed': docker_failed,
                    'network_rx_tx': metrics.get('network_rx_tx', ''),
                },
                'remarks': remarks
            }
        )

        # 3b. Auto-log 'd08' ("Verify container orchestration health")
        task_d08_text = TaskDefinition.objects.filter(task_id='d08').values_list('text', flat=True).first() or 'Verify container orchestration health'
        d08_issue = f"Exited: {failed_names}" if failed_names else ("Issues found" if docker_failed > 0 else "None")
        d08_action = f"Alert: Exited containers ({failed_names})" if failed_names else "Automated container check passed"
        d08_remarks = f"{docker_running} running, {docker_failed} failed"
        TaskLog.objects.update_or_create(
            developer=u,
            server=server,
            task_id='d08',
            logged_at__date=today,
            defaults={
                'task_text': task_d08_text,
                'category': 'd',
                'status': 'done',
                'notes': f"Docker Audit: {docker_running} running, {docker_failed} failed" + (f" ({failed_names})" if failed_names else ""),
                'observations': f"Containers verified on {server.name}",
                'action_taken': d08_action,
                'outcome': 'Issues Found' if docker_failed > 0 else 'All Running',
                'logged_at': timezone.now()
            }
        )
        GeneralTaskEntry.objects.update_or_create(
            developer=u,
            server=server,
            task_id='d08',
            date=today,
            defaults={
                'task_text': task_d08_text,
                'status': 'done',
                'fields_data': {
                    'platform': 'Docker',
                    'total_pods_containers': docker_running + docker_failed,
                    'running_count': docker_running,
                    'failed_count': docker_failed,
                    'restarting_count': 0,
                    'namespace': 'default',
                    'issue_description': d08_issue,
                    'action_taken': d08_action,
                    'remarks': d08_remarks
                },
                'remarks': f"Automated container audit at {now_time_str}"
            }
        )

        # 3c. Auto-log 'd11' ("Check disk usage and clean temporary / log files if required")
        task_d11_text = TaskDefinition.objects.filter(task_id='d11').values_list('text', flat=True).first() or 'Check disk usage'
        d11_action = "Automated partition check passed" if disk < 80 else f"Alert: Root partition at {disk}%"
        TaskLog.objects.update_or_create(
            developer=u,
            server=server,
            task_id='d11',
            logged_at__date=today,
            defaults={
                'task_text': task_d11_text,
                'category': 'd',
                'status': 'done',
                'notes': f"Disk check: {disk}% used ({metrics.get('total_disk', 'N/A')} total)",
                'observations': f"Root partition at {disk}%",
                'action_taken': d11_action,
                'outcome': 'Normal' if disk < 80 else 'Warning',
                'logged_at': timezone.now()
            }
        )
        GeneralTaskEntry.objects.update_or_create(
            developer=u,
            server=server,
            task_id='d11',
            date=today,
            defaults={
                'task_text': task_d11_text,
                'status': 'done',
                'fields_data': {
                    'partition_path': '/',
                    'usage_before_pct': f"{disk}%",
                    'usage_after_pct': f"{disk}%",
                    'space_freed_gb': 0,
                    'files_cleaned': 'Automated check - no cleanup needed' if disk < 80 else 'Inspection recommended',
                    'action_taken': d11_action,
                    'remarks': f"Total disk: {metrics.get('total_disk', 'N/A')}"
                },
                'remarks': f"Automated disk probe at {now_time_str}"
            }
        )

    # 4. Auto-log critical alerts if thresholds breached
    if health_status == 'critical' and target_user:
        AlertCheckEntry.objects.create(
            developer=target_user,
            server=server,
            date=today,
            tool_name='Daily Health Monitor',
            total_alerts=1,
            critical_alerts=1,
            warning_alerts=0,
            alert_description=f"Automated Alert for {server.name}: CPU {cpu}%, RAM {mem}%, Disk {disk}%. Requires immediate attention.",
            status='pending',
            action_taken='Automated alert created. Verification pending.'
        )

    return {'success': True, 'health_status': health_status, 'health_entry_id': health_entry.id}


def run_all_server_checks(verbose=False, target_user=None, important_only=True):
    """
    Iterates over servers, probes them, and returns a summary report.
    By default filters to servers marked as important or falls back to accessible servers.
    """
    from django.db.models import Q

    # Base server queryset according to user permissions
    is_mgmt = (
        not target_user 
        or target_user.is_superuser 
        or target_user.is_staff 
        or getattr(getattr(target_user, 'developer', None), 'role', None) in ('manager', 'tl')
    )
    if is_mgmt:
        base_servers = Server.objects.all()
    else:
        base_servers = Server.objects.filter(Q(owner=target_user) | Q(assigned_users=target_user)).distinct()

    if important_only:
        if target_user and hasattr(target_user, 'developer'):
            servers = base_servers.filter(favorited_by_devs=target_user.developer).distinct().order_by('id')
        else:
            servers = base_servers.filter(favorited_by_devs__isnull=False).distinct().order_by('id')

        # Fallback to all accessible servers if none are favorited
        if not servers.exists():
            servers = base_servers.order_by('id')
    else:
        servers = base_servers.order_by('id')

    summary = {
        'total': servers.count(),
        'successful': 0,
        'failed': 0,
        'results': []
    }

    for server in servers:
        probe_res = probe_single_server(server, timeout=6.0, user=target_user)
        is_ok = bool(probe_res.get('is_up'))
        if is_ok:
            summary['successful'] += 1
        else:
            summary['failed'] += 1
        summary['results'].append({
            'server_id': server.id,
            'server_name': server.name,
            'ip_address': server.ip_address,
            'is_up': probe_res.get('is_up', False),
            'latency_ms': probe_res.get('latency_ms'),
            'health_status': probe_res.get('health_status', 'normal' if is_ok else 'down'),
            'error': probe_res.get('error'),
        })

    return summary
