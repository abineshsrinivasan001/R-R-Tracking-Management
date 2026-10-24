from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count, Q, Avg
from django.contrib import messages
from django.contrib.auth.hashers import make_password
import json
import datetime
import csv

from .models import (
    TaskLog, ServerHealthEntry, AlertCheckEntry,
    PipelineEntry, DeploymentEntry, Developer, TaskDefinition,
    Server, GeneralTaskEntry
)
from .forms import (
    ServerHealthForm, AlertCheckForm,
    PipelineForm, DeploymentForm
)
from .decorators import manager_required, tl_or_manager_required

# Task → entry form mapping (can be moved to TaskDefinition model later if needed)
TASK_ENTRY_MAP = {
    'd01': ('server_health', 'Monitor Server Health'),
    'd02': ('alert_check', 'Check Application & Infrastructure Alerts'),
    'd03': ('pipeline', 'Review CI/CD Pipeline Status'),
    'd04': ('deployment', 'Validate Deployment of Releases'),
}

def get_dynamic_tasks(server=None):
    qs = TaskDefinition.objects.filter(is_active=True)
    if server:
        qs = qs.filter(Q(apply_to_all=True) | Q(servers=server)).distinct()

    tasks = {
        'd': list(qs.filter(category='d').values('task_id', 'text', 'priority', 'fields_schema')),
        'w': list(qs.filter(category='w').values('task_id', 'text', 'priority', 'fields_schema')),
        'm': list(qs.filter(category='m').values('task_id', 'text', 'priority', 'fields_schema')),
    }
    # Rename priority to pri for template compatibility
    for cat in tasks:
        for t in tasks[cat]:
            t['id'] = t.pop('task_id')
            t['pri'] = t.pop('priority')
            t['fields'] = t.pop('fields_schema')
    return tasks


@login_required
@require_POST
def delete_server_view(request, server_id):
    """Dedicated endpoint: Manager/TL/Superuser can delete a server."""
    user = request.user
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    if viewer_role not in ('manager', 'tl'):
        messages.error(request, 'Access denied — only Manager or TL can remove servers.')
        return redirect('dashboard')

    server = Server.objects.filter(id=server_id).first()
    if server:
        name = server.name
        server.delete()
        messages.success(request, f'Server "{name}" removed successfully.')
    else:
        messages.error(request, 'Server not found.')

    # Redirect back to wherever the request came from
    referer = request.META.get('HTTP_REFERER', '')
    if 'manager' in referer:
        return redirect('manager_dashboard')
    return redirect('dashboard')


@login_required
def task_log_filter(request):
    """Log history with date/category/status filters — for all roles."""
    user = request.user
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    # ── Filter params ────────────────────────────────────────────
    date_from_str = request.GET.get('date_from', '')
    date_to_str   = request.GET.get('date_to', '')
    category      = request.GET.get('category', '')      # d / w / m / ''
    week_val      = request.GET.get('week_val', '')      # e.g. 2026-W32
    month_val     = request.GET.get('month_val', '')     # e.g. 2026-08
    status        = request.GET.get('status', '')         # done / wip / blk / miss / ''
    server_id     = request.GET.get('server_id', '')
    developer_id  = request.GET.get('developer_id', '')  # manager/TL only

    today = timezone.now().date()

    if viewer_role in ('manager', 'tl'):
        qs = TaskLog.objects.select_related('developer', 'server').order_by('-logged_at')
    else:
        qs = TaskLog.objects.filter(developer=user).select_related('developer', 'server').order_by('-logged_at')

    # Apply filters
    if category == 'w' and week_val:
        try:
            from datetime import datetime, timedelta
            # Parse ISO week, e.g. '2026-W32'. '%G' is ISO year, '%V' is ISO week, '%u' is day (1=Mon)
            start_date = datetime.strptime(week_val + '-1', "%G-W%V-%u").date()
            end_date = start_date + timedelta(days=6)
            qs = qs.filter(logged_at__date__gte=start_date, logged_at__date__lte=end_date)
        except Exception:
            pass
    elif category == 'm' and month_val:
        try:
            y, m = map(int, month_val.split('-'))
            qs = qs.filter(logged_at__date__year=y, logged_at__date__month=m)
        except Exception:
            pass
    else:
        if date_from_str:
            try:
                qs = qs.filter(logged_at__date__gte=date_from_str)
            except Exception:
                pass
        if date_to_str:
            try:
                qs = qs.filter(logged_at__date__lte=date_to_str)
            except Exception:
                pass
    if category:
        qs = qs.filter(category=category)
    if status:
        qs = qs.filter(status=status)
    if server_id:
        qs = qs.filter(server_id=server_id)
    # Developer filter — only for manager/TL roles
    if developer_id and viewer_role in ('manager', 'tl'):
        qs = qs.filter(developer_id=developer_id)

    # Quick summary cards for the filtered set
    total   = qs.count()
    done    = qs.filter(status='done').count()
    blocked = qs.filter(status='blk').count()
    pending = qs.filter(status='wip').count()

    # Servers list for dropdown
    if viewer_role in ('manager', 'tl'):
        servers = Server.objects.all()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        developers = User.objects.filter(
            developer__isnull=False
        ).select_related('developer').order_by('first_name', 'last_name', 'username')
    else:
        servers = Server.objects.filter(Q(owner=user) | Q(assigned_users=user)).distinct()
        developers = []

    context = {
        'logs': qs[:500],
        'viewer_role': viewer_role,
        'today': today,
        'servers': servers,
        'developers': developers,
        # active filters (to repopulate form)
        'f_date_from': date_from_str,
        'f_date_to': date_to_str,
        'f_week': week_val,
        'f_month': month_val,
        'f_category': category,
        'f_status': status,
        'f_server_id': server_id,
        'f_developer_id': developer_id,
        # summary
        'total': total,
        'done': done,
        'blocked': blocked,
        'pending': pending,
    }
    return render(request, 'tracker/task_log_filter.html', context)


@login_required
def get_log_details(request, log_id):
    """AJAX endpoint: returns the full details (telemetry) for a specific log entry."""
    user = request.user
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    log = get_object_or_404(TaskLog, id=log_id)
    
    # Access check: Managers/TLs see all; developers see only their own or their owned server's logs
    if viewer_role not in ('manager', 'tl'):
        if log.developer != user and log.server and log.server.owner != user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Find the GeneralTaskEntry for this specific submission
    # We use date, server, task_id, and developer to match
    entry = GeneralTaskEntry.objects.filter(
        server=log.server,
        task_id=log.task_id,
        date=log.logged_at.date(),
        developer=log.developer
    ).order_by('-created_at').first()

    return JsonResponse({
        'id': log.id,
        'task_id': log.task_id,
        'task_text': log.task_text,
        'developer': log.developer.get_full_name() or log.developer.username,
        'server': log.server.name if log.server else 'N/A',
        'logged_at': log.logged_at.strftime('%d %b %Y %H:%M'),
        'status': log.get_status_display(),
        'notes': log.notes,
        'observations': log.observations,
        'action_taken': log.action_taken,
        'outcome': log.outcome,
        'fields_data': entry.fields_data if entry else {},
        'remarks': entry.remarks if entry else ''
    })


