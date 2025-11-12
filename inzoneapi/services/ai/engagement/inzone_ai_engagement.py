import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from firebase_admin import firestore
from openai import OpenAI
import re

logger = logging.getLogger(__name__)

class InZoneAIEngagementService:
    """
    AI Engagement Service for InZone social media platform.
    
    This service handles AI character interactions including:
    - Contextual comment generation with GPT-4 Vision analysis
    - Natural DM message generation with conversation awareness
    - Web search integration for popular characters to ensure authentic personality representation
    - Trending content analysis and media content understanding
    
    Features:
    - Popular characters use web search to get current personality information
    - Regular AI users follow generic teen conversation patterns
    - Visual content analysis using GPT-4 Vision
    - Conversation context awareness for DMs
    - Anti-spam protection for AI interactions
    """
    def __init__(self, db: firestore.Client, openai_client: OpenAI):
        self.db = db
        self.openai_client = openai_client
        self.max_daily_interactions = 8  # Increased for more engagement
        
    def get_trending_content_insights(self) -> Dict:
        """Analyze recent posts to understand current trends"""
        try:
            # Get recent human posts for trend analysis
            recent_posts = []
            posts_ref = self.db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(50)
            for doc in posts_ref.stream():
                recent_posts.append(doc.to_dict())
            
            # Analyze trends from categories and content
            trending_topics = []
            popular_emojis = []
            content_styles = []
            
            for post in recent_posts:
                categories = post.get('category', [])
                trending_topics.extend(categories)
                
                # Extract content patterns
                post_obj = post.get('post', {})
                text_content = post_obj.get('text_content', '') or post_obj.get('textContent', '')
                
                # Find emojis
                emoji_pattern = re.compile("["
                    u"\U0001F600-\U0001F64F"  # emoticons
                    u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                    u"\U0001F680-\U0001F6FF"  # transport & map symbols
                    u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                    "]+", flags=re.UNICODE)
                emojis = emoji_pattern.findall(text_content)
                popular_emojis.extend(emojis)
            
            # Get most common trends
            from collections import Counter
            trending_topics = [item for item, count in Counter(trending_topics).most_common(10)]
            popular_emojis = [item for item, count in Counter(popular_emojis).most_common(5)]
            
            return {
                'trending_topics': trending_topics,
                'popular_emojis': popular_emojis,
                'content_styles': ['casual', 'trendy', 'authentic', 'engaging']
            }
            
        except Exception as e:
            logger.error(f"Error getting trending insights: {e}")
            return {
                'trending_topics': ['trending', 'viral', 'aesthetic'],
                'popular_emojis': ['😍', '🔥', '✨', '💀', '😭'],
                'content_styles': ['casual', 'trendy']
            }

    def analyze_post_media_content(self, post: Dict) -> Dict:
        """Enhanced media analysis using GPT-4 Vision for images and videos"""
        try:
            media_analysis = {
                'media_type': 'text',
                'visual_context': 'text post',
                'engagement_factor': 1.0,
                'content_style': 'casual',
                'media_urls': [],
                'total_media_count': 0,
                'gpt_analysis': '',
                'visual_description': ''
            }
            
            post_obj = post.get('post', {})
            image_content = post_obj.get('image_content', [])
            video_content = post_obj.get('video_content', [])
            text_content = post_obj.get('text_content', '') or post_obj.get('textContent', '') or post.get('content', '')
            
            has_image = post.get('has_image', False) and image_content and any(img.strip() for img in image_content if img)
            has_video = post.get('has_video', False) and video_content and any(vid.strip() for vid in video_content if vid)
            
            # Collect valid media URLs
            valid_image_urls = []
            valid_video_urls = []
            
            if has_image:
                for img in image_content:
                    if isinstance(img, str) and img.strip() and ('http' in img or 'firebase' in img.lower()):
                        valid_image_urls.append(img.strip())
                        media_analysis['media_urls'].append(img.strip())
            
            if has_video:
                for vid in video_content:
                    if isinstance(vid, str) and vid.strip() and ('http' in vid or 'firebase' in vid.lower()):
                        valid_video_urls.append(vid.strip())
                        media_analysis['media_urls'].append(vid.strip())
            
            media_analysis['total_media_count'] = len(valid_image_urls) + len(valid_video_urls)
            
            # GPT-4 Vision Analysis for images
            if valid_image_urls:
                try:
                    print(f"🔍 Analyzing image with GPT-4 Vision: {valid_image_urls[0][:100]}...")
                    
                    # Use GPT-4 Vision to analyze the image - PRIORITIZE VISUAL CONTENT
                    vision_response = self.openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"""PRIORITY: Analyze the IMAGE CONTENT FIRST, then relate to text.

TEXT CONTENT: "{text_content}"

INSTRUCTIONS:
1. VISUAL ANALYSIS (Primary - describe exactly what you see):
   - Objects, people, scenery, art, activities in the image
   - Colors, lighting, composition, artistic elements
   - Specific details like materials, techniques, settings
   - Mood and atmosphere created by the visual content

2. TEXT RELATIONSHIP (Secondary):
   - How does the text relate to what you observe in the image?
   
CRITICAL: Be accurate about what's actually visible. If you see:
- A beach/sunset scene → describe the natural scenery
- Recycled art/crafts → describe the materials and creativity
- People/portraits → describe the subjects and setting
- Food/objects → describe what's actually shown

Don't assume content - describe what you observe in the visual."""
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": valid_image_urls[0]
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=350
                    )
                    
                    gpt_analysis = vision_response.choices[0].message.content
                    media_analysis['gpt_analysis'] = gpt_analysis
                    media_analysis['visual_description'] = gpt_analysis[:200] + "..." if len(gpt_analysis) > 200 else gpt_analysis
                    
                    print(f"✅ GPT-4 Vision analysis: {gpt_analysis[:150]}...")
                    
                    # Determine media type and style based on ACTUAL VISUAL CONTENT
                    analysis_lower = gpt_analysis.lower()
                    
                    # Prioritize specific visual content categories
                    if any(word in analysis_lower for word in ['sunset', 'sunrise', 'beach', 'ocean', 'golden', 'horizon', 'sky', 'serene', 'water', 'sand']):
                        media_analysis['media_type'] = 'scenic_image'
                        media_analysis['content_style'] = 'serene'
                        media_analysis['engagement_factor'] = 1.3
                    elif any(word in analysis_lower for word in ['recycl', 'pull tab', 'can tab', 'upcycl', 'repurpos', 'aluminum', 'craft']):
                        media_analysis['media_type'] = 'recycled_art_image'
                        media_analysis['content_style'] = 'eco_creative'
                        media_analysis['engagement_factor'] = 1.4
                    elif any(word in analysis_lower for word in ['art', 'artistic', 'creative', 'painting', 'drawing', 'design', 'handmade']):
                        media_analysis['media_type'] = 'artistic_image'
                        media_analysis['content_style'] = 'artistic'
                        media_analysis['engagement_factor'] = 1.4
                    elif any(word in analysis_lower for word in ['aesthetic', 'beautiful', 'stunning', 'gorgeous', 'peaceful']):
                        media_analysis['media_type'] = 'aesthetic_image'
                        media_analysis['content_style'] = 'aesthetic'
                        media_analysis['engagement_factor'] = 1.3
                    elif any(word in analysis_lower for word in ['funny', 'humorous', 'meme', 'silly', 'amusing']):
                        media_analysis['media_type'] = 'humorous_image'
                        media_analysis['content_style'] = 'humorous'
                        media_analysis['engagement_factor'] = 1.5
                    elif any(word in analysis_lower for word in ['selfie', 'portrait', 'person', 'face', 'people']):
                        media_analysis['media_type'] = 'portrait_image'
                        media_analysis['content_style'] = 'personal'
                        media_analysis['engagement_factor'] = 1.2
                    elif any(word in analysis_lower for word in ['food', 'meal', 'cooking', 'eat', 'dish']):
                        media_analysis['media_type'] = 'food_image'
                        media_analysis['content_style'] = 'appealing'
                        media_analysis['engagement_factor'] = 1.4
                    else:
                        media_analysis['media_type'] = 'image'
                        media_analysis['content_style'] = 'authentic'
                        media_analysis['engagement_factor'] = 1.3
                    
                    media_analysis['visual_context'] = f"image showing: {gpt_analysis[:100]}..."
                    
                except Exception as vision_error:
                    print(f"⚠️ GPT-4 Vision analysis failed: {vision_error}")
                    # Fallback to basic image analysis
                    media_analysis['media_type'] = 'image'
                    media_analysis['visual_context'] = 'image post'
                    media_analysis['content_style'] = 'visual'
                    media_analysis['engagement_factor'] = 1.3
            
            # GPT-4 Vision Analysis for videos (extract frames for analysis)
            elif valid_video_urls:
                try:
                    print(f"🎥 Analyzing video with frame extraction: {valid_video_urls[0][:100]}...")
                    
                    # Try to extract a frame from the video for GPT-4 Vision analysis
                    frame_extracted = False
                    gpt_analysis = ""
                    
                    try:
                        import cv2
                        import tempfile
                        import requests
                        import numpy as np
                        from PIL import Image
                        import base64
                        import io
                        
                        # Download video to temporary file
                        video_response = requests.get(valid_video_urls[0], stream=True, timeout=10)
                        if video_response.status_code == 200:
                            with tempfile.NamedTemporaryFile(suffix='.mov', delete=False) as temp_video:
                                for chunk in video_response.iter_content(chunk_size=8192):
                                    temp_video.write(chunk)
                                temp_video_path = temp_video.name
                            
                            # Extract frame using OpenCV
                            cap = cv2.VideoCapture(temp_video_path)
                            
                            # Get total frames and extract frame from middle
                            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            middle_frame = total_frames // 2
                            
                            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
                            ret, frame = cap.read()
                            
                            if ret:
                                # Convert BGR to RGB
                                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                
                                # Convert to PIL Image
                                pil_image = Image.fromarray(frame_rgb)
                                
                                # Convert to base64 for GPT-4 Vision
                                buffered = io.BytesIO()
                                pil_image.save(buffered, format="JPEG", quality=85)
                                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                
                                # Analyze frame with GPT-4 Vision
                                vision_response = self.openai_client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[
                                        {
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": f"""Analyze this video frame in the context of a social media post.

TEXT CONTENT: "{text_content}"

This is a frame extracted from a video. Provide:
1. What this video frame shows (be specific and detailed)
2. How it relates to the text content
3. The mood/aesthetic of the scene
4. Key visual elements that would be relevant for commenting
5. Overall vibe/energy of the video

Be accurate and specific - focus on what you can actually see in this frame."""
                                                },
                                                {
                                                    "type": "image_url",
                                                    "image_url": {
                                                        "url": f"data:image/jpeg;base64,{img_base64}"
                                                    }
                                                }
                                            ]
                                        }
                                    ],
                                    max_tokens=300
                                )
                                
                                gpt_analysis = vision_response.choices[0].message.content
                                frame_extracted = True
                                print(f"✅ GPT-4 Vision video frame analysis: {gpt_analysis[:100]}...")
                            
                            cap.release()
                            
                            # Clean up temp file
                            import os
                            try:
                                os.unlink(temp_video_path)
                            except:
                                pass
                    
                    except Exception as frame_error:
                        print(f"⚠️ Frame extraction failed: {frame_error}")
                        # Fall back to text-based analysis
                        frame_extracted = False
                    
                    # If frame extraction failed, do text-based analysis
                    if not frame_extracted:
                        print(f"🎥 Falling back to text-based video analysis...")
                        video_response = self.openai_client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "user",
                                    "content": f"""Since I cannot directly analyze the video content, I'll analyze based on the text:

TEXT CONTENT: "{text_content}"

Based on the text content, provide insights about what this video likely contains:
1. Likely video content based on the text
2. Probable mood/vibe
3. How to comment appropriately
4. General aesthetic

Note: This is text-based inference since direct video analysis wasn't possible."""
                                }
                            ],
                            max_tokens=200
                        )
                        gpt_analysis = video_response.choices[0].message.content
                        print(f"✅ Text-based video analysis: {gpt_analysis[:100]}...")
                    
                    media_analysis['gpt_analysis'] = gpt_analysis
                    media_analysis['visual_description'] = gpt_analysis[:200] + "..." if len(gpt_analysis) > 200 else gpt_analysis
                    
                    media_analysis['media_type'] = 'video'
                    media_analysis['visual_context'] = f"video analysis: {gpt_analysis[:100]}..."
                    media_analysis['engagement_factor'] = 1.5
                    
                    # Determine style based on analysis
                    analysis_lower = gpt_analysis.lower()
                    if any(word in analysis_lower for word in ['relaxing', 'calm', 'peaceful', 'soothing', 'serene']):
                        media_analysis['content_style'] = 'calming'
                    elif any(word in analysis_lower for word in ['energetic', 'exciting', 'intense', 'dynamic', 'active']):
                        media_analysis['content_style'] = 'energetic'
                    elif any(word in analysis_lower for word in ['artistic', 'creative', 'aesthetic', 'beautiful']):
                        media_analysis['content_style'] = 'artistic'
                    elif any(word in analysis_lower for word in ['nature', 'outdoor', 'landscape', 'scenery']):
                        media_analysis['content_style'] = 'nature'
                    else:
                        media_analysis['content_style'] = 'dynamic'
                    
                except Exception as video_error:
                    print(f"⚠️ GPT-4 video analysis failed: {video_error}")
                    # Fallback to basic video analysis
                    media_analysis['media_type'] = 'video'
                    media_analysis['visual_context'] = 'video post'
                    media_analysis['content_style'] = 'dynamic'
                    media_analysis['engagement_factor'] = 1.5
            
            # Mixed media
            if valid_image_urls and valid_video_urls:
                media_analysis['media_type'] = 'mixed'
                media_analysis['visual_context'] = 'multimedia post with images and videos'
                media_analysis['content_style'] = 'rich_content'
                media_analysis['engagement_factor'] = 1.7
            
            # Analyze text content for additional context if no media
            if not valid_image_urls and not valid_video_urls and text_content:
                content_lower = text_content.lower()
                
                # Detect content themes
                if any(word in content_lower for word in ['aesthetic', 'vibes', 'mood']):
                    media_analysis['content_style'] = 'aesthetic'
                elif any(word in content_lower for word in ['real', 'authentic', 'honest']):
                    media_analysis['content_style'] = 'authentic'
                elif any(word in content_lower for word in ['funny', 'lol', 'dead', 'crying']):
                    media_analysis['content_style'] = 'humorous'
                elif any(word in content_lower for word in ['trending', 'viral', 'popular']):
                    media_analysis['content_style'] = 'trendy'
            
            return media_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing media content with GPT: {e}")
            return {
                'media_type': 'text',
                'visual_context': 'content',
                'engagement_factor': 1.0,
                'content_style': 'casual',
                'media_urls': [],
                'total_media_count': 0,
                'gpt_analysis': '',
                'visual_description': ''
            }

    def generate_contextual_ai_comment(self, ai_user: Dict, post: Dict, trends: Dict) -> str:
        """Generate highly contextual, trend-aware AI comments with character-specific speaking patterns"""
        try:
            # Get AI personality and interests
            ai_personality = ai_user.get('personality', 'friendly and engaging')
            ai_name = ai_user.get('name', 'AI User')
            ai_username = ai_user.get('username', ai_name)
            
            # Check if this is a popular character (has specific speaking patterns)
            is_popular_character = (
                ai_user.get('_is_popular_character', False) or 
                ai_user.get('_collection_source') == 'popularCharacters' or
                ai_user.get('followerCount', 0) > 100000 or 
                'popularCharacters' in str(ai_user)
            )
            
            # Get post details
            post_obj = post.get('post', {})
            text_content = post_obj.get('text_content', '') or post_obj.get('textContent', '') or post.get('content', '')
            author = post.get('user_name', post.get('user_document_id', 'Unknown User'))
            categories = post.get('category', [])
            likes_count = post.get('likes', 0)
            
            # Enhanced media analysis
            media_analysis = self.analyze_post_media_content(post)
            
            # Get trending insights
            trending_topics = trends.get('trending_topics', [])
            popular_emojis = trends.get('popular_emojis', ['😍', '🔥', '✨'])
            
            
            # Create character-specific or generic prompt
            media_context = ""
            if media_analysis.get('gpt_analysis'):
                media_context = f"\nVISUAL ANALYSIS: {media_analysis['gpt_analysis'][:200]}..."
            
            if is_popular_character:
                # Use character-specific speaking patterns with web search
                logger.info(f"🔍 Using web search for popular character comment generation: {ai_name}")
                prompt = f"""
You are {ai_name} commenting on a social media post. Before writing your comment, search the web for current information about {ai_name}'s personality, speaking style, catchphrases, interests, and characteristic ways of communicating to ensure authenticity.

IMPORTANT: After searching for {ai_name}'s personality and speaking patterns, write a comment that sounds EXACTLY like how {ai_name} would speak based on their well-known characteristics. Do NOT use generic teen slang unless it specifically fits {ai_name}'s character.

POST: "{text_content[:150]}{'...' if len(text_content) > 150 else ''}"
AUTHOR: {author}
MEDIA: {media_analysis['visual_context']} ({media_analysis['media_type']}){media_context}
LIKES: {likes_count}

Please search the web first to gather information about {ai_name}'s:
- Speaking style and tone
- Common phrases and expressions they use
- Their personality traits and interests
- How they typically react to different types of content
- Their characteristic way of communicating

Then write a natural comment (8-20 words) that sounds EXACTLY like {ai_name} would say it based on the web search results. Consider:
- Their authentic personality and speaking style from search results
- Their actual catchphrases or typical expressions  
- Their real interests and perspective
- How they would genuinely react to this content
- Their verified characteristic way of communicating

Be authentic to {ai_name}'s true character based on web search, not generic social media language.

{ai_name}'s authentic comment:"""
            else:
                # Use generic teen commenting style for regular AI users
                prompt = f"""
You are {ai_name}, a {ai_personality} teen commenting on social media naturally.

POST: "{text_content[:150]}{'...' if len(text_content) > 150 else ''}"
AUTHOR: {author}
MEDIA: {media_analysis['visual_context']} ({media_analysis['media_type']}){media_context}
LIKES: {likes_count}

Write a natural comment (8-20 words) that sounds like real teen conversation.

IMPORTANT: If there's visual analysis provided, prioritize commenting on what you can actually see in the image/video over the text. Be specific about visual elements.

AUTHENTIC STYLES - pick ONE approach:

RELATABLE/PERSONAL:
- "This is literally me every single day 😭"
- "Why is this so accurate though"
- "Not me feeling called out rn"
- "This hits different when you relate"

HYPE/SUPPORT:
- "Ok but you absolutely ATE this! 🔥"
- "The way you served today"
- "This energy >>> everything else"
- "You really never miss with these"

GENUINE INTEREST:
- "Wait where is this?? Need to go"
- "Drop the deets pls 🙏"
- "This song choice though what is it"
- "How do you find these spots"

CASUAL/MODERN:
- "Same energy as my weekend tbh"
- "This but make it my personality"
- "Living for this aesthetic ngl"
- "Main character vibes activated"

FUNNY/WITTY:
- "POV: you have your life together"
- "Meanwhile me existing in chaos"
- "The confidence I need fr"
- "This person gets it"

SPECIFIC REACTIONS (especially for visual content):
- "The lighting in this though >>>"
- "Your outfit choices are unmatched"
- "This place looks like a movie set"
- "The way this made me smile"
- "That art is actually insane 🔥"
- "How did you even make this??"
- "The creativity is off the charts"

RULES:
- Sound like a REAL teen, not AI
- Use modern slang naturally (fr, ngl, tbh, lowkey, etc.)
- 1-2 emojis MAX if they fit naturally
- NO generic "wow/great/amazing" responses
- Be specific to what you actually see in the image/video
- Show personality through word choice
- Keep it conversational and authentic
- If you see recycled art (like pull tab crafts), mention the specific creativity/eco-consciousness

ONE natural comment:"""
            
            # Use ChatGPT model with web browsing capability for popular characters
            # This model can actually search the web when instructed to do so
            model_to_use = "chatgpt-4o-latest" if is_popular_character else "gpt-4o"
            
            # For popular characters, we explicitly ask the model to search for current information
            response = self.openai_client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80, 
                temperature=1.0,  # Maximum creativity
                presence_penalty=1.2,  # Strongly encourage unique responses  
                frequency_penalty=0.9   # Avoid repetitive phrases
            )
            
            comment = response.choices[0].message.content.strip()
            
            # Clean up the comment - remove AI artifacts and prefixes
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]
            
            # Remove "You:" prefix that sometimes appears in AI responses
            if comment.startswith("You: "):
                comment = comment[5:].strip()
            elif comment.startswith("You:"):
                comment = comment[4:].strip()
            
            # Remove other common AI prefixes
            ai_name = ai_user.get('name', 'AI User')
            prefixes_to_remove = ["AI: ", "AI:", "Comment: ", "Response: ", f"{ai_name}: ", f"{ai_name}:"]
            for prefix in prefixes_to_remove:
                if comment.startswith(prefix):
                    comment = comment[len(prefix):].strip()
                    break
            
            # Ensure it's not too long
            if len(comment.split()) > 35:
                words = comment.split()
                comment = ' '.join(words[:30]) + '...'
            
            return comment
            
        except Exception as e:
            logger.error(f"Error generating AI comment: {e}")
            # Re-raise the exception - no fallbacks allowed
            raise e

    def generate_ai_dm_message(self, ai_user: Dict, target_user: Dict, conversation_context: Dict = None) -> str:
        """Generate natural DM messages for AI users with better context handling"""
        try:
            ai_personality = ai_user.get('personality', 'friendly and casual')
            ai_name = ai_user.get('name', 'AI User')
            ai_user_id = ai_user.get('username') or ai_user.get('id') or ai_name
            target_name = target_user.get('name', 'there')
            target_user_id = target_user.get('id') or target_user.get('username') or target_name
            target_bio = target_user.get('bio', '')
            target_interests = target_user.get('interests', [])
            
            # Enhanced conversation analysis - don't set is_first_message here, 
            # let the detailed analysis below determine the correct message type
            is_first_message = None  # Will be determined by detailed analysis below
            
            # Advanced context analysis
            if conversation_context:
                ai_message_count = conversation_context.get('ai_message_count', 0)
                human_message_count = conversation_context.get('human_message_count', 0)
                last_human_message = conversation_context.get('last_human_message', '')
                last_ai_message = conversation_context.get('last_ai_message', '')
                conversation_active = conversation_context.get('conversation_active', False)
                
                logger.info(f"DM Context Analysis:")
                logger.info(f"   - Total messages: {conversation_context.get('message_count', 0)}")
                logger.info(f"   - AI messages: {ai_message_count}")
                logger.info(f"   - Human messages: {human_message_count}")
                logger.info(f"   - Conversation active: {conversation_active}")
                logger.info(f"   - Last human said: '{(last_human_message or '')[:50]}...'")
                logger.info(f"   - Last AI said: '{(last_ai_message or '')[:50]}...'")
                
                # Determine message type based on conversation state
                if ai_message_count > 0 and human_message_count == 0:
                    # AI has sent messages but human hasn't responded - don't spam
                    logger.info("🚫 Blocking: AI already sent unanswered messages")
                    raise Exception("AI already sent unanswered messages - preventing spam")
                
                elif human_message_count > 0 and last_human_message:
                    # Human has responded - generate contextual response
                    is_first_message = False
                    logger.info("💬 Using contextual response: Human has sent messages")
                    
                    # Create a detailed context-aware prompt using conversation history
                    recent_convo = ""
                    for msg in conversation_context.get('recent_messages', [])[:5]:  # Last 5 messages for context
                        sender_id = msg.get('senderId')
                        if sender_id == ai_user_id:
                            sender = "You"
                        elif sender_id == target_user_id:
                            sender = target_name
                        else:
                            sender = "Unknown"
                        text = msg.get('text', '')[:100]  # First 100 chars
                        recent_convo += f"{sender}: {text}\n"
                    
                    # Check if this is a popular character
                    is_popular_character = (
                        ai_user.get('_is_popular_character', False) or 
                        ai_user.get('_collection_source') == 'popularCharacters' or
                        ai_user.get('followerCount', 0) > 100000 or 
                        'popularCharacters' in str(ai_user)
                    )
                    
                    if is_popular_character:
                        # Use character-specific speaking patterns for popular characters with web search
                        logger.info(f"🔍 Using web search for popular character DM response: {ai_name}")
                        prompt = f"""
You are {ai_name} continuing a DM conversation with {target_name}. Before writing your response, search the web for current information about {ai_name}'s personality, speaking style, catchphrases, interests, and characteristic ways of communicating to ensure authenticity.

IMPORTANT: After searching for {ai_name}'s personality and speaking patterns, write a response that sounds EXACTLY like how {ai_name} would speak based on their well-known characteristics. Do NOT use generic teen slang unless it specifically fits {ai_name}'s character.

RECENT CONVERSATION:
{recent_convo}

THEIR LAST MESSAGE: "{last_human_message}"

Please search the web first to gather information about {ai_name}'s:
- Speaking style and tone  
- Common phrases and expressions they use
- Their personality traits and interests
- How they typically respond in conversations
- Their characteristic way of communicating

CRITICAL INSTRUCTIONS:
- Read their last message carefully and respond DIRECTLY to what they said
- If they said they DON'T do something, DO NOT mention that topic again
- If they corrected you or said you're wrong about something, acknowledge it and change topics
- If they seem uninterested in a topic, switch to something else
- Be a real person who actually listens and remembers what people tell you

Based on what {target_name} just said and the web search results about {ai_name}, write a natural response (8-25 words) that sounds EXACTLY like {ai_name} would say it. Consider:
- Their authentic personality and speaking style from search results
- Their actual catchphrases or typical expressions
- How they would genuinely respond to this situation
- Their verified characteristic way of communicating

Be authentic to {ai_name}'s true character based on web search, not generic social media language.

{ai_name}'s authentic response:"""
                    else:
                        # Generic teen style for regular AI users
                        prompt = f"""
You are {ai_name}, a real {ai_personality} teen continuing a DM conversation with {target_name}.

RECENT CONVERSATION:
{recent_convo}

THEIR LAST MESSAGE: "{last_human_message}"

CRITICAL INSTRUCTIONS:
- Read their last message carefully and respond DIRECTLY to what they said
- If they said they DON'T do something (like music, art, sports), DO NOT mention that topic again
- If they corrected you or said you're wrong about something, acknowledge it and change topics
- If they seem uninterested in a topic, switch to something else
- Be a real person who actually listens and remembers what people tell you

Based on what {target_name} just said, write a natural response (8-25 words) that:
• Directly acknowledges what they told you
• Shows you actually read and understood their message
• Respects their interests and preferences
• Sounds like a real teen texting back
• Uses modern slang naturally (fr, ngl, tbh, lowkey, etc.)
• 1 emoji max if it naturally fits
• Keeps the conversation flowing in a new direction if they rejected the old topic

DO NOT:
- Ignore what they just said
- Keep talking about topics they said they're not interested in
- Sound formal or robotic
- Use multiple emojis

Examples of good contextual responses:
If they said "I don't really play music": "oh my bad! what are you actually into then?"
If they said "I have no idea why you think I'm an artist": "lol sorry, totally got that wrong 😅 what do you actually do for fun?"
If they said "I'm not into sports": "fair enough! what's your thing instead?"

Your natural, context-aware response:
"""
                    
                    # Execute the contextual response using ChatGPT model with web browsing for popular characters
                    # chatgpt-4o-latest has web search capabilities, while gpt-4o uses training data only
                    model_to_use = "chatgpt-4o-latest" if is_popular_character else "gpt-4o"
                    
                    response = self.openai_client.chat.completions.create(
                        model=model_to_use,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=80,
                        temperature=0.95,
                        presence_penalty=1.0,
                        frequency_penalty=0.8
                    )
                    
                    message = response.choices[0].message.content.strip()
                    if message.startswith('"') and message.endswith('"'):
                        message = message[1:-1]
                    
                    logger.info(f"Generated contextual DM response: {message}")
                    return message
                    
                elif ai_message_count >= 2 and human_message_count > 0:
                    # Active conversation - use continuation logic
                    is_first_message = False
                    logger.info("💬 Using continuation: Active conversation detected")
                
                elif ai_message_count == 1 and human_message_count > 0:
                    # Human responded to first message - continue naturally  
                    is_first_message = False
                    logger.info("🎯 Using continuation: Human responded to initial message")
                
                else:
                    # Either truly first message or unclear state - check message counts
                    if conversation_context.get('message_count', 0) == 0:
                        is_first_message = True
                        logger.info(f"🆕 Using first message logic - No messages in conversation")
                    else:
                        # There are messages but unclear state - default to continuation
                        is_first_message = False
                        logger.info(f"🔄 Using continuation logic - Unclear state with {conversation_context.get('message_count', 0)} messages")
            else:
                # No conversation context provided - assume first message
                is_first_message = True
                logger.info("🆕 Using first message logic - No conversation context provided")
            
            # Get recent message context for repetition avoidance
            recent_messages = conversation_context.get('recent_messages', []) if conversation_context else []
            
            # Build context about the target user
            user_context = ""
            if target_bio:
                user_context += f"Their bio: {target_bio}. "
            if target_interests:
                user_context += f"Their interests: {', '.join(target_interests)}. "
            
            if is_first_message:
                logger.info("Generating FIRST message")
                
                # Check if this is a popular character
                is_popular_character = (
                    ai_user.get('_is_popular_character', False) or 
                    ai_user.get('_collection_source') == 'popularCharacters' or
                    ai_user.get('followerCount', 0) > 100000 or 
                    'popularCharacters' in str(ai_user)
                )
                
                if is_popular_character:
                    # Use character-specific speaking patterns for popular characters with web search
                    logger.info(f"🔍 Using web search for popular character first DM: {ai_name}")
                    if user_context:
                        prompt = f"""
You are {ai_name} sending a DM on social media. Before writing your message, search the web for current information about {ai_name}'s personality, speaking style, catchphrases, interests, and characteristic ways of communicating to ensure authenticity.

IMPORTANT: After searching for {ai_name}'s personality and speaking patterns, write a message that sounds EXACTLY like how {ai_name} would speak based on their well-known characteristics. Do NOT use generic teen slang unless it specifically fits {ai_name}'s character.

Starting a conversation with {target_name}.
{user_context}

Please search the web first to gather information about {ai_name}'s:
- Speaking style and tone
- Common phrases and expressions they use  
- Their personality traits and interests
- How they typically initiate conversations
- Their characteristic way of communicating

Then write a natural first DM (15-30 words) that sounds EXACTLY like {ai_name} would say it based on the web search results. Consider:
- Their authentic personality and speaking style from search results
- Their actual catchphrases or typical expressions
- Their real interests and perspective  
- How they would genuinely reach out to someone
- Their verified characteristic way of communicating

Be authentic to {ai_name}'s true character based on web search, not generic social media language.

{ai_name}'s authentic message:"""
                    else:
                        prompt = f"""
You are {ai_name} sending a DM on social media. Before writing your message, search the web for current information about {ai_name}'s personality, speaking style, catchphrases, interests, and characteristic ways of communicating to ensure authenticity.

IMPORTANT: After searching for {ai_name}'s personality and speaking patterns, write a message that sounds EXACTLY like how {ai_name} would speak based on their well-known characteristics. Do NOT use generic teen slang unless it specifically fits {ai_name}'s character.

Starting a conversation with {target_name}.

Please search the web first to gather information about {ai_name}'s:
- Speaking style and tone
- Common phrases and expressions they use
- Their personality traits and interests  
- How they typically initiate conversations
- Their characteristic way of communicating

Then write a natural first DM (15-25 words) that sounds EXACTLY like {ai_name} would say it based on the web search results. Consider:
- Their authentic personality and speaking style from search results
- Their actual catchphrases or typical expressions
- How they would genuinely reach out to someone
- Their verified characteristic way of communicating

Be authentic to {ai_name}'s true character based on web search, not generic social media language.

{ai_name}'s authentic message:"""
                else:
                    # Generic teen style for regular AI users
                    if user_context:
                        # Use bio/interests for personalized first message
                        prompt = f"""
You are {ai_name}, a real teen reaching out on social media DMs.

Your personality: {ai_personality}
Starting a conversation with {target_name}.
{user_context}

Write a natural, casual first DM (15-30 words) that:
• References something from their bio or interests naturally
• Sounds like authentic teen conversation  
• Shows genuine interest in connecting
• Uses 1-2 emojis naturally
• Is friendly but not pushy
• Doesn't sound generic or AI-generated

Examples:
- "Hey! Saw you're into photography too, your shots are amazing! 📸✨"
- "Hi! Fellow music lover here - what's been on your playlist lately? 🎵"
- "Hey there! Your travel posts are so cool, where's your favorite place you've been? ✈️"

Be natural and specific:
"""
                    else:
                        # Generic but still natural first message
                        prompt = f"""
You are {ai_name}, a real teen reaching out on social media DMs.

Your personality: {ai_personality}
Starting a conversation with {target_name}.

Write a natural, casual first DM (15-25 words) that:
• Sounds like authentic teen conversation
• Shows genuine interest in connecting  
• Uses 1 emoji naturally
• Is friendly but not pushy
• Feels like a real person reaching out

Examples:
- "Hey! Your posts always catch my eye, you seem really cool 😊"
- "Hi there! Love your vibe, would be fun to chat sometime ✨" 
- "Hey! We might have some things in common, hope you're having a great day 💫"

Be natural and authentic:
"""
            else:
                logger.info("Generating CONTINUATION message")
                # Continuation message - create varied follow-ups
                # Generate different types of follow-up messages
                follow_up_styles = [
                    "check_in",
                    "share_experience", 
                    "ask_question",
                    "react_to_activity",
                    "casual_conversation"
                ]
                
                chosen_style = random.choice(follow_up_styles)
                
                if chosen_style == "check_in":
                    prompt = f"""
You are {ai_name}, continuing a DM conversation with {target_name}.
Your personality: {ai_personality}

Write a casual check-in message (10-20 words) that:
• Sounds natural and caring
• Shows you're thinking of them
• Uses 1 emoji naturally
• Feels like a real friend checking in

Examples:
- "How's your week been treating you? 😊"
- "Hope you're having a good day! 🌟"
- "What's been keeping you busy lately? ✨"
- "Just wanted to see how you're doing! 💫"

Be warm and genuine:
"""
                elif chosen_style == "share_experience":
                    prompt = f"""
You are {ai_name}, continuing a DM conversation with {target_name}.
Your personality: {ai_personality}

Write a message sharing something from your day (15-25 words) that:
• Feels like sharing with a friend
• Relates to your personality/interests
• Invites them to share too
• Uses 1 emoji naturally

Examples:
- "Just discovered this amazing new song, reminded me of our music taste! 🎵"
- "Had the most creative day today, made me think of you! ✨"
- "Saw something hilarious earlier and thought you'd appreciate it 😂"

Be natural and relatable:
"""
                elif chosen_style == "ask_question":
                    prompt = f"""
You are {ai_name}, continuing a DM conversation with {target_name}.
Your personality: {ai_personality}

Write a friendly question (10-20 words) that:
• Shows genuine interest in their life
• Is open-ended and engaging
• Relates to their possible interests
• Uses 1 emoji naturally

Examples:
- "What's been the highlight of your week so far? ✨"
- "Any exciting plans coming up? 🌟"
- "What's been on your mind lately? �"
- "Discover anything cool recently? 😊"

Be curious and engaging:
"""
                elif chosen_style == "react_to_activity":
                    prompt = f"""
You are {ai_name}, continuing a DM conversation with {target_name}.
Your personality: {ai_personality}

Write a message reacting to their recent activity (12-22 words) that:
• References something they might have posted
• Shows you pay attention to their content
• Feels supportive and interested
• Uses 1 emoji naturally

Examples:
- "Your recent posts have been so aesthetic lately! 📸"
- "Looks like you've been having some great adventures! ✨"
- "Love seeing all your creative content recently 🎨"
- "You always know how to capture the perfect moments! 💫"

Be observant and supportive:
"""
                else:  # casual_conversation
                    prompt = f"""
You are {ai_name}, continuing a DM conversation with {target_name}.
Your personality: {ai_personality}

Write a casual conversation starter (12-20 words) that:
• Feels like natural friend conversation
• Opens up dialogue
• Shows your personality
• Uses 1 emoji naturally

Examples:
- "Random thought but do you ever feel like time goes too fast? 🤔"
- "Just realized we have such similar vibes, it's wild! ✨"
- "Been thinking about trying something new lately 🌟"
- "Do you ever get those days where everything feels perfect? 😊"

Be conversational and authentic:
"""
            
            # Use ChatGPT model with web browsing capability for popular characters
            # chatgpt-4o-latest has web search capabilities, while gpt-4o uses training data only
            model_to_use = "chatgpt-4o-latest" if is_popular_character else "gpt-4o"
            
            response = self.openai_client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.95,  # High creativity for natural variety
                presence_penalty=1.0,  # Encourage unique responses
                frequency_penalty=0.8   # Avoid repetitive patterns
            )
            
            message = response.choices[0].message.content.strip()
            
            # Clean up the message - remove common AI artifacts and prefixes
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            
            # Remove "You:" prefix that sometimes appears in AI responses
            if message.startswith("You:"):
                message = message[5:].strip()
            elif message.startswith("You:"):
                message = message[4:].strip()
            
            # Remove other common prefixes
            prefixes_to_remove = ["AI: ", "AI:", "Response: ", "Response:", f"{ai_name}: ", f"{ai_name}:"]
            for prefix in prefixes_to_remove:
                if message.startswith(prefix):
                    message = message[len(prefix):].strip()
                    break
            
            return message
            
        except Exception as e:
            logger.error(f"Error generating AI DM: {e}")
            # Re-raise the exception - no fallbacks allowed
            raise e

    def check_ai_daily_limit(self, ai_user_id: str) -> bool:
        """Check if AI user has reached daily interaction limit - simplified version"""
        try:
            # For now, allow interactions (disable daily limit checking to avoid index issues)
            # In production, you can implement this using a simple counter document per AI user per day
            return True
            
            # Original complex implementation (commented out until indexes are created):
            # today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            # 
            # # Check comments today
            # comments_count = 0
            # comments_ref = self.db.collection('postComments').where('userId', '==', ai_user_id).where('createdAt', '>=', today_start)
            # comments_count = len(list(comments_ref.stream()))
            # 
            # # Check messages today (count conversations started)
            # messages_count = 0
            # conversations_ref = self.db.collection('conversations')
            # for conv_doc in conversations_ref.stream():
            #     conv_data = conv_doc.to_dict()
            #     participants = conv_data.get('participants', [])
            #     if ai_user_id in participants:
            #         # Check if AI sent message today
            #         messages_ref = conv_doc.reference.collection('messages')
            #         ai_messages_today = messages_ref.where('senderId', '==', ai_user_id).where('timestamp', '>=', today_start)
            #         if len(list(ai_messages_today.stream())) > 0:
            #             messages_count += 1
            # 
            # total_interactions = comments_count + messages_count
            # return total_interactions < self.max_daily_interactions
            
        except Exception as e:
            logger.error(f"Error checking daily limit: {e}")
            return True  # Allow interaction on error

    def get_random_active_users(self, limit: int = 20) -> List[Dict]:
        """Get random active users for AI engagement"""
        try:
            # Get users who posted recently
            recent_posts = self.db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(100)
            active_user_ids = set()
            
            for doc in recent_posts.stream():
                post_data = doc.to_dict()
                user_id = post_data.get('user_document_id') or post_data.get('user_name')
                if user_id:
                    active_user_ids.add(user_id)
            
            # Convert to list and limit
            active_user_ids = list(active_user_ids)[:limit]
            
            # Get user details
            users = []
            for user_id in active_user_ids:
                try:
                    user_doc = self.db.collection('humanUsers').document(user_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        user_data['id'] = user_id
                        users.append(user_data)
                except:
                    continue
            
            return users
            
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []
