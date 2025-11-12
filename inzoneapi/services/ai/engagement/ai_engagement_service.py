# """
# AI Character Engagement Service for InZone

# This service manages organic AI character interactions with users through:
# - Public comments on posts
# - Private DMs (1:1 only)
# - Likes and supportive behavior
# - Natural, non-spammy engagement patterns

# Max 5 interactions per AI character per day
# No DMs after first unanswered DM
# """

# import random
# import logging
# from datetime import datetime, timedelta
# from typing import List, Dict, Optional, Tuple
# from dataclasses import dataclass
# from firebase_admin import firestore
# from openai import OpenAI
# import os

# logger = logging.getLogger(__name__)

# @dataclass
# class AIEngagementConfig:
#     max_daily_interactions: int = 5
#     min_interaction_interval_hours: int = 2
#     max_interaction_interval_hours: int = 8
#     comment_probability: float = 0.4
#     like_probability: float = 0.6
#     dm_probability: float = 0.3
#     dm_cooldown_hours: int = 24

# @dataclass
# class InteractionLog:
#     ai_user_id: str
#     target_user_id: str
#     interaction_type: str  # 'comment', 'like', 'dm'
#     post_id: Optional[str]
#     timestamp: datetime
#     content: Optional[str] = None

# class AIEngagementService:
#     def __init__(self, db: firestore.Client, openai_client: OpenAI):
#         self.db = db
#         self.openai_client = openai_client
#         self.config = AIEngagementConfig()
        
#     async def get_active_ai_users(self) -> List[Dict]:
#         """Get all AI users eligible for engagement"""
#         try:
#             ai_users_ref = self.db.collection('aiUsers')
#             snapshot = ai_users_ref.stream()
#             return [doc.to_dict() for doc in snapshot if doc.to_dict().get('username')]
#         except Exception as e:
#             logger.error(f"Error getting active AI users: {e}")
#             return []

#     async def get_recent_posts(self, limit: int = 50) -> List[Dict]:
#         """Get recent posts from all users for AI engagement"""
#         try:
#             # Get human posts
#             human_posts = []
#             human_posts_ref = self.db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(limit)
#             human_posts_snapshot = human_posts_ref.stream()
#             for doc in human_posts_snapshot:
#                 post_data = doc.to_dict()
#                 post_data['id'] = doc.id
#                 post_data['collection'] = 'humanPosts'
#                 human_posts.append(post_data)
            
#             # Get AI posts (AIs can engage with other AI posts too)
#             ai_posts = []
#             ai_posts_ref = self.db.collection('aiPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(limit)
#             ai_posts_snapshot = ai_posts_ref.stream()
#             for doc in ai_posts_snapshot:
#                 post_data = doc.to_dict()
#                 post_data['id'] = doc.id
#                 post_data['collection'] = 'aiPosts'
#                 ai_posts.append(post_data)
            
#             # Combine and sort by date
#             all_posts = human_posts + ai_posts
#             all_posts.sort(key=lambda x: x.get('date_posted', datetime.min), reverse=True)
            
#             return all_posts[:limit]
#         except Exception as e:
#             logger.error(f"Error getting recent posts: {e}")
#             return []

#     async def get_daily_interaction_count(self, ai_user_id: str) -> int:
#         """Get number of interactions this AI has made today"""
#         try:
#             today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
#             interactions_ref = self.db.collection('aiInteractions')
#             query = interactions_ref.where('ai_user_id', '==', ai_user_id)\
#                                   .where('timestamp', '>=', today_start)
            
#             snapshot = query.stream()
#             return len(list(snapshot))
#         except Exception as e:
#             logger.error(f"Error getting daily interaction count: {e}")
#             return 0