@login_required
def dashboard(request):
    user = request.user
    today = timezone.now().date()
    # Role-based check: Superusers/Staff are managers; otherwise check developer role.
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete_server' and viewer_role == 'manager':
            server_id = request.POST.get('server_id')
            server = Server.objects.filter(id=server_id).first()
            if server:
                name = server.name
                server.delete()
                messages.success(request, f'Server "{name}" removed successfully.')
            return redirect('dashboard')

    today_logs = TaskLog.objects.filter(developer=user, logged_at__date=today)
    logged_ids = {log.task_id: log.status for log in today_logs}

    # For the UI overall lists, we still want a global task list 
    # to show the user all possible tasks, or we can just fetch all active tasks.
    task_data = get_dynamic_tasks()
    
    # Global 'done' calculations based on all logs today for this user
    daily_done = sum(1 for t in task_data['d'] if logged_ids.get(t['id']) == 'done')
    weekly_done = sum(1 for t in task_data['w'] if logged_ids.get(t['id']) == 'done')
    monthly_done = sum(1 for t in task_data['m'] if logged_ids.get(t['id']) == 'done')

    recent_logs = TaskLog.objects.filter(developer=user).select_related('developer', 'server')[:20]

    # Server visibility logic:
    # Managers and TLs see everything; Developers see only their assigned servers.
    if viewer_role in ['manager', 'tl']:
        servers = Server.objects.all()
        all_logs = TaskLog.objects.all().select_related('developer', 'server').order_by('-logged_at')[:50]
    else:
        servers = Server.objects.filter(Q(owner=request.user) | Q(assigned_users=request.user)).distinct()
        all_logs = TaskLog.objects.filter(Q(developer=user) | Q(server__owner=user) | Q(server__assigned_users=user)).distinct().select_related('developer', 'server').order_by('-logged_at')[:50]
    
    important_server_ids = []
    if hasattr(user, 'developer'):
        important_server_ids = list(user.developer.important_servers.values_list('id', flat=True))

    server_list = []
    overall_weekly_done = 0
    overall_monthly_done = 0
    total_needed_today = 0
    total_needed_weekly = 0
    total_needed_monthly = 0
    done_today_count = 0

    for s in servers:
        s_task_data = get_dynamic_tasks(s)
        d_total = len(s_task_data['d'])
        w_total = len(s_task_data['w'])
        m_total = len(s_task_data['m'])
        
        total_needed_today += d_total
        total_needed_weekly += w_total
        total_needed_monthly += m_total

        # ── DAILY: tasks completed TODAY ─────────────────────
        s_done_d = TaskLog.objects.filter(
            server=s, category='d', logged_at__date=today, status='done'
        ).values('task_id').distinct().count()

        done_today_count += s_done_d

        # ── WEEKLY: tasks completed THIS WEEK (Mon to today) ─
        week_start = today - datetime.timedelta(days=today.weekday())  # Monday
        s_done_w = TaskLog.objects.filter(
            server=s, category='w',
            logged_at__date__gte=week_start,
            logged_at__date__lte=today,
            status='done'
        ).values('task_id').distinct().count()

        # ── MONTHLY: tasks completed THIS MONTH (1st to today) ─
        month_start = today.replace(day=1)
        s_done_m = TaskLog.objects.filter(
            server=s, category='m',
            logged_at__date__gte=month_start,
            logged_at__date__lte=today,
            status='done'
        ).values('task_id').distinct().count()

        overall_weekly_done += s_done_w
        overall_monthly_done += s_done_m

        latest_log = TaskLog.objects.filter(server=s).order_by('-logged_at').first()
        last_activity_dt = latest_log.logged_at if latest_log else None
        last_activity_str = latest_log.logged_at.isoformat() if latest_log else None

        server_list.append({
            'id': s.id,
            'name': s.name,
            'ip': s.ip_address,
            'port_number': s.port_number,
            'username': s.username or '',
            'server_password': s.server_password or '',
            'status': s.status,
            'last_checked': s.last_checked,
            'daily_pct':   min(100, round(s_done_d / d_total * 100)) if d_total else 100 if d_total == 0 else 0, # Handle 0 tasks
            'weekly_pct':  min(100, round(s_done_w / w_total * 100)) if w_total else 100 if w_total == 0 else 0,
            'monthly_pct': min(100, round(s_done_m / m_total * 100)) if m_total else 100 if m_total == 0 else 0,
            'daily_done':   s_done_d,
            'daily_total':  d_total,
            'weekly_done':  s_done_w,
            'weekly_total': w_total,
            'monthly_done':  s_done_m,
            'monthly_total': m_total,
            'is_important': s.id in important_server_ids,
            'last_activity_dt': last_activity_dt,
            'last_activity': last_activity_str,
            'history_7d': [],
        })

        # ── 7-day daily history for heatmap ──────────────────
        for i in range(6, -1, -1):
            day_target = today - datetime.timedelta(days=i)
            day_done = TaskLog.objects.filter(
                server=s, category='d',
                logged_at__date=day_target, status='done'
            ).values('task_id').distinct().count()
            day_pct = min(100, round(day_done / d_total * 100)) if d_total else 0
            server_list[-1]['history_7d'].append({
                'day': day_target.strftime('%a'),
                'pct': day_pct,
                'is_today': (i == 0)
            })

    # Team stats with real data
    team_members = []
    
    # Calculate total system daily needed by summing daily tasks for ALL servers
    all_servers = Server.objects.all()
    total_system_daily_needed = sum(len(get_dynamic_tasks(srv)['d']) for srv in all_servers)

    all_users = User.objects.filter(is_active=True).select_related('developer')
    for u in all_users:
        # Determine effective role identical to the rest of the dashboard
        if u.is_superuser or u.is_staff:
            role = 'manager'
        else:
            role = u.developer.role if hasattr(u, 'developer') else 'developer'

        if role in ('manager', 'tl'):
            u_servers = all_servers
            u_server_count = all_servers.count()
        else:
            u_servers = Server.objects.filter(Q(owner=u) | Q(assigned_users=u)).distinct()
            u_server_count = u_servers.count()
        
        # 1. Performance: Count tasks this person ACTUALLY performed today
        u_today_done = TaskLog.objects.filter(
            developer=u, category='d', logged_at__date=today, status='done',
            server__isnull=False
        ).values('server', 'task_id').distinct().count()
        
        # 2. Target Goal:
        if u_server_count > 0:
            u_total_daily = sum(len(get_dynamic_tasks(srv)['d']) for srv in u_servers)
        else:
            u_total_daily = total_system_daily_needed

        u_pct = min(100, round(u_today_done / u_total_daily * 100)) if u_total_daily else 0
        
        # Check if any tasks for servers they OWN are blocked
        has_blocked = TaskLog.objects.filter(
            server__owner=u, logged_at__date=today, status='blk'
        ).exists()

        if u_pct > 100: u_pct = 100

        team_members.append({
            'user': u,
            'initials': u.developer.initials if hasattr(u, 'developer') else u.username[:2].upper(),
            'role': u.developer.role if hasattr(u, 'developer') else 'Member',
            'gradient': u.developer.avatar_gradient if hasattr(u, 'developer') else 'linear-gradient(135deg,#64748b,#475569)',
            'daily_pct': u_pct,
            'server_count': u_server_count,
            'has_blocked': has_blocked,
            'weekly_pct': 0,
        })

    # Streak Calculation (Real consecutive days of 100% completion)
    streak = 0
    check_date = today
    # Base target for the user (only based on servers they own right now, historical might vary but we use current)
    user_servers = Server.objects.filter(Q(owner=user) | Q(assigned_users=user)).distinct()
    user_day_needed = sum(len(get_dynamic_tasks(srv)['d']) for srv in user_servers)

    while True:
        # Check if all tasks were done on this date
        day_done = TaskLog.objects.filter(
            developer=user, category='d', 
            logged_at__date=check_date, status='done',
            server__isnull=False
        ).values('server', 'task_id').distinct().count()
        
        if user_day_needed > 0 and day_done >= user_day_needed:
            streak += 1
            check_date -= datetime.timedelta(days=1)
        else:
            break
    
    daily_pct = min(100, round(done_today_count / total_needed_today * 100)) if total_needed_today else 100 if done_today_count > 0 else 0
    
    # --- COMPLIANCE BUCKETS FOR CIRCLE GRAPH ---
    compliance = {'full': 0, 'partial': 0, 'none': 0}
    for s in server_list:
        if s['daily_pct'] == 100:
            compliance['full'] += 1
        elif s['daily_pct'] > 0:
            compliance['partial'] += 1
        else:
            compliance['none'] += 1
    # -------------------------------------------
    # ---------------------------

    # Nodes needing attention (Critical/Down or not checked today)
    critical_nodes_count = Server.objects.filter(Q(status='down') | Q(status='maint')).count()
    blocked_count = TaskLog.objects.filter(developer=user, logged_at__date=today, status='blk').count()

    now = timezone.now()
    hour = timezone.localtime(now).hour if timezone.is_aware(now) else now.hour
    greeting = 'Morning' if hour < 12 else ('Afternoon' if hour < 17 else 'Evening')

    # --- TEAM STATS AGGREGATION ---
    active_members = [m for m in team_members if m['server_count'] > 0]
    team_avg = round(sum(m['daily_pct'] for m in active_members) / len(active_members)) if active_members else 0
    full_comp = sum(1 for m in active_members if m['daily_pct'] == 100)
    # Change "Needs Attention" to specifically count users with BLOCKED tasks (more meaningful than just 0% progress)
    needs_attn = sum(1 for m in team_members if m['has_blocked'])

    # ── 5 KPI STAT CARDS (REAL DATA ONLY) ──
    total_servers_count = len(server_list)
    operational_servers_count = sum(1 for s in server_list if s.get('status') == 'up')
    operational_pct = round(operational_servers_count / total_servers_count * 100) if total_servers_count else 0
    critical_servers_count = sum(1 for s in server_list if s.get('status') != 'up')
    critical_pct = round(critical_servers_count / total_servers_count * 100) if total_servers_count else 0

    # Weekly Important Tasks (4 core tasks per server: w01, w02, w07, w09)
    dev = getattr(user, 'developer', None)
    if dev and dev.important_tasks.filter(category='w').exists():
        w_task_ids = list(dev.important_tasks.filter(category='w').values_list('task_id', flat=True))
    else:
        w_task_ids = ['w01', 'w02', 'w07', 'w09']

    imp_subset = [s for s in server_list if s.get('is_important')]
    target_task_servers = imp_subset if imp_subset else server_list
    target_task_server_ids = [s['id'] for s in target_task_servers]

    start_of_week = today - datetime.timedelta(days=today.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)

    weekly_imp_tasks_total = len(target_task_servers) * len(w_task_ids)
    weekly_imp_tasks_done = TaskLog.objects.filter(
        server_id__in=target_task_server_ids,
        task_id__in=w_task_ids,
        category='w',
        status='done',
        logged_at__date__gte=start_of_week,
        logged_at__date__lte=end_of_week
    ).values('server_id', 'task_id').distinct().count()

    weekly_imp_tasks_pct = round(weekly_imp_tasks_done / weekly_imp_tasks_total * 100) if weekly_imp_tasks_total else 0

    # Last update: main trigger live probe timestamp
    latest_probe_srv = Server.objects.filter(last_checked__isnull=False).order_by('-last_checked').first()
    if latest_probe_srv and latest_probe_srv.last_checked:
        dt = latest_probe_srv.last_checked
        if dt.date() == today:
            last_updated_time = f"Today, {dt.strftime('%I:%M %p')}"
        else:
            last_updated_time = dt.strftime('%b %d, %I:%M %p')
    else:
        last_updated_time = f"Today, {timezone.now().strftime('%I:%M %p')}"

    context = {
        'task_data': task_data,
        'task_data_json': json.dumps(task_data),
        'logged_ids': logged_ids,
        'daily_done': done_today_count,
        'daily_total': total_needed_today,
        'daily_pct': daily_pct,
        'weekly_done': overall_weekly_done,
        'weekly_total': total_needed_weekly,
        'weekly_pct': round(overall_weekly_done / total_needed_weekly * 100) if total_needed_weekly else 100 if overall_weekly_done > 0 else 0,
        'monthly_done': overall_monthly_done,
        'monthly_total': total_needed_monthly,
        'monthly_pct': round(overall_monthly_done / total_needed_monthly * 100) if total_needed_monthly else 100 if overall_monthly_done > 0 else 0,
        'compliance': compliance,
        'recent_logs': recent_logs,
        'all_logs': all_logs,
        'team_members': team_members,  # Show all members as requested
        'team_avg': team_avg,
        'full_comp': full_comp,
        'needs_attn': needs_attn,
        'critical_nodes_count': critical_nodes_count,
        'blocked_count': blocked_count,
        'streak': streak,
        'today': today,
        'task_entry_map': TASK_ENTRY_MAP,
        'greeting': greeting,
        'servers': server_list,
        'important_servers_count': sum(1 for s in server_list if s.get('is_important')),
        'total_servers_count': total_servers_count,
        'operational_servers_count': operational_servers_count,
        'operational_pct': operational_pct,
        'critical_servers_count': critical_servers_count,
        'critical_pct': critical_pct,
        'weekly_imp_tasks_done': weekly_imp_tasks_done,
        'weekly_imp_tasks_total': weekly_imp_tasks_total,
        'weekly_imp_tasks_pct': weekly_imp_tasks_pct,
        'last_updated_time': last_updated_time,
        'viewer_role': viewer_role,
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
@require_POST
def log_task(request):
    data = json.loads(request.body)
    task_id = data.get('task_id')
    server_id = data.get('server_id')
    status = data.get('status')
    notes = data.get('notes', '')
    fields_data = data.get('fields_data', {})
    
    # Check for backdated entry
    log_date_str = data.get('log_date')
    today = timezone.now().date()
    logged_at_dt = timezone.now()
    if log_date_str:
        import datetime
        try:
            parsed_date = datetime.datetime.strptime(log_date_str, '%Y-%m-%d').date()
            if parsed_date <= today:
                today = parsed_date
                # Combine with noon time to give it a valid datetime on that past date
                naive_dt = datetime.datetime.combine(today, datetime.time(12, 0))
                logged_at_dt = timezone.make_aware(naive_dt) if timezone.is_aware(timezone.now()) else naive_dt
        except ValueError:
            pass
    
    server = Server.objects.filter(id=server_id).first() if server_id else None
    category = task_id[0] if task_id else 'd'
    task_text = TaskDefinition.objects.filter(task_id=task_id).values_list('text', flat=True).first() or ''

    # Update or create the main TaskLog for today
    log, _ = TaskLog.objects.update_or_create(
        developer=request.user,
        server=server,
        task_id=task_id,
        logged_at__date=today,
        defaults={
            'task_text': task_text,
            'category': category,
            'status': status,
            'notes': notes,
            'logged_at': logged_at_dt
        }
    )

    # Update or create the GeneralTaskEntry which holds the JSON fields for all verification results
    GeneralTaskEntry.objects.update_or_create(
        developer=request.user,
        server=server,
        task_id=task_id,
        date=today,
        defaults={
            'task_text': task_text,
            'status': status,
            'fields_data': fields_data,
            'remarks': notes
        }
    )

    # Automatically map 'd01' (Monitor Server Health) JSON fields to the ServerHealthEntry model
    # so the charts and KPI widgets get updated dynamically!
    if task_id == 'd01' and server:
        try:
            from .models import ServerHealthEntry
            # Safe parsing function
            def parse_float(val):
                try:
                    return float(str(val).strip('%').strip())
                except (ValueError, TypeError):
                    return 0.0

            cpu = parse_float(fields_data.get('cpu_usage', 0))
            mem = parse_float(fields_data.get('memory_usage', 0))
            disk = parse_float(fields_data.get('disk_usage', 0))
            net = parse_float(fields_data.get('network_utilization', 0))
            
            # Map dynamic status dropdown
            raw_status = str(fields_data.get('status', 'Normal')).lower()
            health_status = 'normal'
            if 'critical' in raw_status: health_status = 'critical'
            elif 'warning' in raw_status: health_status = 'warning'

            issue_found = str(fields_data.get('issue_found', 'No')).lower() == 'yes'
            
            action_taken = fields_data.get('action_taken', '')
            remarks = fields_data.get('remarks', notes)

            # New Dynamic Fields
            network_rx_tx = fields_data.get('network_rx_tx', '')
            load_average = fields_data.get('load_average', '')
            uptime = fields_data.get('uptime', '')
            swap_usage = fields_data.get('swap_usage', '')
            
            def parse_int(val):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return 0
                    
            docker_running = parse_int(fields_data.get('docker_running', 0))
            docker_failed = parse_int(fields_data.get('docker_failed', 0))

            ServerHealthEntry.objects.update_or_create(
                server_name=server.name,
                date=today,
                defaults={
                    'developer': request.user,
                    'cpu_usage': cpu,
                    'memory_usage': mem,
                    'disk_usage': disk,
                    'network_utilization': net,
                    'status': health_status,
                    'issue_found': issue_found,
                    'action_taken': action_taken,
                    'remarks': remarks,
                    'network_rx_tx': network_rx_tx,
                    'load_average': load_average,
                    'uptime': uptime,
                    'swap_usage': swap_usage,
                    'docker_running': docker_running,
                    'docker_failed': docker_failed
                }
            )

            # Update the main Server object status and last_checked time!
            server.status = health_status if health_status != 'normal' else 'up'
            server.last_checked = timezone.now()
            server.save()

        except Exception as e:
            print(f"Error syncing ServerHealthEntry: {e}")

    # Also map 'w01' (Review server capacity) weekly fields → ServerHealthEntry
    # The weekly W01 task has cpu_avg_pct / memory_avg_pct / storage_used_pct fields
    if task_id == 'w01' and server:
        try:
            from .models import ServerHealthEntry
            def parse_float_w(val):
                try:
                    return float(str(val).strip('%').strip())
                except (ValueError, TypeError):
                    return 0.0

            cpu  = parse_float_w(fields_data.get('cpu_avg_pct',    fields_data.get('cpu_usage', 0)))
            mem  = parse_float_w(fields_data.get('memory_avg_pct', fields_data.get('memory_usage', 0)))
            disk = parse_float_w(fields_data.get('storage_used_pct', fields_data.get('disk_usage', 0)))
            net  = parse_float_w(fields_data.get('network_utilization', 0))

            raw_status = str(fields_data.get('status', 'Normal')).lower()
            health_status = 'normal'
            if 'critical' in raw_status: health_status = 'critical'
            elif 'warning' in raw_status: health_status = 'warning'

            remarks = fields_data.get('recommendation', notes)

            # Save one entry per day logged (uses the log date, not just today)
            ServerHealthEntry.objects.update_or_create(
                server_name=server.name,
                date=today,
                defaults={
                    'developer': request.user,
                    'cpu_usage': cpu,
                    'memory_usage': mem,
                    'disk_usage': disk,
                    'network_utilization': net,
                    'status': health_status,
                    'issue_found': False,
                    'action_taken': '',
                    'remarks': remarks
                }
            )
        except Exception as e:
            print(f"Error syncing W01 → ServerHealthEntry: {e}")

    return JsonResponse({'success': True})


@login_required
def get_task_details(request):
    """AJAX endpoint: returns the previously saved data for a task on a specific date."""
    task_id = request.GET.get('task_id')
    server_id = request.GET.get('server_id')
    date_str = request.GET.get('date')
    
    today = timezone.now().date()
    if date_str:
        import datetime
        try:
            parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            if parsed_date <= today:
                today = parsed_date
        except ValueError:
            pass

    user = request.user
    # Safe role detection — superusers are treated as managers
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    # Server access check
    if viewer_role in ('manager', 'tl'):
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=user) | Q(assigned_users=user), id=server_id)

    category = task_id[0] if task_id else 'd'
    
    if category == 'w':
        start_of_week = today - datetime.timedelta(days=today.weekday())
        end_of_week = start_of_week + datetime.timedelta(days=6)
        log_filter = Q(logged_at__date__gte=start_of_week, logged_at__date__lte=end_of_week)
        entry_filter = Q(date__gte=start_of_week, date__lte=end_of_week)
        prev_date_limit = start_of_week
    elif category == 'm':
        start_of_month = today.replace(day=1)
        import calendar
        _, last_day = calendar.monthrange(today.year, today.month)
        end_of_month = today.replace(day=last_day)
        log_filter = Q(logged_at__date__gte=start_of_month, logged_at__date__lte=end_of_month)
        entry_filter = Q(date__gte=start_of_month, date__lte=end_of_month)
        prev_date_limit = start_of_month
    else:
        log_filter = Q(logged_at__date=today)
        entry_filter = Q(date=today)
        prev_date_limit = today

    # Today's task log (relative to period/view date)
    if viewer_role in ('manager', 'tl'):
        log = TaskLog.objects.filter(Q(server=server, task_id=task_id) & log_filter).first()
        entry = GeneralTaskEntry.objects.filter(Q(server=server, task_id=task_id) & entry_filter).first()
    else:
        log = TaskLog.objects.filter(Q(developer=user, server=server, task_id=task_id) & log_filter).first()
        entry = GeneralTaskEntry.objects.filter(Q(developer=user, server=server, task_id=task_id) & entry_filter).first()

    # Previous entry (most recent day before current period)
    prev_entry = GeneralTaskEntry.objects.filter(
        server=server, task_id=task_id, date__lt=prev_date_limit
    ).order_by('-date').first()

    if not log:
        return JsonResponse({
            'exists': False,
            'prev_fields_data': prev_entry.fields_data if prev_entry else {}
        })

    # Strip [STATUS] prefix from notes if present
    clean_notes = log.notes or ''
    if clean_notes.startswith('[') and ']' in clean_notes:
        clean_notes = clean_notes.split(']', 1)[1].strip()

    return JsonResponse({
        'exists': True,
        'status': log.status,
        'notes': clean_notes,
        'logged_date': log.logged_at.date().isoformat() if log.logged_at else today.isoformat(),
        'fields_data': entry.fields_data if entry else {},
        'prev_fields_data': prev_entry.fields_data if prev_entry else {}
    })


