"""
Role-based access decorators for the DevOps Tracker.

Usage:
    @manager_required        — only Manager role
    @tl_or_manager_required  — TL or Manager
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def _get_role(user):
    """Safely returns the Developer.role string or None."""
    if user.is_superuser or user.is_staff:
        return 'manager'
    try:
        return user.developer.role
    except Exception:
        return None


def manager_required(view_func):
    """Restricts the view to Manager-role users only."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        role = _get_role(request.user)
        if role != 'manager':
            messages.error(request, 'Access denied — Manager role required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def tl_or_manager_required(view_func):
    """Restricts the view to TL or Manager roles."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        role = _get_role(request.user)
        if role not in ('manager', 'tl'):
            messages.error(request, 'Access denied — Team Lead or Manager role required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped
