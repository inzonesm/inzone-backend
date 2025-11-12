"""
AI Engagement Scheduler for InZone

This module handles scheduling of AI engagement cycles to ensure organic,
natural timing of AI interactions throughout the day.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from threading import Thread
import time
from .inzone_ai_engagement import InZoneAIEngagementService

logger = logging.getLogger(__name__)

class AIEngagementScheduler:
    def __init__(self, engagement_service: InZoneAIEngagementService):
        self.engagement_service = engagement_service
        self.running = False
        self.scheduler_thread = None
        
    def start_scheduler(self):
        """Start the AI engagement scheduler"""
        if self.running:
            logger.warning("Scheduler is already running")
            return
            
        self.running = True
        self.scheduler_thread = Thread(target=self._run_scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("AI engagement scheduler started")
    
    def stop_scheduler(self):
        """Stop the AI engagement scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("AI engagement scheduler stopped")
    
    def _run_scheduler_loop(self):
        """Main scheduler loop - runs in separate thread"""
        while self.running:
            try:
                # Calculate next run time (organic timing)
                next_run_minutes = self._calculate_next_run_interval()
                logger.info(f"Next AI engagement cycle in {next_run_minutes} minutes")
                
                # Sleep until next run
                sleep_seconds = next_run_minutes * 60
                for _ in range(int(sleep_seconds)):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                    
                # Run engagement cycle
                logger.info("Starting scheduled AI engagement cycle")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.engagement_service.process_ai_engagement_cycle())
                loop.close()
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                # Wait 5 minutes before retrying on error
                for _ in range(300):
                    if not self.running:
                        break
                    time.sleep(1)
    
    def _calculate_next_run_interval(self) -> int:
        """Calculate when to run next engagement cycle (in minutes)"""
        current_hour = datetime.now().hour
        
        # Peak engagement times (more frequent interactions)
        peak_hours = [9, 10, 11, 12, 13, 17, 18, 19, 20, 21]  # Morning, lunch, evening
        
        if current_hour in peak_hours:
            # Peak hours: run every 30-90 minutes
            return random.randint(30, 90)
        elif 6 <= current_hour <= 23:
            # Regular hours: run every 60-180 minutes
            return random.randint(60, 180)
        else:
            # Night hours: run every 180-360 minutes (3-6 hours)
            return random.randint(180, 360)
    
    def trigger_immediate_cycle(self):
        """Trigger an immediate engagement cycle (for manual/admin triggers)"""
        def run_cycle():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.engagement_service.process_ai_engagement_cycle())
                loop.close()
                logger.info("Manual AI engagement cycle completed")
            except Exception as e:
                logger.error(f"Error in manual engagement cycle: {e}")
        
        # Run in separate thread to avoid blocking
        thread = Thread(target=run_cycle, daemon=True)
        thread.start()
        return thread

class EngagementAnalytics:
    """Analytics for AI engagement patterns"""
    
    def __init__(self, db):
        self.db = db
    
    def get_engagement_trends(self, days: int = 7) -> dict:
        """Get engagement trends over the past N days"""
        try:
            from datetime import datetime, timedelta
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            interactions_ref = self.db.collection('aiInteractions')
            query = interactions_ref.where('timestamp', '>=', start_date)\
                                  .where('timestamp', '<=', end_date)
            
            snapshot = query.stream()
            interactions = [doc.to_dict() for doc in snapshot]
            
            # Group by day and type
            trends = {}
            for interaction in interactions:
                timestamp = interaction.get('timestamp')
                if hasattr(timestamp, 'date'):
                    date_str = timestamp.date().isoformat()
                else:
                    continue
                    
                if date_str not in trends:
                    trends[date_str] = {
                        'total': 0,
                        'comments': 0,
                        'likes': 0,
                        'dms': 0,
                        'ai_users_active': set()
                    }
                
                trends[date_str]['total'] += 1
                interaction_type = interaction.get('interaction_type', '')
                if interaction_type in ['comment', 'like', 'dm']:
                    trends[date_str][f"{interaction_type}s"] += 1
                
                ai_user_id = interaction.get('ai_user_id')
                if ai_user_id:
                    trends[date_str]['ai_users_active'].add(ai_user_id)
            
            # Convert sets to counts
            for date_data in trends.values():
                date_data['ai_users_active'] = len(date_data['ai_users_active'])
            
            return trends
            
        except Exception as e:
            logger.error(f"Error getting engagement trends: {e}")
            return {}
    
    def get_top_engaging_ais(self, days: int = 7, limit: int = 10) -> list:
        """Get AI users with most engagement in past N days"""
        try:
            from datetime import datetime, timedelta
            from collections import Counter
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            interactions_ref = self.db.collection('aiInteractions')
            query = interactions_ref.where('timestamp', '>=', start_date)\
                                  .where('timestamp', '<=', end_date)
            
            snapshot = query.stream()
            interactions = [doc.to_dict() for doc in snapshot]
            
            ai_engagement_counts = Counter()
            for interaction in interactions:
                ai_user_id = interaction.get('ai_user_id')
                if ai_user_id:
                    ai_engagement_counts[ai_user_id] += 1
            
            return ai_engagement_counts.most_common(limit)
            
        except Exception as e:
            logger.error(f"Error getting top engaging AIs: {e}")
            return []
    
    def get_user_ai_interactions(self, user_id: str, days: int = 30) -> dict:
        """Get how much AI interaction a specific user has received"""
        try:
            from datetime import datetime, timedelta
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            interactions_ref = self.db.collection('aiInteractions')
            query = interactions_ref.where('target_user_id', '==', user_id)\
                                  .where('timestamp', '>=', start_date)\
                                  .where('timestamp', '<=', end_date)
            
            snapshot = query.stream()
            interactions = [doc.to_dict() for doc in snapshot]
            
            summary = {
                'total_interactions': len(interactions),
                'comments_received': 0,
                'likes_received': 0,
                'dms_received': 0,
                'unique_ai_interactions': set(),
                'interactions_by_ai': {}
            }
            
            for interaction in interactions:
                interaction_type = interaction.get('interaction_type', '')
                ai_user_id = interaction.get('ai_user_id', '')
                
                if interaction_type == 'comment':
                    summary['comments_received'] += 1
                elif interaction_type == 'like':
                    summary['likes_received'] += 1
                elif interaction_type == 'dm':
                    summary['dms_received'] += 1
                
                if ai_user_id:
                    summary['unique_ai_interactions'].add(ai_user_id)
                    if ai_user_id not in summary['interactions_by_ai']:
                        summary['interactions_by_ai'][ai_user_id] = 0
                    summary['interactions_by_ai'][ai_user_id] += 1
            
            summary['unique_ai_interactions'] = len(summary['unique_ai_interactions'])
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting user AI interactions: {e}")
            return {}