@login_required
def server_management(request, server_id):
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'
        
    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=request.user) | Q(assigned_users=request.user), id=server_id)
        
    # Support viewing a past period
    view_date_str = request.GET.get('view_date')
    today = timezone.now().date()
    is_historical_view = False
    if view_date_str:
        import datetime
        try:
            parsed_date = datetime.datetime.strptime(view_date_str, '%Y-%m-%d').date()
            if parsed_date < today:
                today = parsed_date
                is_historical_view = True
        except ValueError:
            pass
    task_data = get_dynamic_tasks()
    
    # Show logs for this server today (either by owner or current user)
    # If manager is viewing, show the owner's progress or the server's general progress
    today_logs = TaskLog.objects.filter(server=server, logged_at__date=today)
    
    # Show logs for this server
    # Daily: only today
    # Weekly: current week
    # Monthly: current month
    start_of_week = today - timezone.timedelta(days=today.weekday())  # Monday
    end_of_week = start_of_week + timezone.timedelta(days=6)          # Sunday
    
    start_of_month = today.replace(day=1)
    import calendar
    _, last_day = calendar.monthrange(today.year, today.month)
    end_of_month = today.replace(day=last_day)
    
    query_start = min(start_of_week, start_of_month)
    query_end = max(end_of_week, end_of_month)
    
    period_logs = TaskLog.objects.filter(
        server=server,
        logged_at__date__gte=query_start,
        logged_at__date__lte=query_end
    )
    
    # Create a mapping of task_id to its completion data (status + fields)
    logged_data = {}
    for log in period_logs:
        # Check if the log falls within its relevant category window
        is_valid = False
        log_date = log.logged_at.date()
        if log.category == 'd' and log_date == today:
            is_valid = True
        elif log.category == 'w' and start_of_week <= log_date <= end_of_week:
            is_valid = True
        elif log.category == 'm' and start_of_month <= log_date <= end_of_month:
            is_valid = True
            
        if is_valid:
            # For duplicates in the period, keep the latest one
            if log.task_id not in logged_data or log.logged_at > logged_data[log.task_id]['logged_at']:
                entry = GeneralTaskEntry.objects.filter(server=server, task_id=log.task_id, date=log.logged_at.date()).first()
                logged_data[log.task_id] = {
                    'status': log.status,
                    'fields': entry.fields_data if entry else {},
                    'logged_at': log.logged_at
                }
    
    # Last 7 days compliance for widgets (remains day-by-day)
    compliance_7d = []
    daily_tasks = TaskDefinition.objects.filter(category='d', is_active=True)
    daily_count = daily_tasks.count()
    
    for i in range(6, -1, -1):
        day = today - timezone.timedelta(days=i)
        # Count unique tasks completed for this server on this day
        done_count = TaskLog.objects.filter(
            server=server, 
            logged_at__date=day, 
            category='d', 
            status='done'
        ).values('task_id').distinct().count()
        
        pct = (done_count / daily_count * 100) if daily_count > 0 else 0
        compliance_7d.append({
            'label': day.strftime('%a')[0],
            'pct': min(100, round(pct)), # Cap at 100% for safety
            'is_today': i == 0
        })

    history = TaskLog.objects.filter(server=server).order_by('-logged_at')[:20]

    # Server Status History
    from .models import ServerStatusHistory
    status_history = ServerStatusHistory.objects.filter(server=server).order_by('-timestamp')

    # Get important tasks for this developer
    important_task_ids = []
    if hasattr(request.user, 'developer'):
        important_task_ids = list(request.user.developer.important_tasks.values_list('task_id', flat=True))

    # Fetch latest health entry for dynamic metrics
    from .models import ServerHealthEntry
    latest_health = ServerHealthEntry.objects.filter(server_name=server.name).order_by('-date', '-created_at').first()

    crashed_containers = None
    top_proc = None
    if latest_health and latest_health.remarks:
        if 'Crashed:' in latest_health.remarks:
            try:
                crashed_containers = latest_health.remarks.split('Crashed:')[1].split('|')[0].strip()
            except Exception:
                pass
        if 'Top CPU:' in latest_health.remarks:
            try:
                top_proc = latest_health.remarks.split('Top CPU:')[1].strip()
            except Exception:
                pass

    context = {
        'server': server,
        'latest_health': latest_health,
        'crashed_containers': crashed_containers,
        'top_proc': top_proc,
        'status_history': status_history,
        'task_data': task_data,
        'task_data_json': json.dumps(task_data),
        'important_task_ids_json': json.dumps(important_task_ids),
        'logged_data': logged_data,
        'logged_ids': {tid: d['status'] for tid, d in logged_data.items()},
        'history': history,
        'today': timezone.now().date(),
        'past_7': timezone.now().date() - timezone.timedelta(days=7),
        'past_14': timezone.now().date() - timezone.timedelta(days=14),
        'past_30': timezone.now().date() - timezone.timedelta(days=30),
        'today': timezone.now().date(),
        'view_date': today,
        'is_historical_view': is_historical_view,
        'compliance_7d': compliance_7d,
    }
    return render(request, 'tracker/server_management.html', context)

# ─── Server Health ───────────────────────────────────────────────
@login_required
def server_health_list(request):
    entries = ServerHealthEntry.objects.filter(developer=request.user).order_by('-date', '-created_at')
    # Get all servers the user has access to
    user_servers = Server.objects.filter(
        Q(owner=request.user) | Q(assigned_users=request.user)
    ).distinct().order_by('name')
    form = ServerHealthForm(initial={'date': timezone.now().date()}, user_servers=user_servers)
    return render(request, 'tracker/entries/server_health.html', {'entries': entries, 'form': form, 'servers': user_servers})


