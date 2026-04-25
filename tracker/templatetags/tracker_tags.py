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

@register.filter
def jsonify(value):
    return json.dumps(value)
