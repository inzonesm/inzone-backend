# config/feed_config.py
from typing import Dict, Any

class FeedRecommendationConfig:
    """
    Real-time adjustable configuration for feed recommendation algorithm.
    Allows fine-tuning of scoring weights and boosts without restarting the server.
    """
    def __init__(self):
        # Scoring weights (should sum to ~1.0)
        self.recency_weight = 0.3      # How much to value fresh content
        self.popularity_weight = 0.35  # How much to value engagement (likes, comments)
        self.category_weight = 0.35    # How much to value category matching

        # Content type boosts (multipliers on popularity score)
        self.video_boost = 0.1         # Boost for video posts (+10%)
        self.image_boost = 0.05        # Boost for image posts (+5%)
        self.text_boost = 0.0          # Boost for text-only posts (can boost to promote text)

        # User type boosts
        self.human_boost = 0.2         # Boost for posts from human users
        self.influencer_boost = 0.3    # Boost for posts from influencers (applied to final score)

        # Diversity settings
        self.enable_media_diversity = True  # Enable media type mixing
        self.diversity_strength = 1.0       # How aggressively to mix media types (0.0-2.0)

        # Media ratio enforcement (new 50/50 video-to-text/image feature)
        self.video_ratio = 0.5                      # Target percentage of videos (0.5 = 50%)
        self.enforce_strict_media_ratio = True      # Enforce exact ratio vs. best effort
        self.video_cross_category_fallback = True   # Allow videos from any category when preferred exhausted

    def to_dict(self) -> Dict[str, Any]:
        """Export config as dictionary for API responses"""
        return {
            'weights': {
                'recency': self.recency_weight,
                'popularity': self.popularity_weight,
                'category': self.category_weight,
            },
            'boosts': {
                'video': self.video_boost,
                'image': self.image_boost,
                'text': self.text_boost,
                'human': self.human_boost,
                'influencer': self.influencer_boost,
            },
            'diversity': {
                'enabled': self.enable_media_diversity,
                'strength': self.diversity_strength,
            },
            'media_ratio': {
                'video_ratio': self.video_ratio,
                'enforce_strict': self.enforce_strict_media_ratio,
                'video_cross_category_fallback': self.video_cross_category_fallback,
            }
        }

    def update_from_dict(self, config_dict: Dict[str, Any]):
        """Update config from dictionary (for API updates)"""
        if 'weights' in config_dict:
            weights = config_dict['weights']
            if 'recency' in weights:
                self.recency_weight = float(weights['recency'])
            if 'popularity' in weights:
                self.popularity_weight = float(weights['popularity'])
            if 'category' in weights:
                self.category_weight = float(weights['category'])

        if 'boosts' in config_dict:
            boosts = config_dict['boosts']
            if 'video' in boosts:
                self.video_boost = float(boosts['video'])
            if 'image' in boosts:
                self.image_boost = float(boosts['image'])
            if 'text' in boosts:
                self.text_boost = float(boosts['text'])
            if 'human' in boosts:
                self.human_boost = float(boosts['human'])
            if 'influencer' in boosts:
                self.influencer_boost = float(boosts['influencer'])

        if 'diversity' in config_dict:
            diversity = config_dict['diversity']
            if 'enabled' in diversity:
                self.enable_media_diversity = bool(diversity['enabled'])
            if 'strength' in diversity:
                self.diversity_strength = float(diversity['strength'])

        if 'media_ratio' in config_dict:
            media_ratio = config_dict['media_ratio']
            if 'video_ratio' in media_ratio:
                self.video_ratio = float(media_ratio['video_ratio'])
            if 'enforce_strict' in media_ratio:
                self.enforce_strict_media_ratio = bool(media_ratio['enforce_strict'])
            if 'video_cross_category_fallback' in media_ratio:
                self.video_cross_category_fallback = bool(media_ratio['video_cross_category_fallback'])

# Global configuration instance
feed_config = FeedRecommendationConfig()
