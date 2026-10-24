from django import template
import json

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get dict item by key in templates"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''

@register.filter
def get_entry_url(task_entry_map, task_id):
    """Get the URL name for a task entry form"""
    mapping = {
        'd01': 'server_health_list',
        'd02': 'alert_check_list',
        'd03': 'pipeline_list',
        'd04': 'deployment_list',
    }
    return mapping.get(task_id, 'dashboard')

@register.filter
def subtract(value, arg):
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def calculate_offset(percentage, total_dash):
    """Calculates SVG stroke-dashoffset based on percentage"""
    try:
        pct = float(percentage)
        dash = float(total_dash)
        return dash * (1 - pct / 100)
    except (ValueError, TypeError):
        return total_dash

@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg) if float(arg) != 0 else 0
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

@register.filter
def jsonify(value):
    return json.dumps(value, cls=DateTimeEncoder)

@register.filter
def get_range(value):
    try:
        return range(int(value))
    except (ValueError, TypeError):
        return range(0)

@register.filter
def percentage(value, total):
    try:
        return round((float(value) / float(total)) * 100) if float(total) != 0 else 0
    except (ValueError, TypeError):
        return 0

@register.filter
def replace(value, arg):
    """Replace all occurrences of a string with another. Usage: {{ val|replace:'old,new' }}"""
    if not isinstance(value, str):
        return value
    if ',' not in arg:
        return value
    old, new = arg.split(',', 1)
    return value.replace(old, new)

@register.filter
def get_role(user):
    """Safely get the role of a user, preventing RelatedObjectDoesNotExist if developer profile is missing."""
    if not user.is_authenticated:
        return 'anonymous'
    if user.is_superuser or user.is_staff:
        return 'manager'
    if hasattr(user, 'developer'):
        return user.developer.role
    return 'developer'


@register.simple_tag
def get_server_notifications(user):
    """
    Fetches real active alerts for accessible servers:
    - Offline/Down servers
    - High CPU/RAM/Disk or Critical/Warning health breaches
    Returns a clean list of wanted server notifications.
    """
    if not user or not user.is_authenticated:
        return []

    from django.db.models import Q
    from django.urls import reverse
    from django.utils import timezone
    from tracker.models import Server, ServerHealthEntry

    is_mgmt = (
        user.is_superuser 
        or user.is_staff 
        or getattr(getattr(user, 'developer', None), 'role', None) in ('manager', 'tl')
    )
    if is_mgmt:
        accessible_servers = Server.objects.all()
    else:
        accessible_servers = Server.objects.filter(Q(owner=user) | Q(assigned_users=user)).distinct()

    # Scope notifications strictly to Important Servers if defined
    dev = getattr(user, 'developer', None)
    if dev and dev.important_servers.exists():
        important_ids = list(dev.important_servers.values_list('id', flat=True))
        accessible_servers = accessible_servers.filter(id__in=important_ids)
    else:
        fav_ids = list(Server.objects.filter(favorited_by_devs__isnull=False).values_list('id', flat=True))
        if fav_ids:
            accessible_servers = accessible_servers.filter(id__in=fav_ids)

    notifications = []
    seen_servers = set()
    today = timezone.now().date()
    server_map = {s.name: s for s in accessible_servers}

    # 1. Critical / Down servers
    down_servers = accessible_servers.filter(status='down').order_by('name')
    for s in down_servers[:4]:
        seen_servers.add(s.name)
        notifications.append({
            'level': 'critical',
            'server_id': s.id,
            'server_name': s.name,
            'ip_address': s.ip_address or 'No IP',
            'headline': f"{s.name} is Offline",
            'detail': f"{s.ip_address or 'Server'} unreachable · Check connection",
            'time': s.last_checked.strftime('%H:%M') if s.last_checked else 'Down',
            'url': reverse('server_management', args=[s.id]),
        })

    # 2. Critical / Warning health entries today
    health_entries = ServerHealthEntry.objects.filter(
        date=today,
        server_name__in=accessible_servers.values_list('name', flat=True),
        issue_found=True
    ).order_by('-cpu_usage')

    for h in health_entries:
        if h.server_name in seen_servers:
            continue
        seen_servers.add(h.server_name)
        srv = server_map.get(h.server_name)
        srv_id = srv.id if srv else None
        srv_ip = srv.ip_address if srv else ''

        issues = []
        if h.cpu_usage and h.cpu_usage >= 75:
            issues.append(f"CPU {h.cpu_usage:.0f}%")
        if h.memory_usage and h.memory_usage >= 80:
            issues.append(f"RAM {h.memory_usage:.0f}%")
        if h.disk_usage and h.disk_usage >= 85:
            issues.append(f"Disk {h.disk_usage:.0f}%")
        if h.docker_failed and h.docker_failed > 0:
            issues.append(f"{h.docker_failed} crashed containers")

        issue_text = ", ".join(issues) if issues else (h.action_taken or "Threshold breached")
        is_crit = (h.status == 'critical' or (h.cpu_usage and h.cpu_usage >= 90))

        notifications.append({
            'level': 'critical' if is_crit else 'warning',
            'server_id': srv_id,
            'server_name': h.server_name,
            'ip_address': srv_ip,
            'headline': f"{h.server_name} — {issue_text}",
            'detail': f"{srv_ip} · Status: {h.status.upper()}" if srv_ip else f"Status: {h.status.upper()}",
            'time': 'Today',
            'url': reverse('server_management', args=[srv_id]) if srv_id else reverse('dashboard'),
        })
        if len(notifications) >= 6:
            break

    return notifications

