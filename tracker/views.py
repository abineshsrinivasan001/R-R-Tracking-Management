from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count, Q
import json
import datetime

from .models import (
    TaskLog, ServerHealthEntry, AlertCheckEntry,
    PipelineEntry, DeploymentEntry, Developer, TaskDefinition,
    Server, GeneralTaskEntry
)
from .forms import (
    ServerHealthForm, AlertCheckForm,
    PipelineForm, DeploymentForm
)

# Task → entry form mapping (can be moved to TaskDefinition model later if needed)
TASK_ENTRY_MAP = {
    'd01': ('server_health', 'Monitor Server Health'),
    'd02': ('alert_check', 'Check Application & Infrastructure Alerts'),
    'd03': ('pipeline', 'Review CI/CD Pipeline Status'),
    'd04': ('deployment', 'Validate Deployment of Releases'),
}

def get_dynamic_tasks():
    tasks = {
        'd': list(TaskDefinition.objects.filter(category='d', is_active=True).values('task_id', 'text', 'priority', 'fields_schema')),
        'w': list(TaskDefinition.objects.filter(category='w', is_active=True).values('task_id', 'text', 'priority', 'fields_schema')),
        'm': list(TaskDefinition.objects.filter(category='m', is_active=True).values('task_id', 'text', 'priority', 'fields_schema')),
    }
    # Rename priority to pri for template compatibility
    for cat in tasks:
        for t in tasks[cat]:
            t['id'] = t.pop('task_id')
            t['pri'] = t.pop('priority')
            t['fields'] = t.pop('fields_schema')
    return tasks


