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

    task_data = get_dynamic_tasks()
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
        servers = Server.objects.filter(owner=request.user)
        all_logs = TaskLog.objects.filter(Q(developer=user) | Q(server__owner=user)).select_related('developer', 'server').order_by('-logged_at')[:50]
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
            'history_7d': [],
        })
        
        # Add 7-day history for visualization
        for i in range(6, -1, -1):
            day_target = today - datetime.timedelta(days=i)
            day_done = TaskLog.objects.filter(server=s, category='d', logged_at__date=day_target, status='done').count()
            day_total = len(task_data['d'])
            day_pct = round(day_done / day_total * 100) if day_total else 0
            server_list[-1]['history_7d'].append({
                'day': day_target.strftime('%a'),
                'pct': day_pct,
                'is_today': (i == 0)
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
            'server_count': Server.objects.filter(owner=u).count(),
            'weekly_pct': 0, 
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

    # --- TEAM STATS AGGREGATION ---
    team_avg = round(sum(m['daily_pct'] for m in team_members) / len(team_members)) if team_members else 0
    full_comp = sum(1 for m in team_members if m['daily_pct'] == 100)
    needs_attn = sum(1 for m in team_members if m['daily_pct'] < 50)

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
    today = timezone.now().date()
    
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
            'logged_at': timezone.now() # Update time to latest edit
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

    return JsonResponse({'success': True})


@login_required
def get_task_details(request):
    """AJAX endpoint: returns the previously saved data for a task today."""
    task_id = request.GET.get('task_id')
    server_id = request.GET.get('server_id')
    today = timezone.now().date()
    
    # Role-based check
    if request.user.developer.role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, id=server_id, owner=request.user)
    
    if request.user.developer.role in ['manager', 'tl']:
        log = TaskLog.objects.filter(
            server=server, 
            task_id=task_id, 
            logged_at__date=today
        ).first()
    else:
        log = TaskLog.objects.filter(
            developer=request.user, 
            server=server, 
            task_id=task_id, 
            logged_at__date=today
        ).first()
    
    if request.user.developer.role in ['manager', 'tl']:
        entry = GeneralTaskEntry.objects.filter(
            server=server, 
            task_id=task_id, 
            date=today
        ).first()
    else:
        entry = GeneralTaskEntry.objects.filter(
            developer=request.user, 
            server=server, 
            task_id=task_id, 
            date=today
        ).first()

    # Fetch PREVIOUS entry for comparison (most recent before today)
    prev_entry = GeneralTaskEntry.objects.filter(
        server=server, 
        task_id=task_id, 
        date__lt=today
    ).order_by('-date').first()

    if not log:
        return JsonResponse({
            'exists': False,
            'prev_fields_data': prev_entry.fields_data if prev_entry else {}
        })

    # Try to extract the clean notes (strip the [STATUS] prefix if it exists)
    clean_notes = log.notes
    if clean_notes.startswith('[') and ']' in clean_notes:
        clean_notes = clean_notes.split(']', 1)[1].strip()

    return JsonResponse({
        'exists': True,
        'status': log.status,
        'notes': clean_notes,
        'fields_data': entry.fields_data if entry else {},
        'prev_fields_data': prev_entry.fields_data if prev_entry else {}
    })


@login_required
def server_management(request, server_id):
    viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'
    
    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        # Role-based check
        if request.user.developer.role in ['manager', 'tl']:
            server = get_object_or_404(Server, id=server_id)
        else:
            server = get_object_or_404(Server, id=server_id, owner=request.user)
        
    today = timezone.now().date()
    task_data = get_dynamic_tasks()
    
    # Show logs for this server today (either by owner or current user)
    # If manager is viewing, show the owner's progress or the server's general progress
    today_logs = TaskLog.objects.filter(server=server, logged_at__date=today)
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

    # Owner logic: Managers/TLs can assign to others; Developers only to themselves.
    owner = request.user
    owner_id = data.get('owner_id')
    viewer_role = request.user.developer.role if hasattr(request.user, 'developer') else 'developer'

    if owner_id and viewer_role in ['manager', 'tl']:
        try:
            target_owner = User.objects.get(id=owner_id)
            owner = target_owner
        except User.DoesNotExist:
            pass

    if Server.objects.filter(name__iexact=name, owner=owner).exists():
        return JsonResponse({'success': False, 'error': f'A server named "{name}" already exists for this owner.'}, status=400)

    server = Server.objects.create(
        name=name,
        ip_address=ip_address,
        owner=owner,
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
    # Role-based check
    if request.user.developer.role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
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
    # Role-based check
    if request.user.developer.role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
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
        })

    # ── Team-wide KPIs ──────────────────────────────────────────
    total_users = all_users.count()
    total_tasks_today = TaskLog.objects.filter(logged_at__date=today).count()
    total_done_today = TaskLog.objects.filter(logged_at__date=today, status='done').count()
    total_blocked = TaskLog.objects.filter(logged_at__date=today, status='blk').count()
    total_servers = Server.objects.count()
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
def user_management(request):
    """Create and list users. TL can only create developers; Manager can create TLs too."""
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

            new_user = User.objects.create(
                username=username,
                email=email,
                password=make_password(password),
                is_active=True,
            )
            Developer.objects.create(
                user=new_user,
                role=new_role,
                job_title='DevOps Engineer',
            )
            
            # Assign servers
            if assigned_server_ids:
                Server.objects.filter(id__in=assigned_server_ids).update(owner=new_user)

            messages.success(request, f'User "{username}" created successfully as {new_role}.')
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
    response['Content-Disposition'] = 'attachment; filename="devops_team_report.csv"'

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
    """Server Details (Detailed Infrastructure Audit View)."""
    user = request.user
    # Role-based check: Superusers/Staff are managers; otherwise check developer role.
    if user.is_superuser or user.is_staff:
        viewer_role = 'manager'
    else:
        viewer_role = user.developer.role if hasattr(user, 'developer') else 'developer'

    if viewer_role in ['manager', 'tl']:
        server = get_object_or_404(Server, id=server_id)
    else:
        server = get_object_or_404(Server, id=server_id, owner=user)

    recent_logs = TaskLog.objects.filter(server=server).select_related('developer').order_by('-logged_at')[:100]
    health_entries = ServerHealthEntry.objects.filter(server_name=server.name).order_by('-date', '-created_at')[:14]
    alert_entries = AlertCheckEntry.objects.filter(server=server).order_by('-date', '-created_at')[:10]
    total_tasks_done = TaskLog.objects.filter(server=server, status='done').count()
    total_blocks = TaskLog.objects.filter(server=server, status='blk').count()
    
    context = {
        'server': server, 'recent_logs': recent_logs, 'health_entries': health_entries,
        'alert_entries': alert_entries, 'total_tasks_done': total_tasks_done,
        'total_blocks': total_blocks, 'viewer_role': viewer_role,
    }
    return render(request, 'tracker/server_details.html', context)