#     async def has_recent_dm_unanswered(self, ai_user_id: str, target_user_id: str) -> bool:
#         """Check if AI has sent a DM to user that hasn't been answered"""
#         try:
#             # Check for recent DMs from AI to user
#             dms_ref = self.db.collection('direct_messages')
#             query = dms_ref.where('sender_id', '==', ai_user_id)\
#                           .where('recipient_id', '==', target_user_id)\
#                           .order_by('timestamp', direction=firestore.Query.DESCENDING)\
#                           .limit(1)
            
#             recent_dm_snapshot = query.stream()
#             recent_dm_docs = list(recent_dm_snapshot)
            
#             if not recent_dm_docs:
#                 return False
                
#             recent_dm = recent_dm_docs[0].to_dict()
#             recent_dm_time = recent_dm.get('timestamp')
            
#             # Check if user replied after the AI's last message
#             reply_query = dms_ref.where('sender_id', '==', target_user_id)\
#                                 .where('recipient_id', '==', ai_user_id)\
#                                 .where('timestamp', '>', recent_dm_time)\
#                                 .limit(1)
            
#             reply_snapshot = reply_query.stream()
#             has_reply = len(list(reply_snapshot)) > 0
            
#             return not has_reply
#         except Exception as e:
#             logger.error(f"Error checking unanswered DMs: {e}")
#             return True  # Conservative approach - assume there's an unanswered DM

#     async def analyze_media_content(self, post: Dict) -> Dict:
#         """Analyze media content in posts for richer context"""
#         try:
#             media_analysis = {
#                 'has_media': False,
#                 'media_types': [],
#                 'media_count': 0,
#                 'media_urls': [],
#                 'visual_context': ''
#             }
            
#             # Check for media flags
#             has_image = post.get('has_image', False)
#             has_video = post.get('has_video', False)
            
#             # Get media content arrays
#             post_obj = post.get('post', {})
#             image_content = post_obj.get('image_content', [])
#             video_content = post_obj.get('video_content', [])
            
#             # Analyze images
#             if has_image and image_content:
#                 media_analysis['has_media'] = True
#                 media_analysis['media_types'].append('image')
#                 media_analysis['media_count'] += len(image_content)
                
#                 # Extract image URLs if available
#                 for img in image_content:
#                     if isinstance(img, str):
#                         media_analysis['media_urls'].append(img)
#                     elif isinstance(img, dict) and 'url' in img:
#                         media_analysis['media_urls'].append(img['url'])
                
#                 # Visual context for images
#                 if len(image_content) == 1:
#                     media_analysis['visual_context'] = 'single image'
#                 elif len(image_content) <= 3:
#                     media_analysis['visual_context'] = f'{len(image_content)} images in a slideshow'
#                 else:
#                     media_analysis['visual_context'] = f'image gallery with {len(image_content)} photos'
            
#             # Analyze videos
#             if has_video and video_content:
#                 media_analysis['has_media'] = True
#                 media_analysis['media_types'].append('video')
#                 media_analysis['media_count'] += len(video_content)
                
#                 # Extract video URLs if available
#                 for vid in video_content:
#                     if isinstance(vid, str):
#                         media_analysis['media_urls'].append(vid)
#                     elif isinstance(vid, dict) and 'url' in vid:
#                         media_analysis['media_urls'].append(vid['url'])
                
#                 # Visual context for videos
#                 if len(video_content) == 1:
#                     media_analysis['visual_context'] = 'video content'
#                 else:
#                     media_analysis['visual_context'] = f'{len(video_content)} video clips'
            
#             # Mixed media
#             if has_image and has_video:
#                 media_analysis['visual_context'] = 'mixed media post with images and videos'
            
#             # Look for Firebase Storage URLs in the entire post structure
#             def find_firebase_urls(data):
#                 urls = []
#                 if isinstance(data, dict):
#                     for value in data.values():
#                         if isinstance(value, str) and ('firebase' in value.lower() or 'storage.googleapis.com' in value.lower()):
#                             urls.append(value)
#                         elif isinstance(value, (dict, list)):
#                             urls.extend(find_firebase_urls(value))
#                 elif isinstance(data, list):
#                     for item in data:
#                         urls.extend(find_firebase_urls(item))
#                 return urls
            
