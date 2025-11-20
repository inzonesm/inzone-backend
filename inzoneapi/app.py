import logging
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config

# Import blueprints
from routes.core.health import health_bp
from routes.user.profile import user_profile_bp
from routes.user.social import user_social_bp
from routes.user.referral import user_referral_bp
from routes.content.posts import posts_bp
from routes.content.feed import feed_bp
from routes.content.comments import comments_bp
from routes.content.gorse import gorse_bp
from routes.monetization.wallet import wallet_bp
from routes.monetization.tipping import tipping_bp
from routes.monetization.store import store_bp
from routes.monetization.subscription import subscription_bp
from routes.ai.voice import ai_voice_bp
from routes.ai.chat import ai_chat_bp
from routes.ai.users import ai_users_bp
from routes.ai.social import ai_social_mgmt_bp as ai_social_bp
from routes.ai.content import ai_content_bp
from routes.ai.engagement import ai_engagement_bp
from routes.ai.scheduler import ai_scheduler_bp
from routes.ai.characters import ai_characters_bp
from routes.ai.user_management import ai_user_mgmt_bp
from routes.groups.management import groups_mgmt_bp
from routes.groups.access import groups_access_bp
from routes.groups.recommendations import groups_recommendations_bp
from routes.notifications.events import notif_events_bp
from routes.notifications.preferences import notif_prefs_bp
from routes.notifications.push import notif_push_bp
from routes.notifications.debug import notif_debug_bp
from routes.admin.store import admin_store_bp
from routes.admin.groups import admin_groups_bp
from routes.admin.feed_config import admin_feed_config_bp
from routes.admin.users import admin_users_bp
from routes.admin.maintenance import admin_maintenance_bp
from routes.media.generation import media_generation_bp
from routes.api.sentiment import sentiment_bp
from routes.api.chat import api_chat_bp
from routes.api.users import api_users_bp
from routes.api.profiles import api_profiles_bp
from routes.scheduler.notifications import scheduler_notif_bp

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(user_profile_bp)
app.register_blueprint(user_social_bp)
app.register_blueprint(user_referral_bp)
app.register_blueprint(posts_bp)
app.register_blueprint(feed_bp)
app.register_blueprint(comments_bp)
app.register_blueprint(gorse_bp)
app.register_blueprint(wallet_bp)
app.register_blueprint(tipping_bp)
app.register_blueprint(store_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(ai_voice_bp)
app.register_blueprint(ai_chat_bp)
app.register_blueprint(ai_users_bp)
app.register_blueprint(ai_social_bp)
app.register_blueprint(ai_content_bp)
app.register_blueprint(ai_engagement_bp)
app.register_blueprint(ai_scheduler_bp)
app.register_blueprint(ai_characters_bp)
app.register_blueprint(ai_user_mgmt_bp)
app.register_blueprint(groups_mgmt_bp)
app.register_blueprint(groups_access_bp)
app.register_blueprint(groups_recommendations_bp)
app.register_blueprint(notif_events_bp)
app.register_blueprint(notif_prefs_bp)
app.register_blueprint(notif_push_bp)
app.register_blueprint(notif_debug_bp)
app.register_blueprint(admin_store_bp)
app.register_blueprint(admin_groups_bp)
app.register_blueprint(admin_feed_config_bp)
app.register_blueprint(admin_users_bp)
app.register_blueprint(admin_maintenance_bp)
app.register_blueprint(media_generation_bp)
app.register_blueprint(sentiment_bp)
app.register_blueprint(api_chat_bp)
app.register_blueprint(api_users_bp)
app.register_blueprint(api_profiles_bp)
app.register_blueprint(scheduler_notif_bp)

# Favicon route to prevent 404 errors
@app.route('/favicon.ico')
def favicon():
    """Return empty response for favicon to prevent 404 errors"""
    from flask import make_response
    response = make_response('', 204)  # 204 No Content
    response.headers['Content-Type'] = 'image/x-icon'
    return response

# 404 error handler (specific routes not found)
@app.errorhandler(404)
def handle_404(e):
    """Handle 404 errors gracefully without logging as unhandled exceptions"""
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

# Global error handler for other exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    # Don't log 404 as unhandled exceptions
    from werkzeug.exceptions import NotFound
    if isinstance(e, NotFound):
        return jsonify({"success": False, "error": "Not found"}), 404
    
    logger.exception("[unhandled] %s", e)
    return jsonify({"success": False, "error": "Internal error"}), 500

# Import enhanced AI engagement service
from services.ai.engagement.inzone_ai_engagement import InZoneAIEngagementService
from services.ai.engagement.ai_engagement_scheduler import AIEngagementScheduler
from dependencies import db, openai_client

# Initialize enhanced AI engagement service
inzone_ai_service = InZoneAIEngagementService(db, openai_client)

# Initialize AI engagement scheduler
ai_engagement_scheduler = AIEngagementScheduler(inzone_ai_service)

# Import feed configuration
from config.feed_config import feed_config

# Initialize category mapping on startup
from services.content.category_service import CategoryService
TOPIC_TO_CATEGORY_MAP = CategoryService.initialize_category_mapping()

# Initialize AI scheduler service and inject into scheduler blueprint
from services.ai.scheduler_service import AISchedulerService
from routes.ai.scheduler import init_scheduler_service

scheduler_service = AISchedulerService(ai_engagement_scheduler)
init_scheduler_service(scheduler_service)

# Initialize AI engagement services and inject into engagement blueprint
from services.ai.engagement_service import AIEngagementService
from services.ai.bulk_engagement_service import AIBulkEngagementService
from services.ai.scheduling_wrapper_service import AISchedulingWrapperService
from routes.ai.engagement import init_engagement_services
from ai_scheduler import AIScheduler

# Create AI scheduler instance (using AIScheduler from ai_scheduler.py)
ai_scheduler = AIScheduler(db)

# Initialize engagement services
engagement_service = AIEngagementService(inzone_ai_service)
bulk_engagement_service = AIBulkEngagementService(inzone_ai_service)
scheduling_service = AISchedulingWrapperService(ai_scheduler)

# Inject services into engagement blueprint
init_engagement_services(engagement_service, bulk_engagement_service, scheduling_service)

# ---------------------------
# Initialize AI Scheduler Endpoint Service
# ---------------------------
from services.ai.scheduler_endpoint_service import AISchedulerEndpointService
from routes.ai.scheduler_endpoints import scheduler_endpoint_bp, init_scheduler_service as init_scheduler_endpoint_service

# Create AIScheduler instance for scheduler endpoints
ai_scheduler_instance = AIScheduler(db)
scheduler_endpoint_service = AISchedulerEndpointService(ai_scheduler_instance, db)
init_scheduler_endpoint_service(scheduler_endpoint_service)
app.register_blueprint(scheduler_endpoint_bp)

# ---------------------------
# Initialize AI Data Maintenance Service
# ---------------------------
from services.ai.data_maintenance_service import AIDataMaintenanceService
from routes.ai.maintenance import ai_maintenance_bp, init_maintenance_service

maintenance_service = AIDataMaintenanceService(db)
init_maintenance_service(maintenance_service)
app.register_blueprint(ai_maintenance_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