@login_required
def server_health_create(request):
    if request.method == 'POST':
        user_servers = Server.objects.filter(
            Q(owner=request.user) | Q(assigned_users=request.user)
        ).distinct()
        form = ServerHealthForm(request.POST, user_servers=user_servers)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.developer = request.user
            entry.save()
            # Auto-log the task
            TaskLog.objects.update_or_create(
                developer=request.user,
                task_id='d01',
                logged_at__date=timezone.now().date(),
                defaults={
                    'status': 'done',
                    'notes': entry.remarks or entry.action_taken,
                    'task_text': TaskDefinition.objects.filter(task_id='d01').values_list('text', flat=True).first() or 'Monitor Server Health',
                    'category': 'd',
                }
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('server_health_list')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
    return redirect('server_health_list')


# ─── Alert Check ─────────────────────────────────────────────────
@login_required
def alert_check_list(request):
    entries = AlertCheckEntry.objects.filter(developer=request.user).order_by('-date', '-created_at')
    form = AlertCheckForm(initial={'date': timezone.now().date()})
    return render(request, 'tracker/entries/alert_check.html', {'entries': entries, 'form': form})


@login_required
def alert_check_create(request):
    if request.method == 'POST':
        form = AlertCheckForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.developer = request.user
            entry.save()
            TaskLog.objects.update_or_create(
                developer=request.user, task_id='d02',
                logged_at__date=timezone.now().date(),
                defaults={'status': 'done', 'notes': entry.alert_description,
                          'task_text': TaskDefinition.objects.filter(task_id='d02').values_list('text', flat=True).first() or 'Check Alerts', 'category': 'd'}
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('alert_check_list')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
    return redirect('alert_check_list')


# ─── Pipeline ────────────────────────────────────────────────────
@login_required
def pipeline_list(request):
    entries = PipelineEntry.objects.filter(developer=request.user).order_by('-date', '-created_at')
    form = PipelineForm(initial={'date': timezone.now().date()})
    return render(request, 'tracker/entries/pipeline.html', {'entries': entries, 'form': form})


@login_required
def pipeline_create(request):
    if request.method == 'POST':
        form = PipelineForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.developer = request.user
            entry.save()
            TaskLog.objects.update_or_create(
                developer=request.user, task_id='d03',
                logged_at__date=timezone.now().date(),
                defaults={'status': 'done', 'notes': entry.fix_applied,
                          'task_text': TaskDefinition.objects.filter(task_id='d03').values_list('text', flat=True).first() or 'Review Pipeline', 'category': 'd'}
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('pipeline_list')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
    return redirect('pipeline_list')


# ─── Deployment ──────────────────────────────────────────────────
@login_required
def deployment_list(request):
    entries = DeploymentEntry.objects.filter(developer=request.user).order_by('-date', '-created_at')
    form = DeploymentForm(initial={'date': timezone.now().date()})
    return render(request, 'tracker/entries/deployment.html', {'entries': entries, 'form': form})


@login_required
def deployment_create(request):
    if request.method == 'POST':
        form = DeploymentForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.developer = request.user
            entry.save()
            TaskLog.objects.update_or_create(
                developer=request.user, task_id='d04',
                logged_at__date=timezone.now().date(),
                defaults={'status': 'done', 'notes': entry.remarks,
                          'task_text': TaskDefinition.objects.filter(task_id='d04').values_list('text', flat=True).first() or 'Validate Deployment', 'category': 'd'}
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('deployment_list')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
    return redirect('deployment_list')


@login_required
@require_POST
def create_server(request):
    """AJAX endpoint: creates a new Server owned by the current user."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    name = data.get('name', '').strip()
    ip_address = data.get('ip_address', '').strip() or None
    
    if not ip_address:
        return JsonResponse({'success': False, 'error': 'IP Address is required.'}, status=400)
        
    if not name:
        name = ip_address

    port_number = data.get('port_number')
    if port_number:
        try:
            port_number = int(port_number)
        except ValueError:
            port_number = 22
    else:
        port_number = 22
        
    username = data.get('username', '').strip() or None
    server_password = data.get('server_password', '').strip() or None

    # Owner logic: Managers/TLs can assign to others; Developers only to themselves.
    owner = request.user
    owner_id = data.get('owner_id')
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'

    if owner_id and viewer_role in ['manager', 'tl']:
        try:
            target_owner = User.objects.get(id=owner_id)
            owner = target_owner
        except User.DoesNotExist:
            pass

    if Server.objects.filter(ip_address=ip_address, owner=owner).exists():
        return JsonResponse({'success': False, 'error': f'A server with IP "{ip_address}" already exists for this owner.'}, status=400)

    server = Server.objects.create(
        name=name,
        ip_address=ip_address,
        port_number=port_number,
        username=username,
        server_password=server_password,
        owner=owner,
        status='up'
    )
    
    assigned_users_ids = data.get('assigned_users', [])
    if isinstance(assigned_users_ids, list):
        server.assigned_users.set(assigned_users_ids)
        
    return JsonResponse({'success': True, 'server_id': server.id, 'server_name': server.name})

@login_required
@require_POST
def update_server(request, server_id):
    """AJAX endpoint: updates an existing Server's details."""
    server = get_object_or_404(Server, id=server_id)
    
    # Security: Only owner or manager/TL can update
    viewer_role = 'developer'
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    elif hasattr(request.user, 'developer'):
        viewer_role = request.user.developer.role
        
    if server.owner != request.user and viewer_role not in ['manager', 'tl']:
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    name = data.get('name', '').strip()
    ip_address = data.get('ip_address', '').strip() or None
    
    if not ip_address:
        return JsonResponse({'success': False, 'error': 'IP Address is required.'}, status=400)
        
    if not name:
        name = ip_address
        
    if Server.objects.filter(ip_address=ip_address, owner=server.owner).exclude(id=server.id).exists():
        return JsonResponse({'success': False, 'error': f'A server with IP "{ip_address}" already exists.'}, status=400)
        
    server.name = name
    server.ip_address = ip_address
    
    port_number = data.get('port_number')
    if port_number:
        try:
            server.port_number = int(port_number)
        except ValueError:
            pass
            
    server.username = data.get('username', '').strip() or None
    server.server_password = data.get('server_password', '').strip() or None
    
    server.os_version = data.get('os_version', server.os_version)
    if 'cpu_cores' in data:
        try:
            server.cpu_cores = int(data['cpu_cores']) if data['cpu_cores'] else None
        except ValueError:
            pass
    server.total_ram = data.get('total_ram', server.total_ram)
    server.total_disk = data.get('total_disk', server.total_disk)
    
    server.save()
    
    if 'assigned_users' in data:
        assigned_users_ids = data.get('assigned_users', [])
        if isinstance(assigned_users_ids, list):
            server.assigned_users.set(assigned_users_ids)
            
    return JsonResponse({'success': True})

@login_required
@require_POST
def update_live_telemetry(request, server_id):
    """AJAX endpoint: updates or creates a ServerHealthEntry directly from the dashboard."""
    server = get_object_or_404(Server, id=server_id)
    
    # Security: Only owner or manager/TL can update
    viewer_role = 'developer'
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    elif hasattr(request.user, 'developer'):
        viewer_role = request.user.developer.role
        
    if server.owner != request.user and viewer_role not in ['manager', 'tl']:
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    # Fetch the latest or create a new one for today
    entry = ServerHealthEntry.objects.filter(server_name=server.name).order_by('-date', '-created_at').first()
    
    if not entry or entry.date != timezone.now().date():
        # Create a new entry for today
        entry = ServerHealthEntry(
            developer=request.user,
            server_name=server.name,
            date=timezone.now().date(),
            cpu_usage=data.get('cpu_usage', 0) or 0,
            memory_usage=data.get('memory_usage', 0) or 0,
            disk_usage=data.get('disk_usage', 0) or 0,
            network_utilization=0,  # Legacy field, not used in UI but required by model
        )
    
    # Update fields
    try:
        if 'cpu_usage' in data: entry.cpu_usage = float(data['cpu_usage'] or 0)
        if 'memory_usage' in data: entry.memory_usage = float(data['memory_usage'] or 0)
        if 'disk_usage' in data: entry.disk_usage = float(data['disk_usage'] or 0)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid number format.'}, status=400)

    entry.network_rx_tx = data.get('network_rx_tx', entry.network_rx_tx)
    entry.load_average = data.get('load_average', entry.load_average)
    entry.uptime = data.get('uptime', entry.uptime)
    entry.swap_usage = data.get('swap_usage', entry.swap_usage)
    
    if 'docker_running' in data:
        try:
            entry.docker_running = int(data['docker_running']) if data['docker_running'] else None
        except ValueError:
            pass
            
    if 'docker_failed' in data:
        try:
            entry.docker_failed = int(data['docker_failed']) if data['docker_failed'] else None
        except ValueError:
            pass

    entry.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def probe_server_live(request, server_id):
    """
    On-Demand Live Server Health Probe.
    Connects to the server over TCP and SSH, collects real-time metrics,
    updates ServerHealthEntry, auto-completes task d01, and returns live JSON payload.
    """
    server = get_object_or_404(Server, id=server_id)

    # Permission check: superuser/staff or manager/tl or owner or assigned user
    user = request.user
    viewer_role = 'developer'
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    elif hasattr(user, 'developer'):
        viewer_role = user.developer.role

    is_authorized = (
        viewer_role in ('manager', 'tl')
        or server.owner == user
        or server.assigned_users.filter(id=user.id).exists()
    )
    if not is_authorized:
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    from .monitoring import probe_single_server
    result = probe_single_server(server, timeout=6.0, user=user)

    if not result.get('is_up'):
        return JsonResponse({
            'success': False,
            'is_up': False,
            'latency_ms': result.get('latency_ms'),
            'error': result.get('error') or 'Server is unreachable'
        })

    return JsonResponse({
        'success': True,
        'is_up': True,
        'latency_ms': result.get('latency_ms'),
        'health_status': result.get('health_status', 'normal'),
        'metrics': result.get('metrics'),
        'error': result.get('error')
    })


@login_required
@require_POST
def run_all_servers_check_api(request):
    """
    Triggers automated health check across all registered servers.
    Available to all authenticated users.
    Accepts scope parameter: 'important' (default) or 'all'.
    """
    user = request.user
    important_only = True
    try:
        if request.body:
            body_data = json.loads(request.body)
            if 'important_only' in body_data:
                important_only = bool(body_data['important_only'])
            elif body_data.get('scope') == 'all':
                important_only = False
    except Exception:
        pass

    if request.POST.get('scope') == 'all' or request.GET.get('scope') == 'all':
        important_only = False

    from .monitoring import run_all_server_checks
    summary = run_all_server_checks(target_user=user, important_only=important_only)
    return JsonResponse({'success': True, 'summary': summary})


@login_required
def reassign_server(request, server_id):
    """AJAX endpoint: reassigns a server to a new owner."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    # Security: Only managers and TLs can reassign servers
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'
        
    if viewer_role not in ('manager', 'tl'):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        
    try:
        data = json.loads(request.body)
        new_owner_id = data.get('owner_id')
        server = get_object_or_404(Server, id=server_id)
        
        if new_owner_id:
            new_owner = get_object_or_404(User, id=new_owner_id)
            server.owner = new_owner
        else:
            server.owner = None
            
        server.save()
        
        if 'assigned_users' in data:
            assigned_users_ids = data.get('assigned_users', [])
            if isinstance(assigned_users_ids, list):
                server.assigned_users.set(assigned_users_ids)
                
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)



@login_required
def api_stats(request):
    """AJAX endpoint for dashboard stats"""
    today = timezone.now().date()
    user = request.user
    today_logs = TaskLog.objects.filter(developer=user, logged_at__date=today)
    logged_ids = {log.task_id: log.status for log in today_logs}
    task_data = get_dynamic_tasks()
    daily_done = sum(1 for t in task_data['d'] if logged_ids.get(t['id']) == 'done')
    return JsonResponse({
        'daily_done': daily_done,
        'daily_total': len(task_data['d']),
        'daily_pct': round(daily_done / len(task_data['d']) * 100) if task_data['d'] else 0,
        'logged_ids': logged_ids,
    })


@login_required
def server_logs_api(request, server_id):
    """AJAX endpoint: returns recent task logs for a specific server as JSON."""
    # Role-based check
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'
        
    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=request.user) | Q(assigned_users=request.user), id=server_id)
    logs = TaskLog.objects.filter(server=server).select_related('developer').order_by('-logged_at')[:30]

    data = []
    for log in logs:
        data.append({
            'id': log.id,
            'task_text': log.task_text,
            'task_id': log.task_id,
            'category': log.get_category_display(),
            'status': log.status,
            'developer': log.developer.get_full_name() or log.developer.username,
            'notes': log.notes,
            'logged_at': log.logged_at.strftime('%d %b %Y, %H:%M'),
        })
    return JsonResponse({'server': server.name, 'logs': data})


@login_required
def server_chart_api(request, server_id):
    """AJAX endpoint: returns D/W/M completion % for a specific server for individual charts."""
    # Role-based check
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'
        
    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=request.user) | Q(assigned_users=request.user), id=server_id)
    today = timezone.now().date()
    task_data = get_dynamic_tasks()

    s_done_d = TaskLog.objects.filter(server=server, category='d', logged_at__date=today, status='done').count()
    week_ago = today - datetime.timedelta(days=7)
    s_done_w = TaskLog.objects.filter(server=server, category='w', logged_at__date__gte=week_ago, status='done').count()
    month_ago = today - datetime.timedelta(days=30)
    s_done_m = TaskLog.objects.filter(server=server, category='m', logged_at__date__gte=month_ago, status='done').count()

    d_total = len(task_data['d'])
    w_total = len(task_data['w'])
    m_total = len(task_data['m'])

    return JsonResponse({
        'server_name': server.name,
        'daily':   {'done': s_done_d, 'total': d_total, 'pct': round(s_done_d / d_total * 100) if d_total else 0},
        'weekly':  {'done': s_done_w, 'total': w_total, 'pct': round(s_done_w / w_total * 100) if w_total else 0},
        'monthly': {'done': s_done_m, 'total': m_total, 'pct': round(s_done_m / m_total * 100) if m_total else 0},
    })


# ═══════════════════════════════════════════════════════════════
# RBAC — Manager / TL Views
# ═══════════════════════════════════════════════════════════════

@login_required
@tl_or_manager_required
def manager_dashboard(request):
    """Analytics overview for Manager and TL roles."""
    today = timezone.now().date()
    week_ago = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)

    task_data = get_dynamic_tasks()
    all_users = User.objects.filter(is_active=True).select_related('developer')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete_server':
            server_id = request.POST.get('server_id')
            server = Server.objects.filter(id=server_id).first()
            if server:
                name = server.name
                server.delete()
                messages.success(request, f'Server "{name}" removed successfully.')
            return redirect('manager_dashboard')

    # ── Per-server stats ─────────────────────────────────────────
    d_total = len(task_data['d'])
    w_total = len(task_data['w'])
    m_total = len(task_data['m'])

    server_stats = []
    for s in Server.objects.all().select_related('owner'):
        s_done_d = TaskLog.objects.filter(server=s, category='d', logged_at__date=today, status='done').count()
        s_done_w = TaskLog.objects.filter(server=s, category='w', logged_at__date__gte=week_ago, status='done').count()
        s_done_m = TaskLog.objects.filter(server=s, category='m', logged_at__date__gte=month_ago, status='done').count()
        blk = TaskLog.objects.filter(server=s, logged_at__date=today, status='blk').count()
        
        # Calculate 7-day history matrix
        history_7d = []
        for i in range(6, -1, -1):
            day_target = today - datetime.timedelta(days=i)
            day_done = TaskLog.objects.filter(server=s, category='d', logged_at__date=day_target, status='done').count()
            day_pct = round(day_done / d_total * 100) if d_total else 0
            history_7d.append({
                'day': day_target.strftime('%a'),
                'pct': day_pct,
                'is_today': (i == 0)
            })

        server_stats.append({
            'server': s,
            'owner_name': s.owner.get_full_name() or s.owner.username if s.owner else 'Unassigned',
            'owner_initials': s.owner.developer.initials if s.owner and hasattr(s.owner, 'developer') else (s.owner.username[:2].upper() if s.owner else '--'),
            'owner_color': s.owner.developer.avatar_gradient if s.owner and hasattr(s.owner, 'developer') else '#94a3b8',
            'daily_pct': round(s_done_d / d_total * 100) if d_total else 0,
            'weekly_pct': round(s_done_w / w_total * 100) if w_total else 0,
            'monthly_pct': round(s_done_m / m_total * 100) if m_total else 0,
            'daily_done': s_done_d,
            'daily_total': d_total,
            'weekly_done': s_done_w,
            'weekly_total': w_total,
            'monthly_done': s_done_m,
            'monthly_total': m_total,
            'blocked': blk,
            'history_7d': history_7d,
        })

    # ── Team-wide KPIs ──────────────────────────────────────────
    total_users = all_users.count()
    total_servers = Server.objects.count()
    
    # Calculate target: Total Daily Tasks x Total Servers
    daily_task_count = TaskDefinition.objects.filter(category='d', is_active=True).count()
    total_tasks_today = total_servers * daily_task_count
    
    # Count unique done tasks today (server + task_id unique)
    total_done_today = TaskLog.objects.filter(
        logged_at__date=today, 
        status='done',
        server__isnull=False
    ).values('server', 'task_id').distinct().count()
    
    total_blocked = TaskLog.objects.filter(logged_at__date=today, status='blk').count()
    critical_servers = Server.objects.filter(Q(status='down') | Q(status='maint')).count()

    # ── Daily trend (last 7 days) ────────────────────────────────
    trend_labels = []
    trend_done = []
    trend_blocked = []
    for i in range(6, -1, -1):
        day = today - datetime.timedelta(days=i)
        done = TaskLog.objects.filter(logged_at__date=day, status='done').count()
        blk = TaskLog.objects.filter(logged_at__date=day, status='blk').count()
        trend_labels.append(day.strftime('%d %b'))
        trend_done.append(done)
        trend_blocked.append(blk)

    # ── Status breakdown ────────────────────────────────────────
    status_counts = (
        TaskLog.objects.filter(logged_at__date=today)
        .values('status')
        .annotate(count=Count('id'))
    )
    status_map = {s['status']: s['count'] for s in status_counts}

    # ── Category breakdown (for pie chart) ──────────────────────
    cat_counts = (
        TaskLog.objects.filter(logged_at__date__gte=week_ago)
        .values('category')
        .annotate(count=Count('id'))
    )
    cat_map = {c['category']: c['count'] for c in cat_counts}

    # ── Recent activity feed ─────────────────────────────────────
    recent_activity = TaskLog.objects.select_related('developer').order_by('-logged_at')[:30]

    context = {
        'server_stats': server_stats,
        'total_users': total_users,
        'total_tasks_today': total_tasks_today,
        'total_done_today': total_done_today,
        'total_blocked': total_blocked,
        'total_servers': total_servers,
        'critical_servers': critical_servers,
        'trend_labels_json': json.dumps(trend_labels),
        'trend_done_json': json.dumps(trend_done),
        'trend_blocked_json': json.dumps(trend_blocked),
        'status_map_json': json.dumps(status_map),
        'cat_map_json': json.dumps(cat_map),
        'recent_activity': recent_activity,
        'today': today,
    }
    return render(request, 'tracker/manager_dashboard.html', context)


@login_required
@tl_or_manager_required
def developer_performance(request):
    """Detailed developer task compliance monitor for Manager and TL roles."""
    today = timezone.now().date()

    # ── Parse filters from query params ──────────────────────────
    target_user_id = request.GET.get('user')
    period = request.GET.get('period', 'd')  # d, w, m
    month_offset = int(request.GET.get('month', 0))  # 0 = current, -1 = last month, etc.

    # Calculate target month range
    first_of_current = today.replace(day=1)
    target_month_start = first_of_current
    for _ in range(abs(month_offset)):
        target_month_start = (target_month_start - datetime.timedelta(days=1)).replace(day=1)

    # End of target month
    if month_offset == 0:
        target_month_end = today
    else:
        next_month = target_month_start.replace(day=28) + datetime.timedelta(days=4)
        target_month_end = next_month.replace(day=1) - datetime.timedelta(days=1)

    month_label = target_month_start.strftime('%B %Y')

    # Get all active developers
    all_users = User.objects.filter(is_active=True).select_related('developer').order_by('first_name', 'username')
    
    # Get the focused developer (default: first developer)
    target_user = None
    if target_user_id:
        target_user = User.objects.filter(id=target_user_id).select_related('developer').first()
    if not target_user:
        target_user = all_users.first()

    task_data = get_dynamic_tasks()
    servers = Server.objects.all().select_related('owner')

    # ── Build developer list with summary stats ──────────────────
    dev_list = []
    total_servers_count = Server.objects.count()
    for u in all_users:
        # Determine effective role identical to dashboard
        if u.is_superuser or u.is_staff:
            role = 'manager'
        else:
            role = u.developer.role if hasattr(u, 'developer') else 'developer'
            
        if role in ('manager', 'tl'):
            u_server_count = total_servers_count
        else:
            u_server_count = Server.objects.filter(Q(owner=u) | Q(assigned_users=u)).distinct().count()

        # Count tasks done in target month
        u_done_month = TaskLog.objects.filter(
            developer=u,
            logged_at__date__gte=target_month_start,
            logged_at__date__lte=target_month_end,
            status='done',
            server__isnull=False
        ).values('server', 'task_id').distinct().count()

        u_blocked = TaskLog.objects.filter(
            developer=u,
            logged_at__date__gte=target_month_start,
            logged_at__date__lte=target_month_end,
            status='blk',
            server__isnull=False
        ).count()

        # Calculate total possible tasks for this month
        all_task_count = len(task_data['d']) + len(task_data['w']) + len(task_data['m'])
        total_possible = all_task_count * max(u_server_count, 1)

        dev_list.append({
            'user': u,
            'initials': u.developer.initials if hasattr(u, 'developer') else u.username[:2].upper(),
            'role': u.developer.role if hasattr(u, 'developer') else 'developer',
            'gradient': u.developer.avatar_gradient if hasattr(u, 'developer') else 'linear-gradient(135deg,#64748b,#475569)',
            'server_count': u_server_count,
            'done_month': u_done_month,
            'blocked': u_blocked,
            'is_active': u.id == (target_user.id if target_user else None),
        })

    # ── Build detailed compliance matrix for target developer ────
    compliance_data = []
    if target_user:
        if target_user.is_superuser or target_user.is_staff or (hasattr(target_user, 'developer') and target_user.developer.role in ('manager', 'tl')):
            user_servers = Server.objects.all()
        else:
            user_servers = Server.objects.filter(Q(owner=target_user) | Q(assigned_users=target_user)).distinct()
        # If they own no servers, show all servers they've logged tasks for
        if not user_servers.exists():
            logged_server_ids = TaskLog.objects.filter(
                developer=target_user,
                logged_at__date__gte=target_month_start,
                logged_at__date__lte=target_month_end,
            ).values_list('server_id', flat=True).distinct()
            user_servers = Server.objects.filter(id__in=logged_server_ids)

        # ── Pre-calculate Global Constants for the Month ─────────────
        days_in_period = (target_month_end - target_month_start).days + 1
        
        # Calculate weeks in this period
        start_of_week = target_month_start - datetime.timedelta(days=target_month_start.weekday())
        weeks_count = 0
        ws = start_of_week
        while ws <= target_month_end:
            weeks_count += 1
            ws += datetime.timedelta(days=7)

        d_count = len(task_data['d'])
        w_count = len(task_data['w'])
        m_count = len(task_data['m'])
        # Global total possible tasks for one server this month
        server_month_total = (d_count * days_in_period) + (w_count * weeks_count) + m_count

        # ── Process each server ──────────────────────────────────────
        for server in user_servers:
            # 1. Global Summary (D+W+M) for the header pill
            global_done = TaskLog.objects.filter(
                developer=target_user,
                server=server,
                logged_at__date__gte=target_month_start,
                logged_at__date__lte=target_month_end,
                status='done'
            ).values('task_id', 'logged_at__date').distinct().count()

            server_data = {
                'server': server,
                'summary': {
                    'done': global_done,
                    'total': server_month_total,
                    'missed': max(0, server_month_total - global_done)
                }
            }

            # 2. Period-specific Data (Heatmap / List)
            if period == 'd':
                server_data['dates'] = []
                date_list = []
                d = target_month_start
                while d <= target_month_end:
                    date_list.append(d)
                    d += datetime.timedelta(days=1)

                for date in date_list:
                    day_tasks = []
                    for task in task_data['d']:
                        log = TaskLog.objects.filter(
                            developer=target_user, server=server, task_id=task['id'],
                            category='d', logged_at__date=date
                        ).order_by('-logged_at').first()

                        status = log.status if log else ('pending' if date == today else 'missed')
                        day_tasks.append({
                            'task_id': task['id'], 'task_text': task['text'],
                            'status': status, 'notes': log.notes if log else '',
                            'logged_at': log.logged_at.strftime('%H:%M') if log else ''
                        })
                    
                    server_data['dates'].append({
                        'date': date, 'date_str': date.strftime('%d %b'),
                        'day_name': date.strftime('%a'), 'is_today': date == today,
                        'tasks': day_tasks,
                        'done_count': sum(1 for t in day_tasks if t['status'] == 'done'),
                        'total_count': len(day_tasks)
                    })

            elif period == 'w':
                server_data['weeks'] = []
                ws = start_of_week
                while ws <= target_month_end:
                    we = ws + datetime.timedelta(days=6)
                    w_range = {'start': max(ws, target_month_start), 'end': min(we, target_month_end)}
                    label = f"{w_range['start'].strftime('%d %b')} – {w_range['end'].strftime('%d %b')}"
                    
                    week_tasks = []
                    for task in task_data['w']:
                        log = TaskLog.objects.filter(
                            developer=target_user, server=server, task_id=task['id'],
                            category='w', logged_at__date__gte=w_range['start'],
                            logged_at__date__lte=w_range['end']
                        ).order_by('-logged_at').first()

                        is_future = w_range['start'] > today
                        status = log.status if log else ('pending' if is_future or w_range['end'] >= today else 'missed')
                        week_tasks.append({
                            'task_id': task['id'], 'task_text': task['text'],
                            'status': status, 'notes': log.notes if log else ''
                        })
                    
                    server_data['weeks'].append({
                        'label': label, 'tasks': week_tasks,
                        'done_count': sum(1 for t in week_tasks if t['status'] == 'done'),
                        'total_count': len(week_tasks)
                    })
                    ws += datetime.timedelta(days=7)

            else: # Monthly
                server_data['tasks'] = []
                for task in task_data['m']:
                    log = TaskLog.objects.filter(
                        developer=target_user, server=server, task_id=task['id'],
                        category='m', logged_at__date__gte=target_month_start,
                        logged_at__date__lte=target_month_end
                    ).order_by('-logged_at').first()

                    is_current = month_offset == 0
                    status = log.status if log else ('pending' if is_current else 'missed')
                    server_data['tasks'].append({
                        'task_id': task['id'], 'task_text': task['text'],
                        'status': status, 'notes': log.notes if log else '',
                        'logged_at': log.logged_at.strftime('%d %b %H:%M') if log else ''
                    })
            
            compliance_data.append(server_data)

    # Build overall stats for the target user
    target_stats = {}
    if target_user:
        for cat_key, cat_label in [('d', 'Daily'), ('w', 'Weekly'), ('m', 'Monthly')]:
            done = TaskLog.objects.filter(
                developer=target_user,
                category=cat_key,
                logged_at__date__gte=target_month_start,
                logged_at__date__lte=target_month_end,
                status='done',
                server__isnull=False
            ).values('server', 'task_id').distinct().count()

            total_tasks = len(task_data[cat_key])
            if target_user.is_superuser or target_user.is_staff:
                target_role = 'manager'
            else:
                target_role = target_user.developer.role if hasattr(target_user, 'developer') else 'developer'

            if target_role in ('manager', 'tl'):
                user_servers_count = Server.objects.count()
            else:
                user_servers_count = Server.objects.filter(Q(owner=target_user) | Q(assigned_users=target_user)).distinct().count() or 1
            
            # For daily, multiply by number of days in the period
            if cat_key == 'd':
                days_in_period = (target_month_end - target_month_start).days + 1
                total = total_tasks * user_servers_count * days_in_period
            elif cat_key == 'w':
                # Number of weeks in the period
                weeks = ((target_month_end - target_month_start).days // 7) + 1
                total = total_tasks * user_servers_count * weeks
            else:
                total = total_tasks * user_servers_count

            pct = min(100, round(done / total * 100)) if total > 0 else 0
            target_stats[cat_key] = {
                'label': cat_label,
                'done': done,
                'total': total,
                'pct': pct,
            }

    context = {
        'dev_list': dev_list,
        'target_user': target_user,
        'target_stats': target_stats,
        'compliance_data': compliance_data,
        'period': period,
        'month_offset': month_offset,
        'month_label': month_label,
        'prev_month': month_offset - 1,
        'next_month': min(0, month_offset + 1),
        'task_data': task_data,
        'today': today,
    }
    return render(request, 'tracker/developer_performance.html', context)


@login_required
def user_management(request):
    """Create and list users. TL can only create developers; Manager can create TLs too."""
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_user':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            password = request.POST.get('password', '').strip()
            new_role = request.POST.get('role', 'developer')
            assigned_server_ids = request.POST.getlist('assigned_servers')

            # TL can only create developers
            if viewer_role == 'tl' and new_role != 'developer':
                messages.error(request, 'Team Leads can only create Developer accounts.')
                return redirect('user_management')

            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists.')
                return redirect('user_management')

            can_reset = request.POST.get('can_reset_passwords') == 'on'
            if new_role in ['manager', 'tl']:
                can_reset = True

            new_user = User.objects.create(
                username=username,
                email=email,
                password=make_password(password),
                is_active=True,
            )
            Developer.objects.create(
                user=new_user,
                role=new_role,
                job_title='Engineer',
                can_reset_passwords=can_reset,
            )
            
            # Assign servers
            if assigned_server_ids:
                Server.objects.filter(id__in=assigned_server_ids).update(owner=new_user)

            messages.success(request, f'User "{username}" created successfully as {new_role}.')
            return redirect('user_management')

        elif action == 'reset_password':
            uid = request.POST.get('user_id')
            new_password = request.POST.get('new_password')
            if uid and new_password:
                target = User.objects.filter(id=uid).first()
                if target:
                    is_self = (request.user.id == target.id)
                    can_reset = is_self or viewer_role in ['manager', 'tl'] or (hasattr(request.user, 'developer') and request.user.developer.can_reset_passwords)
                    if can_reset:
                        target.set_password(new_password)
                        target.save()
                        messages.success(request, f'Password for "{target.username}" has been reset successfully.')
                    else:
                        messages.error(request, 'You do not have permission to reset this user\'s password.')
            return redirect('user_management')

        elif action == 'deactivate_user' and viewer_role == 'manager':
            uid = request.POST.get('user_id')
            if uid:
                target = User.objects.filter(id=uid).exclude(id=request.user.id).first()
                if target:
                    target.is_active = False
                    target.save()
                    messages.success(request, f'User "{target.username}" deactivated.')
            return redirect('user_management')

        elif action == 'delete_user' and viewer_role == 'manager':
            uid = request.POST.get('user_id')
            if uid:
                target = User.objects.filter(id=uid).exclude(id=request.user.id).first()
                if target:
                    username = target.username
                    target.delete()
                    messages.success(request, f'User "{username}" has been permanently removed.')
            return redirect('user_management')

    all_users = User.objects.select_related('developer').order_by('-date_joined')
    all_servers = Server.objects.all()
    context = {
        'all_users': all_users,
        'all_servers': all_servers,
        'viewer_role': viewer_role,
    }
    return render(request, 'tracker/user_management.html', context)


@login_required
@tl_or_manager_required
def team_export_csv(request):
    """Export all team task logs as CSV."""
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    user_id = request.GET.get('user_id', '')

    qs = TaskLog.objects.select_related('developer', 'server').order_by('-logged_at')
    if date_from:
        qs = qs.filter(logged_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(logged_at__date__lte=date_to)
    if user_id:
        qs = qs.filter(developer_id=user_id)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="team_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Time', 'Developer', 'Role', 'Server',
        'Task ID', 'Task', 'Category', 'Status', 'Notes'
    ])
    for log in qs:
        dev = log.developer
        role_label = dev.developer.get_role_display() if hasattr(dev, 'developer') else 'Developer'
        writer.writerow([
            log.logged_at.strftime('%Y-%m-%d'),
            log.logged_at.strftime('%H:%M'),
            dev.get_full_name() or dev.username,
            role_label,
            log.server.name if log.server else '',
            log.task_id,
            log.task_text,
            log.get_category_display(),
            log.get_status_display(),
            log.notes,
        ])
    return response


@login_required
@tl_or_manager_required
def servers_export_csv(request):
    """Export server performance metrics as CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="server_performance_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Server Node', 'IP Address', 'Status', 'Owner', 
        'Daily %', 'Daily Done/Total',
        'Weekly %', 'Weekly Done/Total', 
        'Monthly %', 'Monthly Done/Total', 
        'Currently Blocked'
    ])

    today = timezone.now().date()
    week_ago = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)
    task_data = get_dynamic_tasks()
    d_total = len(task_data['d'])
    w_total = len(task_data['w'])
    m_total = len(task_data['m'])

    for s in Server.objects.all().select_related('owner'):
        s_done_d = TaskLog.objects.filter(server=s, category='d', logged_at__date=today, status='done').count()
        s_done_w = TaskLog.objects.filter(server=s, category='w', logged_at__date__gte=week_ago, status='done').count()
        s_done_m = TaskLog.objects.filter(server=s, category='m', logged_at__date__gte=month_ago, status='done').count()
        blk = TaskLog.objects.filter(server=s, logged_at__date=today, status='blk').count()

        daily_pct = round(s_done_d / d_total * 100) if d_total else 0
        weekly_pct = round(s_done_w / w_total * 100) if w_total else 0
        monthly_pct = round(s_done_m / m_total * 100) if m_total else 0
        owner_name = s.owner.get_full_name() or s.owner.username if s.owner else 'Unassigned'

        writer.writerow([
            s.name, s.ip_address, s.get_status_display(), owner_name,
            f"{daily_pct}%", f"{s_done_d}/{d_total}",
            f"{weekly_pct}%", f"{s_done_w}/{w_total}",
            f"{monthly_pct}%", f"{s_done_m}/{m_total}",
            blk
        ])

    return response


@login_required
@tl_or_manager_required
def team_analytics_api(request):
    """JSON endpoint powering the manager dashboard charts."""
    today = timezone.now().date()
    user_id = request.GET.get('user_id', '')
    period = request.GET.get('period', '7')  # days
    try:
        days = int(period)
    except ValueError:
        days = 7
    start = today - datetime.timedelta(days=days - 1)

    qs = TaskLog.objects.all()
    if user_id:
        qs = qs.filter(developer_id=user_id)

    trend_labels = []
    trend_done = []
    trend_blocked = []
    for i in range(days - 1, -1, -1):
        day = today - datetime.timedelta(days=i)
        done = qs.filter(logged_at__date=day, status='done').count()
        blk = qs.filter(logged_at__date=day, status='blk').count()
        trend_labels.append(day.strftime('%d %b'))
        trend_done.append(done)
        trend_blocked.append(blk)

    status_counts = (
        qs.filter(logged_at__date__gte=start)
        .values('status')
        .annotate(count=Count('id'))
    )
    return JsonResponse({
        'trend_labels': trend_labels,
        'trend_done': trend_done,
        'trend_blocked': trend_blocked,
        'status_counts': list(status_counts),
    })

@login_required
def server_details(request, server_id):
    """Advanced Server Details — full intelligence audit view."""
    user = request.user
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=user) | Q(assigned_users=user), id=server_id)

    start_param = request.GET.get('start')
    end_param = request.GET.get('end')
    
    end_date = timezone.now().date()
    if end_param:
        try:
            end_date = datetime.datetime.strptime(end_param, '%Y-%m-%d').date()
        except ValueError:
            pass

    start_date = None
    if start_param:
        try:
            start_date = datetime.datetime.strptime(start_param, '%Y-%m-%d').date()
        except ValueError:
            pass
            
    if start_date and start_date > end_date:
        start_date = end_date
        
    selected_end_str = end_date.strftime('%Y-%m-%d')
    selected_start_str = start_date.strftime('%Y-%m-%d') if start_date else ''
    
    # We will use end_date as 'today' for other calculations outside the graph
    today = end_date

    # Daily Comparison Params
    comp_d_start_str = request.GET.get('comp_d_start', '')
    comp_d_end_str = request.GET.get('comp_d_end', '')
    comp_d_end = timezone.now().date()
    if comp_d_end_str:
        try: comp_d_end = datetime.datetime.strptime(comp_d_end_str, '%Y-%m-%d').date()
        except ValueError: pass
    comp_d_start = None
    if comp_d_start_str:
        try: comp_d_start = datetime.datetime.strptime(comp_d_start_str, '%Y-%m-%d').date()
        except ValueError: pass

    # Weekly Comparison Params
    comp_w_start_str = request.GET.get('comp_w_start', '')
    comp_w_end_str = request.GET.get('comp_w_end', '')
    comp_w_end = timezone.now().date()
    if comp_w_end_str:
        try: comp_w_end = datetime.datetime.strptime(comp_w_end_str + '-0', "%Y-W%W-%w").date() + datetime.timedelta(days=6)
        except ValueError: pass
    comp_w_start = None
    if comp_w_start_str:
        try: comp_w_start = datetime.datetime.strptime(comp_w_start_str + '-0', "%Y-W%W-%w").date() + datetime.timedelta(days=6)
        except ValueError: pass

    # Monthly Comparison Params
    comp_m_start_str = request.GET.get('comp_m_start', '')
    comp_m_end_str = request.GET.get('comp_m_end', '')
    comp_m_end = timezone.now().date()
    if comp_m_end_str:
        try:
            m_date = datetime.datetime.strptime(comp_m_end_str, '%Y-%m').date()
            # Get last day of the month
            next_month = m_date.replace(day=28) + datetime.timedelta(days=4)
            comp_m_end = next_month - datetime.timedelta(days=next_month.day)
        except ValueError: pass
    comp_m_start = None
    if comp_m_start_str:
        try:
            m_date = datetime.datetime.strptime(comp_m_start_str, '%Y-%m').date()
            next_month = m_date.replace(day=28) + datetime.timedelta(days=4)
            comp_m_start = next_month - datetime.timedelta(days=next_month.day)
        except ValueError: pass

    # ── Health trend (Dynamic) ──────────────────────────────────────
    health_daily = []
    health_weekly = []
    health_monthly = []

    def avg_health(entries):
        if not entries: return 0, 0, 0
        return (
            sum(e.cpu_usage for e in entries) / len(entries),
            sum(e.memory_usage for e in entries) / len(entries),
            sum(e.disk_usage for e in entries) / len(entries)
        )

    all_health = list(ServerHealthEntry.objects.filter(
        Q(server_name=server.name) | Q(server_name=server.ip_address)
    ).order_by('-date', '-created_at'))
    
    # Identify which dates have daily (d01) vs weekly (w01) vs monthly (m01) logs
    # so we don't mix them up in the charts!
    d01_dates = set(GeneralTaskEntry.objects.filter(server=server, task_id='d01').values_list('date', flat=True))
    w01_dates = set(GeneralTaskEntry.objects.filter(server=server, task_id='w01').values_list('date', flat=True))
    m01_dates = set(GeneralTaskEntry.objects.filter(server=server, task_id='m01').values_list('date', flat=True))

    health_by_day = {}
    for h in all_health:
        if h.date not in health_by_day:
            health_by_day[h.date] = h

    # Daily: Only include entries that are from a daily task (d01) or manual entry (not w01/m01)
    health_daily_days = (end_date - start_date).days if start_date else 6
    daily_start_date = end_date - datetime.timedelta(days=health_daily_days)
    for i in range(health_daily_days, -1, -1):
        day = end_date - datetime.timedelta(days=i)
        entry = health_by_day.get(day)
        # Skip if this entry was actually a weekly/monthly log
        if entry and (entry.date in w01_dates or entry.date in m01_dates) and entry.date not in d01_dates:
            entry = None

        health_daily.append({
            'day': day.strftime('%d %b'),
            'short': day.strftime('%a'),
            'is_current': (i == 0),
            'cpu': float(entry.cpu_usage) if entry else 0,
            'memory': float(entry.memory_usage) if entry else 0,
            'disk': float(entry.disk_usage) if entry else 0,
        })

    # Weekly: Only include entries from weekly task (w01)
    if start_date:
        w_start_cursor = start_date - datetime.timedelta(days=start_date.weekday())
    else:
        w_start_cursor = (end_date - datetime.timedelta(days=end_date.weekday())) - datetime.timedelta(weeks=3)
    
    w_i = 0
    while w_start_cursor <= end_date:
        w_end_interval = w_start_cursor + datetime.timedelta(days=6)
        w_entries = [h for h in all_health if w_start_cursor <= h.date <= w_end_interval and h.date in w01_dates]
        c, m, d = avg_health(w_entries)
        health_weekly.append({
            'day': f"{w_start_cursor.strftime('%d %b')} - {w_end_interval.strftime('%d %b')}",
            'short': f"Wk {w_i+1}",
            'is_current': (w_start_cursor <= end_date <= w_end_interval),
            'cpu': round(float(c), 1),
            'memory': round(float(m), 1),
            'disk': round(float(d), 1),
        })
        w_start_cursor += datetime.timedelta(weeks=1)
        w_i += 1

    # Monthly: Only include entries from monthly task (m01)
    import calendar
    if start_date:
        m_start_cursor = start_date.replace(day=1)
    else:
        m_month = end_date.month - 5
        m_year = end_date.year
        if m_month <= 0:
            m_month += 12
            m_year -= 1
        m_start_cursor = datetime.date(m_year, m_month, 1)

    while m_start_cursor <= end_date:
        m_year = m_start_cursor.year
        m_month = m_start_cursor.month
        _, last_day = calendar.monthrange(m_year, m_month)
        m_end_interval = datetime.date(m_year, m_month, last_day)
        
        m_entries = [h for h in all_health if m_start_cursor <= h.date <= m_end_interval and h.date in m01_dates]
        c, m, d = avg_health(m_entries)
        
        health_monthly.append({
            'day': m_start_cursor.strftime('%B %Y'),
            'short': m_start_cursor.strftime('%b'),
            'is_current': (m_year == end_date.year and m_month == end_date.month),
            'cpu': round(float(c), 1),
            'memory': round(float(m), 1),
            'disk': round(float(d), 1),
        })
        
        if m_month == 12:
            m_start_cursor = datetime.date(m_year + 1, 1, 1)
        else:
            m_start_cursor = datetime.date(m_year, m_month + 1, 1)

    latest_health = health_by_day.get(today) or (all_health[0] if all_health else None)
    prev_health = None
    for h in all_health:
        if h.date < today:
            prev_health = h
            break

    # ── Task category summaries ─────────────────────────────────────
    from .models import TaskDefinition
    task_counts = {}
    for cat, label in [('d', 'Daily'), ('w', 'Weekly'), ('m', 'Monthly')]:
        total = TaskDefinition.objects.filter(category=cat, is_active=True).count()
        
        # Determine the time window for this category
        if cat == 'd':
            # Daily: only today
            start_date = today
            period_label = 'Today'
        elif cat == 'w':
            # Weekly: rolling 7-day window (last 7 days including today)
            # This ensures Sunday tasks are always captured even at start of new week
            start_date = today - datetime.timedelta(days=6)
            period_label = f"{start_date.strftime('%d %b')} – {today.strftime('%d %b')}"
        else:
            # Monthly: current month
            start_date = today.replace(day=1)
            period_label = today.strftime('%B')
            
        done = TaskLog.objects.filter(
            server=server, 
            category=cat, 
            status='done', 
            logged_at__date__gte=start_date,
            logged_at__date__lte=today
        ).values('task_id').distinct().count()
        
        task_counts[cat] = {
            'label': label, 'done': done, 'total': total,
            'pct': min(100, round(done / total * 100)) if total else 0,
            'period_label': period_label
        }

    # ── Before vs Now: Dynamic Comparison ────────────────────
    from itertools import groupby
    def build_comparisons(prefix, c_start, c_end):
        entries_list = list(
            GeneralTaskEntry.objects.filter(server=server, task_id__startswith=prefix, date__lte=c_end)
            .order_by('task_id', '-date')
            .select_related('developer')
        )
        comps = []
        for task_id, group in groupby(entries_list, key=lambda e: e.task_id):
            entries = list(group)
            current = entries[0] if len(entries) >= 1 else None
            
            previous = None
            if c_start:
                for e in entries:
                    if e.date <= c_start:
                        previous = e
                        break
            else:
                previous = entries[1] if len(entries) >= 2 else None
                
            if not current:
                continue
                
            fields = []
            curr_data = current.fields_data or {}
            prev_data = previous.fields_data if previous else {}
            for key, curr_val in curr_data.items():
                if key == 'verification_result':
                    continue
                prev_val = prev_data.get(key, '')
                
                change = 'same'
                if str(curr_val) != str(prev_val):
                    change = 'changed'
                    try:
                        if curr_val and prev_val:
                            cf, pf = float(str(curr_val).replace('%', '')), float(str(prev_val).replace('%', ''))
                            if cf > pf: change = 'up'
                            elif cf < pf: change = 'down'
                    except (ValueError, TypeError):
                        pass
                        
                fields.append({'key': key.replace('_', ' ').title(), 'current': curr_val,
                               'previous': prev_val, 'change': change})
            comps.append({
                'task_id': task_id,
                'task_text': current.task_text,
                'current_date': current.date,
                'previous_date': previous.date if previous else None,
                'current_status': current.status,
                'developer': current.developer,
                'fields': fields,
            })
        comps.sort(key=lambda x: x['current_date'], reverse=True)
        return comps

    task_comparisons_d = build_comparisons('d', comp_d_start, comp_d_end)
    task_comparisons_w = build_comparisons('w', comp_w_start, comp_w_end)
    task_comparisons_m = build_comparisons('m', comp_m_start, comp_m_end)

    # ── Alert stats ─────────────────────────────────────────────────
    alert_entries = AlertCheckEntry.objects.filter(server=server).order_by('-date', '-created_at')[:20]
    total_critical = sum(a.critical_alerts for a in alert_entries)
    total_warning = sum(a.warning_alerts for a in alert_entries)
    resolved_alerts = sum(1 for a in alert_entries if a.status == 'resolved')

    # ── Recent logs & Total counts ──────────────────────────────────
    recent_logs = TaskLog.objects.filter(server=server).select_related('developer').order_by('-logged_at')[:50]
    total_logs = TaskLog.objects.filter(server=server).count()
    total_blocks = TaskLog.objects.filter(server=server, status='blk').count()

    # ── Compliance score (Current Period) ───────────────────────────
    start_of_week = today - datetime.timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    active_daily = TaskDefinition.objects.filter(category='d', is_active=True).count()
    active_weekly = TaskDefinition.objects.filter(category='w', is_active=True).count()
    active_monthly = TaskDefinition.objects.filter(category='m', is_active=True).count()
    total_required = active_daily + active_weekly + active_monthly

    # Daily: count unique daily tasks done on today specifically
    d_done = TaskLog.objects.filter(server=server, category='d', logged_at__date=today, status='done').values('task_id').distinct().count()
    # Weekly: count unique weekly tasks done anytime this week (Mon-Sun)
    w_done = TaskLog.objects.filter(server=server, category='w', logged_at__date__gte=start_of_week, logged_at__date__lte=today, status='done').values('task_id').distinct().count()
    # Monthly: count unique monthly tasks done anytime this calendar month
    m_done = TaskLog.objects.filter(server=server, category='m', logged_at__date__gte=start_of_month, logged_at__date__lte=today, status='done').values('task_id').distinct().count()
    
    total_tasks_done = d_done + w_done + m_done
    compliance_pct = round(total_tasks_done / total_required * 100) if total_required else 0

    # ── Completion history for bar charts (Dynamic) ─────────────────
    completion_daily = []
    completion_weekly = []
    completion_monthly = []
    
    # Daily (Last 7 Days)
    daily_def_count = TaskDefinition.objects.filter(category='d', is_active=True).count()
    for i in range(6, -1, -1):
        day = today - datetime.timedelta(days=i)
        d_done = TaskLog.objects.filter(server=server, category='d', logged_at__date=day, status='done').values('task_id').distinct().count()
        completion_daily.append({
            'day': day.strftime('%a'),
            'date': day.strftime('%d %b'),
            'done': d_done,
            'total': daily_def_count,
            'pct': min(100, round(d_done / daily_def_count * 100)) if daily_def_count else 0,
            'is_current': (i == 0),
        })

    # Weekly (Last 4 Weeks)
    weekly_def_count = TaskDefinition.objects.filter(category='w', is_active=True).count()
    # Start from the Monday of the current week
    current_week_start = today - datetime.timedelta(days=today.weekday())
    for i in range(3, -1, -1):
        w_start = current_week_start - datetime.timedelta(weeks=i)
        w_end = w_start + datetime.timedelta(days=6)
        w_done = TaskLog.objects.filter(
            server=server, category='w',
            logged_at__date__gte=w_start, logged_at__date__lte=w_end,
            status='done'
        ).values('task_id').distinct().count()
        label = "This Wk" if i == 0 else ("Last Wk" if i == 1 else f"{i} Wks Ago")
        completion_weekly.append({
            'day': label,
            'date': f"{w_start.strftime('%d %b')} - {w_end.strftime('%d %b')}",
            'done': w_done,
            'total': weekly_def_count,
            'pct': min(100, round(w_done / weekly_def_count * 100)) if weekly_def_count else 0,
            'is_current': (i == 0),
        })

    # Monthly (Last 6 Months)
    monthly_def_count = TaskDefinition.objects.filter(category='m', is_active=True).count()
    import calendar
    for i in range(5, -1, -1):
        # Calculate month and year
        m_month = today.month - i
        m_year = today.year
        if m_month <= 0:
            m_month += 12
            m_year -= 1
        
        m_start = datetime.date(m_year, m_month, 1)
        _, last_day = calendar.monthrange(m_year, m_month)
        m_end = datetime.date(m_year, m_month, last_day)
        
        m_done = TaskLog.objects.filter(server=server, category='m', logged_at__date__gte=m_start, logged_at__date__lte=m_end, status='done').values('task_id').distinct().count()
        completion_monthly.append({
            'day': m_start.strftime('%b'),
            'date': m_start.strftime('%B %Y'),
            'done': m_done,
            'total': monthly_def_count,
            'pct': min(100, round(m_done / monthly_def_count * 100)) if monthly_def_count else 0,
            'is_current': (i == 0),
        })

    # ── Server age ──────────────────────────────────────────────────
    first_log = TaskLog.objects.filter(server=server).order_by('logged_at').first()
    server_since = first_log.logged_at.date() if first_log else today

    # ── Detailed History: Group entries by category and date ──────────
    all_history_entries = GeneralTaskEntry.objects.filter(server=server).order_by('-date', 'task_id').select_related('developer')
    
    history_by_cat = {
        'd': {}, 'w': {}, 'm': {}
    }
    
    for entry in all_history_entries:
        cat = entry.task_id[0]
        if cat not in history_by_cat: continue
        
        dt_str = entry.date.strftime('%Y-%m-%d')
        if dt_str not in history_by_cat[cat]:
            history_by_cat[cat][dt_str] = {
                'date': entry.date,
                'entries': []
            }
        history_by_cat[cat][dt_str]['entries'].append(entry)
    
    # Sort dates descending for each category
    sorted_history_cat = {
        'd': sorted(history_by_cat['d'].values(), key=lambda x: x['date'], reverse=True),
        'w': sorted(history_by_cat['w'].values(), key=lambda x: x['date'], reverse=True),
        'm': sorted(history_by_cat['m'].values(), key=lambda x: x['date'], reverse=True),
    }

    context = {
        'server': server,
        'viewer_role': viewer_role,
        'today': today,
        'selected_start_str': selected_start_str,
        'selected_end_str': selected_end_str,
        'comp_d_start_str': comp_d_start_str,
        'comp_d_end_str': comp_d_end_str,
        'comp_w_start_str': comp_w_start_str,
        'comp_w_end_str': comp_w_end_str,
        'comp_m_start_str': comp_m_start_str,
        'comp_m_end_str': comp_m_end_str,
        'health_daily_json': json.dumps(health_daily),
        'health_weekly_json': json.dumps(health_weekly),
        'health_monthly_json': json.dumps(health_monthly),
        # Health
        'latest_health': latest_health,
        'prev_health': prev_health,
        # Tasks
        'task_counts': task_counts,
        'task_comparisons_d': task_comparisons_d,
        'task_comparisons_w': task_comparisons_w,
        'task_comparisons_m': task_comparisons_m,
        'total_tasks_done': total_tasks_done,
        'total_required': total_required,
        'total_blocks': total_blocks,
        'total_logs': total_logs,
        'compliance_pct': compliance_pct,
        'completion_daily_json': json.dumps(completion_daily),
        'completion_weekly_json': json.dumps(completion_weekly),
        'completion_monthly_json': json.dumps(completion_monthly),
        # Alerts
        'alert_entries': alert_entries,
        'total_critical': total_critical,
        'total_warning': total_warning,
        'resolved_alerts': resolved_alerts,
        # Logs & meta
        'recent_logs': recent_logs,
        'history_cat': sorted_history_cat,
        'server_since': server_since,
    }
    return render(request, 'tracker/server_details.html', context)