#             firebase_urls = find_firebase_urls(post)
#             if firebase_urls:
#                 media_analysis['media_urls'].extend(firebase_urls)
#                 if not media_analysis['has_media']:
#                     media_analysis['has_media'] = True
#                     media_analysis['visual_context'] = 'media content'
            
#             return media_analysis
            
#         except Exception as e:
#             logger.error(f"Error analyzing media content: {e}")
#             return {'has_media': False, 'media_types': [], 'media_count': 0, 'media_urls': [], 'visual_context': ''}

#     async def generate_ai_comment(self, ai_user: Dict, post: Dict) -> str:
#         """Generate contextual comment based on AI personality and comprehensive post content"""
#         try:
#             ai_personality = ai_user.get('personality', 'friendly and supportive')
#             ai_name = ai_user.get('name', 'an AI character')
#             ai_categories = ai_user.get('category', [])
            
#             # Extract comprehensive post information
#             post_obj = post.get('post', {})
#             post_content = post_obj.get('text_content', '') or post_obj.get('textContent', '') or post.get('content', '')
            
#             # Advanced media analysis
#             media_analysis = await self.analyze_media_content(post)
            
#             # Advanced post metadata
#             author = post.get('user_name', 'someone')
#             is_influencer = post.get('is_influencer', False)
#             likes_count = post.get('likes', 0)
#             comments = post.get('comments', [])
            
#             # Handle post categories from both humanPosts and aiPosts collections
#             post_categories = post.get('category', [])
#             post_main_category = post.get('main_category', '')
#             post_sub_category = post.get('sub_category', '')
            
#             # Combine all category information
#             all_post_categories = []
#             if isinstance(post_categories, list):
#                 all_post_categories.extend(post_categories)
#             elif isinstance(post_categories, str) and post_categories:
#                 all_post_categories.append(post_categories)
            
#             if post_main_category:
#                 all_post_categories.append(post_main_category)
#             if post_sub_category:
#                 all_post_categories.append(post_sub_category)
            
#             # Remove duplicates and empty strings
#             all_post_categories = [cat for cat in set(all_post_categories) if cat]
            
#             # Enhanced media context
#             media_context = ""
#             if media_analysis['has_media']:
#                 visual_desc = media_analysis['visual_context']
#                 media_types = ' and '.join(media_analysis['media_types'])
#                 media_context = f"This post features {visual_desc} ({media_types})."
#             else:
#                 media_context = "This is a text-based post."
            
#             # Engagement level context
#             engagement_context = ""
#             if likes_count > 10:
#                 engagement_context = f"This post is trending with {likes_count} likes."
#             elif len(comments) > 3:
#                 engagement_context = f"Active discussion happening ({len(comments)} comments)."
#             elif likes_count > 0:
#                 engagement_context = f"{likes_count} people liked this."
            
#             # Create sophisticated contextual prompt with personality-driven responses
#             comment_styles = {
#                 'artist': "Focus on visual aesthetics, creativity, composition, or artistic expression",
#                 'gamer': "Reference gaming mechanics, strategy, or competitive elements",
#                 'musician': "Connect to rhythm, sound, creativity, or emotional expression",  
#                 'tech': "Discuss innovation, functionality, or technical aspects",
#                 'social': "Emphasize community, trends, or social connections",
#                 'fitness': "Relate to energy, motivation, or active lifestyle",
#                 'food': "Connect to flavors, experiences, or sensory details"
#             }
            
