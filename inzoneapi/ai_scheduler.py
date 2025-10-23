#!/usr/bin/env python3
"""
AI Scheduler for InZone
Manages scheduled AI interactions for both popularCharacters and aiUsers
with sophisticated rate limiting, cooldowns, and quality safeguards.
"""

import os
import random
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import firebase_admin
from firebase_admin import firestore
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EngagementType(Enum):
    LIKE = "like"
    COMMENT = "comment"
    DM = "dm"

class TimeWindow(Enum):
    MORNING = "morning"      # 6AM - 12PM
    AFTERNOON = "afternoon"  # 12PM - 6PM
    EVENING = "evening"      # 6PM - 12AM

@dataclass
class EngagementLimits:
    """Daily engagement limits per character"""
    comments_min: int = 2
    comments_max: int = 4
    likes_min: int = 5
    likes_max: int = 7
    dms_max: int = 1

@dataclass
class CooldownRules:
    """Cooldown rules for AI interactions"""
    same_user_comment_hours: int = 24
    dm_no_reply_days: int = 3
    user_interaction_min_hours: int = 48  # 2-3 days minimum
    user_interaction_max_hours: int = 72
    max_daily_interactions_per_user: int = 2

@dataclass
class EngagementRatios:
    """Target engagement distribution ratios"""
    likes_percent: float = 0.50
    comments_percent: float = 0.35
    dms_percent: float = 0.15

class DistributedLock:
    """Firebase-based distributed lock to prevent concurrent executions"""
    
    def __init__(self, db, lock_name: str, timeout_seconds: int = 300):
        self.db = db
        self.lock_name = lock_name
        self.timeout_seconds = timeout_seconds
        self.lock_doc_ref = self.db.collection('system_locks').document(lock_name)
        self.lock_acquired = False
        self.lock_id = None
    
    def acquire(self) -> bool:
        """Attempt to acquire the distributed lock"""
        try:
            # Generate unique lock ID for this instance
            self.lock_id = f"{datetime.now(timezone.utc).isoformat()}_{random.randint(1000, 9999)}"
            
            # Check if lock already exists and is still valid
            lock_doc = self.lock_doc_ref.get()
            
            if lock_doc.exists:
                lock_data = lock_doc.to_dict()
                lock_timestamp = lock_data.get('timestamp')
                
                # Check if lock has expired
                if lock_timestamp:
                    if isinstance(lock_timestamp, datetime):
                        lock_age = (datetime.now(timezone.utc) - lock_timestamp).total_seconds()
                    else:
                        # Handle Firestore server timestamp
                        lock_age = self.timeout_seconds + 1  # Assume expired if can't calculate
                    
                    if lock_age < self.timeout_seconds:
                        # Lock is still valid
                        logger.info(f"Lock '{self.lock_name}' is already held by another process")
                        return False
            
            # Try to acquire the lock atomically
            lock_data = {
                'lock_id': self.lock_id,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'holder': 'ai_scheduler',
                'timeout_seconds': self.timeout_seconds
            }
            
            # Use Firestore transaction to ensure atomicity
            transaction = self.db.transaction()
            
            @firestore.transactional
            def acquire_lock_transaction(transaction):
                # Check again inside transaction
                current_lock = transaction.get(self.lock_doc_ref)
                
                if current_lock.exists:
                    current_data = current_lock.to_dict()
                    current_timestamp = current_data.get('timestamp')
                    
                    if current_timestamp:
                        # For server timestamps, we'll be conservative and not acquire
                        if isinstance(current_timestamp, datetime):
                            lock_age = (datetime.now(timezone.utc) - current_timestamp).total_seconds()
                            if lock_age < self.timeout_seconds:
                                return False
                
                # Acquire the lock
                transaction.set(self.lock_doc_ref, lock_data)
                return True
            
            if acquire_lock_transaction(transaction):
                self.lock_acquired = True
                logger.info(f"Successfully acquired lock '{self.lock_name}' with ID {self.lock_id}")
                return True
            else:
                logger.info(f"Failed to acquire lock '{self.lock_name}' - already held")
                return False
                
        except Exception as e:
            logger.error(f"Error acquiring lock '{self.lock_name}': {e}")
            return False
    
    def release(self):
        """Release the distributed lock"""
        if not self.lock_acquired or not self.lock_id:
            return
        
        try:
            # Only release if we own the lock
            lock_doc = self.lock_doc_ref.get()
            
            if lock_doc.exists:
                lock_data = lock_doc.to_dict()
                if lock_data.get('lock_id') == self.lock_id:
                    self.lock_doc_ref.delete()
                    logger.info(f"Released lock '{self.lock_name}' with ID {self.lock_id}")
                else:
                    logger.warning(f"Cannot release lock '{self.lock_name}' - not owned by this instance")
            
            self.lock_acquired = False
            self.lock_id = None
            
        except Exception as e:
            logger.error(f"Error releasing lock '{self.lock_name}': {e}")
    
    def __enter__(self):
        """Context manager entry"""
        if self.acquire():
            return self
        else:
            raise RuntimeError(f"Could not acquire lock '{self.lock_name}'")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()