# ─── Task Manager ────────────────────────────────────────────────────────────

def _next_task_id(category):
    """Auto-generate the next sequential task_id for a given category (d/w/m)."""
    prefix = category  # 'd', 'w', or 'm'
    existing = (
        TaskDefinition.objects
        .filter(task_id__startswith=prefix)
        .values_list('task_id', flat=True)
    )
    nums = []
    for tid in existing:
        try:
            nums.append(int(tid[1:]))
        except (ValueError, IndexError):
            pass
    next_num = max(nums) + 1 if nums else 1
    return f"{prefix}{next_num:02d}"


@login_required
@tl_or_manager_required
def task_manager(request):
    """Task Manager page — create, edit, toggle, delete TaskDefinitions."""
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'

    if request.method == 'POST':
        action = request.POST.get('action')

        # ── CREATE ──────────────────────────────────────────────
        if action == 'create_task':
            category     = request.POST.get('category', 'd')
            text         = request.POST.get('text', '').strip()
            priority     = request.POST.get('priority', 'med')
            raw_fields   = request.POST.get('fields_schema', '[]')
            apply_to_all = request.POST.get('apply_to_all') == 'on'
            server_ids   = request.POST.getlist('servers')

            if not text:
                messages.error(request, 'Task description is required.')
                return redirect('task_manager')

            try:
                fields_schema = json.loads(raw_fields)
                if not isinstance(fields_schema, list):
                    fields_schema = []
            except json.JSONDecodeError:
                fields_schema = []

            task_id = _next_task_id(category)
            task_def = TaskDefinition.objects.create(
                task_id=task_id,
                text=text,
                category=category,
                priority=priority,
                fields_schema=fields_schema,
                is_active=True,
                apply_to_all=apply_to_all
            )
            if not apply_to_all and server_ids:
                task_def.servers.set(server_ids)
            
            messages.success(request, f'Task "{task_id}" created successfully.')
            return redirect('task_manager')

        # ── EDIT ─────────────────────────────────────────────────
        elif action == 'edit_task':
            task_def_id  = request.POST.get('task_def_id')
            task_def     = get_object_or_404(TaskDefinition, id=task_def_id)
            text         = request.POST.get('text', '').strip()
            priority     = request.POST.get('priority', 'med')
            raw_fields   = request.POST.get('fields_schema', '[]')
            apply_to_all = request.POST.get('apply_to_all') == 'on'
            server_ids   = request.POST.getlist('servers')

            if not text:
                messages.error(request, 'Task description is required.')
                return redirect('task_manager')

            try:
                fields_schema = json.loads(raw_fields)
                if not isinstance(fields_schema, list):
                    fields_schema = []
            except json.JSONDecodeError:
                fields_schema = []

            task_def.text          = text
            task_def.priority      = priority
            task_def.fields_schema = fields_schema
            task_def.apply_to_all  = apply_to_all
            task_def.save()
            
            if not apply_to_all:
                task_def.servers.set(server_ids)
            else:
                task_def.servers.clear()

            messages.success(request, f'Task "{task_def.task_id}" updated.')
            return redirect('task_manager')

        # ── DELETE ───────────────────────────────────────────────
        elif action == 'delete_task':
            task_def_id = request.POST.get('task_def_id')
            task_def    = get_object_or_404(TaskDefinition, id=task_def_id)
            tid         = task_def.task_id
            task_def.delete()
            messages.success(request, f'Task "{tid}" deleted.')
            return redirect('task_manager')

        # ── TOGGLE ACTIVE ─────────────────────────────────────────
        elif action == 'toggle_task':
            task_def_id = request.POST.get('task_def_id')
            task_def    = get_object_or_404(TaskDefinition, id=task_def_id)
            task_def.is_active = not task_def.is_active
            task_def.save()
            state = 'activated' if task_def.is_active else 'deactivated'
            messages.success(request, f'Task "{task_def.task_id}" {state}.')
            return redirect('task_manager')

    # ── GET: load all definitions grouped by category ────────────
    daily_qs   = TaskDefinition.objects.filter(category='d').order_by('task_id')
    weekly_qs  = TaskDefinition.objects.filter(category='w').order_by('task_id')
    monthly_qs = TaskDefinition.objects.filter(category='m').order_by('task_id')

    def serialize_tasks(qs):
        result = []
        for t in qs:
            result.append({
                'id': t.id,
                'task_id': t.task_id,
                'text': t.text,
                'fields_schema': t.fields_schema or [],
                'is_active': t.is_active,
                'apply_to_all': t.apply_to_all,
                'servers': list(t.servers.values_list('id', flat=True)),
            })
        return result

    daily_data   = serialize_tasks(daily_qs)
    weekly_data  = serialize_tasks(weekly_qs)
    monthly_data = serialize_tasks(monthly_qs)

    context = {
        'viewer_role': viewer_role,
        'all_servers': Server.objects.all(),
        'daily':   daily_qs,
        'weekly':  weekly_qs,
        'monthly': monthly_qs,
        'daily_count':   daily_qs.count(),
        'weekly_count':  weekly_qs.count(),
        'monthly_count': monthly_qs.count(),
        'active_daily':   daily_qs.filter(is_active=True).count(),
        'active_weekly':  weekly_qs.filter(is_active=True).count(),
        'active_monthly': monthly_qs.filter(is_active=True).count(),
        # Pre-serialized JSON strings for safe JS embedding
        'daily_json':   json.dumps(daily_data),
        'weekly_json':  json.dumps(weekly_data),
        'monthly_json': json.dumps(monthly_data),
    }
    return render(request, 'tracker/task_manager.html', context)