#             # Determine AI's likely commenting style based on personality
#             style_hint = ""
#             personality_lower = ai_personality.lower()
#             if any(word in personality_lower for word in ['artist', 'creative', 'visual', 'art']):
#                 style_hint = comment_styles['artist']
#             elif any(word in personality_lower for word in ['music', 'song', 'sound']):
#                 style_hint = comment_styles['musician']
#             elif any(word in personality_lower for word in ['game', 'strategy', 'competitive']):
#                 style_hint = comment_styles['gamer']
#             elif any(word in personality_lower for word in ['tech', 'innovation']):
#                 style_hint = comment_styles['tech']
#             elif any(word in personality_lower for word in ['social', 'community']):
#                 style_hint = comment_styles['social']
#             elif any(word in personality_lower for word in ['food', 'culinary', 'flavor']):
#                 style_hint = comment_styles['food']
            
#             prompt = f"""
#             You are {ai_name}, a real teen on social media. Your authentic personality: {ai_personality}
            
#             Your genuine interests: {', '.join(ai_categories) if ai_categories else 'exploring new things'}
            
#             POST ANALYSIS:
#             - Author: {author} {'(verified/influencer)' if is_influencer else ''}
#             - Topic: {', '.join(all_post_categories) if all_post_categories else 'general'}
#             - Text: "{post_content[:250]}{'...' if len(post_content) > 250 else ''}"
#             - Visual: {media_context}
#             - Social proof: {engagement_context}
            
#             PERSONALITY GUIDANCE: {style_hint}
            
#             Write a natural comment (15-35 words) that:
#             • Shows your genuine personality and perspective
#             • References something specific you noticed
#             • Sounds like authentic teen conversation
#             • Uses 1-2 relevant emojis naturally
#             • Asks a question or makes a relatable observation
#             • Reflects your interests/expertise subtly
            
#             AVOID generic responses. Be creative, specific, and authentic:
#             """
            
#             response = self.openai_client.chat.completions.create(
#                 model="gpt-3.5-turbo",
#                 messages=[{"role": "user", "content": prompt}],
#                 max_tokens=120,
#                 temperature=0.9,  # Higher creativity
#                 presence_penalty=0.7,  # Strong variety encouragement
#                 frequency_penalty=0.4   # Reduce repetitive phrases
#             )
            
#             comment = response.choices[0].message.content.strip()
            
#             # Remove quotes if AI added them
#             if comment.startswith('"') and comment.endswith('"'):
#                 comment = comment[1:-1]
                
#             return comment
#         except Exception as e:
#             logger.error(f"Error generating AI comment: {e}")
#             return "This caught my attention! �"

#     async def generate_ai_dm(self, ai_user: Dict, target_user: Dict) -> str:
#         """Generate casual DM based on user's recent activity"""
#         try:
#             ai_personality = ai_user.get('personality', 'friendly and casual')
#             ai_interests = ai_user.get('category', [])
            
#             prompt = f"""
#             You are {ai_user.get('name', 'an AI character')} with this personality: {ai_personality}
            
#             Your interests: {', '.join(ai_interests) if ai_interests else 'general conversation'}
            
#             Send a casual, friendly DM to start a conversation. Be:
#             - Natural and warm
#             - Brief (max 30 words)
#             - Genuinely interested in connecting
#             - Not pushy or artificial
            
#             Example styles:
#             - "Hey! Loved your recent post about [topic]. I'm really into that too!"
#             - "Hi there! Your content always brightens my feed 😊"
#             - "Hello! Been following your posts and would love to chat!"
            
#             Don't mention being AI or artificial.
#             """
            
#             response = self.openai_client.chat.completions.create(
#                 model="gpt-3.5-turbo",
#                 messages=[{"role": "user", "content": prompt}],
#                 max_tokens=80,
#                 temperature=0.9
#             )
            
#             return response.choices[0].message.content.strip()
#         except Exception as e:
#             logger.error(f"Error generating AI DM: {e}")
#             return "Hey! Hope you're having a great day! 😊"

#     async def create_comment_interaction(self, ai_user: Dict, post: Dict) -> bool:
#         """Create a comment on a post"""
#         try:
#             comment_content = await self.generate_ai_comment(ai_user, post)
            
