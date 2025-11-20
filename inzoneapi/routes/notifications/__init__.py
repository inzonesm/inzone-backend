# routes/notifications/__init__.py
from .events import notif_events_bp
from .push import notif_push_bp
from .preferences import notif_prefs_bp
from .debug import notif_debug_bp

__all__ = [
    'notif_events_bp',
    'notif_push_bp',
    'notif_prefs_bp',
    'notif_debug_bp'
]
