# -*- coding: utf-8 -*-
from functools import wraps
from flask import redirect, url_for, request, flash
from flask_login import current_user

def _safe(url_name: str, default: str = "/"):
    try:
        return url_for(url_name)
    except Exception:
        return default

def roles_required(*roles):
    """
    Если не залогинен -> редирект на /login (или auth.login).
    Если роли нет в списке -> редирект на главную и флэш "Недостаточно прав".
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                login_url = _safe("auth.login", "/login")
                # без городов с next: простая переадресация
                return redirect(login_url)
            if current_user.role not in roles:
                flash("Недостаточно прав для доступа.", "warning")
                return redirect(_safe("index", "/"))
            return f(*args, **kwargs)
        return wrapper
    return decorator