#             comment_data = {
#                 "postId": post['id'],
#                 "userId": ai_user['username'],
#                 "content": comment_content,
#                 "createdAt": firestore.SERVER_TIMESTAMP,
#                 "isAIGenerated": True
#             }
            
#             # Add comment to postComments collection
#             self.db.collection('postComments').add(comment_data)
            
#             # Log the interaction
#             await self.log_interaction(
#                 ai_user['username'],
#                 post.get('user_name') or post.get('username'),
#                 'comment',
#                 post['id'],
#                 comment_content
#             )
            
#             logger.info(f"AI {ai_user['username']} commented on post {post['id']}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error creating comment interaction: {e}")
#             return False

#     async def create_like_interaction(self, ai_user: Dict, post: Dict) -> bool:
#         """Create a like on a post"""
#         try:
#             like_data = {
#                 "user_id": ai_user['username'],
#                 "post_id": post['id'],
#                 "timestamp": firestore.SERVER_TIMESTAMP
#             }
            
#             # Add like to postLikes collection
#             self.db.collection('postLikes').add(like_data)
            
#             # Increment likes count on the post
#             post_ref = self.db.collection(post['collection']).document(post['id'])
#             post_ref.update({"likes": firestore.Increment(1)})
            
#             # Log the interaction
#             await self.log_interaction(
#                 ai_user['username'],
#                 post.get('user_name') or post.get('username'),
#                 'like',
#                 post['id']
#             )
            
#             logger.info(f"AI {ai_user['username']} liked post {post['id']}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error creating like interaction: {e}")
#             return False

#     async def create_dm_interaction(self, ai_user: Dict, target_user_id: str) -> bool:
#         """Create a private DM"""
#         try:
#             # Check if already sent unanswered DM
#             if await self.has_recent_dm_unanswered(ai_user['username'], target_user_id):
#                 logger.info(f"AI {ai_user['username']} skipping DM to {target_user_id} - unanswered DM exists")
#                 return False
            
#             # Generate DM content
#             dm_content = await self.generate_ai_dm(ai_user, {'username': target_user_id})
            
#             dm_data = {
#                 "sender_id": ai_user['username'],
#                 "recipient_id": target_user_id,
#                 "content": dm_content,
#                 "timestamp": firestore.SERVER_TIMESTAMP,
#                 "isAIGenerated": True,
#                 "read": False
#             }
            
#             # Add to direct_messages collection
#             self.db.collection('direct_messages').add(dm_data)
            
#             # Log the interaction
#             await self.log_interaction(
#                 ai_user['username'],
#                 target_user_id,
#                 'dm',
#                 None,
#                 dm_content
#             )
            
#             logger.info(f"AI {ai_user['username']} sent DM to {target_user_id}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error creating DM interaction: {e}")
#             return False

#     async def log_interaction(self, ai_user_id: str, target_user_id: str, 
#                             interaction_type: str, post_id: Optional[str] = None, 
#                             content: Optional[str] = None):
#         """Log AI interaction for tracking and rate limiting"""
#         try:
#             log_data = {
#                 "ai_user_id": ai_user_id,
#                 "target_user_id": target_user_id,
#                 "interaction_type": interaction_type,
#                 "post_id": post_id,
#                 "content": content,
#                 "timestamp": firestore.SERVER_TIMESTAMP
#             }
            
#             self.db.collection('aiInteractions').add(log_data)
#         except Exception as e:
#             logger.error(f"Error logging interaction: {e}")

#     async def should_ai_engage_with_post(self, ai_user: Dict, post: Dict) -> bool:
#         """Determine if AI should engage with this post based on relevance"""
#         try:
#             # Don't engage with own posts
#             if post.get('user_name') == ai_user['username'] or post.get('username') == ai_user['username']:
#                 return False
            
#             # Get AI interests
#             ai_interests = ai_user.get('category', [])
#             if not ai_interests:
#                 return random.random() < 0.2  # 20% chance for general content
            
