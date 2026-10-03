from functools import wraps

from flask import abort
from flask_login import current_user

from models import ROLE_SUPER_ADMIN


def roles_required(*roles):
    """Décorateur : n'autorise l'accès qu'aux utilisateurs ayant l'un des rôles donnés.
    Le Super-Admin a toujours accès à tout."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role == ROLE_SUPER_ADMIN or current_user.role in roles:
                return view_func(*args, **kwargs)
            abort(403)

        return wrapped

    return decorator
