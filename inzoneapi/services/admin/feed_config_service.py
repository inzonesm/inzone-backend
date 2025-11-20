# services/admin/feed_config_service.py
from flask import jsonify
from config.feed_config import feed_config, FeedRecommendationConfig
import logging

logger = logging.getLogger(__name__)


class FeedConfigService:
    """Service for managing feed recommendation configuration"""

    @staticmethod
    def get_config() -> tuple:
        """
        Get current feed recommendation configuration

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            return jsonify({
                'success': True,
                'config': feed_config.to_dict()
            }), 200

        except Exception as ex:
            logger.error("Error getting feed config: %s", ex)
            return jsonify({
                'success': False,
                'error': str(ex)
            }), 500

    @staticmethod
    def update_config(data: dict) -> tuple:
        """
        Update feed recommendation configuration in real-time

        Args:
            data: Dictionary containing configuration updates with structure:
                {
                    "weights": {
                        "recency": 0.3,
                        "popularity": 0.35,
                        "category": 0.35
                    },
                    "boosts": {
                        "video": 0.0,
                        "image": 0.0,
                        "text": 0.15,
                        "human": 0.2,
                        "influencer": 0.3
                    },
                    "diversity": {
                        "enabled": true,
                        "strength": 1.0
                    }
                }

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No configuration data provided'
                }), 400

            # Update configuration
            feed_config.update_from_dict(data)

            logger.info("[FeedConfig] Configuration updated:")
            logger.info(f"  Weights: R={feed_config.recency_weight:.2f}, P={feed_config.popularity_weight:.2f}, C={feed_config.category_weight:.2f}")
            logger.info(f"  Media Boosts: Video={feed_config.video_boost:.2f}, Image={feed_config.image_boost:.2f}, Text={feed_config.text_boost:.2f}")
            logger.info(f"  User Boosts: Human={feed_config.human_boost:.2f}, Influencer={feed_config.influencer_boost:.2f}")
            logger.info(f"  Diversity: Enabled={feed_config.enable_media_diversity}, Strength={feed_config.diversity_strength:.2f}")

            return jsonify({
                'success': True,
                'message': 'Configuration updated successfully',
                'config': feed_config.to_dict()
            }), 200

        except Exception as ex:
            logger.error("[FeedConfig] Error updating configuration: %s", ex)
            return jsonify({
                'success': False,
                'error': str(ex)
            }), 500

    @staticmethod
    def reset_config() -> tuple:
        """
        Reset feed recommendation configuration to defaults

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Create a new instance with default values
            global feed_config
            from config import feed_config as config_module
            config_module.feed_config = FeedRecommendationConfig()

            logger.info("[FeedConfig] Configuration reset to defaults")

            return jsonify({
                'success': True,
                'message': 'Configuration reset to defaults',
                'config': config_module.feed_config.to_dict()
            }), 200

        except Exception as ex:
            logger.error("[FeedConfig] Error resetting configuration: %s", ex)
            return jsonify({
                'success': False,
                'error': str(ex)
            }), 500