#             # Get all post categories (handling both collections)
#             post_categories = post.get('category', [])
#             post_main_category = post.get('main_category', '')
#             post_sub_category = post.get('sub_category', '')
            
#             # Combine all post categories
#             all_post_categories = []
#             if isinstance(post_categories, list):
#                 all_post_categories.extend([cat.lower() for cat in post_categories if cat])
#             elif isinstance(post_categories, str) and post_categories:
#                 all_post_categories.append(post_categories.lower())
            
#             if post_main_category:
#                 all_post_categories.append(post_main_category.lower())
#             if post_sub_category:
#                 all_post_categories.append(post_sub_category.lower())
            
#             # Remove duplicates
#             all_post_categories = list(set(all_post_categories))
            
#             # Check for interest alignment
#             for ai_interest in ai_interests:
#                 ai_interest_lower = ai_interest.lower()
#                 for post_category in all_post_categories:
#                     if ai_interest_lower in post_category or post_category in ai_interest_lower:
#                         return random.random() < 0.7  # 70% chance for relevant content
            
#             # Lower probability for non-relevant content
#             return random.random() < 0.2  # 20% chance for general content
            
#         except Exception as e:
#             logger.error(f"Error determining engagement relevance: {e}")
#             return False

#     async def get_potential_dm_targets(self, ai_user: Dict) -> List[str]:
#         """Get list of users AI could potentially DM"""
#         try:
#             # Get recent active users from posts
#             recent_posts = await self.get_recent_posts(30)
#             user_ids = set()
            
#             for post in recent_posts:
#                 user_id = post.get('user_name') or post.get('username')
#                 if user_id and user_id != ai_user['username']:
#                     user_ids.add(user_id)
            
#             return list(user_ids)
#         except Exception as e:
#             logger.error(f"Error getting DM targets: {e}")
#             return []

#     async def process_ai_engagement_cycle(self):
#         """Main function to process AI engagement for all active AI users"""
#         try:
#             active_ai_users = await self.get_active_ai_users()
#             recent_posts = await self.get_recent_posts()
            
#             logger.info(f"Processing engagement for {len(active_ai_users)} AI users on {len(recent_posts)} posts")
            
#             for ai_user in active_ai_users:
#                 try:
#                     # Check daily interaction limit
#                     daily_count = await self.get_daily_interaction_count(ai_user['username'])
#                     if daily_count >= self.config.max_daily_interactions:
#                         continue
                    
#                     # Decide on interaction type
#                     interactions_remaining = self.config.max_daily_interactions - daily_count
                    
#                     # Try post interactions first
#                     eligible_posts = [post for post in recent_posts 
#                                     if await self.should_ai_engage_with_post(ai_user, post)]
                    
#                     if eligible_posts and interactions_remaining > 0:
#                         selected_post = random.choice(eligible_posts)
                        
#                         # Decide interaction type
#                         rand = random.random()
#                         if rand < self.config.comment_probability:
#                             success = await self.create_comment_interaction(ai_user, selected_post)
#                             if success:
#                                 interactions_remaining -= 1
#                         else:
#                             success = await self.create_like_interaction(ai_user, selected_post)
#                             if success:
#                                 interactions_remaining -= 1
                    
#                     # Try DM if still have interactions left
#                     if interactions_remaining > 0 and random.random() < self.config.dm_probability:
#                         dm_targets = await self.get_potential_dm_targets(ai_user)
#                         if dm_targets:
#                             target = random.choice(dm_targets)
#                             await self.create_dm_interaction(ai_user, target)
                    
#                 except Exception as e:
#                     logger.error(f"Error processing engagement for AI {ai_user.get('username')}: {e}")
#                     continue
            
#             logger.info("AI engagement cycle completed")
            
#         except Exception as e:
#             logger.error(f"Error in AI engagement cycle: {e}")

# class ApiException(Exception):
#     def __init__(self, message: str, error_code: str, status_code: int = 500):
#         super().__init__(message)
#         self.error_code = error_code
#         self.status_code = status_code