@login_required
def dashboard(request):
    today = timezone.now().date()
    user = request.user

    today_logs = TaskLog.objects.filter(developer=user, logged_at__date=today)
    logged_ids = {log.task_id: log.status for log in today_logs}

    task_data = get_dynamic_tasks()
    daily_done = sum(1 for t in task_data['d'] if logged_ids.get(t['id']) == 'done')
    weekly_done = sum(1 for t in task_data['w'] if logged_ids.get(t['id']) == 'done')
    monthly_done = sum(1 for t in task_data['m'] if logged_ids.get(t['id']) == 'done')

    recent_logs = TaskLog.objects.filter(developer=user).select_related('developer')[:20]
    all_logs = TaskLog.objects.all().select_related('developer').order_by('-logged_at')[:50]

    # Server data - Filtered to only show "Ours" (Assigned to the current user)
    servers = Server.objects.filter(owner=request.user)
    server_list = []
    for s in servers:
        # Daily
        s_logs_d = TaskLog.objects.filter(server=s, category='d', logged_at__date=today, status='done')
        s_done_d = s_logs_d.count()
        
        # Weekly (Last 7 days)
        week_ago = today - datetime.timedelta(days=7)
        s_logs_w = TaskLog.objects.filter(server=s, category='w', logged_at__date__gte=week_ago, status='done')
        s_done_w = s_logs_w.count()
        
        # Monthly (Last 30 days)
        month_ago = today - datetime.timedelta(days=30)
        s_logs_m = TaskLog.objects.filter(server=s, category='m', logged_at__date__gte=month_ago, status='done')
        s_done_m = s_logs_m.count()

        server_list.append({
            'id': s.id,
            'name': s.name,
            'ip': s.ip_address,
            'status': s.status,
            'last_checked': s.last_checked,
            'daily_pct': round(s_done_d / len(task_data['d']) * 100) if task_data['d'] else 0,
            'weekly_pct': round(s_done_w / len(task_data['w']) * 100) if task_data['w'] else 0,
            'monthly_pct': round(s_done_m / len(task_data['m']) * 100) if task_data['m'] else 0,
            'daily_done': s_done_d,
            'daily_total': len(task_data['d']),
            'weekly_done': s_done_w,
            'weekly_total': len(task_data['w']),
            'monthly_done': s_done_m,
            'monthly_total': len(task_data['m']),
        })

    # Team stats with real data
    team_members = []
    all_users = User.objects.filter(is_active=True).select_related('developer')
    for u in all_users:
        u_today_done = TaskLog.objects.filter(developer=u, logged_at__date=today, status='done').count()
        u_total_daily = len(task_data['d'])
        u_pct = round(u_today_done / u_total_daily * 100) if u_total_daily else 0
        
        team_members.append({
            'user': u,
            'initials': u.developer.initials if hasattr(u, 'developer') else u.username[:2].upper(),
            'role': u.developer.role if hasattr(u, 'developer') else 'Member',
            'gradient': u.developer.avatar_gradient if hasattr(u, 'developer') else 'linear-gradient(135deg,#64748b,#475569)',
            'daily_pct': u_pct,
            'weekly_pct': 0, # Placeholder for now
        })

    # --- NEW PRACTICAL LOGIC ---
    server_count = servers.count()
    daily_task_defs = TaskDefinition.objects.filter(category='d', is_active=True)
    daily_task_count = daily_task_defs.count()
    
    # Total verifications needed = tasks * servers
    total_needed_today = daily_task_count * server_count
    
    # Verifications actually done today (must be linked to a server)
    done_today_count = TaskLog.objects.filter(
        developer=user, 
        category='d', 
        logged_at__date=today, 
        status='done',
        server__isnull=False
    ).values('server', 'task_id').distinct().count()

    # Streak Calculation (Real consecutive days of 100% completion)
    streak = 0
    check_date = today
    while True:
        # Check if all tasks were done on this date
        day_needed = daily_task_count * Server.objects.filter(owner=user).count()
        day_done = TaskLog.objects.filter(
            developer=user, category='d', 
            logged_at__date=check_date, status='done',
            server__isnull=False
        ).values('server', 'task_id').distinct().count()
        
        if day_needed > 0 and day_done >= day_needed:
            streak += 1
            check_date -= datetime.timedelta(days=1)
        else:
            break
    
    daily_pct = round(done_today_count / total_needed_today * 100) if total_needed_today else 0
    
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

    hour = timezone.localtime(timezone.now()).hour
    greeting = 'Morning' if hour < 12 else ('Afternoon' if hour < 17 else 'Evening')

    context = {
        'task_data': task_data,
        'task_data_json': json.dumps(task_data),
        'logged_ids': logged_ids,
        'daily_done': done_today_count,
        'daily_total': total_needed_today,
        'daily_pct': daily_pct,
        'weekly_done': weekly_done,
        'weekly_total': len(task_data['w']),
        'weekly_pct': round(weekly_done / len(task_data['w']) * 100) if task_data['w'] else 0,
        'monthly_done': monthly_done,
        'monthly_total': len(task_data['m']),
        'monthly_pct': round(monthly_done / len(task_data['m']) * 100) if task_data['m'] else 0,
        'compliance': compliance,
        'recent_logs': recent_logs,
        'all_logs': all_logs,
        'team_members': team_members,
        'critical_nodes_count': critical_nodes_count,
        'blocked_count': blocked_count,
        'streak': streak,
        'today': today,
        'task_entry_map': TASK_ENTRY_MAP,
        'greeting': greeting,
        'servers': server_list,
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
    
    server = Server.objects.filter(id=server_id).first() if server_id else None
    
    category = task_id[0] if task_id else 'd'
    task_text = TaskDefinition.objects.filter(task_id=task_id).values_list('text', flat=True).first() or ''

    log = TaskLog.objects.create(
        developer=request.user,
        server=server,
        task_id=task_id,
        task_text=task_text,
        category=category,
        status=status,
        notes=notes
    )

    if status == 'done':
        GeneralTaskEntry.objects.create(
            developer=request.user,
            server=server,
            task_id=task_id,
            task_text=task_text,
            status=status,
            fields_data=fields_data,
            remarks=notes
        )

    return JsonResponse({'success': True})


@login_required
def server_management(request, server_id):
    server = get_object_or_404(Server, id=server_id, owner=request.user)
    today = timezone.now().date()
    
    task_data = get_dynamic_tasks()
    today_logs = TaskLog.objects.filter(server=server, developer=request.user, logged_at__date=today)
    logged_ids = {log.task_id: log.status for log in today_logs}
    
    # Last 7 days compliance for widgets
    compliance_7d = []
    daily_count = len(task_data['d'])
    for i in range(6, -1, -1):
        day = today - timezone.timedelta(days=i)
        logs = TaskLog.objects.filter(server=server, logged_at__date=day, category='d', status='done').count()
        pct = (logs / daily_count * 100) if daily_count > 0 else 0
        compliance_7d.append({
            'label': day.strftime('%a')[0],
            'pct': round(pct),
            'is_today': i == 0
        })

    history = TaskLog.objects.filter(server=server).order_by('-logged_at')[:20]

    context = {
        'server': server,
        'task_data': task_data,
        'task_data_json': json.dumps(task_data),
        'logged_ids': logged_ids,
        'history': history,
        'today': today,
        'compliance_7d': compliance_7d,
    }
    return render(request, 'tracker/server_management.html', context)

# ─── Server Health ───────────────────────────────────────────────
@login_required
def server_health_list(request):
    entries = ServerHealthEntry.objects.filter(developer=request.user).order_by('-date', '-created_at')
    form = ServerHealthForm(initial={'date': timezone.now().date()})
    return render(request, 'tracker/entries/server_health.html', {'entries': entries, 'form': form})


@login_required
def server_health_create(request):
    if request.method == 'POST':
        form = ServerHealthForm(request.POST)
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

    if not name:
        return JsonResponse({'success': False, 'error': 'Server name is required.'}, status=400)

    if Server.objects.filter(name__iexact=name, owner=request.user).exists():
        return JsonResponse({'success': False, 'error': f'A server named "{name}" already exists.'}, status=400)

    server = Server.objects.create(
        name=name,
        ip_address=ip_address,
        owner=request.user,
        status='up'
    )
    return JsonResponse({'success': True, 'server_id': server.id, 'server_name': server.name})


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
    server = get_object_or_404(Server, id=server_id, owner=request.user)
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
    server = get_object_or_404(Server, id=server_id, owner=request.user)
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