@login_required
@tl_or_manager_required
def task_manager_api(request, task_def_id):
    """AJAX API for inline toggle/delete actions from the Task Manager page."""
    task_def = get_object_or_404(TaskDefinition, id=task_def_id)

    if request.method == 'POST':
        try:
            data   = json.loads(request.body)
            action = data.get('action')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

        if action == 'toggle':
            task_def.is_active = not task_def.is_active
            task_def.save()
            return JsonResponse({'success': True, 'is_active': task_def.is_active})

        elif action == 'delete':
            tid = task_def.task_id
            task_def.delete()
            return JsonResponse({'success': True, 'deleted_id': task_def_id, 'task_id': tid})

        elif action == 'edit':
            text       = data.get('text', '').strip()
            priority   = data.get('priority', 'med')
            fields     = data.get('fields_schema', [])

            if not text:
                return JsonResponse({'success': False, 'error': 'Task text is required.'}, status=400)
            if not isinstance(fields, list):
                fields = []

            task_def.text          = text
            task_def.priority      = priority
            task_def.fields_schema = fields
            task_def.save()
            return JsonResponse({
                'success': True,
                'task_id': task_def.task_id,
                'text':    task_def.text,
                'priority': task_def.priority,
                'fields_schema': task_def.fields_schema,
                'is_active': task_def.is_active,
            })

    return JsonResponse({'success': False, 'error': 'Method not allowed.'}, status=405)


