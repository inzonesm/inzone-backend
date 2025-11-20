# routes/groups/__init__.py
from .management import groups_mgmt_bp
from .access import groups_access_bp

__all__ = [
    'groups_mgmt_bp',
    'groups_access_bp'
]
