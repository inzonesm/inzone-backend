# routes/admin/__init__.py
from .store import admin_store_bp
from .groups import admin_groups_bp
from .feed_config import admin_feed_config_bp

__all__ = [
    'admin_store_bp',
    'admin_groups_bp',
    'admin_feed_config_bp'
]