# ─── Database Monitoring Stubs ───────────────────────────────────────────────
@login_required
def db_monitoring(request):
    return HttpResponse('Database monitoring is under construction.')

@login_required
def db_instance_create(request):
    return HttpResponse('db_instance_create under construction.')

@login_required
def db_daily_create(request):
    return HttpResponse('db_daily_create under construction.')

@login_required
def db_weekly_create(request):
    return HttpResponse('db_weekly_create under construction.')

@login_required
def db_monthly_create(request):
    return HttpResponse('db_monthly_create under construction.')

@login_required
def db_export_csv(request):
    return HttpResponse('db_export_csv under construction.')


@login_required
@require_POST
def toggle_important_task(request):
    """AJAX endpoint to toggle a task as important for the current developer."""
    if not hasattr(request.user, 'developer'):
        return JsonResponse({'success': False, 'error': 'Not a developer'}, status=403)
        
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    task_def = get_object_or_404(TaskDefinition, task_id=task_id)
    developer = request.user.developer
    
    if task_def in developer.important_tasks.all():
        developer.important_tasks.remove(task_def)
        is_important = False
    else:
        developer.important_tasks.add(task_def)
        is_important = True
        
    return JsonResponse({'success': True, 'is_important': is_important})

@login_required
@require_POST
def toggle_server_status(request, server_id):
    """AJAX endpoint to toggle server status between up and down and record history."""
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'

    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=request.user) | Q(assigned_users=request.user), id=server_id)

    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    if new_status not in ['up', 'down', 'maint']:
        return JsonResponse({'success': False, 'error': 'Invalid status.'}, status=400)

    server.status = new_status
    server.save()

    from .models import ServerStatusHistory
    ServerStatusHistory.objects.create(
        server=server,
        changed_by=request.user,
        status=new_status
    )

    return JsonResponse({'success': True, 'new_status': new_status})