class AIScheduler:
    def __init__(self, db):
        self.db = db
        self.limits = EngagementLimits()
        self.cooldowns = CooldownRules()
        self.ratios = EngagementRatios()
        
    def get_time_window(self) -> TimeWindow:
        """Determine current time window"""
        current_hour = datetime.now(timezone.utc).hour
        if 6 <= current_hour < 12:
            return TimeWindow.MORNING
        elif 12 <= current_hour < 18:
            return TimeWindow.AFTERNOON
        else:
            return TimeWindow.EVENING
    
    def get_user_engagement_score(self, user_id: str) -> float:
        """Calculate user engagement score based on recent activity"""
        try:
            # Check posts in last 7 days
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            posts_ref = self.db.collection('humanPosts').where('user_id', '==', user_id)
            
            recent_posts = 0
            recent_comments = 0
            
            for post_doc in posts_ref.stream():
                post_data = post_doc.to_dict()
                post_time = post_data.get('timestamp')
                if post_time and post_time > week_ago:
                    recent_posts += 1
                    
                    # Count comments on this post
                    comments_ref = self.db.collection('humanPosts').document(post_doc.id).collection('comments')
                    recent_comments += len(list(comments_ref.stream()))
            
            # Score based on activity (0-1 scale)
            activity_score = min(1.0, (recent_posts * 0.3 + recent_comments * 0.1))
            return activity_score
            
        except Exception as e:
            logger.error(f"Error calculating engagement score for {user_id}: {e}")
            return 0.5  # Default medium engagement
    
    def check_interaction_cooldown(self, ai_id: str, target_user_id: str, interaction_type: EngagementType) -> bool:
        """Check if interaction is allowed based on cooldown rules"""
        try:
            now = datetime.now(timezone.utc)
            
            # Get recent interactions for this AI with this user
            interactions_ref = self.db.collection('aiInteractions')\
                                     .where('ai_id', '==', ai_id)\
                                     .where('target_user_id', '==', target_user_id)
            
            # Check for recent interactions
            for interaction_doc in interactions_ref.stream():
                interaction_data = interaction_doc.to_dict()
                interaction_timestamp = interaction_data.get('timestamp')
                interaction_type_stored = interaction_data.get('interaction_type')
                
                if not interaction_timestamp:
                    continue
                
                # Handle different timestamp types
                if isinstance(interaction_timestamp, str):
                    try:
                        interaction_timestamp = datetime.fromisoformat(interaction_timestamp.replace('Z', '+00:00'))
                    except:
                        continue
                
                # Make timezone aware if needed
                if hasattr(interaction_timestamp, 'tzinfo') and interaction_timestamp.tzinfo is None:
                    interaction_timestamp = interaction_timestamp.replace(tzinfo=timezone.utc)
                
                # Calculate time since last interaction
                time_diff = now - interaction_timestamp
                hours_since = time_diff.total_seconds() / 3600
                
                # Apply cooldown rules based on interaction type
                if interaction_type == EngagementType.DM:
                    # DM cooldown: 24 hours minimum between DMs from same AI to same user
                    if interaction_type_stored == 'dm' and hours_since < 24:
                        logger.debug(f"DM cooldown active: {ai_id} -> {target_user_id}, last DM {hours_since:.1f} hours ago")
                        return False
                    
                    # Also check if user has received too many DMs from ANY AI recently
                    recent_dm_count = self.count_recent_dms_to_user(target_user_id, hours=4)
                    if recent_dm_count >= 2:  # Max 2 DMs from any AI in 4 hours
                        logger.debug(f"User {target_user_id} has received {recent_dm_count} DMs in last 4 hours - cooling down")
                        return False
                
                elif interaction_type == EngagementType.COMMENT:
                    # Comment cooldown: 12 hours minimum between comments from same AI to same user's posts
                    if interaction_type_stored == 'comment' and hours_since < 12:
                        logger.debug(f"Comment cooldown active: {ai_id} -> {target_user_id}, last comment {hours_since:.1f} hours ago")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking cooldown for {ai_id} -> {target_user_id}: {e}")
            return True  # Default to allowing interaction if check fails
    
    def count_recent_dms_to_user(self, user_id: str, hours: int = 4) -> int:
        """Count how many DMs a user has received from ANY AI in the last X hours"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Get all recent DM interactions targeting this user
            interactions_ref = self.db.collection('aiInteractions')\
                                     .where('target_user_id', '==', user_id)\
                                     .where('interaction_type', '==', 'dm')
            
            recent_count = 0
            for interaction_doc in interactions_ref.stream():
                interaction_data = interaction_doc.to_dict()
                interaction_timestamp = interaction_data.get('timestamp')
                
                if not interaction_timestamp:
                    continue
                
                # Handle different timestamp types
                if isinstance(interaction_timestamp, str):
                    try:
                        interaction_timestamp = datetime.fromisoformat(interaction_timestamp.replace('Z', '+00:00'))
                    except:
                        continue
                
                # Make timezone aware if needed
                if hasattr(interaction_timestamp, 'tzinfo') and interaction_timestamp.tzinfo is None:
                    interaction_timestamp = interaction_timestamp.replace(tzinfo=timezone.utc)
                
                if interaction_timestamp >= cutoff_time:
                    recent_count += 1
            
            return recent_count
            
        except Exception as e:
            logger.error(f"Error counting recent DMs for user {user_id}: {e}")
            return 0
    
    def analyze_dm_distribution(self, hours: int = 24) -> Dict:
        """Analyze recent DM distribution to help debug clustering issues"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Get all recent DM interactions
            interactions_ref = self.db.collection('aiInteractions')\
                                     .where('interaction_type', '==', 'dm')
            
            user_dm_counts = {}
            ai_dm_counts = {}
            total_dms = 0
            
            for interaction_doc in interactions_ref.stream():
                interaction_data = interaction_doc.to_dict()
                interaction_timestamp = interaction_data.get('timestamp')
                
                if not interaction_timestamp:
                    continue
                
                # Handle different timestamp types
                if isinstance(interaction_timestamp, str):
                    try:
                        interaction_timestamp = datetime.fromisoformat(interaction_timestamp.replace('Z', '+00:00'))
                    except:
                        continue
                
                # Make timezone aware if needed
                if hasattr(interaction_timestamp, 'tzinfo') and interaction_timestamp.tzinfo is None:
                    interaction_timestamp = interaction_timestamp.replace(tzinfo=timezone.utc)
                
                if interaction_timestamp >= cutoff_time:
                    total_dms += 1
                    
                    # Count per target user
                    target_user_id = interaction_data.get('target_user_id')
                    if target_user_id:
                        user_dm_counts[target_user_id] = user_dm_counts.get(target_user_id, 0) + 1
                    
                    # Count per AI
                    ai_id = interaction_data.get('ai_id')
                    if ai_id:
                        ai_dm_counts[ai_id] = ai_dm_counts.get(ai_id, 0) + 1
            
            # Find users receiving multiple DMs
            heavy_targets = {user_id: count for user_id, count in user_dm_counts.items() if count > 1}
            
            return {
                'total_dms_last_24h': total_dms,
                'unique_users_targeted': len(user_dm_counts),
                'unique_ais_sending': len(ai_dm_counts),
                'users_receiving_multiple_dms': heavy_targets,
                'most_targeted_user': max(user_dm_counts.items(), key=lambda x: x[1]) if user_dm_counts else None,
                'avg_dms_per_user': total_dms / len(user_dm_counts) if user_dm_counts else 0,
                'user_dm_distribution': user_dm_counts,
                'ai_dm_distribution': ai_dm_counts
            }
            
        except Exception as e:
            logger.error(f"Error analyzing DM distribution: {e}")
            return {'error': str(e)}
    
    def get_daily_engagement_counts(self, ai_id: str) -> Dict[str, int]:
        """Get current daily engagement counts for an AI"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Use simple query to get all interactions for this AI
            interactions_ref = self.db.collection('aiInteractions')\
                                     .where('ai_id', '==', ai_id)
            
            counts = {'comments': 0, 'likes': 0, 'dms': 0}
            
            for doc in interactions_ref.stream():
                interaction_data = doc.to_dict()
                interaction_timestamp = interaction_data.get('timestamp')
                
                # Filter locally for today's interactions
                if interaction_timestamp:
                    # Handle both timezone-aware and naive timestamps
                    if hasattr(interaction_timestamp, 'tzinfo') and interaction_timestamp.tzinfo is None:
                        # Make naive timestamp timezone-aware
                        interaction_timestamp = interaction_timestamp.replace(tzinfo=timezone.utc)
                    
                    if interaction_timestamp >= today_start:
                        interaction_type = interaction_data.get('interaction_type', '')
                        if interaction_type in counts:
                            counts[interaction_type] += 1
            
            return counts
            
        except Exception as e:
            logger.error(f"Error getting daily counts for {ai_id}: {e}")
            return {'comments': 0, 'likes': 0, 'dms': 0}
    
    def calculate_engagement_targets(self, ai_id: str, user_engagement_score: float) -> Dict[str, int]:
        """Calculate daily engagement targets - no engagement score dependency"""
        # Base targets
        base_comments = random.randint(self.limits.comments_min, self.limits.comments_max)
        base_likes = random.randint(self.limits.likes_min, self.limits.likes_max)
        base_dms = self.limits.dms_max
        
        # Just use the base targets - no engagement score adjustment
        return {
            'comments': base_comments,
            'likes': base_likes,
            'dms': base_dms  # Always allow DMs
        }
    
    def get_eligible_targets(self, ai_id: str, interaction_type: EngagementType, limit: int = 50) -> List[Dict]:
        """Get eligible targets for interaction - users for DMs, posts for likes/comments"""
        try:
            if interaction_type == EngagementType.DM:
                return self.get_eligible_users_for_dm(ai_id, limit)
            else:
                return self.get_eligible_posts_for_engagement(ai_id, interaction_type, limit)
            
        except Exception as e:
            logger.error(f"Error getting eligible targets for {ai_id}: {e}")
            return []
    
    def get_eligible_users_for_dm(self, ai_id: str, limit: int = 50) -> List[Dict]:
        """Get eligible users for DM interactions with proper distribution"""
        try:
            # Get active human users - get more to ensure variety
            users_ref = self.db.collection('humanUsers').limit(limit * 5)  # Get 5x more for better selection
            all_users = []
            
            # First, collect all potential users
            for user_doc in users_ref.stream():
                user_id = user_doc.id
                user_data = user_doc.to_dict()
                
                # Skip if same as AI character
                if user_id == ai_id:
                    continue
                
                # Basic validation - user has name or username
                if user_data.get('name') or user_data.get('username'):
                    all_users.append({
                        'user_id': user_id,
                        'user_data': user_data,
                        'target_type': 'user'
                    })
            
            # Randomize the user list to ensure variety
            import random
            random.shuffle(all_users)
            
            # Now filter based on cooldowns
            eligible_targets = []
            for user in all_users:
                # Check cooldowns (now actually implemented)
                if not self.check_interaction_cooldown(ai_id, user['user_id'], EngagementType.DM):
                    continue
                
                eligible_targets.append(user)
                
                # Stop when we have enough eligible targets
                if len(eligible_targets) >= limit:
                    break
            
            # Add randomization to final selection
            random.shuffle(eligible_targets)
            
            logger.info(f"Selected {len(eligible_targets)} eligible DM targets for AI {ai_id} from {len(all_users)} total users")
            return eligible_targets[:limit]
            
        except Exception as e:
            logger.error(f"Error getting eligible users for DM: {e}")
            return []
    
    def get_eligible_posts_for_engagement(self, ai_id: str, interaction_type: EngagementType, limit: int = 50) -> List[Dict]:
        """Get eligible posts for like/comment interactions - search more broadly"""
        try:
            eligible_posts = []
            
            # Get more human posts to search through (increase scope)
            human_posts_ref = self.db.collection('humanPosts').limit(limit * 4)  # Search 4x more posts
            for post_doc in human_posts_ref.stream():
                post_id = post_doc.id
                post_data = post_doc.to_dict()
                
                # Skip if already interacted with this post
                if self.has_already_interacted_with_post(ai_id, post_id, interaction_type):
                    continue
                
                eligible_posts.append({
                    'post_id': post_id,
                    'post_data': post_data,
                    'collection': 'humanPosts',
                    'target_type': 'post',
                    'engagement_score': 0.8  # Human posts get high priority
                })
                
                # Stop once we have enough eligible posts
                if len(eligible_posts) >= limit:
                    break
            
            # If we still need more, check AI posts
            if len(eligible_posts) < limit:
                ai_posts_ref = self.db.collection('aiPosts').limit(limit * 2)  # Search more AI posts too
                for post_doc in ai_posts_ref.stream():
                    post_id = post_doc.id
                    post_data = post_doc.to_dict()
                    
                    # Skip if already interacted with this post
                    if self.has_already_interacted_with_post(ai_id, post_id, interaction_type):
                        continue
                    
                    # Skip own posts
                    post_author_id = post_data.get('user_name', '')
                    if post_author_id == ai_id:
                        continue
                    
                    eligible_posts.append({
                        'post_id': post_id,
                        'post_data': post_data,
                        'collection': 'aiPosts',
                        'target_type': 'post',
                        'engagement_score': 0.6  # AI posts get medium priority
                    })
                    
                    # Stop once we have enough
                    if len(eligible_posts) >= limit:
                        break
            
            # Sort by engagement score and randomize a bit
            import random
            eligible_posts.sort(key=lambda x: x['engagement_score'] + random.uniform(-0.1, 0.1), reverse=True)
            
            return eligible_posts[:limit]
            
        except Exception as e:
            logger.error(f"Error getting eligible posts: {e}")
            return []
    
    def has_already_interacted_with_post(self, ai_id: str, post_id: str, interaction_type: EngagementType) -> bool:
        """Check if AI has already interacted with this post (prevent duplicate likes, allow re-commenting after time)"""
        try:
            if interaction_type == EngagementType.LIKE:
                # For likes: NEVER allow duplicate likes on the same post
                existing_like_query = self.db.collection('postLikes')\
                    .where('user_id', '==', ai_id)\
                    .where('post_id', '==', post_id)\
                    .limit(1)
                    
                existing_like_docs = list(existing_like_query.stream())
                return len(existing_like_docs) > 0  # Return True if already liked (block duplicate)
            
            elif interaction_type == EngagementType.COMMENT:
                # For comments: Allow re-commenting after 3 days
                from datetime import timedelta
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
                
                comments_query = self.db.collection('postComments').where('postId', '==', post_id).limit(1)
                for comment_doc in comments_query.stream():
                    comments_data = comment_doc.to_dict()
                    comments = comments_data.get('comments', [])
                    for comment in comments:
                        if comment.get('userId') == ai_id:
                            comment_timestamp = comment.get('timestamp', '')
                            # Block if commented recently (within 3 days)
                            if isinstance(comment_timestamp, str) and comment_timestamp > cutoff_date:
                                return True
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking post interaction: {e}")
            return False
    
    def log_interaction(self, ai_id: str, target_user_id: str, interaction_type: EngagementType, 
                       details: Dict = None) -> None:
        """Log AI interaction for tracking and cooldown management"""
        try:
            interaction_data = {
                'ai_id': ai_id,
                'target_user_id': target_user_id,  # Standardized field name
                'interaction_type': interaction_type.value,
                'timestamp': firestore.SERVER_TIMESTAMP,  # Use server timestamp for consistency
                'details': details or {},
                'user_replied': False  # Will be updated when user responds
            }
            
            self.db.collection('aiInteractions').add(interaction_data)
            logger.info(f"Logged {interaction_type.value} interaction: {ai_id} -> {target_user_id}")
            
        except Exception as e:
            logger.error(f"Error logging interaction: {e}")
    
    def schedule_character_engagement(self, character_id: str) -> Dict:
        """Schedule engagement for a specific popular character"""
        try:
            # Get character data
            char_ref = self.db.collection('popularCharacters').document(character_id)
            char_doc = char_ref.get()
            
            if not char_doc.exists:
                return {'success': False, 'error': 'Character not found'}
            
            char_data = char_doc.to_dict()
            char_name = char_data.get('name', 'Unknown Character')
            
            # Get current daily counts
            daily_counts = self.get_daily_engagement_counts(character_id)
            
            # Calculate average user engagement for this character's targets
            avg_engagement = 0.6  # Default moderate engagement
            
            # Calculate remaining targets for today
            targets = self.calculate_engagement_targets(character_id, avg_engagement)
            
            remaining_targets = {
                'comments': max(0, targets['comments'] - daily_counts['comments']),
                'likes': max(0, targets['likes'] - daily_counts['likes']),
                'dms': max(0, targets['dms'] - daily_counts['dms'])
            }
            
            scheduled_interactions = []
            
            # Schedule remaining interactions
            for interaction_type_str, remaining in remaining_targets.items():
                if remaining <= 0:
                    continue
                
                # Convert string to EngagementType enum
                if interaction_type_str == 'comments':
                    interaction_type = EngagementType.COMMENT
                elif interaction_type_str == 'likes':
                    interaction_type = EngagementType.LIKE
                elif interaction_type_str == 'dms':
                    interaction_type = EngagementType.DM
                else:
                    continue  # Skip unknown types
                
                eligible_targets = self.get_eligible_targets(character_id, interaction_type, remaining * 2)
                
                # Select targets (ensure variety)
                selected_targets = eligible_targets[:remaining]
                
                for target in selected_targets:
                    if target.get('target_type') == 'post':
                        # For posts (likes/comments)
                        scheduled_interactions.append({
                            'character_id': character_id,
                            'character_name': char_name,
                            'target_post_id': target['post_id'],
                            'post_collection': target['collection'],
                            'interaction_type': interaction_type.value,
                            'engagement_score': target.get('engagement_score', 0.5),
                            'time_window': self.get_time_window().value
                        })
                    else:
                        # For users (DMs)
                        target_user_name = target['user_data'].get('name', target['user_data'].get('username', 'Unknown'))
                        scheduled_interactions.append({
                            'character_id': character_id,
                            'character_name': char_name,
                            'target_user_id': target['user_id'],
                            'target_user_name': target_user_name,  # Add user name for logging
                            'interaction_type': interaction_type.value,
                            'engagement_score': target.get('engagement_score', 1.0),
                            'time_window': self.get_time_window().value
                        })
                        
                        # Log the DM target selection for debugging
                        logger.info(f"Scheduled DM: {char_name} -> {target_user_name} ({target['user_id']})")
            
            return {
                'success': True,
                'character_id': character_id,
                'character_name': char_name,
                'daily_counts': daily_counts,
                'targets': targets,
                'remaining_targets': remaining_targets,
                'scheduled_interactions': scheduled_interactions,
                'total_scheduled': len(scheduled_interactions)
            }
            
        except Exception as e:
            logger.error(f"Error scheduling character engagement for {character_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def schedule_all_characters(self, limit: int = 50) -> Dict:
        """Schedule engagement for all popular characters"""
        try:
            # Get all popular characters
            chars_ref = self.db.collection('popularCharacters').limit(limit)
            results = []
            total_scheduled = 0
            
            for char_doc in chars_ref.stream():
                character_result = self.schedule_character_engagement(char_doc.id)
                if character_result['success']:
                    results.append(character_result)
                    total_scheduled += character_result.get('total_scheduled', 0)
            
            return {
                'success': True,
                'total_characters': len(results),
                'total_interactions_scheduled': total_scheduled,
                'characters': results,
                'timestamp': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"Error scheduling all characters: {e}")
            return {'success': False, 'error': str(e)}
    
    def execute_scheduled_engagement_safely(self, limit: int = 20) -> Dict:
        """Safely execute engagement with simple time-based rate limiting"""
        try:
            # Simple time-based rate limiting instead of complex distributed lock
            last_run_doc = self.db.collection('schedulerState').document('lastRun').get()
            
            if last_run_doc.exists:
                last_run_data = last_run_doc.to_dict()
                last_run_time = last_run_data.get('timestamp')
                
                if last_run_time:
                    # Handle different timestamp formats
                    if isinstance(last_run_time, str):
                        try:
                            last_run_time = datetime.fromisoformat(last_run_time.replace('Z', '+00:00'))
                        except:
                            pass  # If parsing fails, proceed with execution
                    
                    # Handle timezone-aware timestamps
                    if hasattr(last_run_time, 'tzinfo') and last_run_time.tzinfo is not None:
                        last_run_time = last_run_time.replace(tzinfo=None)
                    
                    if isinstance(last_run_time, datetime):
                        time_since_last_run = (datetime.now() - last_run_time).total_seconds()
                        
                        # Prevent runs closer than 30 minutes apart (1800 seconds)
                        MIN_INTERVAL_SECONDS = 1800  # 30 minutes
                        
                        if time_since_last_run < MIN_INTERVAL_SECONDS:
                            return {
                                'success': False,
                                'error': 'Recent execution detected',
                                'message': f'Last run was {int(time_since_last_run)} seconds ago. Minimum interval is {MIN_INTERVAL_SECONDS} seconds.',
                                'next_allowed_in_seconds': int(MIN_INTERVAL_SECONDS - time_since_last_run),
                                'last_run_time': str(last_run_time),
                                'time_since_last_run': int(time_since_last_run)
                            }
            
            # Execute the actual engagement
            execution_result = self.execute_all_scheduled_interactions(limit)
            
            # Update last run time on successful execution
            if execution_result.get('success'):
                self.db.collection('schedulerState').document('lastRun').set({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'type': 'scheduled_engagement',
                    'execution_id': f"exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                })
            
            return execution_result
            
        except Exception as e:
            logger.error(f"Error in safe engagement execution: {e}")
            return {
                'success': False,
                'error': 'Execution failed', 
                'message': str(e)
            }
        
        try:
            with lock:
                logger.info("Acquired distributed lock for AI engagement execution")
                
                # Check if we've already run recently (additional safety check)
                last_run_ref = self.db.collection('system_state').document('last_ai_engagement_run')
                last_run_doc = last_run_ref.get()
                
                if last_run_doc.exists:
                    last_run_data = last_run_doc.to_dict()
                    last_run_time = last_run_data.get('timestamp')
                    
                    if last_run_time:
                        if isinstance(last_run_time, datetime):
                            time_since_last_run = (datetime.now(timezone.utc) - last_run_time).total_seconds()
                        else:
                            time_since_last_run = 0  # If can't determine, allow execution
                        
                        # CUSTOMIZABLE SCHEDULING FREQUENCY: 
                        # Change this value to control how often AI engagement runs:
                        # - 1800 = 30 minutes (previous setting - too infrequent!)
                        # - 3600 = 1 hour 
                        # - 21600 = 6 hours (new setting for more frequent daily engagement)
                        # - 86400 = 24 hours (once per day)
                        MIN_INTERVAL_SECONDS = 1800  # 30 minutes - original setting restored
                        
                        # Prevent runs closer than the minimum interval
                        if time_since_last_run < MIN_INTERVAL_SECONDS:
                            return {
                                'success': False,
                                'error': 'Recent execution detected',
                                'message': f'Last run was {int(time_since_last_run)} seconds ago. Minimum interval is {MIN_INTERVAL_SECONDS} seconds ({MIN_INTERVAL_SECONDS/3600:.1f} hours).',
                                'last_run_time': last_run_time,
                                'next_allowed_time': last_run_time + timedelta(seconds=MIN_INTERVAL_SECONDS) if isinstance(last_run_time, datetime) else None
                            }
                
                # Execute the engagement
                result = self.execute_all_scheduled_interactions(limit)
                
                # Update last run timestamp
                last_run_ref.set({
                    'timestamp': datetime.now(timezone.utc),
                    'execution_result': result,
                    'lock_id': lock.lock_id
                }, merge=True)
                
                logger.info("AI engagement execution completed successfully")
                return result
                
        except RuntimeError as e:
            # Lock acquisition failed
            return {
                'success': False,
                'error': 'Execution already in progress',
                'message': str(e),
                'suggestion': 'Another instance is currently running AI engagement. Please wait a few minutes and try again.'
            }
        except Exception as e:
            logger.error(f"Error in safe engagement execution: {e}")
            return {
                'success': False,
                'error': 'Execution failed',
                'message': str(e)
            }
    
    def execute_all_scheduled_interactions(self, limit: int = 20) -> Dict:
        """Execute all scheduled interactions and return detailed results"""
        try:
            # Schedule interactions for all characters
            schedule_result = self.schedule_all_characters(limit)
            
            if not schedule_result['success']:
                return schedule_result
            
            total_executed = 0
            total_errors = 0
            execution_details = []
            
            # Execute each scheduled interaction
            for character_result in schedule_result['characters']:
                character_id = character_result['character_id']
                character_name = character_result['character_name']
                
                for interaction in character_result['scheduled_interactions']:
                    try:
                        success = False
                        interaction_type = interaction['interaction_type']
                        
                        if interaction_type == 'like':
                            success = self.execute_like_interaction(
                                character_id,
                                interaction['target_post_id'],
                                interaction.get('post_collection', 'humanPosts')
                            )
                        elif interaction_type == 'comment':
                            success = self.execute_comment_interaction(
                                character_id,
                                interaction['target_post_id'],
                                interaction.get('post_collection', 'humanPosts')
                            )
                        elif interaction_type == 'dm':
                            success = self.execute_dm_interaction(
                                character_id,
                                interaction['target_user_id']
                            )
                        
                        if success:
                            total_executed += 1
                        else:
                            total_errors += 1
                        
                        execution_details.append({
                            'character_id': character_id,
                            'character_name': character_name,
                            'interaction_type': interaction_type,
                            'success': success,
                            'target_id': interaction.get('target_post_id') or interaction.get('target_user_id')
                        })
                        
                        # Small delay between interactions to be respectful
                        time.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"Error executing interaction for {character_id}: {e}")
                        total_errors += 1
                        execution_details.append({
                            'character_id': character_id,
                            'character_name': character_name,
                            'interaction_type': interaction.get('interaction_type', 'unknown'),
                            'success': False,
                            'error': str(e),
                            'target_id': interaction.get('target_post_id') or interaction.get('target_user_id')
                        })
            
            return {
                'success': True,
                'total_characters': schedule_result['total_characters'],
                'total_scheduled': schedule_result['total_interactions_scheduled'],
                'total_executed': total_executed,
                'total_errors': total_errors,
                'execution_rate': f"{total_executed}/{schedule_result['total_interactions_scheduled']}",
                'execution_details': execution_details,
                'timestamp': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"Error executing all scheduled interactions: {e}")
            return {'success': False, 'error': str(e)}

    def execute_like_interaction(self, character_id: str, post_id: str, collection: str = 'humanPosts') -> bool:
        """Execute a like interaction using proper database structure"""
        try:
            # Check if already liked
            existing_like_query = self.db.collection('postLikes')\
                                        .where('user_id', '==', character_id)\
                                        .where('post_id', '==', post_id)\
                                        .limit(1)
            
            existing_like_docs = list(existing_like_query.stream())
            if existing_like_docs:
                logger.info(f"Character {character_id} already liked post {post_id}")
                return False
            
            # Get post data to find the post author for notification
            post_ref = self.db.collection(collection).document(post_id)
            post_doc = post_ref.get()
            
            if not post_doc.exists:
                logger.error(f"Post {post_id} not found")
                return False
            
            post_data = post_doc.to_dict()
            post_author_id = post_data.get('user_document_id') or post_data.get('user_id')
            
            if not post_author_id:
                logger.error(f"Could not find post author for post {post_id}")
                return False
            
            # Get character data for notification
            char_ref = self.db.collection('popularCharacters').document(character_id)
            char_doc = char_ref.get()
            
            char_name = character_id  # fallback
            if char_doc.exists:
                char_data = char_doc.to_dict()
                char_name = char_data.get('name', character_id)
            
            # Add like with proper timestamp format
            like_data = {
                "user_id": character_id,
                "post_id": post_id,
                "timestamp": firestore.SERVER_TIMESTAMP,  # Firestore timestamp
                "isAIGenerated": True
            }
            
            self.db.collection('postLikes').add(like_data)
            
            # Increment likes count on the post
            post_ref.update({"likes": firestore.Increment(1)})
            
            # Create notification for the post author
            try:
                # Send post engagement notification using the existing API endpoint
                import requests
                
                notification_data = {
                    'postId': post_id,
                    'type': 'like',
                    'userId': character_id,
                    'postAuthorId': post_author_id,
                    'timestamp': datetime.now().isoformat(),
                    'aiGenerated': True,
                    'aiCharacterName': char_name
                }
                
                # Use the existing post engagement notification endpoint
                requests.post(
                    'https://inzoneapi-912424781531.us-central1.run.app/api/notifications/events/post-engagement',
                    json=notification_data,
                    timeout=5  # Short timeout to avoid blocking
                )
                
                logger.info(f"Sent like notification for {post_author_id} from AI {char_name}")
                
            except Exception as e:
                logger.error(f"Error sending like notification: {e}")
                
                # Fallback: create notification directly in database
                try:
                    notification_data = {
                        'title': f"{char_name} liked your post",
                        'body': "Your post got a new like!",
                        'type': 'post_like',
                        'userId': post_author_id,
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'postId': post_id,
                            'engagementType': 'like',
                            'aiCharacterId': character_id,
                            'aiCharacterName': char_name
                        }
                    }
                    
                    self.db.collection('notifications').add(notification_data)
                    logger.info(f"Created fallback like notification for {post_author_id} from {char_name}")
                    
                except Exception as fallback_error:
                    logger.error(f"Error creating fallback like notification: {fallback_error}")
            
            # Log the interaction
            self.log_interaction(character_id, post_id, EngagementType.LIKE, {
                'post_id': post_id,
                'collection': collection,
                'post_author_id': post_author_id
            })
            
            logger.info(f"Character {char_name} liked post {post_id} by {post_author_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error executing like interaction: {e}")
            return False
    
    def execute_comment_interaction(self, character_id: str, post_id: str, collection: str = 'humanPosts') -> bool:
        """Execute a comment interaction using the proper InZoneAIEngagementService"""
        try:
            # Import the proper AI service
            from inzone_ai_engagement import InZoneAIEngagementService
            from openai import OpenAI
            import os
            
            # Initialize the proper AI service
            openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            ai_service = InZoneAIEngagementService(self.db, openai_client)
            
            # Get character data
            char_ref = self.db.collection('popularCharacters').document(character_id)
            char_doc = char_ref.get()
            
            if not char_doc.exists:
                logger.error(f"Character {character_id} not found")
                return False
            
            char_data = char_doc.to_dict()
            
            # Add flag to indicate this is a popular character
            char_data['_is_popular_character'] = True
            char_data['_collection_source'] = 'popularCharacters'
            
            # Get post data
            post_ref = self.db.collection(collection).document(post_id)
            post_doc = post_ref.get()
            
            if not post_doc.exists:
                logger.error(f"Post {post_id} not found")
                return False
            
            post_data = post_doc.to_dict()
            
            # Get trending insights for better context
            trends = ai_service.get_trending_content_insights()
            
            # Generate contextual AI comment using the proper service
            comment_text = ai_service.generate_contextual_ai_comment(char_data, post_data, trends)
            
            # Use the correct postComments structure
            post_comments_ref = self.db.collection('postComments').document(post_id)
            post_comments_doc = post_comments_ref.get()
            
            # Initialize currentComments
            current_comments = []
            
            if post_comments_doc.exists:
                current_comments = post_comments_doc.to_dict().get('comments', [])
            else:
                post_comments_ref.set({'comments': current_comments})
            
            # Create new comment with proper timestamp format
            current_time = datetime.now(timezone.utc)
            new_comment = {
                'author': char_data.get('name', character_id),
                'text': comment_text,
                'userId': character_id,
                'timestamp': current_time,  # Use current UTC time instead of SERVER_TIMESTAMP
                'likedBy': [],
                'isAIGenerated': True
            }
            
            # Add the new comment
            current_comments.append(new_comment)
            post_comments_ref.update({'comments': current_comments})
            
            # Log the interaction
            self.log_interaction(character_id, post_data.get('user_id', 'unknown'), EngagementType.COMMENT, {
                'post_id': post_id,
                'comment': comment_text,
                'collection': collection
            })
            
            # Create notification for the post author
            try:
                post_author_id = post_data.get('user_document_id') or post_data.get('user_id')
                
                if post_author_id and post_author_id != character_id:
                    # Send post engagement notification using the existing API endpoint
                    import requests
                    
                    notification_data = {
                        'postId': post_id,
                        'type': 'comment',
                        'userId': character_id,
                        'postAuthorId': post_author_id,
                        'timestamp': datetime.now().isoformat(),
                        'content': comment_text,
                        'aiGenerated': True,
                        'aiCharacterName': char_data.get('name', character_id)
                    }
                    
                    # Use the existing post engagement notification endpoint
                    requests.post(
                        'https://inzoneapi-912424781531.us-central1.run.app/api/notifications/events/post-engagement',
                        json=notification_data,
                        timeout=5  # Short timeout to avoid blocking
                    )
                    
                    logger.info(f"Sent comment notification for {post_author_id} from AI {char_data.get('name', character_id)}")
                    
            except Exception as e:
                logger.error(f"Error sending comment notification: {e}")
                
                # Fallback: create notification directly in database
                try:
                    post_author_id = post_data.get('user_document_id') or post_data.get('user_id')
                    if post_author_id and post_author_id != character_id:
                        notification_data = {
                            'title': f"{char_data.get('name', character_id)} commented on your post",
                            'body': comment_text,
                            'type': 'post_comment',
                            'userId': post_author_id,
                            'isRead': False,
                            'createdAt': firestore.SERVER_TIMESTAMP,
                            'data': {
                                'postId': post_id,
                                'engagementType': 'comment',
                                'aiCharacterId': character_id,
                                'aiCharacterName': char_data.get('name', character_id),
                                'commentText': comment_text
                            }
                        }
                        
                        self.db.collection('notifications').add(notification_data)
                        logger.info(f"Created fallback comment notification for {post_author_id} from {char_data.get('name', character_id)}")
                        
                except Exception as fallback_error:
                    logger.error(f"Error creating fallback comment notification: {fallback_error}")
            
            logger.info(f"Character {char_data.get('name', character_id)} commented on post {post_id}: {comment_text}")
            return True
            
        except Exception as e:
            logger.error(f"Error executing comment interaction: {e}")
            return False
            
            logger.info(f"Character {character_id} commented on post {post_id}: {comment_text}")
            return True
            
        except Exception as e:
            logger.error(f"Error executing comment interaction: {e}")
            return False
    
    def execute_dm_interaction(self, character_id: str, target_user_id: str) -> bool:
        """Execute a DM interaction using the proper InZoneAIEngagementService"""
        try:
            # Import the proper AI service
            from inzone_ai_engagement import InZoneAIEngagementService
            from openai import OpenAI
            import os
            
            # Initialize the proper AI service
            openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            ai_service = InZoneAIEngagementService(self.db, openai_client)
            
            # Get character data
            char_ref = self.db.collection('popularCharacters').document(character_id)
            char_doc = char_ref.get()
            
            if not char_doc.exists:
                logger.error(f"Character {character_id} not found")
                return False
            
            char_data = char_doc.to_dict()
            
            # Add flag to indicate this is a popular character
            char_data['_is_popular_character'] = True
            char_data['_collection_source'] = 'popularCharacters'
            
            # Get target user data
            target_user_ref = self.db.collection('humanUsers').document(target_user_id)
            target_user_doc = target_user_ref.get()
            
            if not target_user_doc.exists:
                logger.error(f"Target user {target_user_id} not found")
                return False
            
            target_user_data = target_user_doc.to_dict()
            
            # Generate DM message using the proper AI service
            dm_content = ai_service.generate_ai_dm_message(char_data, target_user_data)
            
            # Create conversation ID (sorted to ensure consistency)
            participants = sorted([character_id, target_user_id])
            conversation_id = f"{participants[0]}_{participants[1]}"
            
            # Create conversation
            conversation_ref = self.db.collection('conversations').document(conversation_id)
            
            # Add message with proper timestamp format
            new_message = {
                'text': dm_content,
                'senderId': character_id,
                'senderName': char_data.get('name', character_id),
                'timestamp': firestore.SERVER_TIMESTAMP,  # Firestore timestamp
                'isRead': False,
                'isAIGenerated': True
            }
            
            conversation_ref.collection('messages').add(new_message)
            
            # Update conversation metadata
            conversation_ref.set({
                'lastMessage': dm_content,
                'lastMessageTime': firestore.SERVER_TIMESTAMP,  # Firestore timestamp
                'participants': [character_id, target_user_id],
                'participantNames': {
                    character_id: char_data.get('name', character_id),
                    target_user_id: target_user_data.get('name', target_user_id)
                },
                'lastUpdated': firestore.SERVER_TIMESTAMP,
            }, merge=True)
            
            # Log the interaction
            self.log_interaction(character_id, target_user_id, EngagementType.DM, {
                'conversation_id': conversation_id,
                'message': dm_content
            })
            
            # Create notification for the DM recipient
            try:
                # Use the existing direct message notification handling from the app
                # Since we don't have a specific API endpoint for DM notifications, create directly
                notification_data = {
                    'title': char_data.get('name', character_id),
                    'body': dm_content,
                    'type': 'direct_message',
                    'userId': target_user_id,
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'chatId': conversation_id,
                        'messageContent': dm_content,
                        'senderId': character_id,
                        'senderName': char_data.get('name', character_id),
                        'aiGenerated': True
                    }
                }
                
                self.db.collection('notifications').add(notification_data)
                logger.info(f"Created DM notification for {target_user_id} from AI {char_data.get('name', character_id)}")
                
            except Exception as e:
                logger.error(f"Error creating DM notification: {e}")
            
            logger.info(f"Character {char_data.get('name', character_id)} sent DM to {target_user_id}: {dm_content}")
            return True
            
        except Exception as e:
            logger.error(f"Error executing DM interaction: {e}")
            return False
    
    def log_interaction(self, ai_id: str, target_id: str, interaction_type: EngagementType, metadata: Dict = None):
        """Log an AI interaction"""
        try:
            interaction_data = {
                'ai_id': ai_id,
                'target_id': target_id,
                'interaction_type': interaction_type.value,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'metadata': metadata or {}
            }
            
            self.db.collection('aiInteractions').add(interaction_data)
            
        except Exception as e:
            logger.error(f"Error logging interaction: {e}")
    
    def monitor_and_respond_to_dms(self) -> Dict:
        """Monitor conversations for new messages and respond immediately (24/7 functionality)"""
        try:
            logger.info("Monitoring conversations for AI responses...")
            
            # Get all AI characters from both collections
            ai_chars_ref = self.db.collection('popularCharacters')
            ai_characters = {doc.id: doc.to_dict() for doc in ai_chars_ref.stream()}
            
            # Also include aiUsers collection
            ai_users_ref = self.db.collection('aiUsers')
            ai_users = {doc.id: doc.to_dict() for doc in ai_users_ref.stream()}
            ai_characters.update(ai_users)
            
            if not ai_characters:
                return {'success': True, 'message': 'No AI characters found', 'responses_sent': 0}
            
            responses_sent = 0
            response_details = []
            
            # Check all conversations for pending responses
            conversations_ref = self.db.collection('conversations')
            
            for conv_doc in conversations_ref.stream():
                conv_data = conv_doc.to_dict()
                conversation_id = conv_doc.id
                
                # Check if this conversation involves an AI character
                participants = conv_data.get('participants', [])
                ai_participant = None
                human_participant = None
                
                for participant in participants:
                    if participant in ai_characters:
                        ai_participant = participant
                    else:
                        human_participant = participant
                
                # Skip if no AI character in conversation
                if not ai_participant or not human_participant:
                    continue
                
                # Check if the last message was from the human and needs a response
                last_message_time = conv_data.get('lastMessageTime')
                last_message = conv_data.get('lastMessage', '')
                
                if not last_message_time or not last_message:
                    continue
                
                # Get the actual last message from the messages subcollection to verify sender
                messages_ref = conv_doc.reference.collection('messages')
                recent_messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
                
                messages_list = []
                for msg_doc in recent_messages:
                    msg_data = msg_doc.to_dict()
                    messages_list.append(msg_data)
                
                if not messages_list:
                    continue
                
                # Check if the last message was from human and AI hasn't responded
                last_actual_message = messages_list[0]
                last_sender = last_actual_message.get('senderId')
                
                # Skip if last message was from AI
                if last_sender == ai_participant:
                    continue
                
                # Check if AI has already responded recently (check if AI sent the last message)
                # If the last message is from AI, skip this conversation
                # The above check already handles this, so no additional logic needed here
                
                # Generate and send AI response
                try:
                    response_sent = self.send_immediate_dm_response(
                        ai_participant, 
                        human_participant, 
                        conversation_id, 
                        messages_list,
                        ai_characters[ai_participant]
                    )
                    
                    if response_sent:
                        responses_sent += 1
                        response_details.append({
                            'conversation_id': conversation_id,
                            'ai_character': ai_participant,
                            'human_user': human_participant,
                            'response_time': datetime.now(timezone.utc).isoformat()
                        })
                        
                        # Small delay to avoid overwhelming the system
                        time.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Error sending DM response for conversation {conversation_id}: {e}")
                    continue
            
            return {
                'success': True,
                'responses_sent': responses_sent,
                'response_details': response_details,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'characters_checked': len(ai_characters)
            }
            
        except Exception as e:
            logger.error(f"Error monitoring DM conversations: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_immediate_dm_response(self, ai_id: str, human_id: str, conversation_id: str, 
                                 message_history: List[Dict], ai_character: Dict) -> bool:
        """Send immediate DM response using the proper AI service"""
        try:
            logger.info(f"🚀 Starting immediate DM response: {ai_id} -> {human_id}")
            
            # Import the proper AI service
            from inzone_ai_engagement import InZoneAIEngagementService
            from openai import OpenAI
            import os
            
            # Initialize the proper AI service
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            if not openai_api_key:
                logger.error("❌ OpenAI API key not found in environment")
                return False
            
            openai_client = OpenAI(api_key=openai_api_key)
            ai_service = InZoneAIEngagementService(self.db, openai_client)
            logger.info("✅ AI service initialized")
            
            # Get human user data
            human_user_ref = self.db.collection('humanUsers').document(human_id)
            human_user_doc = human_user_ref.get()
            
            if not human_user_doc.exists:
                logger.error(f"❌ Human user {human_id} not found")
                return False
            
            human_user_data = human_user_doc.to_dict()
            logger.info(f"✅ Human user data loaded: {human_user_data.get('name', 'Unknown')}")
            
            # Build conversation context with proper message analysis
            ai_message_count = 0
            human_message_count = 0
            last_human_message = ""
            last_ai_message = ""
            
            # Analyze message history to count AI vs human messages
            for msg in message_history:
                sender_id = msg.get('senderId', '')
                msg_text = msg.get('text', '')
                
                if sender_id == ai_id:
                    ai_message_count += 1
                    if not last_ai_message:  # Get the most recent AI message
                        last_ai_message = msg_text
                elif sender_id == human_id:
                    human_message_count += 1
                    if not last_human_message:  # Get the most recent human message
                        last_human_message = msg_text
            
            conversation_context = {
                'message_count': len(message_history),
                'ai_message_count': ai_message_count,
                'human_message_count': human_message_count,
                'last_human_message': last_human_message,
                'last_ai_message': last_ai_message,
                'recent_messages': message_history[:5],  # Last 5 messages for context
                'conversation_id': conversation_id,
                'conversation_active': True,
                'is_response': True  # This is a response, not initial DM
            }
            
            logger.info(f"📝 Conversation context built: {len(message_history)} messages, {ai_message_count} from AI, {human_message_count} from human")
            
            # Generate contextual response using the proper AI service
            try:
                response_message = ai_service.generate_ai_dm_message(
                    ai_character, 
                    human_user_data, 
                    conversation_context
                )
                logger.info(f"✅ AI response generated: {response_message[:50]}...")
            except Exception as e:
                logger.error(f"❌ Error generating AI response: {e}")
                logger.error(f"   AI Character: {ai_character.get('name', 'Unknown')}")
                logger.error(f"   Human User: {human_user_data.get('name', 'Unknown')}")
                logger.error(f"   Context: {conversation_context}")
                return False
            
            # Send the response
            conversation_ref = self.db.collection('conversations').document(conversation_id)
            
            # Add message with proper Firestore timestamp
            new_message = {
                'text': response_message,
                'senderId': ai_id,
                'senderName': ai_character.get('name', ai_id),
                'timestamp': firestore.SERVER_TIMESTAMP,
                'isRead': False,
                'isAIGenerated': True,
                'isResponse': True  # Mark as a response to user message
            }
            
            try:
                conversation_ref.collection('messages').add(new_message)
                logger.info("✅ Message added to conversation")
            except Exception as e:
                logger.error(f"❌ Error adding message to conversation: {e}")
                return False
            
            # Update conversation metadata with proper Firestore timestamps
            try:
                conversation_ref.update({
                    'lastMessage': response_message,
                    'lastMessageTime': firestore.SERVER_TIMESTAMP,
                    'lastUpdated': firestore.SERVER_TIMESTAMP,
                })
                logger.info("✅ Conversation metadata updated")
            except Exception as e:
                logger.error(f"❌ Error updating conversation metadata: {e}")
                return False
            
            # Log the interaction
            self.log_interaction(ai_id, human_id, EngagementType.DM, {
                'conversation_id': conversation_id,
                'message': response_message,
                'type': 'response',
                'response_time_seconds': 0  # Immediate response
            })
            
            # Create notification for the human user
            try:
                notification_data = {
                    'title': ai_character.get('name', ai_id),
                    'body': response_message,
                    'type': 'direct_message',
                    'userId': human_id,
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'chatId': conversation_id,
                        'messageContent': response_message,
                        'senderId': ai_id,
                        'senderName': ai_character.get('name', ai_id)
                    }
                }
                
                self.db.collection('notifications').add(notification_data)
                logger.info(f"Created notification for {human_id} about DM from {ai_character.get('name', ai_id)}")
                
                # Send push notification to human user
                try:
                    import requests
                    push_response = requests.post(
                        'https://inzoneapi-912424781531.us-central1.run.app/api/notifications/send-push',
                        json={
                            'userId': human_id,
                            'title': f"{ai_character.get('name', ai_id)} sent you a message",
                            'body': response_message[:100] + '...' if len(response_message) > 100 else response_message,
                            'data': {
                                'type': 'direct_message',
                                'chatId': conversation_id,
                                'senderId': ai_id,
                                'senderName': ai_character.get('name', ai_id),
                                'action': 'navigate_to_chat',
                                'route': f'/chat/{conversation_id}'
                            }
                        },
                        timeout=10
                    )
                    
                    if push_response.status_code == 200:
                        logger.info(f"✅ Push notification sent to {human_id} from AI {ai_character.get('name', ai_id)}")
                    else:
                        logger.warning(f"❌ Push notification failed: {push_response.status_code} - {push_response.text}")
                        
                except Exception as push_e:
                    logger.error(f"Error sending push notification: {push_e}")
                
            except Exception as e:
                logger.error(f"Error creating notification: {e}")
            
            logger.info(f"AI {ai_character.get('name', ai_id)} responded to {human_id} in conversation {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending immediate DM response: {e}")
            return False

# Initialize Firebase if not already done
try:
    if not firebase_admin._apps:
        # Firebase will be initialized by the main app
        pass
except Exception as e:
    logger.warning(f"Firebase initialization: {e}")