# ─── Database Monitoring Stubs ───────────────────────────────────────────────
@login_required

@login_required
def db_monitoring(request):
    return HttpResponse('Database monitoring is under construction.')

@login_required
def db_instance_create(request):
    return HttpResponse('db_instance_create under construction.')

@login_required
def db_daily_create(request):
    return HttpResponse('db_daily_create under construction.')

@login_required
def db_weekly_create(request):
    return HttpResponse('db_weekly_create under construction.')

@login_required
def db_monthly_create(request):
    return HttpResponse('db_monthly_create under construction.')

@login_required
def db_export_csv(request):
    return HttpResponse('db_export_csv under construction.')


@login_required
@require_POST
def toggle_important_task(request):
    """AJAX endpoint to toggle a task as important for the current developer."""
    if not hasattr(request.user, 'developer'):
        return JsonResponse({'success': False, 'error': 'Not a developer'}, status=403)
        
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    task_def = get_object_or_404(TaskDefinition, task_id=task_id)
    developer = request.user.developer
    
    if task_def in developer.important_tasks.all():
        developer.important_tasks.remove(task_def)
        is_important = False
    else:
        developer.important_tasks.add(task_def)
        is_important = True
        
    return JsonResponse({'success': True, 'is_important': is_important})

@login_required
@require_POST
def toggle_server_status(request, server_id):
    """AJAX endpoint to toggle server status between up and down and record history."""
    if request.user.is_superuser or request.user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'

    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, Q(owner=request.user) | Q(assigned_users=request.user), id=server_id)

    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    if new_status not in ['up', 'down', 'maint']:
        return JsonResponse({'success': False, 'error': 'Invalid status.'}, status=400)

    server.status = new_status
    server.save()

    from .models import ServerStatusHistory
    ServerStatusHistory.objects.create(
        server=server,
        changed_by=request.user,
        status=new_status
    )

    return JsonResponse({'success': True, 'new_status': new_status})

@login_required
def export_comparisons_csv(request, server_id):
    server = get_object_or_404(Server, id=server_id)

    # Daily Comparison Params
    comp_d_start_str = request.GET.get('comp_d_start', '')
    comp_d_end_str = request.GET.get('comp_d_end', '')
    comp_d_end = timezone.now().date()
    if comp_d_end_str:
        try: comp_d_end = datetime.datetime.strptime(comp_d_end_str, '%Y-%m-%d').date()
        except ValueError: pass
    comp_d_start = None
    if comp_d_start_str:
        try: comp_d_start = datetime.datetime.strptime(comp_d_start_str, '%Y-%m-%d').date()
        except ValueError: pass

    # Weekly Comparison Params
    comp_w_start_str = request.GET.get('comp_w_start', '')
    comp_w_end_str = request.GET.get('comp_w_end', '')
    comp_w_end = timezone.now().date()
    if comp_w_end_str:
        try: comp_w_end = datetime.datetime.strptime(comp_w_end_str + '-0', "%Y-W%W-%w").date() + datetime.timedelta(days=6)
        except ValueError: pass
    comp_w_start = None
    if comp_w_start_str:
        try: comp_w_start = datetime.datetime.strptime(comp_w_start_str + '-0', "%Y-W%W-%w").date() + datetime.timedelta(days=6)
        except ValueError: pass

    # Monthly Comparison Params
    comp_m_start_str = request.GET.get('comp_m_start', '')
    comp_m_end_str = request.GET.get('comp_m_end', '')
    comp_m_end = timezone.now().date()
    if comp_m_end_str:
        try:
            m_date = datetime.datetime.strptime(comp_m_end_str, '%Y-%m').date()
            next_month = m_date.replace(day=28) + datetime.timedelta(days=4)
            comp_m_end = next_month - datetime.timedelta(days=next_month.day)
        except ValueError: pass
    comp_m_start = None
    if comp_m_start_str:
        try:
            m_date = datetime.datetime.strptime(comp_m_start_str, '%Y-%m').date()
            next_month = m_date.replace(day=28) + datetime.timedelta(days=4)
            comp_m_start = next_month - datetime.timedelta(days=next_month.day)
        except ValueError: pass

    # ── Before vs Now: Dynamic Comparison ────────────────────
    from itertools import groupby
    def build_comparisons(prefix, c_start, c_end):
        def format_date(d):
            if not d: return None
            if prefix == 'd': return d.strftime("%d %b %Y")
            elif prefix == 'w':
                start = d - datetime.timedelta(days=d.weekday())
                end = start + datetime.timedelta(days=6)
                week_of_month = (start.day + start.replace(day=1).weekday()) // 7 + 1
                return f"{start.strftime('%B')}, Week {week_of_month} ({start.strftime('%b %d')} - {end.strftime('%b %d')})"
            elif prefix == 'm':
                return d.strftime("%B %Y")
            return d.strftime("%d %b %Y")

        entries_list = list(
            GeneralTaskEntry.objects.filter(server=server, task_id__startswith=prefix, date__lte=c_end)
            .order_by('task_id', '-date')
            .select_related('developer')
        )
        comps = []
        for task_id, group in groupby(entries_list, key=lambda e: e.task_id):
            entries = list(group)
            current = entries[0] if len(entries) >= 1 else None
            
            previous = None
            if c_start:
                for e in entries:
                    if e.date <= c_start:
                        previous = e
                        break
            else:
                previous = entries[1] if len(entries) >= 2 else None
                
            if not current:
                continue
                
            fields = []
            curr_data = current.fields_data or {}
            prev_data = previous.fields_data if previous else {}
            for key, curr_val in curr_data.items():
                if key == 'verification_result':
                    continue
                prev_val = prev_data.get(key, '')
                
                change = 'same'
                if str(curr_val) != str(prev_val):
                    change = 'changed'
                    try:
                        if curr_val and prev_val:
                            cf, pf = float(str(curr_val).replace('%', '')), float(str(prev_val).replace('%', ''))
                            if cf > pf: change = 'up'
                            elif cf < pf: change = 'down'
                    except (ValueError, TypeError):
                        pass
                        
                fields.append({'key': key.replace('_', ' ').title(), 'current': curr_val,
                               'previous': prev_val, 'change': change})
            comps.append({
                'category': 'Daily' if prefix == 'd' else ('Weekly' if prefix == 'w' else 'Monthly'),
                'task_id': task_id.upper(),
                'task_text': current.task_text,
                'fields': fields,
            })
        comps.sort(key=lambda x: x['task_id'])
        return comps

    all_comps = []
    all_comps.extend(build_comparisons('d', comp_d_start, comp_d_end))
    all_comps.extend(build_comparisons('w', comp_w_start, comp_w_end))
    all_comps.extend(build_comparisons('m', comp_m_start, comp_m_end))

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Server_{server.name}_Comparisons.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Category', 'Task ID', 'Task Name', 'Metric', 'Previous Value', 'Current Value', 'Change'])
    
    for c in all_comps:
        if not c['fields']:
            writer.writerow([c['category'], c['task_id'], c['task_text'], 'N/A', 'N/A', 'N/A', 'N/A'])
        else:
            for f in c['fields']:
                writer.writerow([
                    c['category'], 
                    c['task_id'], 
                    c['task_text'], 
                    f['key'], 
                    f['previous'] if f['previous'] else '—', 
                    f['current'] if f['current'] else '—', 
                    f['change'].title()
                ])
                
    return response

@login_required
def comparison_report_print(request, server_id, category):
    server = get_object_or_404(Server, id=server_id)
    
    # Get parameters
    c_start_str = request.GET.get('start', '')
    c_end_str = request.GET.get('end', '')
    
    c_end = timezone.now().date()
    c_start = None

    if category == 'd':
        if c_end_str:
            try: c_end = datetime.datetime.strptime(c_end_str, '%Y-%m-%d').date()
            except ValueError: pass
        if c_start_str:
            try: c_start = datetime.datetime.strptime(c_start_str, '%Y-%m-%d').date()
            except ValueError: pass
        title = "Daily Tasks Comparison"
    elif category == 'w':
        if c_end_str:
            try: c_end = datetime.datetime.strptime(c_end_str + '-0', "%Y-W%W-%w").date() + datetime.timedelta(days=6)
            except ValueError: pass
        if c_start_str:
            try: c_start = datetime.datetime.strptime(c_start_str + '-0', "%Y-W%W-%w").date() + datetime.timedelta(days=6)
            except ValueError: pass
        title = "Weekly Tasks Comparison"
    elif category == 'm':
        if c_end_str:
            try:
                m_date = datetime.datetime.strptime(c_end_str, '%Y-%m').date()
                next_month = m_date.replace(day=28) + datetime.timedelta(days=4)
                c_end = next_month - datetime.timedelta(days=next_month.day)
            except ValueError: pass
        if c_start_str:
            try:
                m_date = datetime.datetime.strptime(c_start_str, '%Y-%m').date()
                next_month = m_date.replace(day=28) + datetime.timedelta(days=4)
                c_start = next_month - datetime.timedelta(days=next_month.day)
            except ValueError: pass
        title = "Monthly Tasks Comparison"
    else:
        return HttpResponse("Invalid category", status=400)

    # Format human readable strings for PDF
    def format_date_str(raw_str, cat):
        if not raw_str: return ""
        try:
            if cat == 'd':
                d = datetime.datetime.strptime(raw_str, '%Y-%m-%d')
                return d.strftime('%b %#d, %Y').replace('#', '')
            elif cat == 'w':
                if '-W' in raw_str:
                    d = datetime.datetime.strptime(raw_str + '-1', '%Y-W%W-%w')
                    end_d = d + datetime.timedelta(days=6)
                    first_day = d.replace(day=1)
                    week_num = (d.day + first_day.weekday()) // 7 + 1
                    return f"{d.strftime('%B')}, Week {week_num} ({d.strftime('%b')} {d.day} - {end_d.strftime('%b')} {end_d.day})"
            elif cat == 'm':
                d = datetime.datetime.strptime(raw_str, '%Y-%m')
                return d.strftime('%B %Y')
        except: pass
        return raw_str

    human_start_str = format_date_str(c_start_str, category)
    human_end_str = format_date_str(c_end_str, category)

    from itertools import groupby
    entries_list = list(
        GeneralTaskEntry.objects.filter(server=server, task_id__startswith=category, date__lte=c_end)
        .order_by('task_id', '-date')
        .select_related('developer')
    )
    
    comps = []
    for task_id, group in groupby(entries_list, key=lambda e: e.task_id):
        entries = list(group)
        current = entries[0] if len(entries) >= 1 else None
        
        previous = None
        if c_start:
            for e in entries:
                if e.date <= c_start:
                    previous = e
                    break
        else:
            previous = entries[1] if len(entries) >= 2 else None
            
        if not current:
            continue
            
        fields = []
        curr_data = current.fields_data or {}
        prev_data = previous.fields_data if previous else {}
        for key, curr_val in curr_data.items():
            if key == 'verification_result':
                continue
            prev_val = prev_data.get(key, '')
            
            change = 'same'
            if str(curr_val) != str(prev_val):
                change = 'changed'
                try:
                    if curr_val and prev_val:
                        cf, pf = float(str(curr_val).replace('%', '')), float(str(prev_val).replace('%', ''))
                        if cf > pf: change = 'up'
                        elif cf < pf: change = 'down'
                except (ValueError, TypeError):
                    pass
                    
            fields.append({'key': key.replace('_', ' ').title(), 'current': curr_val,
                           'previous': prev_val, 'change': change})
                           
        comps.append({
            'task_id': task_id.upper(),
            'task_text': current.task_text,
            'current_date': current.date,
            'previous_date': previous.date if previous else None,
            'current_status': current.status,
            'developer': current.developer,
            'fields': fields,
        })
        
    comps.sort(key=lambda x: x['task_id'])
    
    context = {
        'server': server,
        'title': title,
        'comps': comps,
        'start_str': human_start_str,
        'end_str': human_end_str,
        'category': category,
        'date_generated': timezone.now()
    }
    return render(request, 'tracker/comparison_report.html', context)

@login_required
def toggle_important_server(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
        
    server_id = request.POST.get('server_id')
    if not server_id:
        return JsonResponse({'error': 'Missing server_id'}, status=400)
        
    try:
        developer = request.user.developer
        server = get_object_or_404(Server, id=server_id)
        
        if developer.important_servers.filter(id=server_id).exists():
            developer.important_servers.remove(server)
            is_important = False
        else:
            developer.important_servers.add(server)
            is_important = True
            
        return JsonResponse({'success': True, 'is_important': is_important})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
