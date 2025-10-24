import io
import asyncio
import re
import requests
import json
import logging
import random
import base64
import time
import uuid
import os
import subprocess
import sys
import math
import traceback
import hashlib
import threading
from flask import Flask, request, jsonify
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from flask_cors import CORS
from openai import OpenAI
from typing import List, Optional
from firebase_admin import credentials, initialize_app, firestore, messaging
from functools import lru_cache
from datetime import datetime, timezone
from queue import Queue
from ai_engagement_scheduler import AIEngagementScheduler, EngagementAnalytics
from typing import List, Optional

"""
Commands
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi
gcloud run deploy --image gcr.io/inzone-f93e4/inzoneapi --set-env-vars OPENAI_API_KEY='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'

"""

load_dotenv()

OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")
MESHY_API_KEY=os.environ.get("MESH_API_KEY")
ELEVENLABS_API_KEY="sk_a7adae8a80cf5bfe52afd8e5ca8fb1307cd06c0e4d8e2789"

if OPENAI_API_KEY is None:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
# if ELEVENLABS_API_KEY is None:
#         raise ValueError("ELEVENLABS_API_KEY environment variable is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    "Authorization": f"Bearer {MESHY_API_KEY}",
    "Content-Type": "application/json",
}


# Create Flask app
# Initialize Firebase Admin
import os
credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "key.json")
if not os.path.isabs(credential_path):
    # If relative path, make it relative to this script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credential_path = os.path.join(script_dir, credential_path)

cred = credentials.Certificate(credential_path)
default_app = initialize_app(cred)


# Initialize Firestore client
db = firestore.client()
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'INZONE1234'

# Import enhanced AI engagement service
from inzone_ai_engagement import InZoneAIEngagementService

# Import notification services
from notification_service import notification_service
from ai_nudge_scheduler import AINudgeScheduler
from rare_offer_service import rare_offer_service

from media_analysis_service import MediaAnalysisService

# Initialize enhanced AI engagement service
inzone_ai_service = InZoneAIEngagementService(db, client)

# Initialize AI engagement scheduler
ai_engagement_scheduler = AIEngagementScheduler(inzone_ai_service)

# ---------------------------
# Gorse Recommendation System Client
# ---------------------------

class GorseClient:
    """Client for Gorse Recommendation System"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json'
        }
        if self.api_key:
            self.headers['X-API-Key'] = self.api_key
        
        # Enable if URL is set and not localhost
        self.enabled = bool(api_url and api_url != 'http://localhost:8087')
        if self.enabled:
            print(f"✓ Gorse client initialized: {self.api_url}")
            if not api_key:
                print("  ⚠ No API key set (may not be required)")
        else:
            print("⚠ Gorse client disabled (no valid URL or using localhost)")
    
    def get_recommendations(self, user_id: str, limit: int = 20, offset: int = 0) -> List[str]:
        """Get personalized post recommendations for a user"""
        if not self.enabled:
            return []
        
        try:
            # 🎯 REMOVED write-back-type to prevent automatic marking
            # We'll manually mark posts as 'read' only after user actually views them
            response = requests.get(
                f'{self.api_url}/api/recommend/{user_id}',
                headers=self.headers,
                params={
                    'n': limit, 
                    'offset': offset
                    # No write-back to avoid premature marking
                },
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # Gorse returns a list of strings (item IDs directly)
                if isinstance(data, list):
                    if data and isinstance(data[0], str):
                        return data  # List of post IDs
                    elif data and isinstance(data[0], dict):
                        return [item.get('Id', item.get('ItemId', '')) for item in data]
                return []
            else:
                print(f"Gorse API error: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error getting recommendations: {e}")
            return []
    
    def record_interaction(self, user_id: str, post_id: str, feedback_type: str):
        """Record user interaction (read, like, comment, share)"""
        if not self.enabled:
            return
        
        try:
            # Gorse expects an array of feedback items
            feedback_list = [{
                'FeedbackType': feedback_type,
                'UserId': user_id,
                'ItemId': post_id,
                'Timestamp': datetime.now(timezone.utc).isoformat()
            }]
            requests.put(
                f'{self.api_url}/api/feedback',
                headers=self.headers,
                json=feedback_list,
                timeout=5
            )
        except Exception as e:
            print(f"Error recording interaction: {e}")
    
    def get_similar_posts(self, post_id: str, limit: int = 5) -> List[str]:
        """Get similar posts based on a post ID"""
        if not self.enabled:
            return []
        
        try:
            response = requests.get(
                f'{self.api_url}/api/item/{post_id}/neighbors',
                headers=self.headers,
                params={'n': limit},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # Handle list of strings or list of dicts
                if isinstance(data, list):
                    if data and isinstance(data[0], str):
                        return data
                    elif data and isinstance(data[0], dict):
                        return [item.get('Id', item.get('ItemId', '')) for item in data]
                return []
            return []
        except Exception as e:
            print(f"Error getting similar posts: {e}")
            return []
    
    def get_popular_posts(self, limit: int = 10) -> List[str]:
        """Get trending/popular posts"""
        if not self.enabled:
            return []
        
        try:
            response = requests.get(
                f'{self.api_url}/api/popular',
                headers=self.headers,
                params={'n': limit},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                # Handle list of strings or list of dicts
                if isinstance(data, list):
                    if data and isinstance(data[0], str):
                        return data
                    elif data and isinstance(data[0], dict):
                        return [item.get('Id', item.get('ItemId', '')) for item in data]
                return []
            return []
        except Exception as e:
            print(f"Error getting popular posts: {e}")
            return []
    
    def insert_user(self, user_id: str, labels: List[str] = None):
        """Insert or update a user in Gorse"""
        if not self.enabled:
            return False
        
        try:
            user_data = {
                'UserId': user_id,
                'Labels': labels or []
            }
            response = requests.patch(
                f'{self.api_url}/api/user/{user_id}',
                headers=self.headers,
                json=user_data,
                timeout=5
            )
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"Error inserting user to Gorse: {e}")
            return False
    
    def insert_item(self, item_id: str, labels: List[str] = None, comment: str = None, timestamp: str = None):
        """Insert or update an item (post) in Gorse"""
        if not self.enabled:
            return False
        
        try:
            item_data = {
                'ItemId': item_id,
                'Labels': labels or [],
                'Comment': comment or '',
                'Timestamp': timestamp or datetime.now(timezone.utc).isoformat()
            }
            # Use POST to insert new items
            response = requests.post(
                f'{self.api_url}/api/item',
                headers=self.headers,
                json=item_data,
                timeout=5
            )
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"Error inserting item to Gorse: {e}")
            return False
    
    def refresh_user_recommendations(self, user_id: str):
        """Clear cached recommendations for a specific user"""
        if not self.enabled:
            return False
        
        # Actually, there's no direct API to clear cache in Gorse
        # The cache will automatically expire based on cache_expire setting
        # The best we can do is ensure the user data is updated (which we already did)
        # and let Gorse handle the cache expiration naturally
        
        print(f"ℹ️  User {user_id} recommendations will refresh after cache expires (cache_expire in config)")
        print(f"   Note: Gorse doesn't provide an API to manually clear individual user cache")
        print(f"   The updated interests are already in Gorse - fresh recommendations will be generated when cache expires")
        return True
    
    def delete_item(self, item_id: str):
        """Delete an item (post) from Gorse"""
        if not self.enabled:
            return False
        
        try:
            response = requests.delete(
                f'{self.api_url}/api/item/{item_id}',
                headers=self.headers,
                timeout=5
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Error deleting item from Gorse: {e}")
            return False


# Initialize Gorse client
GORSE_API_URL = os.getenv('GORSE_API_URL', 'http://localhost:8087')
GORSE_API_KEY = os.getenv('GORSE_API_KEY', '')
gorse_client = GorseClient(GORSE_API_URL, GORSE_API_KEY)

# ---------------------------
# Helper Functions
# ---------------------------

def get_user_name(user_id):
    """Get user name from humanUsers, popularCharacters, or aiUsers collections"""

    try:
        # First try humanUsers collection
        user_doc = db.collection('humanUsers').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return user_data.get('name') or user_data.get('Name') or user_data.get('username') or user_data.get('user_name') or user_id
        
        # Then try popularCharacters collection
        character_doc = db.collection('popularCharacters').document(user_id).get()
        if character_doc.exists:
            character_data = character_doc.to_dict()
            return character_data.get('name') or character_data.get('Name') or character_data.get('username') or character_data.get('user_name') or user_id
        
        # Finally try aiUsers collection
        ai_user_doc = db.collection('aiUsers').document(user_id).get()
        if ai_user_doc.exists:
            ai_user_data = ai_user_doc.to_dict()
            return ai_user_data.get('name') or ai_user_data.get('Name') or ai_user_data.get('username') or ai_user_data.get('user_name') or user_id
        
        # Return user_id as fallback if not found in any collection
        return user_id
    except Exception as e:
        logger.error(f"Error fetching user name for {user_id}: {e}")
        return user_id  # Return ID as fallback on error

# ---------------------------
# ElevenLabs Voice Service
# ---------------------------

class ElevenLabsVoiceService:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1"
        self.headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        # Default voice settings
        self.default_voice_settings = {
            "stability": 0.71,
            "similarity_boost": 0.5,
            "style": 0.0,
            "use_speaker_boost": True
        }
    
    def get_available_voices(self):
        """Get list of available voices from ElevenLabs"""
        try:
            response = requests.get(
                f"{self.base_url}/voices",
                headers={"xi-api-key": self.api_key}
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get voices: {response.text}")
                return None
        except Exception as ex:
            logger.error(f"Error getting voices: {ex}")
            return None
    
    def assign_voice_to_character(self, character_data):
        """Assign appropriate voice based on character personality using ChatGPT analysis"""
        voices = self.get_available_voices()
        if not voices or 'voices' not in voices:
            return "JBFqnCBsd6RMkjVDRZzb"  # Default voice ID
        
        gender = character_data.get('gender', '').lower()
        personality = character_data.get('personality', '').lower()
        
        try:
            # Create voice options list for ChatGPT
            voice_options = []
            for voice in voices['voices']:
                voice_info = {
                    'name': voice.get('name', ''),
                    'voice_id': voice.get('voice_id', ''),
                    'description': voice.get('description', ''),
                    'category': voice.get('category', '')
                }
                voice_options.append(voice_info)
            
            # Use ChatGPT to match personality with best voice
            prompt = f"""
Given the following AI character details:
- Gender: {gender}
- Personality: {personality}

And these available voice options:
{json.dumps(voice_options, indent=2)}

Please analyze the personality traits and recommend the best voice that would match this character's personality and gender. Consider factors like:
- Voice tone that matches the personality
- Gender appropriateness
- Character traits alignment

Respond with only the voice_id of the best match. If no perfect match, choose the most suitable one.
"""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a voice casting expert. Analyze character personalities and match them with the most suitable voice from the available options."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.3
            )
            
            recommended_voice_id = response.choices[0].message.content.strip()
            
            # Validate the recommended voice_id exists in our options
            valid_voice_ids = [voice.get('voice_id') for voice in voices['voices']]
            if recommended_voice_id in valid_voice_ids:
                return recommended_voice_id
            
        except Exception as ex:
            logger.error(f"Error using ChatGPT for voice assignment: {ex}")
        
        # Fallback to simple gender-based selection if ChatGPT fails
        suitable_voices = []
        for voice in voices['voices']:
            voice_name = voice.get('name', '').lower()
            if gender == 'female' and any(word in voice_name for word in ['female', 'woman', 'girl']):
                suitable_voices.append(voice)
            elif gender == 'male' and any(word in voice_name for word in ['male', 'man', 'boy']):
                suitable_voices.append(voice)
            elif not any(word in voice_name for word in ['male', 'female', 'man', 'woman', 'boy', 'girl']):
                suitable_voices.append(voice)
        
        if suitable_voices:
            selected_voice = random.choice(suitable_voices)
            return selected_voice.get('voice_id', "JBFqnCBsd6RMkjVDRZzb")
        
        return "JBFqnCBsd6RMkjVDRZzb"  # Default fallback
    
    def text_to_speech(self, text, voice_id, character_data=None):
        """Convert text to speech using ElevenLabs API"""
        try:
            # Prepare voice settings based on character
            voice_settings = self.default_voice_settings.copy()
            
            if character_data:
                personality = character_data.get('personality', '').lower()
                # Adjust voice settings based on personality
                if any(word in personality for word in ['energetic', 'excited', 'happy']):
                    voice_settings['stability'] = 0.6
                    voice_settings['similarity_boost'] = 0.7
                elif any(word in personality for word in ['calm', 'serene', 'peaceful']):
                    voice_settings['stability'] = 0.8
                    voice_settings['similarity_boost'] = 0.4
                elif any(word in personality for word in ['dramatic', 'theatrical', 'expressive']):
                    voice_settings['style'] = 0.3
                    voice_settings['similarity_boost'] = 0.8
            
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": voice_settings
            }
            
            response = requests.post(
                f"{self.base_url}/text-to-speech/{voice_id}",
                headers=self.headers,
                json=payload,
                params={"output_format": "mp3_44100_128"}
            )
            
            if response.status_code == 200:
                return response.content  # Audio bytes
            else:
                logger.error(f"TTS failed: {response.text}")
                return None
                
        except Exception as ex:
            logger.error(f"Error in text_to_speech: {ex}")
            return None
    
    def speech_to_text(self, audio_file):
        """Convert speech to text using ElevenLabs API"""
        try:
            files = {
                'file': audio_file,
                'model_id': (None, 'scribe_v1')
            }
            
            headers = {"xi-api-key": self.api_key}
            
            response = requests.post(
                f"{self.base_url}/speech-to-text",
                headers=headers,
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('text', '')
            else:
                logger.error(f"STT failed: {response.text}")
                return None
                
        except Exception as ex:
            logger.error(f"Error in speech_to_text: {ex}")
            return None

# Initialize ElevenLabs service
elevenlabs_service = ElevenLabsVoiceService(ELEVENLABS_API_KEY)

@app.route("/", methods=["GET"])
def test():
    return "Work in Progress!"

@app.route('/get_post/<post_id>', methods=['GET'])
def get_post(post_id):
    try:
        # Fetch the post from Firestore
        post_ref = db.collection('posts').document(post_id)
        post_doc = post_ref.get()

        if post_doc.exists:
            return jsonify(post_doc.to_dict()), 200
        else:
            return jsonify({"error": "Post not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

@app.route('/api/image', methods=['POST'])
def image_generate():
    data = request.get_json()

    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing 'prompt' in request"}), 400

    prompt = data['prompt']

    try:
       
        response = client.images.generate(
            model="dall-e-3",
            prompt=f"${prompt}",
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        time.sleep(5)
        image_response = requests.get(image_url)
        if image_response.status_code != 200:
            return jsonify({"error": "Failed to download image"}), 500

        # Save the image locally
        local_file_path = 'prompt_image.png'
        with open(local_file_path, 'wb') as file:
            file.write(image_response.content)

        # Generate a unique ID for the file
        unique_id = str(uuid.uuid4())
        blob_name = f"3d/{unique_id}.png"

        # Upload the file to Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_file_path)

        # Make the file publicly accessible
        blob.make_public()
        public_url = blob.public_url

        # Clean up the local file
        os.remove(local_file_path)

        return jsonify({"image_url": public_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ------------------------------------------------------------------
# 3D avatar helpers
# ------------------------------------------------------------------
def create_preview_task(prompt: str, seed: int) -> str:
    payload = {
        "mode": "preview",
        "prompt": prompt,
        "art_style": "realistic",
        "should_remesh": True,
        "ai_model": "meshy-5",
        "seed": seed,
        "topology": "triangle",
        "target_polycount": 30000,
    }
    resp = requests.post(
        "https://api.meshy.ai/openapi/v2/text-to-3d",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def create_refine_task(preview_task_id: str) -> str:
    payload = {
        "mode": "refine",
        "preview_task_id": preview_task_id,
        "enable_pbr": False,
    }
    resp = requests.post(
        "https://api.meshy.ai/openapi/v2/text-to-3d",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def poll_task(task_id: str, label: str, retries: int = 60, delay: int = 5) -> dict:
    for _ in range(retries):
        time.sleep(delay)
        resp = requests.get(
            f"https://api.meshy.ai/openapi/v2/text-to-3d/{task_id}",
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "SUCCEEDED":
            return data
        if data.get("status") == "FAILED":
            raise RuntimeError(f"{label} task failed")
    raise TimeoutError(f"{label} task timed out")


# ------------------------------------------------------------------
# 3D avatar endpoint
# ------------------------------------------------------------------
@app.route("/api/generate_3d_avatar", methods=["POST"])
def generate_3d_avatar():
    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt")
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400

    seed = random.randint(0, 2**31 - 1)

    try:
        preview_id = create_preview_task(prompt, seed)
        _ = poll_task(preview_id, "Preview")

        refine_id = create_refine_task(preview_id)
        refine_data = poll_task(refine_id, "Refine")

        return jsonify(
            {
                "model_glb": refine_data["model_urls"]["glb"],
                "model_obj": refine_data["model_urls"]["obj"],
                "texture": refine_data["texture_urls"][0]["base_color"],
                "thumbnail": refine_data.get("thumbnail_url"),
                "seed": seed,
            }
        )
    except TimeoutError as e:
        return jsonify({"error": str(e)}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


##############################################################################################################
# InZone Backend
# - Unknown error: 500
# - Specific error: 400
# - Success: 200
##############################################################################################################

# ---------------------------
# API Controller
# ---------------------------

media_analysis_service = MediaAnalysisService(client)

@app.route('/api/sentiment-analysis', methods=['POST'])
def analyze_sentiment():
    try:
        # Extract JSON content from the request
        content = request.get_json()
        if not content:
            return jsonify({"success": False, "error": "Missing request body", "code": "INVALID_REQUEST"}), 400
        
        # Extract text, images, and videos from request
        text_content = content.get('text', '')
        image_urls = content.get('image_urls', [])
        video_urls = content.get('video_urls', [])
        
        if not text_content and not image_urls and not video_urls:
            return jsonify({"success": False, "error": "Missing content to analyze", "code": "INVALID_REQUEST"}), 400
        
        # Initialize analysis results
        text_analysis = None
        urban_dict_analysis = None
        image_analysis = None
        video_analysis = None
        overall_inappropriate = False
        
        # Analyze text content
        if text_content:
            # Enhanced text analysis prompt
            enhanced_prompt = f'''Analyze the sentiment of the following text with enhanced scrutiny for harmful content. 
            Consider context, implied meanings, and potential for harassment or harm.
            
            Text: "{text_content}"
            
            Provide analysis in this exact JSON format (no additional text, no markdown, just JSON):
            {{
                "PositiveScore": <float 0-1>,
                "NegativeScore": <float 0-1>,
                "NeutralScore": <float 0-1>,
                "OverallSentiment": "<positive/negative/neutral>",
                "Categories": ["<category1>", "<category2>"],
                "Keywords": ["<keyword1>", "<keyword2>"],
                "HarmfulContent": {{
                    "detected": <boolean>,
                    "type": "<harassment/hate_speech/violence/none>",
                    "severity": "<low/medium/high/none>",
                    "reasoning": "<brief explanation>"
                }},
                "ContextualRisk": {{
                    "impliedThreat": <boolean>,
                    "targetedHarassment": <boolean>,
                    "misinformation": <boolean>
                }}
            }}'''
            
            # Call OpenAI API for enhanced sentiment analysis
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an advanced content moderation and sentiment analysis AI. Analyze text for both sentiment and potential harmful content with high accuracy."},
                    {"role": "user", "content": enhanced_prompt}
                ]
            )
            
            # Extract and parse the response
            chat_response = completion.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present (more robust handling)
            import re
            # Remove ```json...``` or ```...``` patterns
            markdown_pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
            match = re.match(markdown_pattern, chat_response, re.DOTALL)
            if match:
                chat_response = match.group(1).strip()
            
            try:
                text_analysis = json.loads(chat_response)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON response from OpenAI: %s", chat_response)
                logger.error("JSON decode error: %s", str(e))
                return jsonify({"success": False, "error": "Invalid response format from OpenAI", "code": "SENTIMENT_FORMAT_ERROR"}), 500
            
            urban_dict_analysis = {"flagged_terms": [], "explanations": [], "has_negative_slang": False}
            
            # Determine if content is inappropriate based on text analysis ONLY
            harmful_content = text_analysis.get("HarmfulContent", {})
            if harmful_content.get("detected", False):
                overall_inappropriate = True
        
        # Analyze images
        if image_urls:
            image_analysis = media_analysis_service.analyze_image_content(image_urls)
            if image_analysis.get("has_inappropriate_content", False):
                overall_inappropriate = True
        
        # Analyze videos
        if video_urls:
            video_analysis = media_analysis_service.analyze_video_content(video_urls)
            if video_analysis.get("has_inappropriate_content", False):
                overall_inappropriate = True
        
        # Validate text analysis format if present
        if text_analysis:
            required_keys = {"PositiveScore", "NegativeScore", "NeutralScore", "OverallSentiment", "Categories", "Keywords"}
            if not all(key in text_analysis for key in required_keys):
                logger.error("Missing keys in OpenAI response: %s", text_analysis)
                return jsonify({"success": False, "error": "Invalid response format from OpenAI", "code": "SENTIMENT_FORMAT_ERROR"}), 500
        
        # Combine text and image sentiment for overall sentiment
        combined_sentiment = None
        if text_analysis and image_analysis:
            # Get text sentiment scores
            text_pos = text_analysis.get("PositiveScore", 0)
            text_neg = text_analysis.get("NegativeScore", 0) 
            text_neu = text_analysis.get("NeutralScore", 0)
            
            # Get image sentiment if available
            image_sentiment_adjustments = {"positive": 0, "negative": 0, "neutral": 0}
            if image_analysis.get("analysis"):
                for img_result in image_analysis["analysis"]:
                    img_sentiment = img_result.get("sentiment", "neutral")
                    img_score = img_result.get("sentiment_score", 0.5)
                    if img_sentiment in image_sentiment_adjustments:
                        image_sentiment_adjustments[img_sentiment] += img_score
            
            # Combine scores (give images 30% weight, text 70% weight)
            final_pos = (text_pos * 0.7) + (image_sentiment_adjustments["positive"] * 0.3)
            final_neg = (text_neg * 0.7) + (image_sentiment_adjustments["negative"] * 0.3)  
            final_neu = (text_neu * 0.7) + (image_sentiment_adjustments["neutral"] * 0.3)
            
            # Determine overall sentiment
            if final_pos > final_neg and final_pos > final_neu:
                combined_sentiment = "positive"
            elif final_neg > final_pos and final_neg > final_neu:
                combined_sentiment = "negative"
            else:
                combined_sentiment = "neutral"
            
            # Update text_analysis with combined scores for frontend
            text_analysis["PositiveScore"] = final_pos
            text_analysis["NegativeScore"] = final_neg
            text_analysis["NeutralScore"] = final_neu
            text_analysis["OverallSentiment"] = combined_sentiment
        
        # Prepare comprehensive response
        response_data = {
            "text_analysis": text_analysis,
            "urban_dictionary_check": urban_dict_analysis,
            "image_analysis": image_analysis,
            "video_analysis": video_analysis,
            "overall_assessment": {
                "inappropriate_content_detected": overall_inappropriate,
                "recommendation": "block" if overall_inappropriate else "allow",
                "confidence_score": 0.95 if overall_inappropriate else 0.85
            }
        }
        
        # For backward compatibility, include the original format
        if text_analysis:
            response_data.update(text_analysis)
        
        # Add debugging output
        logger.info("=== SENTIMENT ANALYSIS RESULT ===")
        logger.info(f"Overall Sentiment: {text_analysis.get('OverallSentiment', 'N/A') if text_analysis else 'N/A'}")
        logger.info(f"Has inappropriate content: {overall_inappropriate}")
        if image_analysis and image_analysis.get('analysis'):
            logger.info(f"Image Analysis: {image_analysis['analysis']}")
        logger.info(f"Overall recommendation: {response_data['overall_assessment']['recommendation']}")
        logger.info("=== END ANALYSIS ===")
        
        return jsonify({"success": True, "data": response_data}), 200
        
    except Exception as ex:
        logger.error("Error analyzing sentiment: %s", ex)
        return jsonify({"success": False, "error": "Failed to analyze sentiment", "code": "SENTIMENT_ERROR"}), 500
        
@app.route('/api/main-ai-chat', methods=['POST'])
def main_ai_chat():
    try:
        message = request.get_json()
        chat_data = {
            "message": message,
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('chats').add(chat_data)

        response = "This is a test AI response"

        return jsonify({"success": True, "data": {"response": response}}), 200
    except Exception as ex:
        logger.error("Error in main AI chat: %s", ex)
        return jsonify({"success": False, "error": "Failed to process chat", "code": "CHAT_ERROR"}), 500

@app.route('/api/add-user', methods=['POST'])
def add_user():
    try:
        data = request.get_json()
        user_data = {
            "name": data.get("Name"),
            "born": data.get("Born"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('humanUsers').add(user_data)
        return jsonify({"success": True, "data": {"userId": doc_ref[1].id}}), 200
    except Exception as ex:
        logger.error("Error adding user: %s", ex)
        return jsonify({"success": False, "error": "Failed to add user", "code": "USER_ADD_ERROR"}), 500

@app.route('/api/get-all-ai-profiles', methods=['POST'])
def get_all_ai_profiles():
    try:
        query = db.collection('ai_characters')
        snapshot = query.stream()
        profiles = [doc.to_dict() for doc in snapshot]

        return jsonify({"success": True, "data": profiles}), 200
    except Exception as ex:
        logger.error("Error getting AI profiles: %s", ex)
        return jsonify({"success": False, "error": "Failed to get AI profiles", "code": "PROFILE_GET_ERROR"}), 500

@app.route('/api/create-ai-profile', methods=['POST'])
def create_ai_profile():
    try:
        data = request.get_json()
        profile_data = {
            "userName": data.get("UserName"),
            "description": data.get("Description"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('ai_characters').add(profile_data)
        return jsonify({"success": True, "data": {"profileId": doc_ref[1].id}}), 200
    except Exception as ex:
        logger.error("Error creating AI profile: %s", ex)
        return jsonify({"success": False, "error": "Failed to create AI profile", "code": "AI_PROFILE_CREATE_ERROR"}), 500

@app.route('/api/get-avatars', methods=['GET'])
def get_avatars():
    try:
        # Retrieve all avatars
        avatars_ref = db.collection('avatars')
        snapshot = avatars_ref.stream()

        # Separate predefined avatars based on the image URL
        predefined_avatars = []
        user_created_avatars = []

        for doc in snapshot:
            avatar = doc.to_dict()
            if "predefined" in avatar.get("imgPath", ""):
                predefined_avatars.append(avatar)
            else:
                user_created_avatars.append(avatar)

        # Combine lists, prioritizing predefined avatars
        prioritized_avatars = predefined_avatars + user_created_avatars

        return jsonify(prioritized_avatars), 200
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 500

# ---------------------------
# User Controller
# ---------------------------

@app.route('/user/create-profile', methods=['POST'])
def create_profile():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

        # Check if email already exists
        email = data.get("Email")
        if email:
            existing_user = db.collection('humanUsers').where("email", "==", email).limit(1).get()
            if existing_user:
                return jsonify({
                    "success": False, 
                    "error": "Email already exists",
                    "code": "DUPLICATE_EMAIL"
                }), 400


        user_data = {
            "name": data.get("Name"),
            "age": data.get("Age"),
            "bio": data.get("Bio"),
            "blockout": [],
            "user_interests": data.get("UserInterests", []),
            "email": email,
            "liked_posts": [],
            "balance": 200,
            "followers": [],
            "following": [],
            "gender": data.get("Gender"),
            "profilePicture": data.get("ProfilePicture"),
            "date_created": firestore.SERVER_TIMESTAMP,
            "uid": data.get("UID"),
            "username": data.get("UserName"),
            "is_influencer": db.collection('influencers').document(uid).get().exists if uid else False
        }

        doc_ref = db.collection('humanUsers').document(data.get("UID")).set(user_data)
        
        # Update Gorse with new user
        try:
            user_interests = data.get("UserInterests", [])
            gorse_client.insert_user(data.get("UID"), labels=user_interests)
            print(f"✓ Synced user {data.get('UID')} to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync user to Gorse: {e}")
     
        response = {
            "success": True,
            "data": {
                "UserId": data.get("UID")
            }
        }
        return jsonify(response), 200
    except Exception as ex:
        logger.error("Error creating user profile: %s", ex)
        response = {
            "success": False,
            "error": {
                "message": "Failed to create user profile",
                "code": "PROFILE_CREATE_ERROR"
            }
        }
        return jsonify(response), 500

@app.route('/user/update-name', methods=['POST'])
def update_name():
    try:
        data = request.get_json()
        user_id = data.get("UID")
        name = data.get("Name")
        
        if not user_id or not name:
            return jsonify({"success": False, "error": "User Id and Name are required"}), 400

        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update({"name": name})
        
        # Sync updated user to Gorse
        try:
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_interests = user_data.get("user_interests", [])
                gorse_client.insert_user(user_id, labels=user_interests)
                print(f"✓ Synced user {user_id} name update to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync user update to Gorse: {e}")
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating name: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/update-username', methods=['POST'])
def update_username():
    try:
        data = request.get_json()
        user_id = data.get("UID")
        username = data.get("Username")
        
        if not user_id or not username:
            return jsonify({"success": False, "error": "User Id and Username are required"}), 400

        # Check if username already exists
        existing_user = db.collection('humanUsers').where("username", "==", username).limit(1).get()
        if existing_user and existing_user[0].id != user_id:
            return jsonify({"success": False, "error": "Username already exists"}), 400

        # Get the old username for reference
        user_doc = db.collection('humanUsers').document(user_id).get()
        old_username = None
        if user_doc.exists:
            old_username = user_doc.to_dict().get('username')

        # Use batch writes for atomic updates across multiple collections
        batch = db.batch()
        
        # Update the main user document
        user_ref = db.collection('humanUsers').document(user_id)
        batch.update(user_ref, {"username": username})
        
        # Update username in humanPosts collection
        posts_query = db.collection('humanPosts').where('user_document_id', '==', user_id)
        posts = posts_query.stream()
        
        updated_posts = 0
        for post in posts:
            post_ref = db.collection('humanPosts').document(post.id)
            # Update both username and user_name fields if they exist
            post_data = post.to_dict()
            update_data = {}
            
            if 'username' in post_data:
                update_data['username'] = username
            if 'user_name' in post_data and post_data.get('user_name') == old_username:
                update_data['user_name'] = username
                
            if update_data:
                batch.update(post_ref, update_data)
                updated_posts += 1
        
        # Update username in postComments collection (in the nested comments array)
        # Note: This is more complex due to the nested structure, so we'll handle it separately
        
        # Update username in conversations collection (participantNames)
        conversations_query = db.collection('conversations')
        conversations = conversations_query.stream()
        
        updated_conversations = 0
        for conversation in conversations:
            conv_data = conversation.to_dict()
            participants = conv_data.get('participants', [])
            participant_names = conv_data.get('participantNames', {})
            
            if user_id in participants and user_id in participant_names:
                conv_ref = db.collection('conversations').document(conversation.id)
                batch.update(conv_ref, {f'participantNames.{user_id}': username})
                updated_conversations += 1
        
        # Update username in any notification collections that might reference the user
        notifications_query = db.collection('notifications').where('userId', '==', user_id)
        notifications = notifications_query.stream()
        
        updated_notifications = 0
        for notification in notifications:
            notif_data = notification.to_dict()
            data_field = notif_data.get('data', {})
            
            # Update any username references in notification data
            update_needed = False
            if data_field.get('senderName') == old_username:
                data_field['senderName'] = username
                update_needed = True
            if data_field.get('username') == old_username:
                data_field['username'] = username
                update_needed = True
            
            if update_needed:
                notif_ref = db.collection('notifications').document(notification.id)
                batch.update(notif_ref, {'data': data_field})
                updated_notifications += 1
        
        # Commit all updates
        batch.commit()
        
        # Handle postComments separately due to nested structure
        updated_comments = 0
        try:
            post_comments_query = db.collection('postComments')
            post_comments = post_comments_query.stream()
            
            for post_comment_doc in post_comments:
                post_comment_data = post_comment_doc.to_dict()
                comments = post_comment_data.get('comments', [])
                
                updated_this_post = False
                for comment in comments:
                    if comment.get('userId') == user_id and comment.get('author') == old_username:
                        comment['author'] = username
                        updated_this_post = True
                        updated_comments += 1
                
                if updated_this_post:
                    # Update the entire comments array
                    db.collection('postComments').document(post_comment_doc.id).update({'comments': comments})
                    
        except Exception as comment_error:
            logger.error(f"Error updating comments: {comment_error}")
            # Don't fail the entire operation for comments

        # Update username in other users' followers and following arrays
        updated_followers_arrays = 0
        updated_following_arrays = 0
        
        try:
            # Get all human users to check their followers/following arrays
            all_users_query = db.collection('humanUsers')
            all_users = all_users_query.stream()
            
            for other_user_doc in all_users:
                if other_user_doc.id == user_id:
                    continue  # Skip the user whose username we're updating
                
                other_user_data = other_user_doc.to_dict()
                other_user_ref = db.collection('humanUsers').document(other_user_doc.id)
                user_updated = False
                
                # Check and update followers array
                followers = other_user_data.get('followers', [])
                updated_followers = []
                followers_changed = False
                
                for follower in followers:
                    if isinstance(follower, dict):
                        # New format: {"id": user_id, "username": username, "type": "human"}
                        if follower.get('id') == user_id:
                            follower['username'] = username
                            followers_changed = True
                        updated_followers.append(follower)
                    elif isinstance(follower, str) and follower == user_id:
                        # Legacy format: just user ID - convert to new format with updated username
                        updated_followers.append({
                            "id": user_id,
                            "username": username,
                            "type": "human"
                        })
                        followers_changed = True
                    else:
                        updated_followers.append(follower)
                
                if followers_changed:
                    other_user_ref.update({'followers': updated_followers})
                    updated_followers_arrays += 1
                    user_updated = True
                
                # Check and update following array
                following = other_user_data.get('following', [])
                updated_following = []
                following_changed = False
                
                for followed in following:
                    if isinstance(followed, dict):
                        # New format: {"id": user_id, "username": username, "type": "human"}
                        if followed.get('id') == user_id:
                            followed['username'] = username
                            following_changed = True
                        updated_following.append(followed)
                    elif isinstance(followed, str) and followed == user_id:
                        # Legacy format: just user ID - convert to new format with updated username
                        updated_following.append({
                            "id": user_id,
                            "username": username,
                            "type": "human"
                        })
                        following_changed = True
                    else:
                        updated_following.append(followed)
                
                if following_changed:
                    other_user_ref.update({'following': updated_following})
                    updated_following_arrays += 1
                    user_updated = True
                
        except Exception as followers_following_error:
            logger.error(f"Error updating followers/following arrays: {followers_following_error}")
        
        logger.info(f"Username updated from '{old_username}' to '{username}' for user {user_id}")
        logger.info(f"Updated {updated_posts} posts, {updated_conversations} conversations, {updated_notifications} notifications, {updated_comments} comments, {updated_followers_arrays} followers arrays, {updated_following_arrays} following arrays")
        
        return jsonify({
            "success": True, 
            "message": f"Username updated successfully across all collections",
            "stats": {
                "posts_updated": updated_posts,
                "conversations_updated": updated_conversations, 
                "notifications_updated": updated_notifications,
                "comments_updated": updated_comments,
                "followers_arrays_updated": updated_followers_arrays,
                "following_arrays_updated": updated_following_arrays
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error updating username: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500
    finally:
        # Sync updated user to Gorse
        try:
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_interests = user_data.get("user_interests", [])
                gorse_client.insert_user(user_id, labels=user_interests)
                print(f"✓ Synced user {user_id} username update to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync user update to Gorse: {e}")

@app.route('/user/update-profile', methods=['POST'])
def update_profile():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        print(f"📝 Update profile request for user: {user_id}")
        print(f"   Data: {data}")
        
        update_data = {
            "name": data.get("Name"),
            "username": data.get("Username"),
            "profilePicture": data.get("ProfilePicture"),
            "bio": data.get("Bio"),
        }

        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update(update_data)
        print(f"✓ Updated profile in Firestore for user {user_id}")
        
        # Sync updated user to Gorse
        try:
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_interests = user_data.get("user_interests", [])
                gorse_client.insert_user(user_id, labels=user_interests)
                print(f"✓ Synced user {user_id} profile update to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync user update to Gorse: {e}")
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating profile: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500
        
@app.route('/user/update-profile-picture', methods=['POST'])
def update_profile_picture():
    try:
        data = request.get_json()
        user_id = data.get("UID")
        profile_picture = data.get("ProfilePicture")
        
        if not user_id or not profile_picture:
            return jsonify({"success": False, "error": "User Id and ProfilePicture are required"}), 400

        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update({"profilePicture": profile_picture})
        
        # Sync updated user to Gorse
        try:
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_interests = user_data.get("user_interests", [])
                gorse_client.insert_user(user_id, labels=user_interests)
                print(f"✓ Synced user {user_id} profile picture update to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync user update to Gorse: {e}")
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating profile picture: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/update-bio', methods=['POST'])
def update_bio():
    try:
        data = request.get_json()
        user_id = data.get("UID")
        bio = data.get("Bio")
        
        if not user_id or not bio:
            return jsonify({"success": False, "error": "User Id and Bio are required"}), 400

        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update({"bio": bio})
        
        # Sync updated user to Gorse
        try:
            user_doc = db.collection('humanUsers').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_interests = user_data.get("user_interests", [])
                gorse_client.insert_user(user_id, labels=user_interests)
                print(f"✓ Synced user {user_id} bio update to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync user update to Gorse: {e}")
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating bio: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/update-interests', methods=['POST'])
def update_interests():
    try:
        data = request.get_json()
        user_id = data.get("UID")
        interests = data.get("Interests")
        
        print(f"📝 Update interests request for user: {user_id}")
        print(f"   New interests: {interests}")
        
        if not user_id or interests is None:
            return jsonify({"success": False, "error": "User Id and Interests are required"}), 400

        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update({"user_interests": interests})
        print(f"✓ Updated interests in Firestore for user {user_id}")
        
        # Sync updated user interests to Gorse - THIS IS THE MOST IMPORTANT SYNC!
        try:
            gorse_client.insert_user(user_id, labels=interests)
            print(f"✓ Synced user {user_id} interests to Gorse with {len(interests)} labels")
            
            # Note about cache refresh
            gorse_client.refresh_user_recommendations(user_id)
        except Exception as e:
            print(f"⚠ Failed to sync user interests to Gorse: {e}")
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating interests: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/get-profile', methods=['GET'])
def get_profile():
    try:
        uid = request.args.get('uid')
        if not uid:
            return jsonify({"success": False, "error": "UID is required"}), 400

        user_doc = db.collection('humanUsers').document(uid).get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"success": True, "data": user_data}), 200
    except Exception as ex:
        logger.error("Error retrieving profile: %s", ex)
        return jsonify({"success": False, "error": "Failed to retrieve profile", "code": "PROFILE_RETRIEVE_ERROR"}), 500

@app.route('/user/follow', methods=['POST'])
def follow():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to follow)
        follower_type = data.get("FollowerType", "human")  # "human" or "ai"
        follower_username = data.get("FollowerUserName")
        following_type = data.get("FollowingType", "human")  # "human" or "ai"
        following_username = data.get("FollowingUserName")

        # Determine the correct collections based on user types
        follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
        following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'

        # For AI users, the document ID is the username
        follower_doc_id = follower_id
        following_doc_id = following_id

        follower_ref = db.collection(follower_collection).document(follower_doc_id)
        following_ref = db.collection(following_collection).document(following_doc_id)

        follower_doc = follower_ref.get()
        following_doc = following_ref.get()

        if not follower_doc.exists or not following_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Update the follower's following list
        follower_data = follower_doc.to_dict()
        following_entry = {
            "id": following_id,
            "username": following_username,
            "type": following_type
        }
        
        # Check if already following
        current_following = follower_data.get("following", [])
        already_following = False
        for entry in current_following:
            if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                already_following = True
                break
            elif entry == following_id:  # Handle legacy format
                already_following = True
                break
                
        if not already_following:
            # Convert any legacy format to new format
            new_following = []
            for entry in current_following:
                if isinstance(entry, str):
                    new_following.append({"id": entry, "username": following_username, "type": "human" if follower_collection == "humanUsers" else "ai"})
                else:
                    new_following.append(entry)
            
            new_following.append(following_entry)
            follower_ref.update({
                "following": new_following,
                "following_count": firestore.Increment(1) if follower_collection == 'aiUsers' else len(new_following)
            })

        # Update the following user's followers list
        following_data = following_doc.to_dict()
        follower_entry = {
            "id": follower_id,
            "username": follower_username,
            "type": follower_type
        }
        
        # Check if already in followers
        current_followers = following_data.get("followers", [])
        already_follower = False
        for entry in current_followers:
            if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                already_follower = True
                break
            elif entry == follower_id:  # Handle legacy format
                already_follower = True
                break
                
        if not already_follower:
            # Convert any legacy format to new format
            new_followers = []
            for entry in current_followers:
                if isinstance(entry, str):
                    new_followers.append({"id": entry, "type": "human" if following_collection == "humanUsers" else "ai"})
                else:
                    new_followers.append(entry)
            
            new_followers.append(follower_entry)
            following_ref.update({
                "followers": new_followers,
                "followers_count": firestore.Increment(1) if following_collection == 'aiUsers' else len(new_followers)
            })
            
            # Create notification for the user being followed (only for human users)
            if following_type == "human":
                try:
                    # Get the actual follower name from the database if not provided
                    actual_follower_name = follower_username
                    if not actual_follower_name or actual_follower_name == 'None':
                        actual_follower_name = get_user_name(follower_id)
                    
                    notification_data = {
                        'userId': following_id,
                        'type': 'follow',
                        'title': 'New Follower',
                        'body': f'{actual_follower_name} started following you',
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'followerId': follower_id,
                            'followerUsername': actual_follower_name,
                            'followerType': follower_type
                        },
                        # deeplink removed per repository-wide deprecation of in-app deeplinks
                    }
                    
                    db.collection('notifications').add(notification_data)
                    logger.info(f"Follow notification created for user {following_id}")
                    
                    # Also send push notification
                    try:
                        # Get followed user's FCM tokens
                        user_doc = db.collection('humanUsers').document(following_id).get()
                        if user_doc.exists:
                            user_data = user_doc.to_dict()
                            user_tokens = user_data.get('fcmTokens', [])
                            
                            if user_tokens:
                                # Send FCM notifications to all user's devices
                                for token in user_tokens:
                                    try:
                                        message = messaging.Message(
                                            notification=messaging.Notification(
                                                title='New Follower',
                                                body=f'{actual_follower_name} started following you'
                                            ),
                                            data={
                                                'type': 'user_follow',
                                                'followerId': follower_id,
                                                'followerUsername': actual_follower_name,
                                                'action': 'navigate_to_profile',
                                                'route': f'/profile/{follower_id}',
                                            },
                                            token=token
                                        )
                                        
                                        response = messaging.send(message)
                                        logger.info(f"Follow push notification sent to token {token[:20]}...")
                                        
                                    except Exception as token_error:
                                        logger.error(f"Failed to send follow push notification to token {token[:20]}...: {token_error}")
                            else:
                                logger.info(f"No FCM tokens found for followed user {following_id}")
                        else:
                            logger.warning(f"Followed user {following_id} not found in humanUsers collection")
                            
                    except Exception as push_error:
                        logger.error(f"Error sending follow push notification: {push_error}")
                    
                except Exception as e:
                    logger.error(f"Error creating follow notification: {e}")

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error adding follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/unfollow', methods=['POST'])
def unfollow():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to follow)
        follower_type = data.get("FollowerType", "human")  # "human" or "ai"
        follower_username = data.get("FollowerUserName")
        following_type = data.get("FollowingType", "human")  # "human" or "ai"
        follower_username = data.get("FollowingUserName")

        # Determine the correct collections based on user types
        follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
        following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'

        # For AI users, the document ID is the username
        follower_doc_id = follower_id
        following_doc_id = following_id

        follower_ref = db.collection(follower_collection).document(follower_doc_id)
        following_ref = db.collection(following_collection).document(following_doc_id)

        follower_doc = follower_ref.get()
        following_doc = following_ref.get()

        if not follower_doc.exists or not following_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Update the follower's following list
        follower_data = follower_doc.to_dict()
        current_following = follower_data.get("following", [])
        new_following = []
        removed = False
        
        for entry in current_following:
            if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                removed = True
                continue
            elif entry == following_id:  # Handle legacy format
                removed = True
                continue
            new_following.append(entry)
            
        if removed:
            follower_ref.update({
                "following": new_following,
                "following_count": firestore.Increment(-1) if follower_collection == 'aiUsers' else len(new_following)
            })

        # Update the following user's followers list
        following_data = following_doc.to_dict()
        current_followers = following_data.get("followers", [])
        new_followers = []
        removed = False
        
        for entry in current_followers:
            if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                removed = True
                continue
            elif entry == follower_id:  # Handle legacy format
                removed = True
                continue
            new_followers.append(entry)
            
        if removed:
            following_ref.update({
                "followers": new_followers,
                "followers_count": firestore.Increment(-1) if following_collection == 'aiUsers' else len(new_followers)
            })

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/remove-from-following', methods=['POST'])
def remove_from_following():
    try:
        data = request.get_json()
        user_id = data.get("UserId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to remove from A's following list)
        user_type = data.get("UserType", "human")  # "human" or "ai"
        following_type = data.get("FollowingType", "human")  # "human" or "ai"

        logger.info(f"User {user_id} ({user_type}) is managing their following list by removing {following_id} ({following_type}).")

        # Determine the correct collections based on user types
        user_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'
        
        # For AI users, the document ID is the username
        user_doc_id = user_id
        following_doc_id = following_id

        user_ref = db.collection(user_collection).document(user_doc_id)
        following_ref = db.collection(following_collection).document(following_doc_id)
        
        # Get current following list
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404
            
        user_data = user_doc.to_dict()
        current_following = user_data.get("following", [])
        new_following = []
        removed = False
        
        for entry in current_following:
            if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                removed = True
                continue
            elif entry == following_id:  # Handle legacy format
                removed = True
                continue
            new_following.append(entry)
            
        if removed:
            user_ref.update({
                "following": new_following,
                "following_count": firestore.Increment(-1) if user_collection == 'aiUsers' else len(new_following)
            })
            
            # Also update the followers list of the followed user
            following_doc = following_ref.get()
            if following_doc.exists:
                following_data = following_doc.to_dict()
                current_followers = following_data.get("followers", [])
                new_followers = []
                
                for entry in current_followers:
                    if isinstance(entry, dict) and entry.get("id") == user_id and entry.get("type") == user_type:
                        continue
                    elif entry == user_id:  # Handle legacy format
                        continue
                    new_followers.append(entry)
                    
                following_ref.update({
                    "followers": new_followers,
                    "followers_count": firestore.Increment(-1) if following_collection == 'aiUsers' else len(new_followers)
                })
        
        return jsonify({"success": True, "message": "User successfully removed from your following list."}), 200
    except Exception as ex:
        logger.error("Error removing from following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/remove-from-followers', methods=['POST'])
def remove_from_followers():
    try:
        data = request.get_json()
        user_id = data.get("UserId")  # A (authenticated user)
        follower_id = data.get("FollowerId")  # B (user to remove as follower)
        user_type = data.get("UserType", "human")  # "human" or "ai"
        follower_type = data.get("FollowerType", "human")  # "human" or "ai"

        logger.info(f"User {user_id} ({user_type}) is removing follower {follower_id} ({follower_type}).")

        # Determine the correct collections based on user types
        user_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
        
        # For AI users, the document ID is the username
        user_doc_id = user_id
        follower_doc_id = follower_id

        user_ref = db.collection(user_collection).document(user_doc_id)
        follower_ref = db.collection(follower_collection).document(follower_doc_id)
        
        # Get current followers list
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404
            
        user_data = user_doc.to_dict()
        current_followers = user_data.get("followers", [])
        new_followers = []
        removed = False
        
        for entry in current_followers:
            if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                removed = True
                continue
            elif entry == follower_id:  # Handle legacy format
                removed = True
                continue
            new_followers.append(entry)
            
        if removed:
            user_ref.update({
                "followers": new_followers,
                "followers_count": firestore.Increment(-1) if user_collection == 'aiUsers' else len(new_followers)
            })
            
            # Also update the following list of the follower
            follower_doc = follower_ref.get()
            if follower_doc.exists:
                follower_data = follower_doc.to_dict()
                current_following = follower_data.get("following", [])
                new_following = []
                
                for entry in current_following:
                    if isinstance(entry, dict) and entry.get("id") == user_id and entry.get("type") == user_type:
                        continue
                    elif entry == user_id:  # Handle legacy format
                        continue
                    new_following.append(entry)
                    
                follower_ref.update({
                    "following": new_following,
                    "following_count": firestore.Increment(-1) if follower_collection == 'aiUsers' else len(new_following)
                })
        
        return jsonify({"success": True, "message": "User successfully removed from your followers list."}), 200
    except Exception as ex:
        logger.error("Error removing from followers: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@app.route('/feedback', methods=['POST'])
def send_feedback():
    try:
        data = request.get_json()
        email = data.get("email")
        feedback_text = data.get("Feedback")

        feedback_data = {
            "email": email,
            "feedback": feedback_text,
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        db.collection('feedbacks').add(feedback_data)

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error submitting feedback: %s", ex)
        return jsonify({"success": False, "error": "Failed to submit feedback", "code": "FEEDBACK_ERROR"}), 500

@app.route('/user/like-post', methods=['POST'])
def like_post():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        post_id = data.get("PostId")

        # Get post details to find the author
        post_doc = db.collection('humanPosts').document(post_id).get()
        if not post_doc.exists:
            return jsonify({"success": False, "error": "Post not found"}), 404
        
        post_data = post_doc.to_dict()
        post_author_id = post_data.get('author_id')

        like_data = {
            "user_id": user_id,
            "post_id": post_id,
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        # Increment the like count in the posts collection
        post_ref = db.collection('humanPosts').document(post_id)
        post_ref.update({
            "likes": firestore.Increment(1)
        })

        # Update the liked_posts field in humanUsers collection
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.update({
            "liked_posts": firestore.ArrayUnion([post_id])
        })

        # Trigger engagement notification if post author is different
        # if post_author_id and post_author_id != user_id:

        # Build like entry (id, username, type)
        try:
            user_doc = user_ref.get()
            username = ''
            if user_doc.exists:
                username = user_doc.to_dict().get('username', '') or user_doc.to_dict().get('name', '')
        except Exception:
            username = ''

        like_entry = {
            'id': user_id,
            'username': username,
            'type': 'human'
        }

        # Use transaction to add likedBy entry only if not already present
        did_add_like = False
        try:
            def _add_like_transaction(transaction, ref, entry, uid):
                snap = ref.get(transaction=transaction)
                if not snap.exists:
                    transaction.set(ref, {'likedBy': [entry]}, merge=True)
                    return True
                data = snap.to_dict() or {}
                liked_by = list(data.get('likedBy', []))
                exists = any((isinstance(e, dict) and e.get('id') == uid) for e in liked_by)
                if not exists:
                    liked_by.append(entry)
                    transaction.update(ref, {'likedBy': liked_by})
                    return True
                return False

            transaction = db.transaction()
            did_add_like = _add_like_transaction(transaction, post_ref, like_entry, user_id)
        except Exception as e:
            # Fall back: try a simple update with arrayUnion (best-effort)
            try:
                post_ref.update({'likedBy': firestore.ArrayUnion([like_entry])})
                did_add_like = True
            except Exception:
                logger.error(f"Error updating likedBy for post {post_id}: {e}")

        # Record interaction in Gorse
        if did_add_like:
            try:
                gorse_client.record_interaction(user_id, post_id, 'like')
                print(f"💚 GORSE SYNC: Recorded like - user={user_id[:15]}..., post={post_id[:15]}...")
            except Exception as e:
                print(f"⚠️  Failed to record like in Gorse: {e}")
        
        # Trigger engagement notification if post author is different and like was actually added
        if did_add_like and post_author_id and post_author_id != user_id:
            try:
                import requests
                notification_data = {
                    'postId': post_id,
                    'type': 'like',
                    'userId': user_id,
                    'postAuthorId': post_author_id,
                    'timestamp': datetime.utcnow().isoformat()
                }
                requests.post('https://inzoneapi-912424781531.us-central1.run.app/api/notifications/events/post-engagement', json=notification_data)
            except Exception as notif_error:
                logger.error(f"Error sending like notification: {notif_error}")

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error liking post: %s", ex)
        return jsonify({"success": False, "error": "Failed to like post", "code": "LIKE_POST_ERROR"}), 500

@app.route('/user/unlike-post', methods=['POST'])
def unlike_post():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        post_id = data.get("PostId")

        # Query to find the like relationship
        query = db.collection('postLikes').where('user_id', '==', user_id).where('post_id', '==', post_id)
        snapshot = query.stream()

        # Remove the like relationship
        for doc in snapshot:
            doc.reference.delete()

        # Decrement the like count in the posts collection
        post_ref = db.collection('humanPosts').document(post_id)
        try:
            post_ref.update({
                "likes": firestore.Increment(-1)
            })
        except Exception:
            pass

        # Update the liked_posts field in humanUsers collection
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.update({
            "liked_posts": firestore.ArrayRemove([post_id])
        })

        # Remove from post's likedBy array (match by id)
        try:
            snap = post_ref.get()
            if snap.exists:
                data = snap.to_dict() or {}
                liked_by = list(data.get('likedBy', []))
                updated = [e for e in liked_by if not (isinstance(e, dict) and e.get('id') == user_id)]
                post_ref.update({'likedBy': updated})
        except Exception as e:
            logger.error(f"Error removing likedBy entry for post {post_id}: {e}")

        return jsonify({"success": True, "message": "Post unliked successfully."}), 200
    except Exception as ex:
        logger.error("Error unliking post: %s", ex)
        return jsonify({"success": False, "error": "Failed to unlike post", "code": "UNLIKE_POST_ERROR"}), 500

@app.route('/user/get-liked-posts', methods=['POST'])
def get_liked_posts():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        # Retrieve the liked posts from the user's profile
        user_ref = db.collection('humanUsers').document(user_id).get()
        if user_ref.exists:
            liked_posts = user_ref.to_dict().get("liked_posts", [])
        else:
            liked_posts = []

        # Fetch the post details for each liked post ID
        liked_posts_details = []
        for post_id in liked_posts:
            post_ref = db.collection('humanPosts').document(post_id).get()
            if post_ref.exists:
                liked_posts_details.append(post_ref.to_dict())

        return jsonify({"success": True, "liked_posts": liked_posts_details}), 200
    except Exception as ex:
        logger.error("Error retrieving liked posts: %s", ex)
        return jsonify({"success": False, "error": "Failed to retrieve liked posts", "code": "GET_LIKED_POSTS_ERROR"}), 500

@app.route('/user/generate-referral-code', methods=['POST'])
def generate_referral_code():
    try:
        data = request.get_json()
        user_id = data.get("UserDocumentId")
        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        referral_code = f"INZONE-{uuid.uuid4().hex[:6].upper()}"

        # Update user profile with referral code
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.update({
            "referral_code": referral_code,
            "referral_count": 0,
            "total_referral_earnings": 0
        })

        return jsonify({
            "success": True,
            "data": {
                "referral_code": referral_code,
                "referral_link": f"https://inzone.ai/referral?code={referral_code}"
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/user/apply-referral', methods=['POST'])
def apply_referral():
    try:
        data = request.get_json()
        referral_code = data.get("ReferralCode")
        new_user_id = data.get("UserDocumentId")

        if not referral_code or not new_user_id:
            return jsonify({"success": False, "error": "Referral code and user ID are required"}), 400

        # Find referrer by referral code
        referrer_query = db.collection('humanUsers').where("referral_code", "==", referral_code).limit(1).get()
        if not referrer_query:
            return jsonify({"success": False, "error": "Invalid referral code"}), 404

        referrer_doc = referrer_query[0]
        referrer_id = referrer_doc.id

        # Check if user has already used a referral code
        new_user_ref = db.collection('humanUsers').document(new_user_id)
        new_user_doc = new_user_ref.get()
        if new_user_doc.exists and new_user_doc.to_dict().get("used_referral_code"):
            return jsonify({"success": False, "error": "User has already used a referral code"}), 400

        # Create referral record
        referral_data = {
            "referrer_id": referrer_id,
            "referee_id": new_user_id,
            "referral_code": referral_code,
            "status": "completed",
            "date_created": firestore.SERVER_TIMESTAMP,
            "rewards_granted": False
        }
        db.collection('referrals').add(referral_data)

        # Update new user's profile
        new_user_ref.update({
            "used_referral_code": referral_code,
            "referrer_id": referrer_id
        })

        # Update referrer's stats
        db.collection('humanUsers').document(referrer_id).update({
            "referral_count": firestore.Increment(1)
        })

        # Grant InCash rewards
        grant_referral_rewards(referrer_id, new_user_id)

        return jsonify({"success": True, "message": "Referral applied successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def grant_referral_rewards(referrer_id, referee_id):
    """Grant InCash rewards to both referrer and referee"""
    try:
        referrer_reward = 1500  # 10$ worth of InCash
        referee_reward = 1500   # 10$ worth of InCash

        # Grant reward to referrer
        db.collection('humanUsers').document(referrer_id).update({
            "balance": firestore.Increment(referrer_reward),
            "total_referral_earnings": firestore.Increment(referrer_reward)
        })

        # Grant reward to new user
        db.collection('humanUsers').document(referee_id).update({
            "balance": firestore.Increment(referee_reward)
        })

        # Record rewards
        reward_data = {
            "referrer_id": referrer_id,
            "referee_id": referee_id,
            "referrer_reward": referrer_reward,
            "referee_reward": referee_reward,
            "date_granted": firestore.SERVER_TIMESTAMP
        }
        db.collection('referral_rewards').add(reward_data)
    except Exception as e:
        logger.error(f"Error granting referral rewards: {e}")
        raise e

@app.route('/user/referral-stats', methods=['GET'])
def get_referral_stats():
    try:
        user_id = request.args.get('UserDocumentId')
        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        user_doc = db.collection('humanUsers').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()

        # Get referral history
        referrals = db.collection('referrals').where("referrer_id", "==", user_id).get()
        referral_history = [{
            "referee_id": ref.get("referee_id"),
            "date": ref.get("date_created"),
            "status": ref.get("status")
        } for ref in referrals]

        return jsonify({
            "success": True,
            "data": {
                "referral_code": user_data.get("referral_code"),
                "referral_link": f"https://inzone.ai/referral?code={user_data.get('referral_code')}",
                "referral_count": user_data.get("referral_count", 0),
                "total_earnings": user_data.get("total_referral_earnings", 0),
                "referral_history": referral_history
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ---------------------------
# Tipping System Endpoints
# ---------------------------

@app.route('/user/tip/send', methods=['POST'])
def send_tip():
    """
    Send a tip from one user to another
    Request body: {
        "sender_id": "user123",
        "recipient_handle": "@dana.ward",  # or recipient_id
        "amount": 2500,
    }
    """
    try:
        data = request.get_json()
        required_fields = ['sender_id', 'recipient_handle', 'amount']
        
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400
        
        amount = int(data['amount'])
        if amount <= 0:
            return jsonify({"error": "Tip amount must be positive"}), 400
        
        # Get sender's current balance from humanUsers collection
        sender_ref = db.collection('humanUsers').document(data['sender_id'])
        sender_doc = sender_ref.get()
        
        if not sender_doc.exists:
            return jsonify({"error": "Sender not found"}), 404
            
        sender_data = sender_doc.to_dict()
        current_balance = sender_data.get('balance', 200)
        
        if current_balance < amount:
            return jsonify({"error": "Insufficient balance"}), 400
        
        # Find recipient by handle (remove @ if present)
        recipient_handle = data['recipient_handle'].lstrip('@')
        recipient_query = db.collection('humanUsers').where('username', '==', recipient_handle).limit(1).stream()
        recipient_doc = next(recipient_query, None)
        
        if not recipient_doc:
            return jsonify({"error": "Recipient not found"}), 404
            
        # Generate a unique tip ID
        tip_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)
        
        # Create tip data
        tip_data = {
            'id': tip_id,
            'sender_id': data['sender_id'],
            'recipient_id': recipient_doc.id,
            'amount': amount,
            'status': 'completed',
            'createdAt': timestamp
        }
        
        # Start transaction
        transaction = db.transaction()
        
        # Update sender's balance and add to sent tips
        transaction.update(sender_ref, {
            'balance': firestore.Increment(-amount),
            'tips_sent': firestore.ArrayUnion([tip_data])
        })
        
        # Update recipient's received tips
        recipient_ref = db.collection('humanUsers').document(recipient_doc.id)
        transaction.update(recipient_ref, {
            'balance': firestore.Increment(amount),
            'tips_received': firestore.ArrayUnion([tip_data])
        })
        
        # Commit transaction
        transaction.commit()
        
        return jsonify({
            "message": "Tip sent successfully",
            "new_balance": current_balance - amount,
            "tip_id": tip_id
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for Cloud Run warm-up.
    Returns a simple JSON response to confirm the service is running.
    """
    return jsonify({
        'status': 'healthy',
    }), 200

@app.route('/user/tip/transactions/<user_id>', methods=['GET'])
def get_tip_transactions(user_id):
    """Get user's tipping history"""
    try:
        # Get user document from humanUsers
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"error": "User not found"}), 404
            
        user_data = user_doc.to_dict()
        
        # Get sent and received tips
        sent_tips = user_data.get('tips_sent', [])
        received_tips = user_data.get('tips_received', [])
        
        # Process sent tips
        for tip in sent_tips:
            tip['type'] = 'sent'
            
        # Process received tips
        for tip in received_tips:
            tip['type'] = 'received'
        
        # Combine and sort all transactions by timestamp (newest first)
        all_transactions = sent_tips + received_tips
        all_transactions.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        
        return jsonify({
            "transactions": all_transactions
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------
# Monetization System Endpoints
# ---------------------------
@app.errorhandler(Exception)
def _json_errors(e):
    app.logger.exception("[unhandled] %s", e)
    return jsonify({"success": False, "error": "Internal error"}), 500


@app.route('/wallet/balance', methods=['GET'])
def get_balance():
    try:
        user_id = request.args.get('UserDocumentId')
        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()
        balance = user_data.get('balance')

        # If balance field does not exist, set it to 0 in Firestore
        if balance is None:
            user_ref.update({'balance': 200})
            balance = 200

        return jsonify({
            "success": True,
            "data": {
                "balance": balance,
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/wallet/purchase-incash", methods=["POST"])
def purchase_incash():
    try:
        data = request.get_json()
        app.logger.info(f"Purchase request received: {data}")
        user_id = data.get("UserDocumentId")
        package_id = data.get("PackageId")
        platform = data.get("Platform")  # "ios" or "android"
        receipt_data = data.get("ReceiptData")

        if not all([user_id, package_id, platform, receipt_data]):
            app.logger.error(f"Missing required fields - user_id: {user_id}, package_id: {package_id}, platform: {platform}, receipt_data: {'***' if receipt_data else None}")
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        packages = {
            # iOS packages
            "InCashGold": 2500,  # Monthly subscription
            "InCashElite2025": 1500,  # One-time purchase
            "InCashAdvanced2025": 500,
            "InCashBasic2025": 100,
            # Android packages
            "2025incashgold": 2500,  # Monthly subscription
            "2025incashelite": 1500,  # One-time purchase
            "2025incashadvanced": 500,
            "2025incashbasic": 100,
        }
        if package_id not in packages:
            return jsonify({"success": False, "error": "Invalid package"}), 400

        user_ref = db.collection("humanUsers").document(user_id)
        user_doc = user_ref.get()

        if not getattr(user_snap, "exists", False):
            return jsonify({"success": False, "error": "User not found"}), 404

        # Get current balance
        user_data = user_doc.to_dict()
        current_balance = user_data.get("balance", 200)

        # Get the amount from the packages dictionary
        amount = packages[package_id]

        # Update balance
        new_balance = current_balance + amount

        # Record purchase history
        purchase_history = user_data.get("purchaseHistory", [])
        purchase_history.append(
            {
                "packageId": package_id,
                "platform": platform,
                "amount": amount,
                "date": datetime.now().isoformat(),
                "receiptData": receipt_data,
            }
        )

        # Check if this is a subscription purchase
        is_subscription = package_id in ["InCashGold", "2025incashgold"]

        # If it's a subscription, update subscription status
        if is_subscription:
            subscription_data = {
                "isSubscribed": True,
                "subscriptionType": "gold",
                "subscriptionId": package_id,
                "startDate": datetime.now().isoformat(),
                "nextRenewalDate": (datetime.now() + timedelta(days=30)).isoformat(),
            }
            user_ref.update(
                {
                    "balance": new_balance,
                    "purchaseHistory": purchase_history,
                    "subscription": subscription_data,
                }
            )
        else:
            # For one-time purchases
            user_ref.update(
                {"balance": new_balance, "purchaseHistory": purchase_history}
            )

        return jsonify(
            {
                "success": True,
                "data": {
                    "balance": new_balance,
                    "packageId": package_id,
                    "amountAdded": amount,
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def verify_ios_subscription(receipt_data, user_id):
    try:
        function_path = functions_client.function_path('inzone-project', 'us-central1', 'verifyIosSubscription')
        
        request_data = {
            'receiptData': receipt_data,
            'userId': user_id
        }
        
        response = functions_client.call_function(
            name=function_path,
            data=json.dumps(request_data).encode()
        )
        
        result = json.loads(response.result)
        
        if result.get('success'):
            subscription_info = result.get('data', {})
            return {
                'is_valid': True,
                'expiry_date': subscription_info.get('expiryDate'),
                'product_id': subscription_info.get('productId'),
                'is_trial_period': subscription_info.get('isTrialPeriod', False),
                'original_transaction_id': subscription_info.get('originalTransactionId')
            }
        else:
            print(f"iOS subscription verification failed: {result.get('error')}")
            return {'is_valid': False}
    except Exception as e:
        print(f"Error verifying iOS subscription: {e}")
        return {'is_valid': False}

# Verify Android subscription using Google Play Developer API
def verify_android_subscription(subscription_id, purchase_token):
    try:
        # Get the Android Publisher API client
        android_publisher = get_android_publisher_api()
        if not android_publisher:
            return {'is_valid': False}
        
        # Call the API to verify the subscription
        purchases_service = android_publisher.purchases().subscriptions()
        result = purchases_service.get(
            packageName=PACKAGE_NAME,
            subscriptionId=subscription_id,
            token=purchase_token
        ).execute()
        
        # Check if the subscription is active
        if result.get('paymentState') == 1:  # 1 means payment received
            expiry_time_millis = int(result.get('expiryTimeMillis', 0))
            expiry_date = datetime.fromtimestamp(expiry_time_millis / 1000).isoformat()
            
            return {
                'is_valid': True,
                'expiry_date': expiry_date,
                'auto_renewing': result.get('autoRenewing', False),
                'purchase_token': purchase_token,
                'order_id': result.get('orderId')
            }
        else:
            return {'is_valid': False}
    except Exception as e:
        print(f"Error verifying Android subscription: {e}")
        return {'is_valid': False}

@app.route('/wallet/spend-incash', methods=['POST'])
def spend_incash():
    try:
        data = request.get_json()
        user_id = data.get('UserDocumentId')
        amount = data.get('Amount')
        purpose = data.get('Purpose')  # 'group_access' or other future purposes
        group_id = data.get('GroupId')  # Only required for group_access purpose
        
        if not all([user_id, amount, purpose]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
            
        if purpose == 'group_access' and not group_id:
            return jsonify({"success": False, "error": "GroupId is required for group access"}), 400
        
        # Get user document
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404
            
        # Get current balance
        user_data = user_doc.to_dict()
        current_balance = user_data.get('balance', 200)
        
        # Check if user has enough balance
        if current_balance < amount:
            return jsonify({
                "success": False, 
                "error": f"Insufficient balance. You have {current_balance} InCash, but {amount} is required."
            }), 400
        
        # Update balance
        new_balance = current_balance - amount
        
        # Record transaction history
        transaction_history = user_data.get('transactionHistory', [])
        transaction_history.append({
            'type': 'spend',
            'amount': amount,
            'purpose': purpose,
            'groupId': group_id if purpose == 'group_access' else None,
            'date': datetime.now().isoformat()
        })
        
        # Update user document
        user_ref.update({
            'balance': new_balance,
            'transactionHistory': transaction_history
        })
        
        # If purpose is group_access, add user to group  pants if not already there
        if purpose == 'group_access':
            # Check if group exists in conversations collection
            group_ref = db.collection('conversations').document(group_id)
            group_doc = group_ref.get()
            
            if group_doc.exists:
                group_data = group_doc.to_dict()
                participants = group_data.get('participants', [])
                
                # Add user to participants if not already there
                if user_id not in participants:
                    participants.append(user_id)
                    group_ref.update({
                        'participants': participants,
                        'lastMessageTime': firestore.SERVER_TIMESTAMP,
                        'lastMessage': 'A new user joined the group'
                    })
            else:
                # Create group document if it doesn't exist
                group_ref.set({
                    'isGroupChat': True,
                    'participants': [user_id],
                    'lastMessageTime': firestore.SERVER_TIMESTAMP,
                    'lastMessage': 'A new user joined the group'
                })
        
        return jsonify({
            "success": True,
            "data": {
                "balance": new_balance,
                "amountSpent": amount,
                "purpose": purpose
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint to update subscription status
@app.route('/wallet/update-subscription', methods=['POST'])
def update_subscription():
    try:
        data = request.json
        user_id = data.get('UserDocumentId')
        platform = data.get('Platform', '').lower()  # 'ios' or 'android'
        subscription_id = data.get('SubscriptionId')
        receipt_data = data.get('ReceiptData')  # For iOS: receipt data, For Android: purchase token
        
        if not user_id or not platform or not subscription_id or not receipt_data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
            
        # Get user document
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Verify subscription based on platform
        if platform == 'ios':
            verification_result = verify_ios_subscription(receipt_data, user_id)
        elif platform == 'android':
            verification_result = verify_android_subscription(subscription_id, receipt_data)
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid platform'
            }), 400
        
        # Update subscription status based on verification result
        if verification_result.get('is_valid'):
            expiry_date = verification_result.get('expiry_date')
            expiry_datetime = datetime.fromisoformat(expiry_date) if expiry_date else (datetime.now() + timedelta(days=30))
            
            subscription_data = {
                'isSubscribed': True,
                'subscriptionType': 'gold',
                'subscriptionId': subscription_id,
                'platform': platform,
                'startDate': datetime.now().isoformat(),
                'expiryDate': expiry_date,
                'nextRenewalDate': expiry_date,
                'verificationDetails': verification_result
            }
            
            user_ref.update({
                'subscription': subscription_data
            })
            
            return jsonify({
                'success': True,
                'data': {
                    'isSubscribed': True,
                    'subscriptionType': 'gold',
                    'expiryDate': expiry_date
                }
            })
        else:
            # Subscription is not valid
            subscription_data = {
                'isSubscribed': False,
                'cancelDate': datetime.now().isoformat(),
                'verificationDetails': verification_result
            }
            
            user_ref.update({
                'subscription': subscription_data
            })
            
            return jsonify({
                'success': False,
                'error': 'Subscription verification failed',
                'data': {
                    'isSubscribed': False
                }
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Endpoint to check subscription status
@app.route('/wallet/subscription-status', methods=['GET'])
def subscription_status():
    try:
        user_id = request.args.get('UserDocumentId')
        verify = request.args.get('verify', 'false').lower() == 'true'
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Missing user ID'
            }), 400
            
        # Get user document
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
            
        # Get subscription data
        user_data = user_doc.to_dict()
        subscription_data = user_data.get('subscription', {})
        is_subscribed = subscription_data.get('isSubscribed', False)
        
        # If verify flag is true, verify the subscription with the platform
        if verify and is_subscribed:
            platform = subscription_data.get('platform')
            subscription_id = subscription_data.get('subscriptionId')
            
            # For iOS, we need the original receipt data which should be stored
            if platform == 'ios':
                receipt_data = subscription_data.get('verificationDetails', {}).get('original_transaction_id')
                if receipt_data:
                    verification_result = verify_ios_subscription(receipt_data, user_id)
                    is_subscribed = verification_result.get('is_valid', False)
            
            # For Android, we need the purchase token
            elif platform == 'android':
                purchase_token = subscription_data.get('verificationDetails', {}).get('purchase_token')
                if purchase_token and subscription_id:
                    verification_result = verify_android_subscription(subscription_id, purchase_token)
                    is_subscribed = verification_result.get('is_valid', False)
            
            # Update subscription status if verification failed
            if not is_subscribed:
                subscription_data['isSubscribed'] = False
                subscription_data['cancelDate'] = datetime.now().isoformat()
                user_ref.update({
                    'subscription': subscription_data
                })
        
        return jsonify({
            'success': True,
            'data': {
                'isSubscribed': is_subscribed,
                'subscriptionData': subscription_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Endpoint to process monthly subscription rewards
@app.route('/wallet/process-subscription-rewards', methods=['POST'])
def process_subscription_rewards():
    try:
        # This endpoint should be called by a scheduled job/cron job at the start of each month
        # It will add 2500 InCash to all subscribed users
        
        # Get all subscribed users
        subscribed_users = db.collection('humanUsers').where('subscription.isSubscribed', '==', True).stream()
        
        processed_count = 0
        verified_count = 0
        failed_count = 0
        
        for user_doc in subscribed_users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            # Check if subscription is still active
            subscription_data = user_data.get('subscription', {})
            next_renewal_date = subscription_data.get('nextRenewalDate')
            platform = subscription_data.get('platform')
            subscription_id = subscription_data.get('subscriptionId')
            
            # Verify subscription with the platform
            is_valid = False
            
            if platform == 'ios':
                # For iOS, verify with Apple through Firebase Functions
                receipt_data = subscription_data.get('verificationDetails', {}).get('original_transaction_id')
                if receipt_data:
                    verification_result = verify_ios_subscription(receipt_data, user_id)
                    is_valid = verification_result.get('is_valid', False)
                    verified_count += 1
            
            elif platform == 'android':
                # For Android, verify with Google Play Developer API
                purchase_token = subscription_data.get('verificationDetails', {}).get('purchase_token')
                if purchase_token and subscription_id:
                    verification_result = verify_android_subscription(subscription_id, purchase_token)
                    is_valid = verification_result.get('is_valid', False)
                    verified_count += 1
            
            # If subscription is not valid, update status and skip reward
            if not is_valid:
                user_ref = db.collection('humanUsers').document(user_id)
                user_ref.update({
                    'subscription.isSubscribed': False,
                    'subscription.cancelDate': datetime.now().isoformat()
                })
                failed_count += 1
                continue
            
            # If subscription is valid and renewal date has passed, add the monthly reward
            if next_renewal_date and is_valid:
                next_renewal = datetime.fromisoformat(next_renewal_date)
                
                # If the renewal date has passed, add the monthly reward
                if datetime.now() >= next_renewal:
                    # Get current balance
                    current_balance = user_data.get('balance', 200)
                    
                    # Add 2500 InCash
                    new_balance = current_balance + 2500
                    
                    # Update next renewal date (30 days from now)
                    new_next_renewal = (datetime.now() + timedelta(days=30)).isoformat()
                    
                    # Record subscription reward
                    reward_history = user_data.get('subscriptionRewards', [])
                    reward_history.append({
                        'amount': 2500,
                        'date': datetime.now().isoformat(),
                        'type': 'monthly_subscription'
                    })
                    
                    # Update user document
                    user_ref = db.collection('humanUsers').document(user_id)
                    user_ref.update({
                        'balance': new_balance,
                        'subscriptionRewards': reward_history,
                        'subscription.nextRenewalDate': new_next_renewal
                    })
                    
                    processed_count += 1
        
        return jsonify({
            'success': True,
            'data': {
                'processedCount': processed_count,
                'verifiedCount': verified_count,
                'failedCount': failed_count
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ---------------------------
# Asset Store Endpoints
# ---------------------------

@app.route('/store/items', methods=['GET'])
def get_items():
    items = [doc.to_dict() for doc in db.collection('store_items').stream()]
    return jsonify({'items': items})

@app.route('/store/purchase', methods=['POST'])
def purchase_item():
    data = request.json
    user_id = data['user_id']
    item_id = data['item_id']

    item_ref = db.collection('store_items').document(item_id)
    item = item_ref.get().to_dict()
    user_ref = db.collection('humanUsers').document(user_id)
    user_data = user_ref.get().to_dict()

    if not item:
        return jsonify({'error': 'Item not found'}), 404
    if user_data.get('balance', 200) < item.get('price', 0):
        return jsonify({'error': 'Insufficient funds'}), 400

    # Deduct funds and record purchase in the humanUsers document
    user_ref.update({
        'balance': firestore.Increment(-item.get('price', 0)),
        'purchases': firestore.ArrayUnion([item_id])
    })
    # Save purchased item to the user's inventory (subcollection)
    db.collection('humanUsers').document(user_id).collection('inventory').document(item_id).set(item)
    return jsonify({'message': 'Purchase successful'})

@app.route('/store/inventory', methods=['GET'])
def get_inventory():
    user_id = request.args.get('user_id')
    inventory = [doc.to_dict() for doc in db.collection('humanUsers').document(user_id).collection('inventory').stream()]
    return jsonify({'inventory': inventory})

# ---------------------------
# Feed Controller
# ---------------------------
def generate_categories(post_text):
    try:
        if not post_text:
            return []
        
        prompt = (
            f"Classify the following post into relevant categories and return a JSON array. "
            f"Do not add anything else—just give me a JSON array starting and ending with brackets. "
            f"Post: {post_text}"
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a text classification model."},
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.choices[0].message.content.strip()

        # Ensure we only get valid JSON output
        try:
            categories = json.loads(content)
            if isinstance(categories, list):
                return categories[:5]
        except json.JSONDecodeError:
            print(f"Invalid JSON response: {content}")
        
        return []
    
    except Exception as ex:
        print(f"Error generating categories: {ex}")
        return []

@app.route('/feed/create-human-post', methods=['POST'])
def create_human_post():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

        username = data.get("UserName")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "INVALID_USERNAME"}), 400

        post_text = data.get("Post").get("TextContent", "")
        image_content = data.get("Post").get("ImageContent", [])
        video_content = data.get("Post").get("VideoContent", [])
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)
        user_document_id = data.get("UserDocumentId")

        # Check if user is an influencer
        influencer_doc = db.collection('influencers').document(user_document_id).get()
        is_influencer = influencer_doc.exists

        post_data = {
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_document_id": user_document_id,
            "user_name": username,
            "id": data.get("Id"),
            "is_influencer": is_influencer,
            "character_info": data.get("character_info")
        }

        db.collection('humanPosts').document(data.get("Id")).set(post_data)
        
        # Update Gorse with new post
        try:
            labels = categories.copy() if categories else []
            if image_content:
                labels.append('image')
            if video_content:
                labels.append('video')
            labels.append('humanPosts')
            
            gorse_client.insert_item(
                item_id=data.get("Id"),
                labels=labels,
                comment=post_text[:200] if post_text else '',
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            print(f"✓ Synced post {data.get('Id')} to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync post to Gorse: {e}")

        return jsonify({"postId": data.get("Id")}), 200
    except Exception as ex:
        logger.error("Error creating human post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

@app.route('/feed/create-ai-post', methods=['POST'])
def create_ai_post():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

        username = data.get("username")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "MISSING_USERNAME"}), 400

        ai_user_ref = db.collection('aiUsers').document(username)
        ai_user_doc = ai_user_ref.get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": "Invalid username", "code": "USER_NOT_FOUND"}), 400

        post_text = data.get("Post").get("TextContent", "")
        image_content = data.get("Post").get("ImageContent", [])
        video_content = data.get("Post").get("VideoContent", [])
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)

        post_data = {
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_name": username,
        }

        doc_ref = db.collection('aiPosts').document()
        post_id = doc_ref.id
        post_data["id"] = post_id
        doc_ref.set(post_data)

        ai_user_ref.update({"posts": firestore.ArrayUnion([post_id])})
        
        # Update Gorse with new AI post
        try:
            labels = categories.copy() if categories else []
            if image_content:
                labels.append('image')
            if video_content:
                labels.append('video')
            labels.append('aiPosts')
            
            gorse_client.insert_item(
                item_id=post_id,
                labels=labels,
                comment=post_text[:200] if post_text else '',
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            print(f"✓ Synced AI post {post_id} to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync AI post to Gorse: {e}")

        return jsonify({"postId": post_id}), 200
    except Exception as ex:
        logger.error("Error creating AI post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

# create a repost endpoint for reposting normal posts not just ai chats
@app.route('/feed/repost', methods=['POST'])
def repost_post():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request data missing", "code": "NO_DATA"}), 400

        original_post_id = data.get("OriginalPostId")
        reposting_user_id = data.get("RepostingUserId")

        if not original_post_id or not reposting_user_id:
            return jsonify({"success": False, "error": "OriginalPostId and RepostingUserId are required", "code": "MISSING_PARAMS"}), 400

        original_doc = db.collection("humanPosts").document(original_post_id).get()
        original_post_type = "human"

        if not original_doc.exists:
            original_doc = db.collection("aiPosts").document(original_post_id).get()
            original_post_type = "ai"

        if not original_doc.exists:
            return jsonify({"success": False, "error": "Original post not found", "code": "ORIGINAL_POST_NOT_FOUND"}), 404

        original_data = original_doc.to_dict()
        post = original_data.get("post", {})
        post_text = post.get("text_content", "")
        image_content = post.get("image_content", [])
        video_content = post.get("video_content", [])
        categories = original_data.get("category", [])
        original_user_name = original_data.get("user_name")

        reposting_user_doc = db.collection("humanUsers").document(reposting_user_id).get()
        user_type = "human"

        if not reposting_user_doc.exists:
            reposting_user_doc = db.collection("aiUsers").document(reposting_user_id).get()
            user_type = "ai"

        if not reposting_user_doc.exists:
            return jsonify({"success": False, "error": "Reposting user not found", "code": "REPOSTING_USER_NOT_FOUND"}), 404

        reposting_user_data = reposting_user_doc.to_dict()

        repost_id = str(uuid.uuid4())
        repost_data = {
            "original_post_id": original_post_id,
            "original_post_type": original_post_type,
            "original_post_author": original_user_name,
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_document_id": reposting_user_id,
            "user_name": reposting_user_data.get("username"),
            "id": repost_id,
            "user_type": user_type
        }

        db.collection("reposts").document(repost_id).set(repost_data)
        
        # Update Gorse with new repost
        try:
            labels = categories.copy() if categories else []
            if image_content:
                labels.append('image')
            if video_content:
                labels.append('video')
            labels.append('reposts')
            
            gorse_client.insert_item(
                item_id=repost_id,
                labels=labels,
                comment=post_text[:200] if post_text else '',
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            print(f"✓ Synced repost {repost_id} to Gorse")
        except Exception as e:
            print(f"⚠ Failed to sync repost to Gorse: {e}")
        
        # Create notification for original post author (don't notify yourself)
        original_author_id = original_data.get('user_document_id')
        if original_author_id and original_author_id != reposting_user_id:
            try:
                reposting_username = get_user_name(reposting_user_id)
                
                notification_data = {
                    'userId': original_author_id,
                    'type': 'repost',
                    'title': 'Post Reposted',
                    'body': f'{reposting_username} reposted your post',
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'originalPostId': original_post_id,
                        'repostId': repost_id,
                        'reposterId': reposting_user_id,
                        'reposterUsername': reposting_username
                    },
                    # deeplink removed per repository-wide deprecation of in-app deeplinks
                }
                
                db.collection('notifications').add(notification_data)
                logger.info(f"Repost notification created for user {original_author_id}")
                
            except Exception as e:
                logger.error(f"Error creating repost notification: {e}")

        return jsonify({"postId": repost_id}), 200
    except Exception as ex:
        logger.error("Error creating repost: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "REPOST_ERROR"}), 500

@app.route('/feed/create-repost', methods=['POST'])
def create_repost():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400
       
        post_text = data.get("Post").get("TextContent", "")
        image_content = data.get("Post").get("ImageContent", [])
        video_content = data.get("Post").get("VideoContent", [])

        post_data = {
            "ai_chat_content": data.get("AIChatContent"),
            "ai_name": data.get("AIName"),
            "ai_profile_image_url": data.get("AIProfileImageURL"),
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_document_id": data.get("UserDocumentId"),
            "user_name": data.get("UserName"),
            "ai_id": data.get("AiId"),
            "id": data.get("Id")
        }

        db.collection('reposts').document(data.get("Id")).set(post_data)

        return jsonify({"postId": data.get("Id")}), 200
    except Exception as ex:
        logger.error("Error creating repost: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

@app.route('/feed/update-human-post', methods=['POST'])
def update_human_post():
    try:
        data = request.get_json()
        post_id = data.get("Id")
        doc_ref = db.collection('humanPosts').document(post_id)
        
        if not doc_ref.get().exists:
            return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404
        
        update_data = {
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            }
        }
        
        doc_ref.update(update_data)
        return jsonify({"postId": post_id}), 200
    except Exception as ex:
        logger.error("Error updating human post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

@app.route('/feed/update-ai-post', methods=['POST'])
def update_ai_post():
    try:
        data = request.get_json()
        post_id = data.get("Id")
        doc_ref = db.collection('aiPosts').document(post_id)
        
        if not doc_ref.get().exists:
            return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404
        
        update_data = {
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            }
        }
        
        doc_ref.update(update_data)
        return jsonify({"postId": post_id}), 200
    except Exception as ex:
        logger.error("Error updating AI post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500


@app.route('/feed/get-feed', methods=['POST'])
def get_feed():
    try:
        collections = ['aiPosts', 'humanPosts', 'reposts']
        posts = []

        for coll in collections:
            query = (
                db.collection(coll)
                  .order_by("date_posted", direction=firestore.Query.DESCENDING)
                  .limit(15)
            )
            for doc in query.stream():
                data = doc.to_dict() or {}
                data['id'] = doc.id
                data['collection'] = coll

                ts = data.get('date_posted')
                if isinstance(ts, datetime):
                    data['date_posted'] = ts.astimezone(timezone.utc).isoformat()
                elif ts is None:
                    data['date_posted'] = ""

                posts.append(data)

        posts.sort(key=lambda x: x.get('date_posted', ''), reverse=True)

        return jsonify({"success": True, "data": posts[:15]}), 200

    except Exception as ex:
        app.logger.exception("Error getting feed")
        return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/feed/posts-flow', methods=['GET'])
# retrieval and ranking (LLM) two stage pipeline for social media recommendation systems
# Use openai to convert all posts into some encodable text form to work with Gorse.io
# def posts_flow():
#     try:
#         user_id = request.args.get('user_id')
#         page = request.args.get('page', default=1, type=int)
#         posts_per_page = 30

#         print(f"Processing posts flow for user {user_id}, page {page}")

#         user_doc = db.collection('humanUsers').document(user_id).get()

#         # Helper Functions
#         def parse_date(date_str):
#             try:
#                 naive_dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
#                 return naive_dt.replace(tzinfo=timezone.utc)
#             except Exception:
#                 return datetime.min.replace(tzinfo=timezone.utc)

#         def compute_freshness_score(post_date):
#             now = datetime.now(timezone.utc)
#             seconds_since = (now - post_date).total_seconds()
#             return 1 / math.log(seconds_since + 2)

#         def compute_engagement_score(post):
#             return float(post.get("engagement_score", 0.5))

#         def compute_media_score(post):
#             if post.get("has_video"):
#                 return 1.0 if post.get("post_type") == "human_post" else 0.9
#             elif post.get("has_image"):
#                 return 0.8 if post.get("post_type") == "human_post" else 0.7
#             else:
#                 return 0.6 if post.get("post_type") == "human_post" else 0.5

#         def compute_human_score(post):
#             return 1.0 if post.get("post_type") in ["human_post", "repost"] else 0.8

#         def compute_repost_adjustment(post):
#             if post.get("post_type") == "repost":
#                 return 0.8
#             return 0.0

#         def compute_final_score(post):
#             date_str = post.get('date_posted', '')
#             post_date = parse_date(date_str)
#             freshness = compute_freshness_score(post_date)
#             engagement = compute_engagement_score(post)
#             media = compute_media_score(post)
#             human = compute_human_score(post)
#             repost_adj = compute_repost_adjustment(post)

#             # Base score calculation
#             if post.get("has_video"):
#                 base_score = (0.30 * freshness +
#                          0.20 * engagement +
#                          0.15 * media +
#                          0.12 * human +
#                          0.23 * repost_adj)
#             else:
#                 base_score = (0.25 * freshness +
#                          0.20 * engagement +
#                          0.10 * media +
#                          0.15 * human +
#                          0.30 * repost_adj)

#             # Apply penalties and boosts
#             # human_boost = 0.04102886 if post.get("post_type") == "human_post" else 0.0
#             # repost_boost = 0.2 if post.get("post_type") == "repost" else 0.0
#             # text_boost = 0.09 if not post.get("has_video") or not post.get("has_image") else 0.0
            
#             final_score = base_score
#             return final_score

#         # Fetch and Filter Posts
#         def fetch_posts(collection_name, limit=None, filter=None, or_filter=None):
#             results = []
#             seen_ids = set()

#             if filter:
#                 field, value = filter
#                 query = db.collection(collection_name).where(field, '==', value)
#                 if limit:
#                     query = query.limit(limit)
#                 return [doc.to_dict() for doc in query.stream()]

#             if or_filter:
#                 for field, value in or_filter:
#                     query = db.collection(collection_name).where(field, '==', value)
#                     if limit:
#                         query = query.limit(limit)
#                     for doc in query.stream():
#                         doc_dict = doc.to_dict()
#                         doc_id = doc.id
#                         if doc_id not in seen_ids:
#                             results.append(doc_dict)
#                             seen_ids.add(doc_id)
#                 return results[:limit] if limit else results

#             # If no filters
#             query = db.collection(collection_name)
#             if limit:
#                 query = query.limit(limit)
#             return [doc.to_dict() for doc in query.stream()]

#         human_posts_all = fetch_posts('humanPosts')

#         human_count = len(human_posts_all)

#         ai_posts_all = (
#             fetch_posts('aiPosts', limit=(human_count * 2), filter=('has_image', True)) +
#             fetch_posts('aiPosts', limit=(human_count * 4), filter=('has_video', True)) +
#             fetch_posts('aiPosts', limit=(human_count // 2), or_filter=[('has_image', False), ('has_video', False)])
#         )

#         reposts_all = fetch_posts('reposts')

#         print(f"Total posts fetched - AI: {len(ai_posts_all)}, Human: {len(human_posts_all)}, Reposts: {len(reposts_all)}")

#         # Separate Posts by Type
#         def separate_posts(posts):
#             text_posts = [p for p in posts if not p.get("has_video") and not p.get("has_image")]
#             video_posts = [p for p in posts if p.get("has_video")]
#             image_posts = [p for p in posts if p.get("has_image")]
#             return text_posts, video_posts, image_posts

#         ai_text, ai_video, ai_image = separate_posts(ai_posts_all)
#         human_text, human_video, human_image = separate_posts(human_posts_all)

#         print(f"Separated posts - AI: Text={len(ai_text)}, Video={len(ai_video)}, Image={len(ai_image)}")
#         print(f"Separated posts - Human: Text={len(human_text)}, Video={len(human_video)}, Image={len(human_image)}")

#         # Assign Post Types
#         for post in ai_text + ai_video + ai_image:
#             post['post_type'] = 'ai_post'
#         for post in human_text + human_video + human_image:
#             post['post_type'] = 'human_post'
#         for post in reposts_all:
#             post['post_type'] = 'repost'

#         # Combine all posts
#         all_posts = human_posts_all + reposts_all + ai_posts_all

#         # Compute scores for all posts
#         for post in all_posts:
#             post['final_score'] = compute_final_score(post)

#         # Sort Posts by Final Score
#         sorted_posts = sorted(all_posts, key=lambda x: x['final_score'], reverse=True)
#         print(f"Posts after sorting: {len(sorted_posts)}")

#         # Deduplication
#         seen_ids = set()
#         unique_posts = []
#         for post in sorted_posts:
#             post_id = post.get('id')
#             if post_id and post_id not in seen_ids:
#                 unique_posts.append(post)
#                 seen_ids.add(post_id)
#         print(f"Unique posts after deduplication: {len(unique_posts)}")

#         random.shuffle(unique_posts)
#         offset = (page - 1) * posts_per_page
#         final_feed = unique_posts[offset:offset + posts_per_page]
        
#         # Count post types in final feed
#         post_types = {'ai_post': 0, 'human_post': 0, 'repost': 0}
#         media_types = {'text': 0, 'video': 0, 'image': 0}
#         for post in final_feed:
#             post_types[post.get('post_type', 'unknown')] += 1
#             if post.get('has_video'):
#                 media_types['video'] += 1
#             elif post.get('has_image'):
#                 media_types['image'] += 1
#             else:
#                 media_types['text'] += 1
        
#         print(f"Final feed composition:")
#         print(f"Post types: {post_types}")
#         print(f"Media types: {media_types}")
#         print(f"Total posts in feed: {len(final_feed)}")
#         print(f"Showing posts {offset + 1} to {offset + len(final_feed)} of {len(unique_posts)} total unique posts")

#         return jsonify({'posts': final_feed}), 200

#     except Exception as ex:
#         print(f"Error generating posts flow: {ex}")
#         return jsonify({"success": False, "error": str(ex)}), 500

# ---------------------------
# Gorse Recommendation Tracking Endpoints
# ---------------------------

@app.route('/feed/track-view', methods=['POST'])
def track_post_view():
    """Track when a user views a post"""
    try:
        data = request.json
        user_id = data.get('user_id')
        post_id = data.get('post_id')
        
        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400
        
        # Record in Gorse as 'read' feedback
        gorse_client.record_interaction(user_id, post_id, 'read')
        print(f"👁️  User {user_id[:8]}... viewed post {post_id[:8]}... (tracked as 'read')")
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"Error tracking view: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/feed/track-like', methods=['POST'])
def track_post_like():
    """Track when a user likes a post"""
    try:
        data = request.json
        user_id = data.get('user_id')
        post_id = data.get('post_id')
        
        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400
        
        # Record in Gorse
        gorse_client.record_interaction(user_id, post_id, 'like')
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"Error tracking like: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/feed/track-comment', methods=['POST'])
def track_post_comment():
    """Track when a user comments on a post"""
    try:
        data = request.json
        user_id = data.get('user_id')
        post_id = data.get('post_id')
        
        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400
        
        # Record in Gorse
        gorse_client.record_interaction(user_id, post_id, 'comment')
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"Error tracking comment: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/feed/track-share', methods=['POST'])
def track_post_share():
    """Track when a user shares a post"""
    try:
        data = request.json
        user_id = data.get('user_id')
        post_id = data.get('post_id')
        
        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400
        
        # Record in Gorse
        gorse_client.record_interaction(user_id, post_id, 'share')
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"Error tracking share: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/feed/similar-posts/<post_id>', methods=['GET'])
def get_similar_posts_endpoint(post_id):
    """Get similar posts for 'You may also like' section"""
    try:
        limit = int(request.args.get('limit', 5))
        
        # Get similar posts from Gorse
        similar_post_ids = gorse_client.get_similar_posts(post_id, limit=limit)
        
        # Fetch actual post data
        posts = []
        for pid in similar_post_ids:
            post_data = get_post_from_firestore_by_id(pid)
            if post_data:
                posts.append(post_data)
        
        return jsonify({'posts': posts}), 200
    except Exception as e:
        print(f"Error getting similar posts: {e}")
        return jsonify({'error': str(e)}), 500


def get_post_from_firestore_by_id(post_id):
    """Helper function to fetch a post from Firestore by ID"""
    try:
        # Try humanPosts first
        post_doc = db.collection('humanPosts').document(post_id).get()
        if post_doc.exists:
            return post_doc.to_dict()
        
        # Try aiPosts
        post_doc = db.collection('aiPosts').document(post_id).get()
        if post_doc.exists:
            return post_doc.to_dict()
        
        # Try reposts
        post_doc = db.collection('reposts').document(post_id).get()
        if post_doc.exists:
            return post_doc.to_dict()
        
        return None
    except Exception as e:
        print(f"Error fetching post {post_id}: {e}")
        return None


def get_posts_by_ids(post_ids: List[str]) -> List[dict]:
    """Fetch multiple posts from Firestore by their IDs"""
    posts = []
    for post_id in post_ids:
        post_data = get_post_from_firestore_by_id(post_id)
        if post_data:
            posts.append(post_data)
    return posts

# ---------------------------
# Feed Endpoints
# ---------------------------

@app.route('/feed/posts-flow', methods=['GET'])
def posts_flow():
    try:
        user_id = request.args.get('user_id')
        page = request.args.get('page', default=1, type=int)
        posts_per_page = 10  # 🎯 Changed from 30 to 10 posts per page

        print(f"\n{'='*60}")
        print(f"📱 FEED REQUEST from user: {user_id}, page: {page}")
        print(f"{'='*60}")

        # Try to get recommendations from Gorse first
        if gorse_client.enabled:
            try:
                offset = (page - 1) * posts_per_page
                print(f"🤖 Requesting recommendations from Gorse...")
                
                # 🎯 Request 50% more posts to filter duplicates and low-quality recommendations
                request_limit = int(posts_per_page * 1.5)
                recommended_ids = gorse_client.get_recommendations(
                    user_id=user_id,
                    limit=request_limit,
                    offset=offset
                )
                
                if recommended_ids and len(recommended_ids) >= posts_per_page * 0.5:  # At least 50% success rate
                    print(f"✅ GORSE ACTIVE: Got {len(recommended_ids)} personalized recommendations!")
                    print(f"   Post IDs: {recommended_ids[:3]}..." if len(recommended_ids) > 3 else f"   Post IDs: {recommended_ids}")
                    
                    # 🎯 Check recommendation quality: if we got fewer posts than requested, pool is draining
                    recommendation_quality = len(recommended_ids) / request_limit
                    print(f"📊 Recommendation quality: {recommendation_quality:.1%} ({len(recommended_ids)}/{request_limit})")
                    
                    posts = get_posts_by_ids(recommended_ids)
                    
                    if posts and len(posts) >= posts_per_page * 0.5:
                        print(f"✅ Successfully fetched {len(posts)} posts from Firestore")
                        
                        # 🎯 Only take the number we need
                        posts = posts[:posts_per_page]
                        actual_post_ids = [p.get('id') for p in posts if p.get('id')]
                        
                        # 🎯 Do NOT mark as 'read' here - let Flutter track actual views via /feed/track-view
                        print(f"📝 Returning {len(actual_post_ids)} recommendations (will be marked as read when actually viewed)")
                        
                        # 🎯 If quality is low (< 70%), warn that we're running out of recommendations
                        if recommendation_quality < 0.7:
                            print(f"⚠️  LOW QUALITY WARNING: Recommendation pool draining (quality: {recommendation_quality:.1%})")
                            print(f"   Consider generating more content or waiting for user interactions")
                        
                        print(f"🎯 Returning GORSE-POWERED recommendations\n")
                        # Add source indicator
                        for post in posts:
                            post['recommendation_source'] = 'gorse'
                        
                        return jsonify({
                            'posts': posts,
                            'page': page,
                            'has_more': recommendation_quality > 0.3,  # Only say "has_more" if quality is decent
                            'source': 'gorse',
                            'quality': round(recommendation_quality, 2)
                        }), 200
                    else:
                        print(f"⚠️  Not enough valid posts from Gorse ({len(posts)} posts), falling back")
                else:
                    if recommended_ids:
                        print(f"⚠️  Too few recommendations from Gorse ({len(recommended_ids)}/{request_limit}), falling back")
                    else:
                        print("⚠️  No recommendations from Gorse, falling back to legacy algorithm")
            except Exception as e:
                print(f"❌ Error getting Gorse recommendations: {e}")
                print("⚠️  Falling back to legacy algorithm")
        else:
            print("⚠️  Gorse is disabled, using legacy algorithm")

        user_doc = db.collection('humanUsers').document(user_id).get()
        user_categories = set()
        if user_doc.exists:
            user_categories.update(user_doc.to_dict().get('interests', []))

        # Helper Functions
        def parse_date(date_str):
            try:
                naive_dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
                return naive_dt.replace(tzinfo=timezone.utc)
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        def compute_freshness_score(post_date):
            now = datetime.now(timezone.utc)
            seconds_since = (now - post_date).total_seconds()
            return 1 / math.log(seconds_since + 2)

        def compute_engagement_score(post):
            return float(post.get("engagement_score", 0.5))

        def compute_media_score(post):
            if post.get("has_video"):
                return 1.0 if post.get("post_type") == "human_post" else 0.9
            elif post.get("has_image"):
                return 0.8 if post.get("post_type") == "human_post" else 0.7
            else:
                return 0.6 if post.get("post_type") == "human_post" else 0.5

        def compute_human_score(post):
            return 1.0 if post.get("post_type") in ["human_post", "repost"] else 0.8

        def compute_repost_adjustment(post):
            if post.get("post_type") == "repost":
                return 0.8
            return 0.0

        def compute_category_score(post):
            if not user_categories:
                return 0.0
            post_cats = set(post.get('category', []))
            matches = user_categories.intersection(post_cats)
            return min(0.1 * len(matches), 0.3)

        def compute_final_score(post):
            date_str = post.get('date_posted', '')
            post_date = parse_date(date_str)
            freshness = compute_freshness_score(post_date)
            engagement = compute_engagement_score(post)
            media = compute_media_score(post)
            human = compute_human_score(post)
            repost_adj = compute_repost_adjustment(post)
            category_score = compute_category_score(post)

            # Base score calculation
            if post.get("has_video"):
                base_score = (0.30 * freshness +
                         0.20 * engagement +
                         0.15 * media +
                         0.12 * human +
                         0.23 * repost_adj)
            else:
                base_score = (0.25 * freshness +
                         0.20 * engagement +
                         0.10 * media +
                         0.15 * human +
                         0.30 * repost_adj)

            final_score = base_score + category_score
            return final_score

        # Fetch and Filter Posts
        def fetch_posts(collection_name, limit=None, filter=None, or_filter=None):
            results = []
            seen_ids = set()

            if filter:
                field, value = filter
                query = db.collection(collection_name).where(field, '==', value)
                if limit:
                    query = query.limit(limit)
                return [doc.to_dict() for doc in query.stream()]

            if or_filter:
                for field, value in or_filter:
                    query = db.collection(collection_name).where(field, '==', value)
                    if limit:
                        query = query.limit(limit)
                    for doc in query.stream():
                        doc_dict = doc.to_dict()
                        doc_id = doc.id
                        if doc_id not in seen_ids:
                            results.append(doc_dict)
                            seen_ids.add(doc_id)
                return results[:limit] if limit else results

            # If no filters
            query = db.collection(collection_name)
            if limit:
                query = query.limit(limit)
            return [doc.to_dict() for doc in query.stream()]

        human_posts_all = fetch_posts('humanPosts')

        human_count = len(human_posts_all)

        ai_posts_all = (
            fetch_posts('aiPosts', limit=(human_count * 2), filter=('has_image', True)) +
            fetch_posts('aiPosts', limit=(human_count * 4), filter=('has_video', True)) +
            fetch_posts('aiPosts', limit=(human_count // 2), or_filter=[('has_image', False), ('has_video', False)])
        )

        reposts_all = fetch_posts('reposts')

        print(f"Total posts fetched - AI: {len(ai_posts_all)}, Human: {len(human_posts_all)}, Reposts: {len(reposts_all)}")

        # Separate Posts by Type
        def separate_posts(posts):
            text_posts = [p for p in posts if not p.get("has_video") and not p.get("has_image")]
            video_posts = [p for p in posts if p.get("has_video")]
            image_posts = [p for p in posts if p.get("has_image")]
            return text_posts, video_posts, image_posts

        ai_text, ai_video, ai_image = separate_posts(ai_posts_all)
        human_text, human_video, human_image = separate_posts(human_posts_all)

        print(f"Separated posts - AI: Text={len(ai_text)}, Video={len(ai_video)}, Image={len(ai_image)}")
        print(f"Separated posts - Human: Text={len(human_text)}, Video={len(human_video)}, Image={len(human_image)}")

        # Assign Post Types
        for post in ai_text + ai_video + ai_image:
            post['post_type'] = 'ai_post'
        for post in human_text + human_video + human_image:
            post['post_type'] = 'human_post'
        for post in reposts_all:
            post['post_type'] = 'repost'

        # Combine all posts
        all_posts = human_posts_all + reposts_all + ai_posts_all

        # Compute scores for all posts
        for post in all_posts:
            post['final_score'] = compute_final_score(post)

        # Sort Posts by Final Score
        sorted_posts = sorted(all_posts, key=lambda x: x['final_score'], reverse=True)
        print(f"Posts after sorting: {len(sorted_posts)}")

        # Deduplication
        seen_ids = set()
        unique_posts = []
        for post in sorted_posts:
            post_id = post.get('id')
            if post_id and post_id not in seen_ids:
                unique_posts.append(post)
                seen_ids.add(post_id)
        print(f"Unique posts after deduplication: {len(unique_posts)}")

        random.shuffle(unique_posts)
        offset = (page - 1) * posts_per_page
        final_feed = unique_posts[offset:offset + posts_per_page]
        
        # Count post types in final feed
        post_types = {'ai_post': 0, 'human_post': 0, 'repost': 0}
        media_types = {'text': 0, 'video': 0, 'image': 0}
        for post in final_feed:
            post_types[post.get('post_type', 'unknown')] += 1
            if post.get('has_video'):
                media_types['video'] += 1
            elif post.get('has_image'):
                media_types['image'] += 1
            else:
                media_types['text'] += 1
        
        print(f"Final feed composition:")
        print(f"Post types: {post_types}")
        print(f"Media types: {media_types}")
        print(f"Total posts in feed: {len(final_feed)}")
        print(f"Showing posts {offset + 1} to {offset + len(final_feed)} of {len(unique_posts)} total unique posts")

        return jsonify({'posts': final_feed}), 200

    except Exception as ex:
        print(f"Error generating posts flow: {ex}")
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/test-feed-quality', methods=['GET'])
def test_feed_quality():
    try:
        user_id = request.args.get('user_id')
        page = request.args.get('page', default=1, type=int)
        pages_to_test = request.args.get('pages', default=10, type=int)
        
        all_posts = []
        seen_post_ids = set()  # Track all post IDs we've seen
        seen_content_hashes = set()  # Track content hashes to catch duplicates with different IDs
        
        post_occurrences = {}  # Track how many times each post appears
        post_locations = {}    # Track which pages each post appears on
        
        issues = {
            "repeating_posts": [],
            "consecutive_user_posts": [],
            "cross_page_duplicates": [],
            "content_duplicates": []  # New: duplicates based on content, not just ID
        }
        
        # Track user session to ensure same session across requests
        session_headers = {
            'User-Agent': 'TestFeedQuality/1.0',
            'X-Test-Session-ID': str(uuid.uuid4())
        }
        
        # Collect posts from multiple pages
        for p in range(page, page + pages_to_test):
            print(f"Testing page {p}...")
            # Use direct function call instead of HTTP request to avoid any caching issues
            with app.test_client() as client:
                response = client.get(
                    f"/feed/posts-flow?user_id={user_id}&page={p}",
                    headers=session_headers
                )
                
                if response.status_code == 200:
                    try:
                        response_data = response.json
                        
                        page_posts = response_data.get('posts', [])
                        if not isinstance(page_posts, list):
                            return jsonify({
                                "error": "Posts data is not a list",
                                "details": page_posts
                            }), 500
                        
                        print(f"Collected {len(page_posts)} posts from page {p}")
                        
                        # Process each post on this page
                        for post in page_posts:
                            if not isinstance(post, dict):
                                continue
                                
                            post_id = post.get('id')
                            if not post_id:
                                continue
                                
                            # Track this post occurrence
                            if post_id in post_occurrences:
                                post_occurrences[post_id] += 1
                            else:
                                post_occurrences[post_id] = 1
                                
                            # Track which pages this post appears on
                            if post_id in post_locations:
                                post_locations[post_id].append(p)
                            else:
                                post_locations[post_id] = [p]
                                
                            # Create a content hash to detect same content with different IDs
                            # We'll use a combination of fields that should uniquely identify content
                            content_fields = []
                            if post.get('post_text'):
                                content_fields.append(post.get('post_text'))
                            if post.get('post', {}).get('video_content'):
                                video_content = post.get('post', {}).get('video_content')
                                if isinstance(video_content, list) and len(video_content) > 0:
                                    content_fields.append(str(video_content[0]))
                                elif isinstance(video_content, dict) and video_content.get('url'):
                                    content_fields.append(video_content.get('url'))
                            if post.get('post', {}).get('image_content'):
                                image_content = post.get('post', {}).get('image_content')
                                if isinstance(image_content, list) and len(image_content) > 0:
                                    content_fields.append(str(image_content[0]))
                                elif isinstance(image_content, dict) and image_content.get('url'):
                                    content_fields.append(image_content.get('url'))
                                    
                            if content_fields:
                                content_hash = hashlib.md5(''.join(content_fields).encode()).hexdigest()
                                
                                if content_hash in seen_content_hashes:
                                    issues["content_duplicates"].append({
                                        "post_id": post_id,
                                        "username": post.get('user_name', 'unknown'),
                                        "page": p,
                                        "content_hash": content_hash
                                    })
                                seen_content_hashes.add(content_hash)
                            
                            # Add post to the all_posts collection
                            all_posts.append(post)
                            
                    except ValueError as e:
                        return jsonify({"error": f"Invalid JSON response: {str(e)}"}), 500
                else:
                    return jsonify({"error": f"Failed to fetch page {p}"}), 500
        
        # Process post occurrences to find duplicates
        for post_id, count in post_occurrences.items():
            if count > 1:
                # Find a post with this ID
                matching_posts = [p for p in all_posts if p.get('id') == post_id]
                if matching_posts:
                    post = matching_posts[0]
                    issues["repeating_posts"].append({
                        "post_id": post_id,
                        "username": post.get('user_name', 'unknown'),
                        "count": count,
                        "pages": post_locations.get(post_id, [])
                    })
        
        # Test for consecutive posts by the same user
        for i in range(1, len(all_posts)):
            if not isinstance(all_posts[i], dict) or not isinstance(all_posts[i - 1], dict):
                continue
            current_username = all_posts[i].get('user_name')
            prev_username = all_posts[i - 1].get('user_name')
            
            if current_username and current_username == prev_username:
                issues["consecutive_user_posts"].append({
                    "username": current_username,
                    "post_ids": [all_posts[i - 1].get('id'), all_posts[i].get('id')]
                })

        # Test for cross-page duplicates
        for post_id, pages in post_locations.items():
            if len(pages) > 1:
                # Find a post with this ID
                matching_posts = [p for p in all_posts if p.get('id') == post_id]
                if matching_posts:
                    post = matching_posts[0]
                    issues["cross_page_duplicates"].append({
                        "post_id": post_id,
                        "username": post.get('user_name', 'unknown'),
                        "duplicate_pages": pages
                    })
        
        # Collect statistics about the feed quality
        stats = {
            "total_posts_analyzed": len(all_posts),
            "unique_post_ids": len(post_occurrences),
            "unique_content_hashes": len(seen_content_hashes),
            "unique_users": len(set(post.get('user_name') for post in all_posts if isinstance(post, dict) and post.get('user_name'))),
            "pages_analyzed": pages_to_test,
            "repeating_posts_count": len(issues["repeating_posts"]),
            "consecutive_user_posts_count": len(issues["consecutive_user_posts"]),
            "cross_page_duplicates_count": len(issues["cross_page_duplicates"]),
            "content_duplicates_count": len(issues["content_duplicates"])
        }
        
        print(f"Feed quality test results: {stats}")
        if issues["repeating_posts"]:
            print(f"Found {len(issues['repeating_posts'])} repeating posts")
            for post in issues["repeating_posts"]:
                print(f"Post {post['post_id']} by {post['username']} appears {post['count']} times on pages {post['pages']}")
        
        if issues["consecutive_user_posts"]:
            print(f"Found {len(issues['consecutive_user_posts'])} instances of consecutive posts by the same user")
        
        if issues["cross_page_duplicates"]:
            print(f"Found {len(issues['cross_page_duplicates'])} posts that appear on multiple pages")
            for dup in issues["cross_page_duplicates"]:
                print(f"Post {dup['post_id']} by {dup['username']} appears on pages {dup['duplicate_pages']}")
                
        if issues["content_duplicates"]:
            print(f"Found {len(issues['content_duplicates'])} posts with duplicate content but different IDs")
            for dup in issues["content_duplicates"]:
                print(f"Post {dup['post_id']} by {dup['username']} on page {dup['page']} has duplicate content")
        
        # Add detailed post inventory to the response for debugging
        pages_inventory = {}
        for post_id, pages in post_locations.items():
            for page_num in pages:
                if page_num not in pages_inventory:
                    pages_inventory[page_num] = []
                pages_inventory[page_num].append(post_id)
        
        return jsonify({
            "stats": stats,
            "issues": issues,
            "pages_inventory": pages_inventory  # Shows which posts appear on which pages
        }), 200
    except Exception as ex:
        logger.error("Error testing feed quality: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/update-post', methods=['POST'])
def update_post():
    try:
        data = request.get_json()
        post_id = data.get("PostId")

        if not post_id:
            return jsonify({"success": False, "error": "PostId is required", "code": "INVALID_POST_ID"}), 400

        update_data = {
            "content": data.get("Content"),
            "imageUrl": data.get("ImageUrl"),
            "updatedAt": firestore.SERVER_TIMESTAMP
        }

        collections = ['aiPosts', 'humanPosts', 'reposts']
        post_found = False

        for collection in collections:
            post_ref = db.collection(collection).document(post_id)
            post_doc = post_ref.get()

            if post_doc.exists:
                post_ref.update(update_data)
                post_found = True
                break

        if not post_found:
            return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

@app.route('/feed/write-comment', methods=['POST'])
def write_comment():
    try:
        data = request.get_json()
        post_id = data.get("PostId")
        user_id = data.get("UserId")
        content = data.get("Content")
        
        comment_data = {
            "postId": post_id,
            "userId": user_id,
            "content": content,
            "createdAt": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('postComments').add(comment_data)
        
        # Find the post owner to send notification
        collections = ['humanPosts', 'reposts', 'aiPosts']
        post_author_id = None
        
        for collection in collections:
            try:
                post_doc = db.collection(collection).document(post_id).get()
                if post_doc.exists:
                    post_data = post_doc.to_dict()
                    post_author_id = post_data.get('user_document_id')
                    break
            except Exception as e:
                continue
        
        # Create notification for post author (don't notify yourself)
        if post_author_id and post_author_id != user_id:
            try:
                # Get commenter's username
                commenter_username = get_user_name(user_id)
                
                notification_data = {
                    'userId': post_author_id,
                    'type': 'comment',
                    'title': 'New Comment',
                    'body': f'{commenter_username} commented on your post',
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'postId': post_id,
                        'commentId': doc_ref[1].id,
                        'commenterId': user_id,
                        'commenterUsername': commenter_username
                    },
                    # deeplink removed per repository-wide deprecation of in-app deeplinks

                }
                
                db.collection('notifications').add(notification_data)
                logger.info(f"Comment notification created for user {post_author_id}")
                
            except Exception as e:
                logger.error(f"Error creating comment notification: {e}")
        
        return jsonify({"commentId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error writing comment: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/comments/add-threaded-comment', methods=['POST'])
# def add_threaded_comment():
#     """Add a comment or reply with proper threading support - OUTDATED"""
#     try:
#         data = request.get_json()
#         post_id = data.get("postId")
#         user_id = data.get("userId")
#         content = data.get("content")
#         parent_comment_id = data.get("parentCommentId")  # null for top-level comments
#         
#         if not post_id or not user_id or not content:
#             return jsonify({"success": False, "error": "Missing required fields"}), 400
#         
#         # Generate unique comment ID
#         import time
#         import random
#         comment_id = f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
#         
#         # Create comment data with threading support
#         comment_data = {
#             "id": comment_id,
#             "author": get_user_name(user_id),
#             "text": content,
#             "userId": user_id,
#             "postId": post_id,
#             "parentCommentId": parent_comment_id,
#             "timestamp": str(int(time.time() * 1000)),
#             "createdAt": firestore.SERVER_TIMESTAMP,
#             "likedBy": [],
#             "dislikedBy": [],
#             "replyCount": 0,
#             "isReply": parent_comment_id is not None
#         }

#         # Reference to the post's comment document
#         post_comment_ref = db.collection('postComments').document(post_id)
#         
#         # Use transaction for atomic updates
#         @firestore.transactional
#         def update_comments(transaction):
#             # Get current comments
#             post_doc = transaction.get(post_comment_ref)
#             current_comments = []
#             
#             if post_doc.exists:
#                 current_comments = post_doc.to_dict().get('comments', [])
#             
#             # Add the new comment
#             current_comments.append(comment_data)
#             
#             # If this is a reply, increment parent's reply count
#             if parent_comment_id:
#                 for comment in current_comments:
#                     if comment.get('id') == parent_comment_id:
#                         comment['replyCount'] = comment.get('replyCount', 0) + 1
#                         break
#             
#             # Update the document
#             transaction.set(post_comment_ref, {'comments': current_comments}, merge=True)
#             
#             return current_comments
#         
#         # Execute transaction
#         transaction = db.transaction()
#         updated_comments = update_comments(transaction)
#         
#         # Send notifications
#         try:
#             # Find the post owner to send notification
#             collections = ['humanPosts', 'reposts', 'aiPosts']
#             post_author_id = None
#             
#             for collection in collections:
#                 try:
#                     post_doc = db.collection(collection).document(post_id).get()
#                     if post_doc.exists:
#                         post_data = post_doc.to_dict()
#                         post_author_id = post_data.get('user_document_id')
#                         break
#                 except Exception as e:
#                     continue
#             
#             # Notify post author (if not commenting on own post)
#             if post_author_id and post_author_id != user_id:
#                 notification_type = 'comment_reply' if parent_comment_id else 'comment'
#                 notification_data = {
#                     'userId': post_author_id,
#                     'type': notification_type,
#                     'title': f'New {"Reply" if parent_comment_id else "Comment"}',
#                     'body': f'{get_user_name(user_id)} {"replied to" if parent_comment_id else "commented on"} your post',
#                     'isRead': False,
#                     'createdAt': firestore.SERVER_TIMESTAMP,
#                     'data': {
#                         'postId': post_id,
#                         'commentId': comment_id,
#                         'parentCommentId': parent_comment_id,
#                         'commenterId': user_id,
#                         'commenterUsername': get_user_name(user_id),
#                         'content': content
#                     }
#                 }
#                 db.collection('notifications').add(notification_data)
#             
#             # If this is a reply, also notify the parent comment author
#             if parent_comment_id:
#                 parent_comment = next((c for c in updated_comments if c.get('id') == parent_comment_id), None)
#                 if parent_comment:
#                     parent_author_id = parent_comment.get('userId')
#                     if parent_author_id and parent_author_id != user_id and parent_author_id != post_author_id:
#                         reply_notification_data = {
#                             'userId': parent_author_id,
#                             'type': 'comment_reply',
#                             'title': 'Reply to Your Comment',
#                             'body': f'{get_user_name(user_id)} replied to your comment',
#                             'isRead': False,
#                             'createdAt': firestore.SERVER_TIMESTAMP,
#                             'data': {
#                                 'postId': post_id,
#                                 'commentId': comment_id,
#                                 'parentCommentId': parent_comment_id,
#                                 'replierId': user_id,
#                                 'replierUsername': get_user_name(user_id),
#                                 'content': content
#                             }
#                         }
#                         db.collection('notifications').add(reply_notification_data)
#                         
#         except Exception as e:
#             logger.error(f"Error sending notifications: {e}")
#         
#         return jsonify({
#             "success": True,
#             "commentId": comment_id,
#             "isReply": parent_comment_id is not None
#         }), 200
#         
#     except Exception as ex:
#         logger.error("Error adding threaded comment: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/comments/get-threaded-comments', methods=['POST'])
# def get_threaded_comments():
#     """Get comments for a post with proper threading"""
#     try:
#         data = request.get_json()
#         post_id = data.get("postId")
        
#         if not post_id:
#             return jsonify({"success": False, "error": "Missing postId"}), 400
        
#         # Get comments from Firestore
#         post_comment_doc = db.collection('postComments').document(post_id).get()
        
#         if not post_comment_doc.exists:
#             return jsonify({"success": True, "comments": []}), 200
        
#         comments_data = post_comment_doc.to_dict().get('comments', [])
        
#         # Separate parent comments and replies
#         parent_comments = []
#         replies_by_parent = {}
        
#         for comment in comments_data:
#             if comment.get('parentCommentId'):
#                 # This is a reply
#                 parent_id = comment['parentCommentId']
#                 if parent_id not in replies_by_parent:
#                     replies_by_parent[parent_id] = []
#                 replies_by_parent[parent_id].append(comment)
#             else:
#                 # This is a parent comment
#                 parent_comments.append(comment)
        
#         # Sort parent comments by timestamp (newest first)
#         parent_comments.sort(key=lambda x: int(x.get('timestamp', 0)), reverse=True)
        
#         # Sort replies within each parent (newest first)
#         for replies in replies_by_parent.values():
#             replies.sort(key=lambda x: int(x.get('timestamp', 0)), reverse=True)
        
#         # Build the final threaded structure
#         threaded_comments = []
#         for parent in parent_comments:
#             parent_id = parent.get('id')
#             replies = replies_by_parent.get(parent_id, [])
            
#             # Update reply count
#             parent['replyCount'] = len(replies)
            
#             threaded_comments.append(parent)
#             # Add replies after parent
#             threaded_comments.extend(replies)
        
#         return jsonify({
#             "success": True,
#             "comments": threaded_comments
#         }), 200
        
#     except Exception as ex:
#         logger.error("Error getting threaded comments: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/get-user-posts', methods=['POST'])
def get_user_posts():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        # Retrieve user posts from all collections
        collections = ['humanPosts', 'reposts']
        posts = []

        for collection in collections:
            query = db.collection(collection).where("user_document_id", "==", user_id).limit(25)
            snapshot = query.stream()
            posts.extend([doc.to_dict() for doc in snapshot])


        posts.sort(key=lambda x: x['date_posted'], reverse=True)

        return jsonify(posts[:25]), 200
    except Exception as ex:
        logger.error("Error getting user posts: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/get-ai-posts', methods=['POST'])
def get_ai_posts():
    try:
        data = request.get_json()
        username = data.get("UserName")

        # Retrieve user posts from all collections
        collection = 'aiPosts'
        posts = []

        query = db.collection(collection).where("user_name", "==", username).limit(25)
        snapshot = query.stream()
        posts.extend([doc.to_dict() for doc in snapshot])

        posts.sort(key=lambda x: x['date_posted'], reverse=True)

        return jsonify(posts[:25]), 200
    except Exception as ex:
        logger.error("Error getting user posts: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# --------------------------
# AI Voice Controller
# --------------------------

@app.route('/api/ai/voice/debug-character', methods=['GET'])
def debug_character_voice():
    """Debug endpoint to test popularCharacters collection access"""
    try:
        character_id = request.args.get('character_id', 'test_character')
        
        debug_info = {
            "timestamp": datetime.now().isoformat(),
            "character_id": character_id,
            "tests": {}
        }
        
        # Test 1: Check if popularCharacters collection exists
        try:
            collections = db.collections()
            collection_names = [col.id for col in collections]
            debug_info["tests"]["collection_exists"] = {
                "success": "popularCharacters" in collection_names,
                "all_collections": collection_names
            }
        except Exception as e:
            debug_info["tests"]["collection_exists"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 2: Try to get the specific document
        try:
            char_doc = db.collection('popularCharacters').document(character_id).get()
            debug_info["tests"]["document_lookup"] = {
                "success": char_doc.exists,
                "document_data": char_doc.to_dict() if char_doc.exists else None
            }
        except Exception as e:
            debug_info["tests"]["document_lookup"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 3: List some documents in popularCharacters
        try:
            chars_ref = db.collection('popularCharacters').limit(5)
            sample_docs = []
            for doc in chars_ref.stream():
                sample_docs.append({
                    "id": doc.id,
                    "data": doc.to_dict()
                })
            debug_info["tests"]["sample_documents"] = {
                "success": True,
                "count": len(sample_docs),
                "documents": sample_docs
            }
        except Exception as e:
            debug_info["tests"]["sample_documents"] = {
                "success": False,
                "error": str(e)
            }
        
        return jsonify({"success": True, "debug_info": debug_info}), 200
        
    except Exception as ex:
        logger.error("Error in debug character voice: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/voice/test', methods=['POST'])
def test_voice_endpoint():
    """Simple test endpoint to verify JSON processing"""
    try:
        data = request.get_json()
        logger.info(f"[Voice Test] Received data: {data}")
        
        return jsonify({
            "success": True,
            "received_data": data,
            "data_type": str(type(data)),
            "content_type": request.content_type
        }), 200
        
    except Exception as ex:
        logger.error("Error in test voice endpoint: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


AI_CHAT_API_URL = "https://ai-apis-912424781531.us-east1.run.app/chat/popularCharacter"
VOICE_CHAT_COST = 25

# ElevenLabs 권장 모델
ELEVEN_MODEL_ID = "eleven_multilingual_v2"
ELEVEN_API_BASE = "https://api.elevenlabs.io"
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # Cloud Run env에 반드시 설정
DEFAULT_VOICE_ID = os.getenv("DEFAULT_VOICE_ID", "NOpBlnGInO9m6vDvFkFC")

# 필수 키 체크 (운영 시 앞 6글자만 찍음)
if not ELEVEN_API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY is not set in environment")
app.logger.info(f"[boot] XI={ELEVEN_API_KEY[:6]}*** DEFAULT_VOICE_ID={DEFAULT_VOICE_ID}")

_session = requests.Session()
_session.headers.update({
    "xi-api-key": ELEVEN_API_KEY,
    "Content-Type": "application/json"
})

def _log_eleven_error(where, resp):
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    app.logger.error(f"[ElevenLabs]{where} status={resp.status_code} body={body}")
def _sanitize_voice_name(raw_name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9 _-]", "", str(raw_name)).strip()
    if len(name) < 3:
        name = "Custom Character"
    return f"{name} Style"

def personality_to_description(name, personality):
    # 정책 이슈 줄이려고 name은 설명에서 제거
    text = (personality or "").lower()
    gender = "female" if any(k in text for k in ["diva","queen","female","she","her"]) else "male"
    age = "young" if any(k in text for k in ["young","youthful","teen"]) else "middle-aged"
    if any(k in text for k in ["british","uk","london"]):
        accent = "british"
    elif any(k in text for k in ["spanish","latin","argentin"]):
        accent = "spanish"
    else:
        accent = "american"
    tone = "confident and bright" if any(k in text for k in ["confident","bright","upbeat","lively","pop"]) else "natural"
    pacing = "medium to fast" if any(k in text for k in ["upbeat","lively","pop"]) else "medium"
    emotion = "upbeat and lively" if any(k in text for k in ["upbeat","lively","pop"]) else "warm"
    desc = (
        f"A {gender} {age} {accent} voice. "
        f"Tone {tone}. Pacing {pacing}. Emotional color {emotion}. "
        f"Broadcast clarity. Noise suppressed. Natural, not over-acted."
    )
    # 20자 미만이면 API가 422 내리므로 보강
    if len(desc) < 20:
        desc = "A natural, warm, clear speaking voice suitable for conversation. Broadcast clarity."
    return desc[:1000]

def create_voice(name, description):
    """
    Flow:
      1) POST /v1/text-to-voice/design  -> previews[].generated_voice_id
      2) POST /v1/text-to-voice         -> voice_id
    """
    # 1) 프리뷰 생성
    design_payload = {
        "voice_description": description,
        "auto_generate_text": True,  # 문구 자동
        # "model_id": "eleven_multilingual_ttv_v2"  # 명시하고 싶으면 주석 해제
    }
    r1 = _session.post(f"{ELEVEN_API_BASE}/v1/text-to-voice/design", json=design_payload, timeout=60)
    if r1.status_code != 200:
        _log_eleven_error("design", r1)
        return None

    j1 = r1.json() or {}
    previews = j1.get("previews") or []
    if not previews or not previews[0].get("generated_voice_id"):
        app.logger.error(f"[ElevenLabs] design returned no previews name={name} desc_head={description[:60]}")
        return None

    generated_voice_id = previews[0]["generated_voice_id"]

    # 2) 실제 보이스 생성
    create_payload = {
        "voice_name": _sanitize_voice_name(name),
        "voice_description": description,
        "generated_voice_id": generated_voice_id
    }
    r2 = _session.post(f"{ELEVEN_API_BASE}/v1/text-to-voice", json=create_payload, timeout=60)
    if r2.status_code != 200:
        _log_eleven_error("create", r2)
        return None

    vid = (r2.json() or {}).get("voice_id")
    app.logger.info(f"[create_voice] new voice_id={vid} for name={name}")
    return vid
def tts_generate(voice_id, text):
    url = f"{ELEVEN_API_BASE}/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVEN_API_KEY or "",
    }
    # 텍스트 길이 방어
    safe_text = (text or "").strip()
    if len(safe_text) > 5000:
        safe_text = safe_text[:5000]

    attempts = []

    def _call(payload, tag, timeout=120):
        r = _session.post(url, data=json.dumps(payload), timeout=timeout, headers=headers)
        rid = r.headers.get("x-request-id") or r.headers.get("x-eleven-request-id")
        ct  = r.headers.get("Content-Type", "")
        prev = r.text[:500] if r.text else ""
        app.logger.error(f"[ElevenLabs]{tag} status={r.status_code} ct={ct} req_id={rid} prev={prev}")
        return r

    # try 1: 지정 모델
    payload1 = {
        "text": safe_text,
        "model_id": ELEVEN_MODEL_ID,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
    }
    r1 = _call(payload1, "tts-try1")
    if r1.status_code == 200:
        return r1.content, None
    attempts.append(("try1", r1.status_code, r1.text[:500]))

    # try 2: model_id 제거(서버가 자동선택)
    payload2 = dict(payload1); payload2.pop("model_id", None)
    r2 = _call(payload2, "tts-try2")
    if r2.status_code == 200:
        return r2.content, None
    attempts.append(("try2", r2.status_code, r2.text[:500]))

    # try 3: 짧은 텍스트 핑
    payload3 = dict(payload2); payload3["text"] = "Hello."
    r3 = _call(payload3, "tts-try3", timeout=60)
    if r3.status_code == 200:
        app.logger.warning("[ElevenLabs] TTS ping ok but main text failed → content/length/safety suspected")
        return None, {"reason": "ping_ok_main_failed", "code": r2.status_code}

    attempts.append(("try3", r3.status_code, r3.text[:500]))
    # 에러 요약 반환
    return None, {"attempts": attempts}

def tts_ping(voice_id):
    audio = tts_generate(voice_id, "Voice check for initialization.")
    return audio is not None

def tts_ping_retry(voice_id, attempts=3, first_wait=0.8):
    wait = first_wait
    for i in range(attempts):
        if tts_ping(voice_id):
            return True
        app.logger.warning(f"[tts_ping] retry {i+1}/{attempts} voice_id={voice_id}")
        time.sleep(wait)
        wait *= 2
    return False
def ensure_voice_id_for_character(ai_character_id: str, *, force_create: bool=False):
    char_ref = db.collection("popularCharacters").document(ai_character_id)
    snap = char_ref.get()
    if not snap.exists:
        return None, "AI character not found", 404
    char = snap.to_dict() or {}

    if char.get("voice_enabled", True) is False:
        return None, "Voice disabled for this character", 400

    name = char.get("name", "Character")
    now_iso = datetime.now(timezone.utc).isoformat()

    existing_voice_id = char.get("voice_id")
    app.logger.info(f"[ensure] start ai_character_id={ai_character_id} name={name} existing_voice_id={existing_voice_id} force_create={force_create}")

    # 이미 voice_id가 있고 강제 생성 아님 → 바로 리턴
    if existing_voice_id and not force_create:
        data = {
            "voice_id": existing_voice_id,
            "was_created": False,
            "name": name,
            "description_used": char.get("voice_description_used", ""),
            "source": char.get("last_voice_source", "existing"),
            "checked_at": now_iso
        }
        try:
            char_ref.update({
                "last_voice_check_at": datetime.now(timezone.utc),
                "last_voice_source": data["source"]
            })
        except Exception as e:
            app.logger.error(f"[ensure] Firestore update failed(existing): {e}")
        return data, None, 200

    # 생성 시도
    full_personality = f"{name} - {char.get('personality', '')}"
    desc = personality_to_description(name, full_personality)
    app.logger.info(f"[ensure] creating voice for {name} desc_head={desc[:60]}...")

    new_voice_id = create_voice(name, desc)
    if not new_voice_id:
        app.logger.error(f"[ensure] create_voice failed ai_character_id={ai_character_id} name={name}")
        # 폴백
        if DEFAULT_VOICE_ID:
            app.logger.warning(f"Falling back to DEFAULT_VOICE_ID={DEFAULT_VOICE_ID} ai_character_id={ai_character_id} name={name}")
            try:
                char_ref.update({
                    "voice_id": DEFAULT_VOICE_ID,
                    "voice_description_used": "[fallback default voice]",
                    "voice_verified": True,
                    "last_voice_check_at": datetime.now(timezone.utc),
                    "last_voice_source": "fallback",
                    "last_voice_create_failed_at": datetime.now(timezone.utc)
                })
            except Exception as e:
                app.logger.error(f"[ensure] Firestore update failed(fallback): {e}")
            data = {
                "voice_id": DEFAULT_VOICE_ID,
                "was_created": False,
                "name": name,
                "description_used": "[fallback default voice]",
                "source": "fallback",
                "checked_at": now_iso
            }
            return data, None, 200
        return None, "Failed to create voice", 502

    # 생성 후 핑 재시도
    if not tts_ping_retry(new_voice_id):
        app.logger.error(f"[ensure] TTS ping failed for new_voice_id={new_voice_id}")
        if DEFAULT_VOICE_ID:
            app.logger.warning(f"Falling back to DEFAULT_VOICE_ID={DEFAULT_VOICE_ID} ai_character_id={ai_character_id} name={name}")
            try:
                char_ref.update({
                    "voice_id": DEFAULT_VOICE_ID,
                    "voice_description_used": "[fallback default voice]",
                    "voice_verified": True,
                    "last_voice_check_at": datetime.now(timezone.utc),
                    "last_voice_source": "fallback",
                    "last_voice_create_failed_at": datetime.now(timezone.utc)
                })
            except Exception as e:
                app.logger.error(f"[ensure] Firestore update failed(fallback2): {e}")
            data = {
                "voice_id": DEFAULT_VOICE_ID,
                "was_created": False,
                "name": name,
                "description_used": "[fallback default voice]",
                "source": "fallback",
                "checked_at": now_iso
            }
            return data, None, 200
        return None, "Failed to create voice", 502

    # 성공 저장
    try:
        char_ref.update({
            "voice_id": new_voice_id,
            "voice_description_used": desc,
            "voice_verified": True,
            "last_voice_check_at": datetime.now(timezone.utc),
            "last_voice_source": "created",
            "last_voice_create_failed_at": None
        })
    except Exception as e:
        app.logger.error(f"[ensure] Firestore update failed(created): {e}")

    data = {
        "voice_id": new_voice_id,
        "was_created": True,
        "name": name,
        "description_used": desc,
        "source": "created",
        "checked_at": now_iso
    }
    return data, None, 200

@app.route('/api/ai/voice/ensure', methods=['POST'])
def ensure_voice_for_character():
    body = request.get_json(force=True) or {}
    ai_character_id = body.get("ai_character_id")
    force_create = bool(body.get("force_create"))  # 디버깅/관리용
    if not ai_character_id:
        return jsonify({"success": False, "error": "Missing ai_character_id"}), 400

    data, err_msg, code = ensure_voice_id_for_character(ai_character_id, force_create=force_create)
    if err_msg:
        return jsonify({"success": False, "error": err_msg}), code

    return jsonify({
        "success": True,
        "data": {
            "voice_id": data["voice_id"],
            "was_created": data["was_created"],
            "character_name": data["name"],
            "description_used": data["description_used"],
            "voice_source": data["source"],
            "checked_at": data["checked_at"]
        }
    }), 200


LLM_TIMEOUT = 15

def generate_ai_text(message, ai_character_id, user_id, chat_history):
    url = AI_CHAT_API_URL
    payload = {
        "message": message,
        "ai_id": ai_character_id,
        "user_id": user_id,
        "chat_history": chat_history or []
    }

    try:
        # 1차 호출
        r = requests.post(
            url,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            data=json.dumps(payload),
            timeout=LLM_TIMEOUT,
        )
    except requests.RequestException as e:
        app.logger.exception(f"[llm] request error: {e}")
        # 크래시 없이 None 반환
        return None

    # 상태/헤더/본문 일부 로깅
    ct = r.headers.get("Content-Type", "")
    body_preview = r.text[:500] if r.text else ""
    app.logger.info(f"[llm] status={r.status_code} ct={ct} len={len(r.content)} preview={body_preview}")

    # 비정상 상태코드면 실패
    if r.status_code < 200 or r.status_code >= 300:
        return None

    # Content-Type이 json이 아닐 수 있음 (text/plain 등)
    try:
        resp = r.json()
    except ValueError:
        # json이 아니면 파싱 실패로 간주
        app.logger.error("[llm] non-JSON response")
        return None

    # 다양한 스키마 허용
    # 1) {"data":{"message":"..."}}
    # 2) {"message":"..."}
    # 3) {"output":"..."} 같은 변종도 보호
    msg = (
        (resp.get("data") or {}).get("message")
        or resp.get("message")
        or resp.get("output")
    )

    if not msg or not isinstance(msg, str):
        app.logger.error(f"[llm] missing message in response keys={list(resp.keys())}")
        return None

    return msg.strip()

@app.route('/api/ai/voice/chat', methods=['POST'])
def ai_voice_chat():
    body = request.get_json(force=True) or {}
    user_id = body.get("user_id")
    ai_character_id = body.get("ai_character_id")
    message = body.get("message", "")
    chat_history = body.get("chat_history") or []

    try:
        if not user_id or not ai_character_id or not message:
            return jsonify({"success": False, "error": "Missing required fields", "stage": "input"}), 400

        # 1) ensure
        try:
            data, err_msg, code = ensure_voice_id_for_character(ai_character_id)
            if err_msg:
                app.logger.warning(f"[chat] ensure failed code={code} err={err_msg}")
                return jsonify({"success": False, "error": err_msg, "stage": "ensure"}), code
            voice_id = data["voice_id"]
            app.logger.info(f"[chat] voice_id={voice_id} source={data.get('source')}")
        except Exception as e:
            app.logger.exception("[chat] ensure crash")
            return jsonify({"success": False, "error": "Ensure crashed", "stage": "ensure"}), 500

        # 2) AI text
        try:
            ai_text = generate_ai_text(message, ai_character_id, user_id, chat_history)
            if not ai_text:
                return jsonify({"success": False, "error": "AI generation failed", "stage": "llm"}), 500
            app.logger.info(f"[chat] ai_text_len={len(ai_text)}")
        except Exception as e:
            app.logger.exception("[chat] llm crash")
            return jsonify({"success": False, "error": "AI generation crashed", "stage": "llm"}), 500

        # 3) TTS
        try:
            audio_bytes, tts_err = tts_generate(voice_id, ai_text)
            if not audio_bytes:
                app.logger.error(f"[chat] tts failed detail={tts_err}")
                return jsonify({"success": False, "error": "TTS failed", "stage": "tts", "detail": tts_err}), 502
            app.logger.info(f"[chat] tts_ok bytes={len(audio_bytes)}")
        except Exception:
            app.logger.exception("[chat] tts crash")
            return jsonify({"success": False, "error": "TTS crashed", "stage": "tts"}), 500

        # 4) coins
        try:
            user_ref = db.collection("humanUsers").document(user_id)
            user_snap = user_ref.get()
            if not getattr(user_snap, "exists", False):
                return jsonify({"success": False, "error": "User not found", "stage": "coins"}), 404
            balance = int((user_snap.to_dict() or {}).get("balance", 0))
            if balance < VOICE_CHAT_COST:
                return jsonify({"success": False, "error": "Insufficient balance",
                                "current_balance": balance, "required_coins": VOICE_CHAT_COST, "stage": "coins"}), 402
            user_ref.update({"balance": balance - VOICE_CHAT_COST})
            new_balance = balance - VOICE_CHAT_COST
            app.logger.info(f"[chat] coins ok new_balance={new_balance}")
        except Exception as e:
            app.logger.exception("[chat] coins crash")
            return jsonify({"success": False, "error": "Coin deduction crashed", "stage": "coins"}), 500

        # 5) persist
        try:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            conv_ref = db.collection("voice_conversations").document()
            conv_ref.set({
                "user_id": user_id,
                "ai_character_id": ai_character_id,
                "user_message": message,
                "ai_response": ai_text,
                "voice_id": voice_id,
                "coins_spent": VOICE_CHAT_COST,
                "timestamp": datetime.now(timezone.utc)
            })
            db.collection("voice_analytics").add({
                "user_id": user_id,
                "ai_character_id": ai_character_id,
                "conversation_id": conv_ref.id,
                "timestamp": datetime.now(timezone.utc),
                "platform": "server"
            })
        except Exception as e:
            app.logger.exception("[chat] persist crash")
            return jsonify({"success": False, "error": "Persist crashed", "stage": "persist"}), 500

        return jsonify({
            "success": True,
            "data": {
                "user_message_text": message,
                "ai_response_text": ai_text,
                "ai_response_audio": audio_b64,
                "conversation_id": conv_ref.id,
                "coins_spent": VOICE_CHAT_COST,
                "new_balance": new_balance,
                "voice_id": voice_id,
                "voice_source": data.get("source", "existing"),
                "voice_description_used": data.get("description_used",""),
                "character_name": data.get("name","")
            }
        }), 200

    except Exception:
        app.logger.exception("[chat] unhandled top")
        return jsonify({"success": False, "error": "Internal error", "stage": "top"}), 500


@app.route('/api/ai/voice/batch-setup-voices', methods=['POST'])
def batch_setup_voices():
    """Setup voice settings for multiple characters in popularCharacters collection"""
    try:
        data = request.get_json()
        force_update = data.get('force_update', False)
        limit = data.get('limit', 50)  # Process up to 50 characters at a time
        
        # Get characters without voice settings or all if force_update
        if force_update:
            query = db.collection('popularCharacters').limit(limit)
        else:
            # This might not work directly in Firestore, so we'll get all and filter
            query = db.collection('popularCharacters').limit(limit)
        
        characters = []
        updated_count = 0
        
        for doc in query.stream():
            character_data = doc.to_dict()
            character_id = doc.id
            
            # Skip if voice settings exist and not forcing update
            if character_data.get('voice_settings') and not force_update:
                continue
            
            # Generate voice settings
            voice_id = elevenlabs_service.assign_voice_to_character(character_data)
            
            voice_settings = {
                "voice_id": voice_id,
                "voice_enabled": True,
                "custom_voice_settings": elevenlabs_service.default_voice_settings.copy()
            }
            
            # Update the character
            db.collection('popularCharacters').document(character_id).update({
                'voice_settings': voice_settings
            })
            
            characters.append({
                "character_id": character_id,
                "name": character_data.get('name', ''),
                "voice_id": voice_id
            })
            
            updated_count += 1
        
        return jsonify({
            "success": True,
            "message": f"Updated voice settings for {updated_count} characters",
            "updated_characters": characters
        }), 200
        
    except Exception as ex:
        logger.error("Error batch setting up voices: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# --------------------------
# AI Controller
# --------------------------

def generate_ai_response(message, ai_character_id):
    try:
        ai_character = None
        if ai_character_id:
            # Try popularCharacters collection first
            doc_ref = db.collection("popularCharacters").document(ai_character_id)
            snapshot = doc_ref.get()
            ai_character = snapshot.to_dict()

        personality = ai_character.get('personality', ai_character.get('Personality', 'friendly and helpful'))
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You are an AI character with the following personality: {personality}. Respond as this character would, staying true to their personality. Keep responses conversational and engaging."},
                {"role": "user", "content": message}
            ],
            max_tokens=150,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()
    except Exception as ex:
        logger.error("Error generating AI response: %s", ex)
        return "Sorry, I'm having trouble responding right now."

@app.route('/api/ai/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        response = generate_ai_response(data.get("Message"), data.get("AICharacterId"))

        chat_response = {
            "Message": response,
            "ConversationId": str(uuid.uuid4())
        }

        return jsonify({"success": True, "data": chat_response}), 200
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        return jsonify({"success": False, "error": "Failed to process chat", "code": "CHAT_ERROR"}), 500

@app.route('/api/ai/popular-character-name', methods=['POST'])
def update_popular_character_name():
    try:
        doc_id = request.args.get('docId')
        name = request.json.get('name')

        if not doc_id:
            return jsonify({"success": False, "error": "Document ID (docId) is required"}), 400

        if not name:
            return jsonify({"success": False, "error": "Name is required"}), 400

        character_ref = db.collection('popularCharacters').document(doc_id)
        character_ref.set({'name': name}, merge=True)

        return jsonify({"success": True, "message": "Name field updated successfully."}), 200

    except Exception as ex:
        logger.error("Error updating name field: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/upvote', methods=['POST'])
def upvote():
    try:
        name = request.json.get('Name')
        if not name:
            return jsonify({"success": False, "error": "Popular character's name is required"}), 400

        character_ref = db.collection('popularCharacters').document(name)
        character_doc = character_ref.get()

        if not character_doc.exists:
            return jsonify({"success": False, "error": "Character not found"}), 404

        data = character_doc.to_dict()
        if 'upvotes' in data:
            character_ref.update({'upvotes': firestore.Increment(1)})
        else:
            character_ref.update({'upvotes': 1})

        return jsonify({"success": True, "message": "Upvote successful."}), 200
    except Exception as ex:
        logger.error("Error upvoting: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/downvote', methods=['POST'])
def downvote():
    try:
        name = request.json.get('Name')
        if not name:
            return jsonify({"success": False, "error": "Popular character's name is required"}), 400

        character_ref = db.collection('popularCharacters').document(name)
        character_doc = character_ref.get()

        if not character_doc.exists:
            return jsonify({"success": False, "error": "Character not found"}), 404

        data = character_doc.to_dict()
        if 'downvotes' in data:
            character_ref.update({'downvotes': firestore.Increment(1)})
        else:
            character_ref.update({'downvotes': 1})

        return jsonify({"success": True, "message": "Downvote successful."}), 200
    except Exception as ex:
        logger.error("Error downvoting: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/chat-counter', methods=['GET'])
def chat_counter():
    try:
        name = request.args.get('Name')
        if not name:
            return jsonify({"success": False, "error": "Popular character's name is required"}), 400

        character_ref = db.collection('popularCharacters').document(name)
        character_doc = character_ref.get()

        if not character_doc.exists:
            return jsonify({"success": False, "error": "Character not found"}), 404

        data = character_doc.to_dict()
        return jsonify({"success": True, "numberOfChats": data.get('numberOfChats', 0)}), 200
    except Exception as ex:
        logger.error("Error retrieving numberOfChats: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/create-ai-user', methods=['POST'])
def create_ai_user():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "AI User data is required", "code": "INVALID_AI_USER_DATA"}), 400

        username = data.get("Username")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "MISSING_USERNAME"}), 400

        # Check if a user with the same username already exists
        existing_users = db.collection('aiUsers').where("username", "==", username).stream()
        if any(existing_users):
            return jsonify({"success": False, "error": "Username already exists", "code": "DUPLICATE_USERNAME"}), 400

        character_data = {
            "name": data.get("Name"),
            "age": data.get("Age"),
            "gender": data.get("Gender"),
            "bio": data.get("Bio"),
            "popularity": bool(data.get("Popularity", False)),
            "followers": [],
            "followers_count": 0,
            "following": [],
            "following_count": 0,
            "personality": data.get("Personality"),
            "posts": [],
            "category": [],
            "conversations": [],
            "username": username,
            "voice_settings": {
                "voice_id": elevenlabs_service.assign_voice_to_character({
                    "gender": data.get("Gender"),
                    "personality": data.get("Personality")
                }),
                "voice_enabled": True,
                "custom_voice_settings": elevenlabs_service.default_voice_settings.copy()
            }
        }

        doc_ref = db.collection('aiUsers').document(username).set(character_data)

        return jsonify({"AiUserId": username}), 200
        # return jsonify({"AiUserId": data.get("username")}), 200
        # return jsonify({"AiUserId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error creating AI User: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "CHARACTER_CREATE_ERROR"}), 500

@app.route('/api/ai/update-ai-user', methods=['POST'])
def update_ai_profile():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        update_data = {
            "name": data.get("Name"),
            "bio": data.get("Bio"),
            "username": data.get("UserName")
        }

        # Update the document in Firestore
        db.collection('aiUsers').document(data.get("username")).update(update_data)
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating profile: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-ai-user', methods=['GET'])
def get_ai_profile():
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({"success": False, "error": "Username is required"}), 400

        user_doc = db.collection('aiUsers').document(username).get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"success": True, "data": user_data}), 200
    except Exception as ex:
        logger.error("Error retrieving profile: %s", ex)
        return jsonify({"success": False, "error": "Failed to retrieve profile", "code": "PROFILE_RETRIEVE_ERROR"}), 500

# @app.route('/api/ai/carousel/characters', methods=['GET'])
# def get_carousel_characters():
#     try:
#         # Retrieve all characters from the 'popularCharacters' collection
#         characters_ref = db.collection('popularCharacters')
#         snapshot = characters_ref.stream()

#         # Convert all documents to dictionaries
#         all_characters = []
#         for doc in snapshot:
#             character = doc.to_dict()
#             all_characters.append(character)

#         # Get 20 random characters
#         num_characters_to_show = 20
        
#         # If we have fewer than 20 characters, return all of them
#         if len(all_characters) <= num_characters_to_show:
#             selected_characters = all_characters
#         else:
#             # Shuffle the characters and select 20 random ones
#             random.shuffle(all_characters)
#             selected_characters = all_characters[:num_characters_to_show]

#         return jsonify(selected_characters), 200

#     except Exception as ex:
#         logger.error("Error retrieving carousel characters: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/carousel/characters', methods=['GET'])
def get_carousel_characters():
    try:
        # Get the showPopularFirst query parameter
        show_popular_first = request.args.get('showPopularFirst', 'false').lower() == 'true'
        
        # Build the query
        characters_ref = db.collection('popularCharacters')
        if show_popular_first:
            query = characters_ref.where('showFirst', '==', True)
        else:
            query = characters_ref

        # Fetch documents
        snapshot = query.stream()

        # Convert docs to dicts with ID
        filtered_characters = []
        for doc in snapshot:
            character = doc.to_dict()
            character['id'] = doc.id  
            filtered_characters.append(character)

        # Limit to 20 random characters
        num_characters_to_show = 20
        if len(filtered_characters) <= num_characters_to_show:
            selected_characters = filtered_characters
        else:
            random.shuffle(filtered_characters)
            selected_characters = filtered_characters[:num_characters_to_show]

        return jsonify(selected_characters), 200

    except Exception as ex:
        logger.error("Error retrieving carousel characters: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@app.route('/api/ai/follow', methods=['POST'])
def follow_ai_user():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated AI user)
        following_id = data.get("FollowingId")  # B (AI user to follow)

        follower_ref = db.collection('aiUsers').document(follower_id)
        following_ref = db.collection('aiUsers').document(following_id)

        follower_doc = follower_ref.get()
        following_doc = following_ref.get()

        if not follower_doc.exists or not following_doc.exists:
            return jsonify({"success": False, "error": "AI User not found"}), 404

        follower_data = follower_doc.to_dict()
        if following_id not in follower_data.get("following", []):
            follower_data["following"].append(following_id)
            follower_ref.update({"following": follower_data["following"], "following_count": firestore.Increment(1)})

        following_data = following_doc.to_dict()
        if follower_id not in following_data.get("followers", []):
            following_data["followers"].append(follower_id)
            following_ref.update({"followers": following_data["followers"], "followers_count": firestore.Increment(1)})

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error adding AI follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/unfollow', methods=['POST'])
def unfollow_ai_user():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")
        following_id = data.get("FollowingId")

        follower_ref = db.collection('aiUsers').document(follower_id)
        following_ref = db.collection('aiUsers').document(following_id)

        follower_ref.update({"following": firestore.ArrayRemove([following_id]), "following_count": firestore.Increment(-1)})
        following_ref.update({"followers": firestore.ArrayRemove([follower_id]), "followers_count": firestore.Increment(-1)})
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing AI follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-followers', methods=['POST'])
def get_ai_followers():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        user_doc = db.collection('aiUsers').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "AI User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"followers": user_data.get("followers", [])}), 200
    except Exception as ex:
        logger.error("Error getting AI followers: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-following', methods=['POST'])
def get_ai_following():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        user_doc = db.collection('aiUsers').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "AI User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"following": user_data.get("following", [])}), 200
    except Exception as ex:
        logger.error("Error getting AI following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/remove-from-followers', methods=['POST'])
def remove_ai_follower():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        follower_id = data.get("FollowerId")

        user_ref = db.collection('aiUsers').document(user_id)
        follower_ref = db.collection('aiUsers').document(follower_id)

        user_ref.update({"followers": firestore.ArrayRemove([follower_id]), "followers_count": firestore.Increment(-1)})
        follower_ref.update({"following": firestore.ArrayRemove([user_id]), "following_count": firestore.Increment(-1)})
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing AI follower: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/remove-from-following', methods=['POST'])
def remove_ai_following():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        following_id = data.get("FollowingId")

        user_ref = db.collection('aiUsers').document(user_id)
        following_ref = db.collection('aiUsers').document(following_id)

        user_ref.update({"following": firestore.ArrayRemove([following_id]), "following_count": firestore.Increment(-1)})
        following_ref.update({"followers": firestore.ArrayRemove([user_id]), "followers_count": firestore.Increment(-1)})
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing AI following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/generate-image', methods=['POST'])
def generate_image():
    try:
        # Add image generation logic here
        image_url = f"https://storage.googleapis.com/inzonebackend.appspot.com/generated-images/{uuid.uuid4().hex}.png"


        return jsonify({"success": True, "data": {"ImageUrl": image_url}}), 200
    except ApiException as ex:
        return jsonify({"success": False, "error": ex.args[0], "code": ex.error_code}), ex.status_code
    except Exception as ex:
        logger.error("Error generating image: %s", ex)
        return jsonify({"success": False, "error": "Failed to generate image", "code": "IMAGE_GENERATION_ERROR"}), 500


# ---------------------------
# AI Content Controller
# ---------------------------

class AIContentGenerationService:
    def generate_ai_post(self, ai_user_id):
        # Mock implementation of AI post generation
        return {
            "Category": "Tech",
            "MainCategory": "AI",
            "SubCategory": "Machine Learning",
            "Comments": [],
            "DatePosted": firestore.SERVER_TIMESTAMP,
            "Likes": 0,
            "Post": {
                "ImageContent": [],
                "TextContent": "This is a generated AI post.",
                "VideoContent": []
            },
            "UserName": ai_user_id,
            "UserReferences": f"aiUsers/{ai_user_id}/"
        }

content_service = AIContentGenerationService()

@app.route('/ai-content/generate-post', methods=['POST'])
def generate_post():
    try:
        ai_user_id = request.get_json()
        post = content_service.generate_ai_post(ai_user_id)

        # Save the generated post
        post_data = {
            "category": post["Category"],
            "main_category": post["MainCategory"],
            "sub_category": post["SubCategory"],
            "comments": post["Comments"],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": post["Likes"],
            "post": {
                "image_content": post["Post"]["ImageContent"],
                "textContent": post["Post"]["TextContent"],
                "video_content": post["Post"]["VideoContent"]
            },
            "username": post["UserName"],
            "user_references": post["UserReferences"]
        }

        doc_ref = db.collection('posts').add(post_data)
        post_id = doc_ref[1].id


        return jsonify({"success": True, "data": {**post, "Id": post_id}}), 200
    except Exception as ex:
        logger.error("Error generating AI post: %s", ex)
        return jsonify({"success": False, "error": "Failed to generate post", "code": "POST_GENERATION_ERROR"}), 500

# ---------------------------
# Group Chat
# ---------------------------
# modifying profile picture
# modifying groupchat name
# return number people in groupchat

@app.route('/group/add-participant', methods=['POST'])
def add_participant():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    user_id = data.get('user_id')
    username = data.get('username')
    
    if not all([groupchat_id, user_id, username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupChats').document(groupchat_id)
    groupchat = groupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_data = groupchat.to_dict()
    if user_id in groupchat_data['user_ids']:
        return jsonify({"error": "User already in the group chat"}), 400
    
    groupchat_ref.update({
        'user_ids': firestore.ArrayUnion([user_id]),
        'usernames': firestore.ArrayUnion([username])
    })
    
    return jsonify({"message": "Participant added successfully"}), 200

@app.route('/group/delete-participant', methods=['POST'])
def delete_participant():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    user_id = data.get('user_id')
    username = data.get('username')
    
    if not all([groupchat_id, user_id, username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupChats').document(groupchat_id)
    groupchat = gsroupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_data = groupchat.to_dict()
    if user_id not in groupchat_data['user_ids']:
        return jsonify({"error": "User not in the group chat"}), 400
    
    groupchat_ref.update({
        'user_ids': firestore.ArrayRemove([user_id]),
        'usernames': firestore.ArrayRemove([username])
    })
    
    return jsonify({"message": "Participant removed successfully"}), 200

@app.route('/group/create-groupchat', methods=['POST'])
def create_group_chat():
    data = request.json
    groupchat_name = data.get('groupchat_name')
    bio = data.get('bio')
    creator_id = data.get('creator_id')
    creator_username = data.get('creator_username')
    
    if not all([groupchat_name, creator_id, creator_username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    new_groupchat = {
        'groupchat_name': groupchat_name,
        'bio': bio,
        'user_ids': [creator_id],
        'usernames': [creator_username],
        'ai_usernames': [],
        'messages': [],
        'date_created': firestore.SERVER_TIMESTAMP,
        'groupchat_doc_id': data.get("GroupchatDocId")
    }
    
    doc_ref = db.collection('groupChats').document(data.get("GroupchatDocId")).set(post_data)    
    return jsonify({
        "message": "Group chat created successfully",
        "groupchat_id": doc_ref[1].id
    }), 201

@app.route('/group/add-ai-character', methods=['POST'])
def add_ai_character():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    ai_username = data.get('ai_username')
    
    if not all([groupchat_id, ai_username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupChats').document(groupchat_id)
    groupchat = groupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_ref.update({
        'ai_usernames': firestore.ArrayUnion([ai_username])
    })
    
    return jsonify({"message": "AI character added successfully"}), 200

@app.route('/group/delete-ai-character', methods=['POST'])
def delete_ai_character():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    ai_username = data.get('ai_username')
    
    if not all([groupchat_id, ai_username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupChats').document(groupchat_id)
    groupchat = groupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_data = groupchat.to_dict()
    if ai_username not in groupchat_data['ai_usernames']:
        return jsonify({"error": "AI character not in the group chat"}), 400
    
    groupchat_ref.update({
        'ai_usernames': firestore.ArrayRemove([ai_username])
    })
    
    return jsonify({"message": "AI character removed successfully"}), 200

# ---------------------------
# Premium Group Chat Access Endpoints (Subscription Model using InCash)
# ---------------------------
@app.route('/groups/available', methods=['GET'])
def available_groups():
    groups = [doc.to_dict() for doc in db.collection('groups').stream()]
    return jsonify({'groups': groups})

@app.route('/groups/join', methods=['POST'])
def join_group():
    data = request.json
    user_id = data['user_id']
    group_id = data['group_id']
    # The subscription tier: expected values are "free", "pass", or "vip"
    tier = data.get('tier', 'free').lower()

    group_ref = db.collection('groups').document(group_id)
    group = group_ref.get().to_dict()
    user_ref = db.collection('humanUsers').document(user_id)
    user_data = user_ref.get().to_dict()

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    # Determine pricing and duration based on the tier.
    # The group document should contain pricing and duration info for each tier.
    if tier == 'free':
        price = 0
        duration = group.get('free_duration')  # For example, could be None (or indefinite) or set to a default period
    elif tier == 'pass':
        price = group.get('pass_price', 0)
        duration = group.get('pass_duration', 1)  # Default to 1 day if not provided
    elif tier == 'vip':
        price = group.get('vip_price', 0)
        duration = group.get('vip_duration', 30)  # Default to 30 days if not provided
    else:
        return jsonify({'error': 'Invalid tier specified'}), 400
    
    # For tiers with a price, ensure the user has sufficient funds.
    if price > 0 and user_data.get('balance', 200) < price:
        return jsonify({'error': 'Insufficient funds'}), 400

    # Deduct funds if necessary.
    if price > 0:
        user_ref.update({'balance': firestore.Increment(-price)})
    
    # Add the group to the user's groups array in the humanUsers document.
    user_ref.update({'groups': firestore.ArrayUnion([group_id])})
    
    # Calculate the subscription end time if a duration is provided.
    if duration:
        subscription_end = datetime.utcnow() + timedelta(days=duration)
        subscription_end_iso = subscription_end.isoformat()
    else:
        subscription_end_iso = None

    membership_data = {
        'group_id': group_id,
        'tier': tier,
        'subscription_end': subscription_end_iso,
        'joined_at': datetime.utcnow().isoformat()
    }
    
    # Save the group subscription in a subcollection under humanUsers.
    db.collection('humanUsers').document(user_id).collection('groups').document(group_id).set(membership_data)
    
    return jsonify({
        'message': 'Group joined successfully',
        'tier': tier,
        'subscription_end': subscription_end_iso
    })

@app.route('/groups/user-access', methods=['GET'])
def user_access():
    user_id = request.args.get('user_id')
    groups = [doc.to_dict() for doc in db.collection('humanUsers').document(user_id).collection('groups').stream()]
    return jsonify({'groups': groups})

# ---------------------------
# Admin Endpoints
# ---------------------------

@app.route('/admin/store/add-item', methods=['POST'])
def add_item():
    data = request.json
    db.collection('store_items').document(data['id']).set(data)
    return jsonify({'message': 'Item added successfully'})

@app.route('/admin/groups/create', methods=['POST'])
def create_group():
    data = request.json
    db.collection('groups').document(data['id']).set(data)
    return jsonify({'message': 'Group created successfully'})

# --------------------------
# AI Engagement System
# --------------------------

# @app.route('/api/ai/engagement/trigger', methods=['POST'])
# def trigger_ai_engagement():
#     """Manually trigger AI engagement cycle (for testing/admin)"""
#     try:
#         import asyncio
#         # Run the async function in the event loop
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         loop.run_until_complete(ai_engagement_service.process_ai_engagement_cycle())
#         loop.close()
        
#         return jsonify({"success": True, "message": "AI engagement cycle triggered"}), 200
#     except Exception as ex:
#         logger.error("Error triggering AI engagement: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement/config', methods=['GET', 'POST'])
# def ai_engagement_config():
#     """Get or update AI engagement configuration"""
#     try:
#         if request.method == 'GET':
#             config = {
#                 "max_daily_interactions": ai_engagement_service.config.max_daily_interactions,
#                 "min_interaction_interval_hours": ai_engagement_service.config.min_interaction_interval_hours,
#                 "max_interaction_interval_hours": ai_engagement_service.config.max_interaction_interval_hours,
#                 "comment_probability": ai_engagement_service.config.comment_probability,
#                 "like_probability": ai_engagement_service.config.like_probability,
#                 "dm_probability": ai_engagement_service.config.dm_probability,
#                 "dm_cooldown_hours": ai_engagement_service.config.dm_cooldown_hours
#             }
#             return jsonify({"success": True, "data": config}), 200
        
#         else:  # POST - update config
#             data = request.get_json()
#             if data.get("max_daily_interactions"):
#                 ai_engagement_service.config.max_daily_interactions = data["max_daily_interactions"]
#             if data.get("comment_probability"):
#                 ai_engagement_service.config.comment_probability = data["comment_probability"]
#             if data.get("like_probability"):
#                 ai_engagement_service.config.like_probability = data["like_probability"]
#             if data.get("dm_probability"):
#                 ai_engagement_service.config.dm_probability = data["dm_probability"]
            
#             return jsonify({"success": True, "message": "Configuration updated"}), 200
            
#     except Exception as ex:
#         logger.error("Error with AI engagement config: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement/stats', methods=['GET'])
# def ai_engagement_stats():
#     """Get AI engagement statistics"""
#     try:
#         # Get today's interactions
#         today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
#         interactions_ref = db.collection('aiInteractions')
#         today_query = interactions_ref.where('timestamp', '>=', today_start)
#         today_snapshot = today_query.stream()
        
#         today_interactions = [doc.to_dict() for doc in today_snapshot]
        
#         # Calculate stats
#         stats = {
#             "total_today": len(today_interactions),
#             "comments_today": len([i for i in today_interactions if i.get('interaction_type') == 'comment']),
#             "likes_today": len([i for i in today_interactions if i.get('interaction_type') == 'like']),
#             "dms_today": len([i for i in today_interactions if i.get('interaction_type') == 'dm']),
#             "active_ai_users": len(set([i.get('ai_user_id') for i in today_interactions])),
#             "interactions_by_ai": {}
#         }
        
#         # Count interactions per AI
#         for interaction in today_interactions:
#             ai_id = interaction.get('ai_user_id')
#             if ai_id:
#                 if ai_id not in stats["interactions_by_ai"]:
#                     stats["interactions_by_ai"][ai_id] = {"total": 0, "comments": 0, "likes": 0, "dms": 0}
                
#                 stats["interactions_by_ai"][ai_id]["total"] += 1
#                 interaction_type = interaction.get('interaction_type')
#                 if interaction_type in ["comments", "likes", "dms"]:
#                     stats["interactions_by_ai"][ai_id][interaction_type] += 1
        
#         return jsonify({"success": True, "data": stats}), 200
        
#     except Exception as ex:
#         logger.error("Error getting AI engagement stats: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement/interactions/<ai_user_id>', methods=['GET'])
# def get_ai_interactions(ai_user_id):
#     """Get recent interactions for a specific AI user"""
#     try:
#         limit = int(request.args.get('limit', 50))
        
#         interactions_ref = db.collection('aiInteractions')
#         query = interactions_ref.where('ai_user_id', '==', ai_user_id)\
#                               .order_by('timestamp', direction=firestore.Query.DESCENDING)\
#                               .limit(limit)
        
#         snapshot = query.stream()
#         interactions = [doc.to_dict() for doc in snapshot]
        
#         return jsonify({"success": True, "data": interactions}), 200
        
#     except Exception as ex:
#         logger.error("Error getting AI interactions: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/direct-messages', methods=['POST'])
# def create_direct_message():
#     """Create a direct message (for both AI and human users)"""
#     try:
#         data = request.get_json()
        
#         dm_data = {
#             "sender_id": data.get("sender_id"),
#             "recipient_id": data.get("recipient_id"),
#             "content": data.get("content"),
#             "timestamp": firestore.SERVER_TIMESTAMP,
#             "read": False,
#             "isAIGenerated": data.get("isAIGenerated", False)
#         }
        
#         doc_ref = db.collection('direct_messages').add(dm_data)
#         return jsonify({"success": True, "data": {"message_id": doc_ref[1].id}}), 200
        
#     except Exception as ex:
#         logger.error("Error creating direct message: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/direct-messages/<user_id>', methods=['GET'])
# def get_direct_messages(user_id):
#     """Get direct messages for a user"""
#     try:
#         limit = int(request.args.get('limit', 50))
        
#         # Get messages where user is sender or recipient
#         messages_ref = db.collection('direct_messages')
        
#         # Query messages where user is sender
#         sent_query = messages_ref.where('sender_id', '==', user_id).limit(limit)
#         sent_snapshot = sent_query.stream()
#         sent_messages = [doc.to_dict() for doc in sent_snapshot]
        
#         # Query messages where user is recipient
#         received_query = messages_ref.where('recipient_id', '==', user_id).limit(limit)
#         received_snapshot = received_query.stream()
#         received_messages = [doc.to_dict() for doc in received_snapshot]
        
#         # Combine and sort by timestamp
#         all_messages = sent_messages + received_messages
#         all_messages.sort(key=lambda x: x.get('timestamp', datetime.min), reverse=True)
        
#         return jsonify({"success": True, "data": all_messages[:limit]}), 200
        
#     except Exception as ex:
#         logger.error("Error getting direct messages: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/direct-messages/conversation/<user1_id>/<user2_id>', methods=['GET'])
# def get_conversation(user1_id, user2_id):
#     """Get conversation between two users"""
#     try:
#         limit = int(request.args.get('limit', 100))
        
#         messages_ref = db.collection('direct_messages')
        
#         # Get messages between the two users in both directions
#         query1 = messages_ref.where('sender_id', '==', user1_id).where('recipient_id', '==', user2_id)
#         query2 = messages_ref.where('sender_id', '==', user2_id).where('recipient_id', '==', user1_id)
        
#         snapshot1 = query1.stream()
#         snapshot2 = query2.stream()
        
#         messages = []
#         messages.extend([doc.to_dict() for doc in snapshot1])
#         messages.extend([doc.to_dict() for doc in snapshot2])
        
#         # Sort by timestamp
#         messages.sort(key=lambda x: x.get('timestamp', datetime.min))
        
#         return jsonify({"success": True, "data": messages[-limit:]}), 200  # Get most recent messages
        
#     except Exception as ex:
#         logger.error("Error getting conversation: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement/analytics/trends', methods=['GET'])
# def get_engagement_trends():
#     """Get AI engagement trends"""
#     try:
#         days = int(request.args.get('days', 7))
#         trends = engagement_analytics.get_engagement_trends(days)
        
#         return jsonify({"success": True, "data": trends}), 200
        
#     except Exception as ex:
#         logger.error("Error getting engagement trends: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement/analytics/top-ais', methods=['GET'])
# def get_top_engaging_ais():
#     """Get most engaging AI users"""
#     try:
#         days = int(request.args.get('days', 7))
#         limit = int(request.args.get('limit', 10))
        
#         top_ais = engagement_analytics.get_top_engaging_ais(days, limit)
        
#         return jsonify({"success": True, "data": top_ais}), 200
        
#     except Exception as ex:
#         logger.error("Error getting top engaging AIs: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement/analytics/user/<user_id>', methods=['GET'])
# def get_user_ai_interactions_analytics(user_id):
#     """Get AI interaction analytics for a specific user"""
#     try:
#         days = int(request.args.get('days', 30))
#         analytics = engagement_analytics.get_user_ai_interactions(user_id, days)
        
#         return jsonify({"success": True, "data": analytics}), 200
        
#     except Exception as ex:
#         logger.error("Error getting user AI interaction analytics: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/engagement/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """Get AI engagement scheduler status"""
    try:
        status = {
            "running": ai_engagement_scheduler.running,
            "thread_alive": ai_engagement_scheduler.scheduler_thread.is_alive() if ai_engagement_scheduler.scheduler_thread else False
        }
        
        return jsonify({"success": True, "data": status}), 200
        
    except Exception as ex:
        logger.error("Error getting scheduler status: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/engagement/scheduler/control', methods=['POST'])
def control_scheduler():
    """Start or stop the AI engagement scheduler"""
    try:
        data = request.get_json()
        action = data.get("action")  # "start" or "stop"
        
        if action == "start":
            if not ai_engagement_scheduler.running:
                ai_engagement_scheduler.start_scheduler()
                return jsonify({"success": True, "message": "Scheduler started"}), 200
            else:
                return jsonify({"success": False, "message": "Scheduler already running"}), 400
                
        elif action == "stop":
            if ai_engagement_scheduler.running:
                ai_engagement_scheduler.stop_scheduler()
                return jsonify({"success": True, "message": "Scheduler stopped"}), 200
            else:
                return jsonify({"success": False, "message": "Scheduler not running"}), 400
        else:
            return jsonify({"success": False, "error": "Invalid action. Use 'start' or 'stop'"}), 400
            
    except Exception as ex:
        logger.error("Error controlling scheduler: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# ---------------------------
# Notification System Endpoints
# ---------------------------

@app.route('/api/notifications/events/group-message', methods=['POST'])
def handle_group_message_notification():
    """Handle group message notification event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['groupId', 'content', 'senderId', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Get group members to notify
        group_doc = db.collection('groupChats').document(data['groupId']).get()
        if not group_doc.exists:
            return jsonify({"success": False, "error": "Group not found"}), 404
        
        group_data = group_doc.to_dict()
        participants = group_data.get('participants', [])

        # Normalize and deduplicate participant IDs to avoid duplicate notifications
        participant_ids = []
        seen_ids = set()
        for participant in participants:
            pid = None
            if isinstance(participant, dict):
                pid = participant.get('uid')
            elif isinstance(participant, str):
                pid = participant

            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                participant_ids.append(pid)

        # Create notification events for each unique participant (except sender)
        notifications_created = 0
        for participant_id in participant_ids:
            if not participant_id or participant_id == data['senderId']:
                continue

            # Check if user has group notifications enabled
            user_doc = db.collection('humanUsers').document(participant_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                prefs = user_data.get('notificationPrefs', {})
                categories = prefs.get('categories', {})
                group_prefs = categories.get('group', {'enabled': True})
                
                if group_prefs.get('enabled', True):
                    # Create notification document in notifications collection
                    notification_doc = {
                        'userId': participant_id,
                        'type': 'group_message',
                        'title': f"New message in {group_data.get('name', 'Group Chat')}",
                        'body': f"{get_user_name(data['senderId'])}: {data['content'][:50]}...",
                        'isRead': False,
                        'createdAt': firestore.SERVER_TIMESTAMP,
                        'data': {
                            'groupId': data['groupId'],
                            'groupName': group_data.get('name', 'Group Chat'),
                            'senderId': data['senderId'],
                            'senderName': get_user_name(data['senderId']),
                            'messageContent': data['content']
                        }
                        # deeplink removed per repository-wide deprecation of in-app deeplinks
                    }
                    
                    # Store notification in Firestore
                    db.collection('notifications').add(notification_doc)
                    
                    # Also queue for FCM push notification
                    notification_data = {
                        'type': 'group_digest',
                        'userId': participant_id,
                        'groupId': data['groupId'],
                        'groupName': group_data.get('name', 'Group Chat'),
                        'senderName': get_user_name(data['senderId']),
                        'content': data['content'][:100],
                        'timestamp': data['timestamp']
                    }
                    _queue_notification(notification_data, batch=True, delay_minutes=5)
                    notifications_created += 1
        
        return jsonify({
            "success": True, 
            "message": "Group message notifications created and queued",
            "notifications_created": notifications_created
        }), 200
        
    except Exception as e:
        logger.error(f"Error handling group message notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/events/group-mention', methods=['POST'])
def handle_group_mention_notification():
    """Handle group mention notification event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['groupId', 'mentionedUserId', 'content', 'senderId', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Get group info
        group_doc = db.collection('groupChats').document(data['groupId']).get()
        if not group_doc.exists:
            return jsonify({"success": False, "error": "Group not found"}), 404
        
        group_data = group_doc.to_dict()
        
        # Create immediate mention notification
        notification_data = {
            'type': 'mention',
            'userId': data['mentionedUserId'],
            'groupId': data['groupId'],
            'groupName': group_data.get('name', 'Group Chat'),
            'senderName': get_user_name(data['senderId']),
            'snippet': data['content'][:50],
            'msgId': data.get('msgId', ''),
            'timestamp': data['timestamp']
        }
        
        # Queue high-priority notification
        _queue_notification(notification_data, immediate=True)
        
        return jsonify({"success": True, "message": "Mention notification queued"}), 200
        
    except Exception as e:
        logger.error(f"Error handling mention notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/events/direct-message', methods=['POST'])
def handle_direct_message_notification():
    """Handle direct message notification event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['chatId', 'content', 'senderId', 'receiverId', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Check if receiver has DM notifications enabled
        user_doc = db.collection('humanUsers').document(data['receiverId']).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            prefs = user_data.get('notificationPrefs', {})
            categories = prefs.get('categories', {})
            dm_prefs = categories.get('dm', {'enabled': True})
            
            if dm_prefs.get('enabled', True):
                # Store notification directly in notifications collection (main collection)
                notification_doc = {
                    'userId': data['receiverId'],
                    'type': 'direct_message',
                    'title': get_user_name(data['senderId']),
                    'body': data['content'][:100] + '...' if len(data['content']) > 100 else data['content'],
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'chatId': data['chatId'],
                        'senderId': data['senderId'],
                        'senderName': get_user_name(data['senderId']),
                        'messageContent': data['content']
                    }
                    # deeplink removed per repository-wide deprecation of in-app deeplinks
                }
                
                # Store in main notifications collection
                db.collection('notifications').add(notification_doc)
        
        return jsonify({"success": True, "message": "DM notification created"}), 200
        
    except Exception as e:
        logger.error(f"Error handling DM notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/events/post-engagement', methods=['POST'])
def handle_post_engagement_notification():
    """Handle post engagement notification event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['postId', 'type', 'userId', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Only notify if there's a post author and it's not the same user
        post_author_id = data.get('postAuthorId')
        if not post_author_id or post_author_id == data['userId']:
            return jsonify({"success": True, "message": "No notification needed"}), 200
        
        # Check if post author has engagement notifications enabled
        user_doc = db.collection('humanUsers').document(post_author_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            prefs = user_data.get('notificationPrefs', {})
            categories = prefs.get('categories', {})
            engagement_prefs = categories.get('engagement', {'enabled': True})
            
            if engagement_prefs.get('enabled', True):
                # Create notification document
                engagement_types = {
                    'like': 'liked',
                    'comment': 'commented on',
                    'share': 'shared'
                }
                
                # Create proper notification type and title based on engagement type
                engagement_type = data['type']
                if engagement_type == 'like':
                    notification_type = 'post_like'
                    notification_title = f"{get_user_name(data['userId'])} liked your post"
                elif engagement_type == 'comment':
                    notification_type = 'post_comment' 
                    notification_title = f"{get_user_name(data['userId'])} commented on your post"
                elif engagement_type == 'share':
                    notification_type = 'post_share'
                    notification_title = f"{get_user_name(data['userId'])} shared your post"
                else:
                    notification_type = 'post_engagement'
                    notification_title = f"{get_user_name(data['userId'])} engaged with your post"
                
                notification_doc = {
                    'userId': post_author_id,
                    'type': notification_type,
                    'title': notification_title,
                    'body': f"{get_user_name(data['userId'])} {engagement_types.get(data['type'], 'engaged with')} your post",
                    'isRead': False,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'data': {
                        'postId': data['postId'],
                        'engagementType': data['type'],
                        'engagerUserId': data['userId'],
                        'content': data.get('content', '')
                    }
                    # deeplink removed per repository-wide deprecation of in-app deeplinks
                }
                
                # Store notification in Firestore
                db.collection('notifications').add(notification_doc)
                
                # Also queue for FCM (batched)
                notification_data = {
                    'type': 'engagement_digest',
                    'userId': post_author_id,
                    'postId': data['postId'],
                    'engagementType': data['type'],
                    'engagerUserId': data['userId'],
                    'content': data.get('content', ''),
                    'timestamp': data['timestamp']
                }
                _queue_notification(notification_data, batch=True, delay_minutes=30)
        
        return jsonify({"success": True, "message": "Engagement notification created and queued"}), 200
        
    except Exception as e:
        logger.error(f"Error handling engagement notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/events/user-follow', methods=['POST'])
def handle_user_follow_notification():
    """Handle user follow notification event"""
    try:
        data = request.get_json()
        logger.info(f"=== USER FOLLOW NOTIFICATION EVENT ===")
        logger.info(f"Request data: {data}")
        
        # Validate required fields
        required_fields = ['followerId', 'followedUserId', 'timestamp']
        if not all(field in data for field in required_fields):
            logger.error(f"Missing required fields. Data: {data}")
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        follower_id = data['followerId']
        followed_user_id = data['followedUserId']
        
        logger.info(f"Processing follow notification: {follower_id} -> {followed_user_id}")
        
        # Get follower name
        follower_name = get_user_name(follower_id)
        logger.info(f"Follower name resolved: {follower_name}")
        
        # Get followed user's FCM tokens
        try:
            user_doc = db.collection('humanUsers').document(followed_user_id).get()
            if not user_doc.exists:
                logger.warning(f"Followed user {followed_user_id} not found in humanUsers collection")
                return jsonify({"success": False, "error": f"User {followed_user_id} not found"}), 404
            
            user_data = user_doc.to_dict()
            user_tokens = user_data.get('fcmTokens', [])
            
            if not user_tokens:
                logger.info(f"No FCM tokens found for user {followed_user_id}")
                return jsonify({"success": True, "message": "No tokens to send notification to"}), 200
            
            # Send FCM notifications to all user's devices
            successful_sends = 0
            failed_sends = 0
            
            for token in user_tokens:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title='New Follower',
                            body=f'{follower_name} started following you'
                        ),
                        data={
                            'type': 'user_follow',
                            'followerId': follower_id,
                            'timestamp': data['timestamp'],
                            'action': 'navigate_to_profile',
                            'route': f'/profile/{follower_id}',
                        },
                        token=token
                    )
                    
                    response = messaging.send(message)
                    logger.info(f"Follow notification sent to token {token[:20]}... Response: {response}")
                    successful_sends += 1
                    
                except Exception as token_error:
                    logger.error(f"Failed to send notification to token {token[:20]}...: {token_error}")
                    failed_sends += 1
            
            logger.info(f"Follow notification stats - Successful: {successful_sends}, Failed: {failed_sends}")
            
        except Exception as e:
            logger.error(f"Error sending follow push notification: {e}")
            return jsonify({"success": False, "error": f"Failed to send push notification: {str(e)}"}), 500
        
        return jsonify({"success": True, "message": "Follow notification processed", "stats": {"successful": successful_sends, "failed": failed_sends}}), 200
        
    except Exception as e:
        logger.error(f"Error handling follow notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/events/rare-offer', methods=['POST'])
def handle_rare_offer_notification():
    """Handle rare coin offer notification event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['userId', 'offerType', 'coinAmount', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Check if user is eligible for rare offers
        if not _check_rare_offer_eligibility(data['userId']):
            return jsonify({"success": True, "message": "User not eligible for rare offers"}), 200
        
        # Get a random AI character for the offer
        character_name = _get_random_character_name()
        
        # Create offer notification
        offer_texts = {
            'watch_video': f"Watch a short video for +{data['coinAmount']} InCash",
            'refer_friend': f"Invite 1 friend → +{data['coinAmount']} InCash", 
            'double_coins': f"Limited time: Double coins for {data['coinAmount']} minutes!"
        }
        
        notification_data = {
            'type': 'rare_offer',
            'userId': data['userId'],
            'characterName': character_name,
            'offerType': data['offerType'],
            'offerText': offer_texts.get(data['offerType'], f"Earn {data['coinAmount']} InCash!"),
            'coinAmount': data['coinAmount'],
            'reason': data.get('reason', 'special_offer'),
            'timestamp': data['timestamp']
        }
        
        # Queue high-priority notification
        _queue_notification(notification_data, immediate=True)
        
        # Log rare offer
        _log_rare_offer(data['userId'], data['offerType'], data['coinAmount'])
        
        return jsonify({"success": True, "message": "Rare offer notification queued"}), 200
        
    except Exception as e:
        logger.error(f"Error handling rare offer notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/events/ai-nudge', methods=['POST'])
def handle_ai_nudge_notification():
    """Handle AI nudge notification event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['userId', 'characterId', 'lastChatId', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Get character info
        character_name = _get_character_name(data['characterId'])
        
        # Create AI nudge notification
        notification_data = {
            'type': 'ai_nudge',
            'userId': data['userId'],
            'characterId': data['characterId'],
            'characterName': character_name,
            'chatId': data['lastChatId'],
            'personalizedHook': data.get('personalizedHook', f"{character_name} wants to continue your conversation"),
            'timestamp': data['timestamp']
        }
        
        # Queue with slight delay for natural feel
        delay_minutes = random.randint(5, 30)
        _queue_notification(notification_data, delay_minutes=delay_minutes)
        
        return jsonify({"success": True, "message": "AI nudge notification queued"}), 200
        
    except Exception as e:
        logger.error(f"Error handling AI nudge notification: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/register-token', methods=['POST'])
def register_fcm_token():
    """Register FCM token for user"""
    try:
        data = request.get_json()
        
        if 'userId' not in data or 'token' not in data:
            return jsonify({"success": False, "error": "Missing userId or token"}), 400
        
        user_id = data['userId']
        token = data['token']
        
        # Update user's FCM tokens in humanUsers collection
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.set({
            'fcmTokens': firestore.ArrayUnion([token]),
            'lastTokenUpdate': firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        return jsonify({"success": True, "message": "FCM token registered"}), 200
        
    except Exception as e:
        logger.error(f"Error registering FCM token: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/send-push', methods=['POST'])
def send_push_notification():
    """Send push notification to user via FCM"""
    try:
        logger.info("=== SEND PUSH NOTIFICATION ENDPOINT HIT ===")
        data = request.get_json()
        logger.info(f"Request data received: {data}")
        
        if not data:
            logger.error("No request data provided")
            return jsonify({"success": False, "error": "Missing request data"}), 400
        
        required_fields = ['userId', 'title', 'body']
        if not all(field in data for field in required_fields):
            logger.error(f"Missing required fields. Data: {data}")
            return jsonify({"success": False, "error": "Missing required fields: userId, title, body"}), 400
        
        user_id = data['userId']
        title = data['title']
        body = data['body']
        notification_data = data.get('data', {})
        
        logger.info(f"Sending push notification to user {user_id}: {title}")
        
        # Get user's FCM tokens - check humanUsers first, then popularCharacters for validation
        user_tokens = []
        try:
            logger.info(f"Fetching user document for user_id: {user_id}")
            user_doc = db.collection('humanUsers').document(user_id).get()
            logger.info(f"User document exists in humanUsers: {user_doc.exists}")
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_tokens = user_data.get('fcmTokens', [])
                logger.info(f"Found user in humanUsers collection with {len(user_tokens)} FCM tokens")
                logger.info(f"FCM tokens: {[token[:20] + '...' for token in user_tokens]}")
            else:
                # Check if this is an AI character (should not receive push notifications)
                ai_doc = db.collection('popularCharacters').document(user_id).get()
                if ai_doc.exists:
                    logger.warning(f"Attempted to send push notification to AI character {user_id} - AI characters cannot receive push notifications")
                    return jsonify({"success": False, "error": f"Cannot send push notifications to AI characters (ID: {user_id})"}), 400
                else:
                    logger.warning(f"User {user_id} not found in humanUsers or popularCharacters collections")
                    return jsonify({"success": False, "error": f"User {user_id} not found"}), 404
        except Exception as e:
            logger.error(f"Error fetching user tokens: {e}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception args: {e.args}")
            return jsonify({"success": False, "error": f"Error fetching user: {str(e)}"}), 500
        
        if not user_tokens:
            logger.warning(f"No FCM tokens found for user {user_id}")
            return jsonify({"success": False, "error": "No FCM tokens found for user"}), 400
        
        # Send push notification to all user's devices
        successful_sends = 0
        failed_sends = 0
        invalid_tokens = []
        
        logger.info(f"Starting to send notifications to {len(user_tokens)} tokens")
        
        for i, token in enumerate(user_tokens):
            try:
                logger.info(f"Sending to token {i+1}/{len(user_tokens)}: {token[:20]}...")
                
                # Create FCM message
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data={str(k): str(v) for k, v in notification_data.items()},  # FCM data must be strings
                    token=token,
                    android=messaging.AndroidConfig(
                        notification=messaging.AndroidNotification(
                            channel_id='high_importance_channel',
                            priority='high',  # Use string instead of enum
                        ),
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                alert=messaging.ApsAlert(
                                    title=title,
                                    body=body,
                                ),
                                badge=1,
                                sound='default',
                            ),
                        ),
                    ),
                )
                
                logger.info(f"FCM message created, sending...")
                
                # Send message
                response = messaging.send(message)
                logger.info(f"✅ Push notification sent successfully to token {token[:20]}... Response: {response}")
                successful_sends += 1
                
            except messaging.UnregisteredError as e:
                logger.warning(f"❌ Invalid FCM token: {token[:20]}... Error: {e}")
                invalid_tokens.append(token)
                failed_sends += 1
            except Exception as e:
                logger.error(f"❌ Error sending push notification to token {token[:20]}...: {e}")
                logger.error(f"Exception type: {type(e)}")
                logger.error(f"Exception args: {e.args}")
                failed_sends += 1
        
        # Remove invalid tokens from user document
        if invalid_tokens:
            try:
                logger.info(f"Removing {len(invalid_tokens)} invalid tokens...")
                user_ref = db.collection('humanUsers').document(user_id)
                for invalid_token in invalid_tokens:
                    user_ref.update({
                        'fcmTokens': firestore.ArrayRemove([invalid_token])
                    })
                logger.info(f"Removed {len(invalid_tokens)} invalid tokens for user {user_id}")
            except Exception as e:
                logger.error(f"Error removing invalid tokens: {e}")
        
        result = {
            "success": True, 
            "message": f"Push notification processing complete",
            "stats": {
                "successful": successful_sends,
                "failed": failed_sends,
                "invalidTokens": len(invalid_tokens)
            }
        }
        
        logger.info(f"Push notification result: {result}")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"CRITICAL ERROR in send_push_notification: {e}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Exception args: {e.args}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": "Internal error"}), 500

@app.route('/api/notifications/preferences', methods=['POST'])
def update_notification_preferences():
    """Update user notification preferences"""
    try:
        data = request.get_json()
        
        if 'userId' not in data or 'preferences' not in data:
            return jsonify({"success": False, "error": "Missing userId or preferences"}), 400
        
        user_id = data['userId']
        preferences = data['preferences']
        
        # Update user preferences (try humanUsers collection first)
        try:
            user_ref = db.collection('humanUsers').document(user_id)
            user_ref.update({
                'notificationPrefs': preferences,
                'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
            })
            return jsonify({"success": True, "message": "Preferences updated"}), 200
        except Exception as e1:
            # If humanUsers doesn't work, try users collection
            try:
                user_ref = db.collection('users').document(user_id)
                user_ref.update({
                    'notificationPrefs': preferences,
                    'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
                })
                return jsonify({"success": True, "message": "Preferences updated"}), 200
            except Exception as e2:
                return jsonify({"success": False, "error": f"User document not found in any collection: {str(e2)}"}), 404
        
    except Exception as e:
        logger.error(f"Error updating preferences: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/scheduler/daily-nudges', methods=['POST'])
def trigger_daily_nudges():
    """Cloud Scheduler endpoint for daily AI nudges"""
    try:
        # Simple implementation for daily nudges
        nudges_created = 0
        
        # Get active users who might need nudges
        try:
            # Get users who haven't had recent AI interactions
            day_ago = datetime.utcnow() - timedelta(days=1)
            
            # Query recent AI chat activity (this is a simple implementation)
            # In practice, you'd want more sophisticated logic
            recent_chats = (db.collection('conversations')
                          .where('timestamp', '>', day_ago)
                          .limit(100)
                          .get())
            
            # Create sample nudges for testing
            for i in range(5):  # Create 5 test nudges
                user_id = f"test_user_{i}"
                character_id = f"test_character_{i}"
                
                notification_data = {
                    'type': 'ai_nudge',
                    'userId': user_id,
                    'characterId': character_id,
                    'characterName': f"AI Friend {i}",
                    'chatId': f"chat_{i}",
                    'personalizedHook': f"Come back and chat with AI Friend {i}!",
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                # Queue nudge notification
                _queue_notification(notification_data, delay_minutes=random.randint(10, 60))
                nudges_created += 1
            
        except Exception as e:
            logger.error(f"Error creating daily nudges: {e}")
        
        return jsonify({
            "success": True, 
            "message": "Daily nudges scheduled",
            "stats": {"nudges_created": nudges_created}
        }), 200
        
    except Exception as e:
        logger.error(f"Error triggering daily nudges: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/scheduler/rare-offers', methods=['POST'])
def trigger_weekly_rare_offers():
    """Cloud Scheduler endpoint for weekly rare offer selection"""
    try:
        # Get eligible users for rare offers
        eligible_users = _get_rare_offer_eligible_users()
        
        offers_created = 0
        for user_id in eligible_users:
            # Create random rare offer
            offer_type = random.choice(['watch_video', 'refer_friend', 'double_coins'])
            coin_amount = random.randint(50, 200)
            
            notification_data = {
                'userId': user_id,
                'offerType': offer_type,
                'coinAmount': coin_amount,
                'reason': 'weekly_selection',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Queue rare offer notification
            _queue_notification({
                'type': 'rare_offer',
                'userId': user_id,
                'characterName': _get_random_character_name(),
                'offerType': offer_type,
                'offerText': f"Special offer: +{coin_amount} InCash",
                'coinAmount': coin_amount,
                'reason': 'weekly_selection',
                'timestamp': datetime.utcnow().isoformat()
            }, immediate=True)
            
            offers_created += 1
        
        return jsonify({
            "success": True,
            "message": f"Weekly rare offers created: {offers_created}",
            "eligible_users": len(eligible_users)
        }), 200
        
    except Exception as e:
        logger.error(f"Error triggering weekly rare offers: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# Helper functions for notifications
def _queue_notification(notification_data, immediate=False, batch=False, delay_minutes=0):
    """Queue notification for processing"""
    try:
        notification_id = str(uuid.uuid4())
        
        # Calculate when to send
        send_time = datetime.utcnow()
        if delay_minutes > 0:
            send_time += timedelta(minutes=delay_minutes)
        elif not immediate:
            send_time += timedelta(minutes=1)  # Default small delay
        
        queue_data = {
            'id': notification_id,
            'uid': notification_data['userId'],
            'type': notification_data['type'],
            'payload': notification_data,
            'status': 'pending',
            'notBefore': send_time,
            'immediate': immediate,
            'batch': batch,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'retryCount': 0
        }
        
        db.collection('notificationsQueue').document(notification_id).set(queue_data)
        logger.info(f"Notification queued: {notification_id}")
        
    except Exception as e:
        logger.error(f"Error queueing notification: {e}")

def _check_rare_offer_eligibility(user_id):
    """Check if user is eligible for rare offers"""
    try:
        # Check user preferences
        user_doc = db.collection('humanUsers').document(user_id).get()
        if not user_doc.exists:
            return False
        
        user_data = user_doc.to_dict()
        prefs = user_data.get('notificationPrefs', {})
        categories = prefs.get('categories', {})
        rare_offers = categories.get('rareOffers', {})
        
        if not rare_offers.get('enabled', True):
            return False
        
        # Check weekly limit
        max_per_week = rare_offers.get('maxPerWeek', 2)
        
        # Check recent rare offers
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_offers = (db.collection('rareOffersLog')
                        .where('userId', '==', user_id)
                        .where('timestamp', '>', week_ago)
                        .get())
        
        if len(recent_offers) >= max_per_week:
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking rare offer eligibility: {e}")
        return False

def _get_random_character_name():
    """Get a random AI character name for offers"""
    try:
        characters = db.collection('aiCharacters').limit(10).get()
        if characters:
            char = random.choice(characters)
            return char.to_dict().get('name', 'InZone')
        return 'InZone'
    except:
        return 'InZone'

def _get_character_name(character_id):
    """Get character name by ID"""
    try:
        if character_id == 'system' or character_id == 'default':
            return 'InZone'
        
        char_doc = db.collection('aiCharacters').document(character_id).get()
        if char_doc.exists:
            return char_doc.to_dict().get('name', 'AI Friend')
        return 'AI Friend'
    except:
        return 'AI Friend'

def _log_rare_offer(user_id, offer_type, coin_amount):
    """Log rare offer to track limits"""
    try:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        log_data = {
            'userId': user_id,
            'type': offer_type,
            'status': 'sent',
            'coinsAwarded': 0,  # Will be updated when completed
            'coinAmount': coin_amount,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'date': today
        }
        
        db.collection('rareOffersLog').add(log_data)
        
    except Exception as e:
        logger.error(f"Error logging rare offer: {e}")

def _get_rare_offer_eligible_users():
    """Get users eligible for weekly rare offer selection"""
    try:
        # Get users with low coin balance or no recent coin earning
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        # Query users with rare offers enabled
        users_query = (db.collection('humanUsers')
                      .where('notificationPrefs.categories.rareOffers.enabled', '==', True)
                      .limit(500))
        
        users_docs = users_query.get()
        eligible_users = []
        
        for user_doc in users_docs:
            user_data = user_doc.to_dict()
            user_id = user_doc.id
            
            # Check weekly limit
            recent_offers = (db.collection('rareOffersLog')
                           .where('userId', '==', user_id)
                           .where('timestamp', '>', week_ago)
                           .get())
            
            max_per_week = user_data.get('notificationPrefs', {}).get('categories', {}).get('rareOffers', {}).get('maxPerWeek', 2)
            
            if len(recent_offers) < max_per_week:
                # Check if user has low coins or no recent earning
                coin_balance = user_data.get('coinBalance', 0)
                if coin_balance < 100:  # Low balance threshold
                    eligible_users.append(user_id)
        
        return eligible_users[:50]  # Limit to 50 users per week
        
    except Exception as e:
        logger.error(f"Error getting rare offer eligible users: {e}")
        return []

# ---------------------------
# Notification System Test Endpoints
# ---------------------------

@app.route('/api/notifications/debug/count', methods=['GET'])
def debug_notification_count():
    """Debug endpoint to count notifications in queue"""
    try:
        user_id = request.args.get('user_id')
        
        # Count all documents in notificationsQueue
        all_docs = db.collection('notificationsQueue').get()
        total_count = len(all_docs)
        
        # Count for specific user if provided
        user_count = 0
        user_docs = []
        if user_id:
            user_query = db.collection('notificationsQueue').where('uid', '==', user_id).get()
            user_count = len(user_query)
            user_docs = [doc.to_dict() for doc in user_query]
        
        return jsonify({
            "success": True,
            "data": {
                "total_notifications": total_count,
                "user_notifications": user_count,
                "user_id": user_id,
                "sample_user_docs": user_docs[:3]  # First 3 for debugging
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in debug count: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/user/<user_id>/all', methods=['GET'])
def get_all_user_notifications(user_id):
    """Get all notifications for a user - simplified to avoid index issues"""
    try:
        notifications = []
        
        # 1. Get notifications from main notifications collection (simple query)
        try:
            notifications_query = (db.collection('notifications')
                                   .where('userId', '==', user_id)
                                   .limit(50))
            
            for doc in notifications_query.get():
                # Append the actual notification document from Firestore.
                # The previous code referenced `offer_data` which is undefined here
                # and caused a NameError. Use the document data directly.
                notification = doc.to_dict()
                notification['id'] = doc.id
                # Ensure timestamp key exists for sorting logic later
                if 'timestamp' not in notification and 'createdAt' in notification:
                    notification['timestamp'] = notification.get('createdAt')
                notifications.append(notification)
                
        except Exception as e:
            logger.error(f"Error getting rare offers: {e}")
        
        # 2. Also get rare offers from rareOffersLog (if any) and normalize them
        try:
            rare_offers_query = (db.collection('rareOffersLog')
                                 .document(user_id)
                                 .collection('offers')
                                 .order_by('sentAt', direction=firestore.Query.DESCENDING)
                                 .limit(20))
            for doc in rare_offers_query.get():
                offer = doc.to_dict()
                # Normalize fields to match notification structure used by client
                notif = {
                    'id': f"rare_{doc.id}",
                    'type': 'rare_offer',
                    'source': 'rare_offers_log',
                    'offerType': offer.get('type'),
                    'coinAmount': offer.get('coinAmount') or offer.get('coinsAwarded') or offer.get('coinAmount'),
                    'status': offer.get('status'),
                    'timestamp': offer.get('sentAt') or offer.get('sentAt'),
                    'characterName': offer.get('characterName', 'InZone'),
                    'notificationId': offer.get('notificationId')
                }
                notifications.append(notif)
        except Exception as e:
            logger.error(f"Error fetching rareOffersLog for user {user_id}: {e}")
        
        # 6. Get AI nudge logs
        try:
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            nudge_doc = (db.collection('nudges')
                        .document(user_id)
                        .collection('daily')
                        .document(today_str)
                        .get())
            
            if nudge_doc.exists:
                nudge_data = nudge_doc.to_dict()
                if nudge_data.get('sentCount', 0) > 0:
                    notifications.append({
                        'type': 'ai_nudge',
                        'source': 'nudges_log',
                        'sentCount': nudge_data.get('sentCount'),
                        'lastNudgeAt': nudge_data.get('lastNudgeAt'),
                        'characterName': 'AI Assistant',
                        'personalizedHook': 'Come back and continue the conversation!'
                    })
                    
        except Exception as e:
            logger.error(f"Error getting AI nudges: {e}")
        
        # Sort all notifications by timestamp (newest first)
        def get_timestamp(notif):
            ts = notif.get('timestamp')
            if ts is None:
                return datetime.min
            if hasattr(ts, 'timestamp'):  # Firestore timestamp
                return datetime.fromtimestamp(ts.timestamp())
            return ts
        
        notifications.sort(key=get_timestamp, reverse=True)
        
        # Group notifications by type for summary
        notification_summary = {}
        for notif in notifications:
            notif_type = notif.get('type', 'unknown')
            if notif_type not in notification_summary:
                notification_summary[notif_type] = 0
            notification_summary[notif_type] += 1
        
        return jsonify({
            "success": True,
            "data": {
                "user_id": user_id,
                "total_notifications": len(notifications),
                "summary_by_type": notification_summary,
                "notifications": notifications[:50],  # Limit to 50 most recent
                "sources_checked": [
                    "notificationsQueue",
                    "group_activity", 
                    "post_likes",
                    "post_comments",
                    "direct_messages",
                    "rare_offers_log",
                    "nudges_log"
                ]
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting all user notifications: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/notifications/test/create-sample', methods=['POST'])
def create_sample_notifications():
    """Create sample notifications for testing"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({"success": False, "error": "user_id required"}), 400
        
        # Create sample notifications in queue
        sample_notifications = [
            {
                'uid': user_id,
                'type': 'group_digest',
                'payload': {
                    'groupId': 'test_group_1',
                    'groupName': 'Test Group',
                    'senderName': 'TestUser',
                    'content': 'This is a test group message notification'
                },
                'status': 'pending',
                'createdAt': firestore.SERVER_TIMESTAMP,
                'immediate': False,
                'batch': True
            },
            {
                'uid': user_id,
                'type': 'dm_new',
                'payload': {
                    'chatId': 'test_chat_1',
                    'senderName': 'AI Friend',
                    'preview': 'Hey! How are you doing today?'
                },
                'status': 'pending',
                'createdAt': firestore.SERVER_TIMESTAMP,
                'immediate': True,
                'batch': False
            },
            {
                'uid': user_id,
                'type': 'engagement_digest',
                'payload': {
                    'postId': 'test_post_1',
                    'engagementType': 'like',
                    'engagerUserId': 'test_user_2',
                    'content': 'Your post got some engagement!'
                },
                'status': 'pending',
                'createdAt': firestore.SERVER_TIMESTAMP,
                'immediate': False,
                'batch': True
            },
            {
                'uid': user_id,
                'type': 'rare_offer',
                'payload': {
                    'characterName': 'InZone',
                    'offerType': 'watch_video',
                    'offerText': 'Watch a short video for +50 InCash',
                    'coinAmount': 50
                },
                'status': 'pending',
                'createdAt': firestore.SERVER_TIMESTAMP,
                'immediate': True,
                'batch': False
            }
        ]
        
        created_ids = []
        for notification in sample_notifications:
            doc_ref = db.collection('notificationsQueue').add(notification)
            created_ids.append(doc_ref[1].id)
        
        return jsonify({
            "success": True,
            "message": f"Created {len(sample_notifications)} sample notifications",
            "notification_ids": created_ids
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating sample notifications: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/admin/ai-engagement', methods=['GET'])
# def ai_engagement_admin():
#     """Admin dashboard for AI engagement system"""
#     return get_admin_dashboard_html()

# ---------------------------
# AI User Engagement Endpoints
# ---------------------------

@app.route('/api/ai/send-dm', methods=['POST'])
def ai_send_dm():
    """AI user sends a DM using existing conversations system"""
    try:
        data = request.get_json()
        ai_user_id = data.get('ai_user_id')
        target_user_id = data.get('target_user_id')
        
        if not ai_user_id or not target_user_id:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Check daily limits
        can_interact = inzone_ai_service.check_ai_daily_limit(ai_user_id)
        if not can_interact:
            return jsonify({"success": False, "error": "Daily interaction limit reached"}), 429
        
        # Get AI user details - try both aiUsers and popularCharacters collections
        ai_user_doc = db.collection('aiUsers').document(ai_user_id).get()
        ai_user = None
        
        if ai_user_doc.exists:
            ai_user = ai_user_doc.to_dict()
            ai_user['username'] = ai_user_id
        else:
            # Try popularCharacters collection using document ID
            popular_char_doc = db.collection('popularCharacters').document(ai_user_id).get()
            if popular_char_doc.exists:
                ai_user = popular_char_doc.to_dict()
                ai_user['username'] = ai_user.get('name', ai_user_id)
            else:
                return jsonify({"success": False, "error": "AI user not found"}), 404
        
        # Get target user details
        target_user_doc = db.collection('humanUsers').document(target_user_id).get()
        if not target_user_doc.exists:
            return jsonify({"success": False, "error": "Target user not found"}), 404
        
        target_user = target_user_doc.to_dict()
        
        # Create conversation ID (sorted to ensure consistency)
        participants = sorted([ai_user_id, target_user_id])
        conversation_id = f"{participants[0]}_{participants[1]}"
        
        # Check if conversation exists and get context
        conversation_ref = db.collection('conversations').document(conversation_id)
        conversation_doc = conversation_ref.get()
        
        print(f"🔍 DEBUG: Conversation ID: {conversation_id}")
        print(f"🔍 DEBUG: Conversation exists: {conversation_doc.exists}")
        
        conversation_context = None
        if conversation_doc.exists:
            # Get recent messages for better context
            messages_ref = conversation_ref.collection('messages').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5)
            recent_messages = []
            total_messages = 0
            
            for msg_doc in messages_ref.stream():
                msg_data = msg_doc.to_dict()
                recent_messages.append({
                    'senderId': msg_data.get('senderId'),
                    'text': msg_data.get('text', ''),
                    'timestamp': msg_data.get('timestamp')
                })
                total_messages += 1
            
            # Count total messages for context
            all_messages_ref = conversation_ref.collection('messages')
            total_message_count = len(list(all_messages_ref.stream()))
            
            print(f"🔍 DEBUG: Total message count: {total_message_count}")
            print(f"🔍 DEBUG: Recent messages: {len(recent_messages)}")
            for i, msg in enumerate(recent_messages):
                print(f"🔍 DEBUG: Message {i}: {msg}")
            
            conversation_context = {
                'message_count': total_message_count,
                'recent_messages': recent_messages,
                'has_conversation': True
            }
        else:
            print("🔍 DEBUG: No existing conversation found")
        
        # Generate DM message
        dm_content = inzone_ai_service.generate_ai_dm_message(ai_user, target_user, conversation_context)
        
        # Check if this message is too similar to recent messages to avoid repetition
        if conversation_context and conversation_context.get('recent_messages'):
            recent_texts = [msg.get('text', '').lower() for msg in conversation_context['recent_messages']]
            dm_lower = dm_content.lower()
            
            # If message is too similar to recent ones, generate a different one
            for recent_text in recent_texts:
                if recent_text and len(recent_text) > 10:  # Only check substantial messages
                    # Simple similarity check - if many words overlap
                    dm_words = set(dm_lower.split())
                    recent_words = set(recent_text.split())
                    if len(dm_words.intersection(recent_words)) / max(len(dm_words), len(recent_words)) > 0.6:
                        # Too similar, regenerate
                        dm_content = inzone_ai_service.generate_ai_dm_message(ai_user, target_user, conversation_context)
                        break
        
        # Create message using existing system structure
        new_message = {
            'text': dm_content,
            'senderId': ai_user_id,
            'senderName': ai_user.get('name', ai_user_id),
            'timestamp': firestore.SERVER_TIMESTAMP,
            'isRead': False,
            'isAIGenerated': True
        }
        
        # Add message to conversation
        conversation_ref.collection('messages').add(new_message)
        
        # Update conversation metadata
        conversation_ref.set({
            'lastMessage': dm_content,
            'lastMessageTime': firestore.SERVER_TIMESTAMP,
            'participants': [ai_user_id, target_user_id],
            'participantNames': {
                ai_user_id: ai_user.get('name', ai_user_id),
                target_user_id: target_user.get('name', target_user_id)
            },
            'lastUpdated': firestore.SERVER_TIMESTAMP,
            'isAIConversation': True
        }, merge=True)
        
        # Store DM notification directly in notifications collection
        try:
            notification_doc = {
                'userId': target_user_id,
                'type': 'direct_message',
                'title': ai_user.get('name', ai_user_id),
                'body': dm_content[:100] + '...' if len(dm_content) > 100 else dm_content,
                'isRead': False,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'data': {
                    'chatId': conversation_id,
                    'senderId': ai_user_id,
                    'senderName': ai_user.get('name', ai_user_id),
                    'messageContent': dm_content
                },
                # deeplink removed per repository-wide deprecation of in-app deeplinks
            }
            db.collection('notifications').add(notification_doc)
        except Exception as notif_error:
            logger.error(f"Error creating DM notification: {notif_error}")
        
        return jsonify({
            "success": True, 
            "data": {
                "conversation_id": conversation_id,
                "message": dm_content,
                "ai_user": ai_user.get('name'),
                "target_user": target_user.get('name')
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error sending AI DM: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/like-post', methods=['POST'])
def ai_like_post():
    """AI user likes a post using existing like system"""
    try:
        data = request.get_json()
        ai_user_id = data.get('ai_user_id')
        post_id = data.get('post_id')
        post_collection = data.get('post_collection', 'humanPosts')  # humanPosts or aiPosts
        
        if not ai_user_id or not post_id:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Check daily limits
        can_interact = inzone_ai_service.check_ai_daily_limit(ai_user_id)
        if not can_interact:
            return jsonify({"success": False, "error": "Daily interaction limit reached"}), 429
        
        # Verify AI user exists
        ai_user_doc = db.collection('aiUsers').document(ai_user_id).get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": "AI user not found"}), 404
        
        # Verify post exists
        post_doc = db.collection(post_collection).document(post_id).get()
        if not post_doc.exists:
            return jsonify({"success": False, "error": "Post not found"}), 404
        
        # Check if already liked
        existing_like = db.collection('postLikes').where('user_id', '==', ai_user_id).where('post_id', '==', post_id).limit(1).get()
        if existing_like:
            return jsonify({"success": False, "error": "Post already liked by this AI user"}), 400
        
        # Add like using existing structure
        like_data = {
            "user_id": ai_user_id,
            "post_id": post_id,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "isAIGenerated": True
        }
        
        db.collection('postLikes').add(like_data)
        
        # Increment likes count on the post
        post_ref = db.collection(post_collection).document(post_id)
        post_ref.update({"likes": firestore.Increment(1)})
        
        ai_user = ai_user_doc.to_dict()
        return jsonify({
            "success": True,
            "data": {
                "post_id": post_id,
                "ai_user": ai_user.get('name'),
                "action": "liked"
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error AI liking post: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/comment-on-post', methods=['POST'])
def ai_comment_on_post():
    """AI user comments on a post using existing comment system"""
    try:
        data = request.get_json()
        ai_user_id = data.get('ai_user_id')
        post_id = data.get('post_id')
        post_collection = data.get('post_collection', 'humanPosts')  # humanPosts or aiPosts
        
        if not ai_user_id or not post_id:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Check daily limits
        can_interact = inzone_ai_service.check_ai_daily_limit(ai_user_id)
        if not can_interact:
            return jsonify({"success": False, "error": "Daily interaction limit reached"}), 429
        
        # Get AI user details
        ai_user_doc = db.collection('aiUsers').document(ai_user_id).get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": "AI user not found"}), 404
        
        ai_user = ai_user_doc.to_dict()
        ai_user['username'] = ai_user_id
        
        # Get post details
        post_doc = db.collection(post_collection).document(post_id).get()
        if not post_doc.exists:
            return jsonify({"success": False, "error": "Post not found"}), 404
        
        post_data = post_doc.to_dict()
        post_data['id'] = post_id
        post_data['collection'] = post_collection
        
        # Get trending insights for context
        trends = inzone_ai_service.get_trending_content_insights()
        
        # Generate contextual comment
        comment_content = inzone_ai_service.generate_contextual_ai_comment(ai_user, post_data, trends)
        
        # Add comment using existing structure
        comment_data = {
            "postId": post_id,
            "userId": ai_user_id,
            "content": comment_content,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "isAIGenerated": True,
            "aiUserName": ai_user.get('name', ai_user_id)
        }
        
        doc_ref = db.collection('postComments').add(comment_data)
        
        return jsonify({
            "success": True,
            "data": {
                "comment_id": doc_ref[1].id,
                "post_id": post_id,
                "comment": comment_content,
                "ai_user": ai_user.get('name'),
                "post_author": post_data.get('user_name'),
                "post_collection": post_collection
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error AI commenting on post: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/admin/search-user', methods=['GET'])
def search_human_user():
    """Search for human users by name"""
    try:
        search_term = request.args.get('name', '')
        
        if not search_term:
            return jsonify({"success": False, "error": "Name parameter is required"}), 400
        
        # Get all human users and filter by name
        users_ref = db.collection('humanUsers')
        users_snapshot = users_ref.stream()
        
        matching_users = []
        
        for doc in users_snapshot:
            user_data = doc.to_dict()
            user_data['id'] = doc.id
            
            # Check if name contains the search term (case insensitive)
            # Handle cases where name might be None or empty
            user_name = user_data.get('name')
            if user_name and isinstance(user_name, str):
                if search_term.lower() in user_name.lower():
                    matching_users.append(user_data)
        
        if not matching_users:
            return jsonify({
                "success": True, 
                "message": f"No users found with name containing '{search_term}'",
                "data": []
            }), 200
        
        return jsonify({
            "success": True,
            "message": f"Found {len(matching_users)} user(s) with name containing '{search_term}'",
            "data": matching_users
        }), 200
        
    except Exception as ex:
        logger.error("Error searching for user: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/bulk-engage', methods=['POST'])
def ai_bulk_engage():
    """AI users perform bulk engagement (comments, likes, DMs) on recent content"""
    try:
        data = request.get_json()
        max_interactions = data.get('max_interactions', 10)
        engagement_types = data.get('engagement_types', ['comment', 'like', 'dm'])
        
        # Get active AI users (increased for more variety)
        ai_users_ref = db.collection('aiUsers').limit(50)
        ai_users = []
        for doc in ai_users_ref.stream():
            ai_data = doc.to_dict()
            ai_data['id'] = doc.id
            ai_users.append(ai_data)
        
        if not ai_users:
            return jsonify({"success": False, "error": "No AI users found"}), 404
        
        # Get recent posts for engagement (more variety)
        recent_posts = []
        
        # Get human posts (increased limit)
        human_posts_ref = db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(60)
        for doc in human_posts_ref.stream():
            post_data = doc.to_dict()
            post_data['id'] = doc.id
            post_data['collection'] = 'humanPosts'
            recent_posts.append(post_data)
        
        # Get AI posts (for cross-AI engagement)
        ai_posts_ref = db.collection('aiPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(40)
        for doc in ai_posts_ref.stream():
            post_data = doc.to_dict()
            post_data['id'] = doc.id
            post_data['collection'] = 'aiPosts'
            recent_posts.append(post_data)
        
        # Get trending insights
        trends = inzone_ai_service.get_trending_content_insights()
        
        results = {
            'comments': [],
            'likes': [],
            'dms': [],
            'errors': []
        }
        
        interaction_count = 0
        used_ai_post_combinations = set()  # Track AI-post combinations to avoid duplicates
        
        # Shuffle AI users and posts for more variety
        random.shuffle(ai_users)
        random.shuffle(recent_posts)
        
        for ai_user in ai_users:
            if interaction_count >= max_interactions:
                break
                
            ai_user_id = ai_user['id']
            
            # Check if AI can still interact today
            can_interact = inzone_ai_service.check_ai_daily_limit(ai_user_id)
            if not can_interact:
                continue
            
            # Get posts this AI hasn't interacted with yet
            available_posts = []
            for post in recent_posts:
                # Skip posts by the same AI user
                if post.get('user_name') == ai_user_id or post.get('user_id') == ai_user_id:
                    continue
                
                # Skip if we've already used this AI-post combination
                combination_key = f"{ai_user_id}_{post['id']}"
                if combination_key not in used_ai_post_combinations:
                    available_posts.append(post)
            
            if not available_posts:
                continue
            
            # Select multiple posts for this AI to create more engagement
            posts_to_engage = random.sample(available_posts, min(3, len(available_posts)))
            
            for selected_post in posts_to_engage:
                if interaction_count >= max_interactions:
                    break
                
                # Mark this combination as used
                combination_key = f"{ai_user_id}_{selected_post['id']}"
                used_ai_post_combinations.add(combination_key)
                
                # Weight engagement types (likes are more common than comments)
                engagement_weights = {'like': 0.6, 'comment': 0.3, 'dm': 0.1}
                available_engagement_types = [et for et in engagement_types if et in engagement_weights]
                
                if available_engagement_types:
                    engagement_type = random.choices(
                        available_engagement_types,
                        weights=[engagement_weights[et] for et in available_engagement_types]
                    )[0]
                else:
                    engagement_type = random.choice(engagement_types)
            
            try:
                if engagement_type == 'comment':
                    # Generate and add comment
                    comment_content = inzone_ai_service.generate_contextual_ai_comment(ai_user, selected_post, trends)
                    
                    comment_data = {
                        "postId": selected_post['id'],
                        "userId": ai_user_id,
                        "content": comment_content,
                        "createdAt": firestore.SERVER_TIMESTAMP,
                        "isAIGenerated": True,
                        "aiUserName": ai_user.get('name', ai_user_id)
                    }
                    
                    doc_ref = db.collection('postComments').add(comment_data)
                    results['comments'].append({
                        'ai_user': ai_user.get('name'),
                        'post_id': selected_post['id'],
                        'comment': comment_content,
                        'comment_id': doc_ref[1].id
                    })
                    
                elif engagement_type == 'like':
                    # Check if already liked
                    existing_like = db.collection('postLikes').where('user_id', '==', ai_user_id).where('post_id', '==', selected_post['id']).limit(1).get()
                    if not existing_like:
                        like_data = {
                            "user_id": ai_user_id,
                            "post_id": selected_post['id'],
                            "timestamp": firestore.SERVER_TIMESTAMP,
                            "isAIGenerated": True
                        }
                        
                        db.collection('postLikes').add(like_data)
                        
                        # Increment likes count
                        post_ref = db.collection(selected_post['collection']).document(selected_post['id'])
                        post_ref.update({"likes": firestore.Increment(1)})
                        
                        results['likes'].append({
                            'ai_user': ai_user.get('name'),
                            'post_id': selected_post['id'],
                            'post_author': selected_post.get('user_name')
                        })
                
                elif engagement_type == 'dm':
                    # Send DM to post author
                    target_user_id = selected_post.get('user_document_id') or selected_post.get('user_name')
                    if target_user_id and target_user_id != ai_user_id:
                        
                        # Get target user details
                        target_user_doc = db.collection('humanUsers').document(target_user_id).get()
                        if target_user_doc.exists:
                            target_user = target_user_doc.to_dict()
                            
                            # Create conversation ID
                            participants = sorted([ai_user_id, target_user_id])
                            conversation_id = f"{participants[0]}_{participants[1]}"
                            
                            # Generate DM
                            dm_content = inzone_ai_service.generate_ai_dm_message(ai_user, target_user)
                            
                            # Add to conversation
                            conversation_ref = db.collection('conversations').document(conversation_id)
                            
                            new_message = {
                                'text': dm_content,
                                'senderId': ai_user_id,
                                'senderName': ai_user.get('name', ai_user_id),
                                'timestamp': firestore.SERVER_TIMESTAMP,
                                'isRead': False,
                                'isAIGenerated': True
                            }
                            
                            conversation_ref.collection('messages').add(new_message)
                            
                            # Update conversation metadata
                            conversation_ref.set({
                                'lastMessage': dm_content,
                                'lastMessageTime': firestore.SERVER_TIMESTAMP,
                                'participants': [ai_user_id, target_user_id],
                                'participantNames': {
                                    ai_user_id: ai_user.get('name', ai_user_id),
                                    target_user_id: target_user.get('name', target_user_id)
                                },
                                'lastUpdated': firestore.SERVER_TIMESTAMP,
                                'isAIConversation': True
                            }, merge=True)
                            
                            results['dms'].append({
                                'ai_user': ai_user.get('name'),
                                'target_user': target_user.get('name'),
                                'conversation_id': conversation_id,
                                'message': dm_content
                            })
                
                interaction_count += 1
                
            except Exception as e:
                results['errors'].append({
                    'ai_user': ai_user.get('name'),
                    'error': str(e),
                    'engagement_type': engagement_type
                })
        
        return jsonify({
            "success": True,
            "data": {
                "total_interactions": interaction_count,
                "results": results,
                "trending_insights": trends
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error in bulk AI engagement: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/engagement-stats', methods=['GET'])
def get_ai_engagement_stats():
    """Get statistics on AI engagement activities"""
    try:
        ai_user_id = request.args.get('ai_user_id')
        days = int(request.args.get('days', 7))
        
        start_date = datetime.now() - timedelta(days=days)
        
        stats = {
            'comments': 0,
            'likes': 0,
            'dms': 0,
            'total_interactions': 0
        }
        
        if ai_user_id:
            # Get stats for specific AI user
            # Count comments
            comments_ref = db.collection('postComments').where('userId', '==', ai_user_id).where('createdAt', '>=', start_date)
            stats['comments'] = len(list(comments_ref.stream()))
            
            # Count likes
            likes_ref = db.collection('postLikes').where('user_id', '==', ai_user_id).where('timestamp', '>=', start_date)
            stats['likes'] = len(list(likes_ref.stream()))
            
            # Count DMs (conversations where AI sent messages)
            conversations_ref = db.collection('conversations')
            dm_count = 0
            for conv_doc in conversations_ref.stream():
                conv_data = conv_doc.to_dict()
                participants = conv_data.get('participants', [])
                if ai_user_id in participants:
                    messages_ref = conv_doc.reference.collection('messages')
                    ai_messages = messages_ref.where('senderId', '==', ai_user_id).where('timestamp', '>=', start_date)
                    if len(list(ai_messages.stream())) > 0:
                        dm_count += 1
            stats['dms'] = dm_count
        else:
            # Get overall AI engagement stats (simplified to avoid index requirements)
            # For now, return mock data to avoid complex queries
            stats['comments'] = 0  # Would require index: isAIGenerated + createdAt
            stats['likes'] = 0     # Would require index: isAIGenerated + timestamp  
            stats['dms'] = 0       # Would require complex conversation scanning
            
            # Original implementation (commented out until indexes are created):
            # # Count all AI comments
            # all_comments_ref = db.collection('postComments').where('isAIGenerated', '==', True).where('createdAt', '>=', start_date)
            # stats['comments'] = len(list(all_comments_ref.stream()))
            # 
            # # Count all AI likes
            # all_likes_ref = db.collection('postLikes').where('isAIGenerated', '==', True).where('timestamp', '>=', start_date)
            # stats['likes'] = len(list(all_likes_ref.stream()))
            # 
            # # Count AI conversations
            # conversations_ref = db.collection('conversations').where('isAIConversation', '==', True)
            # dm_count = 0
            # for conv_doc in conversations_ref.stream():
            #     messages_ref = conv_doc.reference.collection('messages')
            #     ai_messages = messages_ref.where('isAIGenerated', '==', True).where('timestamp', '>=', start_date)
            #     if len(list(ai_messages.stream())) > 0:
            #         dm_count += 1
            stats['dms'] = dm_count
        
        stats['total_interactions'] = stats['comments'] + stats['likes'] + stats['dms']
        
        return jsonify({"success": True, "data": stats}), 200
        
    except Exception as ex:
        logger.error("Error getting AI engagement stats: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-popular-characters', methods=['GET'])
def get_popular_characters_for_dm():
    """Get available popular characters for DM conversations"""
    try:
        limit = int(request.args.get('limit', 50))
        
        # Get popular characters
        chars_ref = db.collection('popularCharacters').limit(limit)
        characters = []
        
        for doc in chars_ref.stream():
            char_data = doc.to_dict()
            characters.append({
                'id': doc.id,
                'name': char_data.get('name', 'Unknown Character'),
                'personality': char_data.get('personality', ''),
                'greeting': char_data.get('greeting', 'Hello!'),
                'profile_picture_url': char_data.get('profile_picture_url', ''),
                'votes': char_data.get('votes', 0),
                'numberOfChats': char_data.get('numberOfChats', 0),
                'collection_type': 'popularCharacters'
            })
        
        return jsonify({"success": True, "data": characters}), 200
        
    except Exception as ex:
        logger.error("Error getting popular characters: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/schedule-character-engagement', methods=['POST'])
def schedule_character_engagement():
    """Schedule AI engagement for a specific popular character"""
    try:
        data = request.get_json()
        character_id = data.get('character_id')
        
        if not character_id:
            return jsonify({"success": False, "error": "character_id is required"}), 400
        
        result = ai_scheduler.schedule_character_engagement(character_id)
        
        if result['success']:
            return jsonify({"success": True, "data": result}), 200
        else:
            return jsonify({"success": False, "error": result.get('error', 'Unknown error')}), 400
        
    except Exception as ex:
        logger.error("Error scheduling character engagement: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/schedule-all-characters', methods=['POST'])
def schedule_all_characters():
    """Schedule AI engagement for all popular characters"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 20)
        
        result = ai_scheduler.schedule_all_characters(limit)
        
        if result['success']:
            return jsonify({"success": True, "data": result}), 200
        else:
            return jsonify({"success": False, "error": result.get('error', 'Unknown error')}), 400
        
    except Exception as ex:
        logger.error("Error scheduling all characters: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/check-interaction-cooldown', methods=['POST'])
# def check_interaction_cooldown():
#     """Check if an AI can interact with a target user"""
#     try:
#         data = request.get_json()
#         ai_id = data.get('ai_id')
#         target_user_id = data.get('target_user_id')
#         interaction_type = data.get('interaction_type')
        
#         if not all([ai_id, target_user_id, interaction_type]):
#             return jsonify({"success": False, "error": "ai_id, target_user_id, and interaction_type are required"}), 400
        
#         from ai_scheduler import EngagementType
#         try:
#             interaction_enum = EngagementType(interaction_type.lower())
#         except ValueError:
#             return jsonify({"success": False, "error": "Invalid interaction_type. Must be 'like', 'comment', or 'dm'"}), 400
        
#         can_interact = ai_scheduler.check_interaction_cooldown(ai_id, target_user_id, interaction_enum)
        
#         return jsonify({
#             "success": True, 
#             "data": {
#                 "can_interact": can_interact,
#                 "ai_id": ai_id,
#                 "target_user_id": target_user_id,
#                 "interaction_type": interaction_type
#             }
#         }), 200
        
#     except Exception as ex:
#         logger.error("Error checking interaction cooldown: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/api/ai/engagement-stats-detailed', methods=['GET'])
# def get_detailed_engagement_stats():
#     """Get detailed AI engagement statistics with scheduling info"""
#     try:
#         # Get current stats from existing endpoint logic
#         stats = {'comments': 0, 'likes': 0, 'dms': 0}
        
#         try:
#             # Get stats from aiInteractions collection
#             today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
#             interactions_ref = db.collection('aiInteractions').where('timestamp', '>=', today_start)
            
#             for doc in interactions_ref.stream():
#                 interaction_type = doc.to_dict().get('interaction_type', '')
#                 if interaction_type in ['comment', 'like', 'dm']:
#                     key = interaction_type + 's' if interaction_type != 'dm' else 'dms'
#                     stats[key] = stats.get(key, 0) + 1
#         except:
#             # Fallback to existing method if aiInteractions doesn't exist yet
#             pass
        
#         stats['total_interactions'] = stats['comments'] + stats['likes'] + stats['dms']
        
#         # Add scheduling info
#         scheduling_info = {
#             'limits': {
#                 'comments_per_day': f"{ai_scheduler.limits.comments_min}-{ai_scheduler.limits.comments_max}",
#                 'likes_per_day': f"{ai_scheduler.limits.likes_min}-{ai_scheduler.limits.likes_max}",
#                 'dms_per_day': ai_scheduler.limits.dms_max
#             },
#             'cooldowns': {
#                 'comment_cooldown_hours': ai_scheduler.cooldowns.same_user_comment_hours,
#                 'dm_no_reply_cooldown_days': ai_scheduler.cooldowns.dm_no_reply_days,
#                 'user_interaction_min_hours': ai_scheduler.cooldowns.user_interaction_min_hours,
#                 'max_daily_interactions_per_user': ai_scheduler.cooldowns.max_daily_interactions_per_user
#             },
#             'ratios': {
#                 'likes_percent': ai_scheduler.ratios.likes_percent,
#                 'comments_percent': ai_scheduler.ratios.comments_percent,
#                 'dms_percent': ai_scheduler.ratios.dms_percent
#             }
#         }
        
#         return jsonify({
#             "success": True, 
#             "data": {
#                 "daily_stats": stats,
#                 "scheduling_config": scheduling_info,
#                 "timestamp": datetime.now()
#             }
#         }), 200
        
#     except Exception as ex:
#         logger.error("Error getting detailed engagement stats: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/execute-scheduled-engagement', methods=['POST'])
def execute_scheduled_engagement():
    """Execute scheduled AI engagement with proper rate limiting and cooldowns"""
    try:
        data = request.get_json() or {}
        character_limit = data.get('character_limit', 10)
        force_execute = data.get('force_execute', False)
        
        # First, schedule all characters to get planned interactions
        schedule_result = ai_scheduler.schedule_all_characters(character_limit)
        
        if not schedule_result['success']:
            return jsonify({"success": False, "error": "Failed to create schedule"}), 400
        
        executed_interactions = []
        errors = []
        
        # Execute scheduled interactions
        for character_data in schedule_result['characters']:
            character_id = character_data['character_id']
            character_name = character_data['character_name']
            
            for interaction in character_data['scheduled_interactions']:
                target_user_id = interaction['target_user_id']
                interaction_type = interaction['interaction_type']
                
                try:
                    if interaction_type == 'dm':
                        # Execute DM using existing logic
                        ai_user_data = get_user_data_from_any_collection(character_id)
                        target_user_data = get_user_data_from_any_collection(target_user_id)
                        
                        if ai_user_data and target_user_data:
                            # Generate and send DM
                            ai_service = InZoneAIEngagementService(db, client)
                            message = ai_service.generate_ai_dm_message(ai_user_data, target_user_data)
                            conversation_id = f"{character_id}_{target_user_id}"
                            
                            # Create or update conversation
                            conv_ref = db.collection('conversations').document(conversation_id)
                            conv_doc = conv_ref.get()
                            
                            if not conv_doc.exists:
                                conv_ref.set({
                                    'participants': [character_id, target_user_id],
                                    'created_at': datetime.now(),
                                    'last_message_at': datetime.now()
                                })
                            
                            # Add message
                            message_ref = conv_ref.collection('messages').add({
                                'sender_id': character_id,
                                'message': message,
                                'timestamp': datetime.now(),
                                'read': False
                            })
                            
                            executed_interactions.append({
                                'type': 'dm',
                                'character': character_name,
                                'target_user': target_user_data.get('name', 'Unknown'),
                                'message': message
                            })
                            
                            # Log the interaction
                            from ai_scheduler import EngagementType
                            ai_scheduler.log_interaction(
                                character_id, 
                                target_user_id, 
                                EngagementType.DM,
                                {'conversation_id': conversation_id}
                            )
                    
                    elif interaction_type == 'like':
                        # Find a recent post to like
                        posts_ref = db.collection('humanPosts').where('user_id', '==', target_user_id).limit(3)
                        posts = list(posts_ref.stream())
                        
                        if posts:
                            post_doc = random.choice(posts)
                            post_ref = db.collection('humanPosts').document(post_doc.id)
                            
                            # Add like
                            like_data = {
                                'user_id': character_id,
                                'timestamp': datetime.now()
                            }
                            post_ref.collection('likes').document(character_id).set(like_data)
                            
                            # Update like count
                            post_data = post_doc.to_dict()
                            current_likes = post_data.get('likes', 0)
                            post_ref.update({'likes': current_likes + 1})
                            
                            executed_interactions.append({
                                'type': 'like',
                                'character': character_name,
                                'post_author': post_data.get('author_name', 'Unknown'),
                                'post_id': post_doc.id
                            })
                            
                            # Log the interaction
                            from ai_scheduler import EngagementType
                            ai_scheduler.log_interaction(
                                character_id,
                                target_user_id,
                                EngagementType.LIKE,
                                {'post_id': post_doc.id}
                            )
                    
                    elif interaction_type == 'comment':
                        # Find a recent post to comment on
                        posts_ref = db.collection('humanPosts').where('user_id', '==', target_user_id).limit(3)
                        posts = list(posts_ref.stream())
                        
                        if posts:
                            post_doc = random.choice(posts)
                            post_data = post_doc.to_dict()
                            
                            # Generate comment
                            ai_service = InZoneAIEngagementService(db, client)
                            ai_user_data = get_user_data_from_any_collection(character_id)
                            trends = ai_service.get_trending_content_insights()
                            comment_text = ai_service.generate_contextual_ai_comment(ai_user_data, post_data, trends)
                            
                            # Add comment
                            comment_data = {
                                'user_id': character_id,
                                'comment': comment_text,
                                'timestamp': datetime.now(),
                                'likes': 0
                            }
                            
                            post_ref = db.collection('humanPosts').document(post_doc.id)
                            comment_ref = post_ref.collection('comments').add(comment_data)
                            
                            # Update comment count
                            current_comments = post_data.get('comments', 0)
                            post_ref.update({'comments': current_comments + 1})
                            
                            executed_interactions.append({
                                'type': 'comment',
                                'character': character_name,
                                'post_author': post_data.get('author_name', 'Unknown'),
                                'comment': comment_text,
                                'post_id': post_doc.id
                            })
                            
                            # Log the interaction
                            from ai_scheduler import EngagementType
                            ai_scheduler.log_interaction(
                                character_id,
                                target_user_id,
                                EngagementType.COMMENT,
                                {'post_id': post_doc.id, 'comment_id': comment_ref[1].id}
                            )
                
                except Exception as interaction_error:
                    errors.append({
                        'character': character_name,
                        'target': target_user_id,
                        'type': interaction_type,
                        'error': str(interaction_error)
                    })
        
        return jsonify({
            "success": True,
            "data": {
                "scheduled_plan": schedule_result,
                "executed_interactions": executed_interactions,
                "total_executed": len(executed_interactions),
                "errors": errors,
                "execution_timestamp": datetime.now()
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error executing scheduled engagement: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# ---------------------------
# AI Scheduler Endpoints
# ---------------------------
from ai_scheduler import AIScheduler
ai_scheduler = AIScheduler(db)

@app.route('/api/ai/schedule-character-engagement', methods=['POST'])
def schedule_character_engagement_api():
    """Manually trigger engagement for a specific character"""
    try:
        data = request.get_json()
        character_id = data.get('character_id')
        
        if not character_id:
            return jsonify({"success": False, "error": "Character ID required"}), 400
        
        result = ai_scheduler.schedule_character_engagement(character_id)
        return jsonify(result), 200 if result.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in character engagement API: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/schedule-all-characters', methods=['POST'])
def schedule_all_characters_api():
    """Trigger engagement for all popular characters"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 20)
        
        result = ai_scheduler.schedule_all_characters(limit=limit)
        return jsonify(result), 200 if result.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in all characters engagement API: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/schedule-engagement-auto', methods=['POST'])
def schedule_engagement_auto():
    """Auto-schedule and EXECUTE engagement with simple concurrency protection"""
    try:
        # Simple in-memory lock to prevent concurrent executions
        if not hasattr(schedule_engagement_auto, '_is_running'):
            schedule_engagement_auto._is_running = False
        
        if schedule_engagement_auto._is_running:
            return jsonify({
                'success': False,
                'error': 'AI engagement already running',
                'message': 'Another instance is currently executing AI engagement. Please wait and try again.',
                'suggestion': 'Wait a few minutes before trying again.'
            }), 429
        
        # Set running flag
        schedule_engagement_auto._is_running = True
        
        try:
            data = request.get_json() or {}
            
            # Check if we've run recently (additional rate limiting)
            last_run_ref = db.collection('system_state').document('last_ai_engagement_run')
            last_run_doc = last_run_ref.get()
            
            if last_run_doc.exists:
                last_run_data = last_run_doc.to_dict()
                last_run_time = last_run_data.get('timestamp')
                
                if last_run_time:
                    # Handle timezone-aware timestamps
                    if hasattr(last_run_time, 'tzinfo') and last_run_time.tzinfo is not None:
                        last_run_time = last_run_time.replace(tzinfo=None)
                    
                    time_since_last_run = (datetime.now() - last_run_time).total_seconds()
                    
                    # Prevent runs closer than 30 minutes apart (1800 seconds) - original setting restored
                    if time_since_last_run < 1800:
                        return jsonify({
                            'success': False,
                            'error': 'Rate limit exceeded',
                            'message': f'Last run was {int(time_since_last_run)} seconds ago. Minimum interval is 1800 seconds.',
                            'last_run_time': str(last_run_time),
                            'time_since_last_run': int(time_since_last_run)
                        }), 429
            
            # Execute the scheduling and actual interactions
            schedule_result = ai_scheduler.schedule_all_characters(limit=50)
            
            if not schedule_result['success']:
                return jsonify(schedule_result), 500
            
            executed_interactions = []
            total_executed = 0
            errors = []
            
            # 🤖 CRITICAL FIX: Run DM monitoring FIRST to catch immediate responses
            try:
                print('🔄 Running DM monitoring to catch pending responses...')
                dm_monitor_result = ai_scheduler.monitor_and_respond_to_dms()
                
                if dm_monitor_result['success']:
                    dm_responses = dm_monitor_result.get('responses_sent', 0)
                    total_executed += dm_responses
                    
                    # Add DM responses to executed interactions
                    for response_detail in dm_monitor_result.get('response_details', []):
                        executed_interactions.append({
                            'type': 'dm_response',
                            'character': response_detail.get('ai_character', 'Unknown'),
                            'target_user': response_detail.get('human_user', 'Unknown'),
                            'conversation_id': response_detail.get('conversation_id', ''),
                            'immediate_response': True
                        })
                    
                    print(f'✅ DM monitoring sent {dm_responses} immediate responses')
                else:
                    print(f'⚠️ DM monitoring had issues: {dm_monitor_result.get("error", "Unknown")}')
            except Exception as dm_error:
                print(f'❌ DM monitoring error: {dm_error}')
                errors.append({
                    'type': 'dm_monitoring',
                    'error': str(dm_error)
                })
            
            # Execute each character's scheduled interactions
            for character_data in schedule_result.get('characters', []):
                character_id = character_data['character_id']
                character_name = character_data['character_name']
                
                for interaction in character_data.get('scheduled_interactions', []):
                    try:
                        interaction_type = interaction['interaction_type']
                        success = False
                        
                        if interaction_type == 'like' and 'target_post_id' in interaction:
                            success = ai_scheduler.execute_like_interaction(
                                character_id, 
                                interaction['target_post_id'],
                                interaction.get('post_collection', 'humanPosts')
                            )
                            if success:
                                executed_interactions.append({
                                    'type': 'like',
                                    'character': character_name,
                                    'post_id': interaction['target_post_id']
                                })
                                total_executed += 1
                        
                        elif interaction_type == 'comment' and 'target_post_id' in interaction:
                            success = ai_scheduler.execute_comment_interaction(
                                character_id,
                                interaction['target_post_id'],
                                interaction.get('post_collection', 'humanPosts')
                            )
                            if success:
                                executed_interactions.append({
                                    'type': 'comment',
                                    'character': character_name,
                                    'post_id': interaction['target_post_id']
                                })
                                total_executed += 1
                        
                        elif interaction_type == 'dm' and 'target_user_id' in interaction:
                            success = ai_scheduler.execute_dm_interaction(
                                character_id,
                                interaction['target_user_id']
                            )
                            if success:
                                executed_interactions.append({
                                    'type': 'dm',
                                    'character': character_name,
                                    'target_user': interaction['target_user_id']
                                })
                                total_executed += 1
                                
                    except Exception as e:
                        errors.append({
                            'character': character_name,
                            'interaction_type': interaction.get('interaction_type'),
                            'error': str(e)
                        })
                        logger.error(f"Error executing interaction for {character_name}: {e}")
            
            # Update last run timestamp
            last_run_ref.set({
                'timestamp': firestore.SERVER_TIMESTAMP,
                'total_executed': total_executed,
                'total_scheduled': schedule_result.get('total_interactions_scheduled', 0)
            }, merge=True)
            
            result = {
                'success': True,
                'total_characters': schedule_result.get('total_characters', 0),
                'total_interactions_scheduled': schedule_result.get('total_interactions_scheduled', 0),
                'total_executed': total_executed,
                'executed_interactions': executed_interactions,
                'errors': errors,
                'execution_summary': f"Executed {total_executed}/{schedule_result.get('total_interactions_scheduled', 0)} scheduled interactions"
            }
            
            logger.info(f"AI engagement completed: {total_executed} interactions executed for {result['total_characters']} characters")
            return jsonify(result), 200
            
        finally:
            # Always clear the running flag
            schedule_engagement_auto._is_running = False
        
    except Exception as e:
        # Make sure to clear the flag even if there's an exception
        if hasattr(schedule_engagement_auto, '_is_running'):
            schedule_engagement_auto._is_running = False
        logger.error(f"Error in auto engagement scheduling: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/engagement-status', methods=['GET'])
def get_engagement_status():
    """Get current engagement status and counts"""
    try:
        # Get count of popular characters
        chars_ref = db.collection('popularCharacters')
        char_count = len(list(chars_ref.limit(100).stream()))
        
        # Get recent activity counts (use simple queries to avoid index issues)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Count today's likes (fetch all recent and filter in Python)
        likes_docs = list(db.collection('postLikes').limit(500).stream())
        likes_today = sum(1 for doc in likes_docs 
                         if doc.to_dict().get('is_ai', False) and 
                         doc.to_dict().get('timestamp', datetime.min.replace(tzinfo=timezone.utc)) >= today)
        
        # Count today's comments (fetch all recent and filter in Python)
        comments_docs = list(db.collection('postComments').limit(500).stream())
        comments_today = sum(1 for doc in comments_docs 
                           if doc.to_dict().get('is_ai', False) and 
                           doc.to_dict().get('timestamp', datetime.min.replace(tzinfo=timezone.utc)) >= today)
        
        # Count today's DMs (fetch all recent and filter in Python)
        dms_docs = list(db.collection('messages').limit(500).stream())
        dms_today = sum(1 for doc in dms_docs 
                       if doc.to_dict().get('is_ai', False) and 
                       doc.to_dict().get('timestamp', datetime.min.replace(tzinfo=timezone.utc)) >= today)
        
        return jsonify({
            "success": True,
            "data": {
                "total_characters": char_count,
                "today_stats": {
                    "likes": likes_today,
                    "comments": comments_today,
                    "dms": dms_today,
                    "total_interactions": likes_today + comments_today + dms_today
                },
                "scheduler_config": {
                    "comments_range": f"{ai_scheduler.limits.comments_min}-{ai_scheduler.limits.comments_max}",
                    "likes_range": f"{ai_scheduler.limits.likes_min}-{ai_scheduler.limits.likes_max}",
                    "max_dms": ai_scheduler.limits.dms_max
                }
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting engagement status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/api/ai/dm-reply-webhook', methods=['POST'])
# def handle_dm_reply():
#     """Instantly respond when someone replies to an AI DM - 24/7 real-time responses"""
#     try:
#         data = request.get_json()
#         conversation_id = data.get('conversation_id')
#         sender_id = data.get('sender_id')
#         message_text = data.get('message_text')
        
#         if not conversation_id or not sender_id:
#             return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
#         # Get conversation to check if it involves an AI character
#         conv_ref = db.collection('conversations').document(conversation_id)
#         conv_doc = conv_ref.get()
        
#         if not conv_doc.exists:
#             return jsonify({'success': False, 'error': 'Conversation not found'}), 404
            
#         conv_data = conv_doc.to_dict()
#         participants = conv_data.get('participants', [])
        
#         # Find AI character in conversation
#         ai_chars_ref = db.collection('popularCharacters')
#         ai_characters = {doc.id: doc.to_dict() for doc in ai_chars_ref.stream()}
        
#         ai_participant = None
#         for participant in participants:
#             if participant in ai_characters and participant != sender_id:
#                 ai_participant = participant
#                 break
                
#         if not ai_participant:
#             return jsonify({'success': False, 'error': 'No AI character in conversation'}), 400
        
#         # Import AI service and generate immediate response
#         from ai_scheduler import AIScheduler
#         ai_scheduler = AIScheduler(db)
        
#         # Get human user data
#         human_ref = db.collection('humanUsers').document(sender_id)
#         human_doc = human_ref.get()
        
#         if not human_doc.exists:
#             return jsonify({'success': False, 'error': 'Human user not found'}), 404
            
#         human_data = human_doc.to_dict()
#         ai_character = ai_characters[ai_participant]
        
#         # Get recent message history for context
#         messages_ref = conv_ref.collection('messages')
#         recent_messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
#         message_history = [msg.to_dict() for msg in recent_messages]
        
#         # Send immediate response
#         success = ai_scheduler.send_immediate_dm_response(
#             ai_participant, 
#             sender_id, 
#             conversation_id, 
#             message_history,
#             ai_character
#         )
        
#         if success:
#             return jsonify({
#                 'success': True, 
#                 'message': 'AI responded immediately',
#                 'ai_character': ai_character.get('name', ai_participant),
#                 'conversation_id': conversation_id
#             }), 200
#         else:
#             return jsonify({'success': False, 'error': 'Failed to send response'}), 500
            
#     except Exception as e:
#         logger.error(f"Error in DM reply webhook: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500

# # DEPRECATED: Duplicate of dm-reply-webhook - use /api/ai/dm-auto-responder instead  
# # @app.route('/api/ai/dm-instant-response', methods=['POST'])
# # def dm_instant_response():
#     """Instantly respond when someone replies to an AI DM - 24/7 real-time responses"""
#     try:
#         data = request.get_json()
#         conversation_id = data.get('conversation_id')
#         sender_id = data.get('sender_id')
#         message_text = data.get('message_text')
        
#         if not conversation_id or not sender_id:
#             return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
#         # Get conversation to check if it involves an AI character
#         conv_ref = db.collection('conversations').document(conversation_id)
#         conv_doc = conv_ref.get()
        
#         if not conv_doc.exists:
#             return jsonify({'success': False, 'error': 'Conversation not found'}), 404
            
#         conv_data = conv_doc.to_dict()
#         participants = conv_data.get('participants', [])
        
#         # Find AI character in conversation
#         ai_chars_ref = db.collection('popularCharacters')
#         ai_characters = {doc.id: doc.to_dict() for doc in ai_chars_ref.stream()}
        
#         ai_participant = None
#         for participant in participants:
#             if participant in ai_characters and participant != sender_id:
#                 ai_participant = participant
#                 break
                
#         if not ai_participant:
#             return jsonify({'success': False, 'error': 'No AI character in conversation'}), 400
        
#         # Import AI service and generate immediate response
#         from ai_scheduler import AIScheduler
#         ai_scheduler = AIScheduler(db)
        
#         # Get human user data
#         human_ref = db.collection('humanUsers').document(sender_id)
#         human_doc = human_ref.get()
        
#         if not human_doc.exists:
#             return jsonify({'success': False, 'error': 'Human user not found'}), 404
            
#         human_data = human_doc.to_dict()
#         ai_character = ai_characters[ai_participant]
        
#         # Get recent message history for context
#         messages_ref = conv_ref.collection('messages')
#         recent_messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
#         message_history = [msg.to_dict() for msg in recent_messages]
        
#         # Send immediate response
#         success = ai_scheduler.send_immediate_dm_response(
#             ai_participant, 
#             sender_id, 
#             conversation_id, 
#             message_history,
#             ai_character
#         )
        
#         if success:
#             return jsonify({
#                 'success': True, 
#                 'message': 'AI responded immediately',
#                 'ai_character': ai_character.get('name', ai_participant),
#                 'conversation_id': conversation_id,
#                 'response_time': 'immediate'
#             }), 200
#         else:
#             return jsonify({'success': False, 'error': 'Failed to send response'}), 500
            
#     except Exception as e:
#         logger.error(f"Error in DM instant response: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/dm-auto-responder', methods=['POST'])
def dm_auto_responder():
    """
    SINGLE-CONVERSATION DM RESPONSE: Responds to a specific conversation when Flutter app triggers it.
    Use this when a human sends a message and you want an immediate AI response for that specific conversation.
    
    Required data: user_id, ai_character_id, message_text, conversation_id (optional)
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        ai_character_id = data.get('ai_character_id') 
        message_text = data.get('message_text', '')
        conversation_id = data.get('conversation_id')
        
        if not user_id or not ai_character_id:
            return jsonify({'success': False, 'error': 'Missing user_id or ai_character_id'}), 400
        
        # Generate conversation ID if not provided
        if not conversation_id:
            participants = sorted([user_id, ai_character_id])
            conversation_id = f"{participants[0]}_{participants[1]}"
        
        # Get AI character data
        ai_char_ref = db.collection('popularCharacters').document(ai_character_id)
        ai_char_doc = ai_char_ref.get()
        
        if not ai_char_doc.exists:
            return jsonify({'success': False, 'error': 'AI character not found'}), 404
            
        ai_character = ai_char_doc.to_dict()
        
        # Get human user data  
        human_ref = db.collection('humanUsers').document(user_id)
        human_doc = human_ref.get()
        
        if not human_doc.exists:
            return jsonify({'success': False, 'error': 'Human user not found'}), 404
            
        human_data = human_doc.to_dict()
        
        # Get conversation history
        conv_ref = db.collection('conversations').document(conversation_id)
        conv_doc = conv_ref.get()
        
        # Ensure conversation exists
        if not conv_doc.exists:
            logger.info(f"Creating new conversation: {conversation_id}")
            conv_ref.set({
                'participants': [user_id, ai_character_id],
                'participantNames': {
                    user_id: human_data.get('name', user_id),
                    ai_character_id: ai_character.get('name', ai_character_id)
                },
                'lastMessage': message_text,
                'lastMessageTime': firestore.SERVER_TIMESTAMP,
                'lastUpdated': firestore.SERVER_TIMESTAMP,
                'isAIConversation': True
            })
        
        messages_ref = conv_ref.collection('messages')
        recent_messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
        message_history = [msg.to_dict() for msg in recent_messages]
        
        # Generate and send AI response
        from ai_scheduler import AIScheduler
        ai_scheduler = AIScheduler(db)
        
        logger.info(f"🚀 DM Auto-Responder: {ai_character.get('name', ai_character_id)} responding to {human_data.get('name', user_id)}")
        logger.info(f"Message history length: {len(message_history)}")
        
        success = ai_scheduler.send_immediate_dm_response(
            ai_character_id,
            user_id, 
            conversation_id,
            message_history,
            ai_character
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'AI auto-response sent',
                'ai_character_name': ai_character.get('name', ai_character_id),
                'conversation_id': conversation_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to generate response'}), 500
            
    except Exception as e:
        logger.error(f"Error in DM auto responder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/monitor-dms', methods=['POST'])
def monitor_and_respond_dms():
    """
    MASS DM MONITORING: Monitors ALL conversations across ALL AI characters and responds automatically.
    Use this for background monitoring to catch any missed messages. Includes notifications.
    
    No required data - scans everything and responds where needed.
    """
    try:
        from ai_scheduler import AIScheduler
        
        # Initialize the AI scheduler for DM monitoring (separate from scheduled engagement)
        ai_scheduler = AIScheduler(db)
        
        # Monitor conversations and respond to pending DMs
        result = ai_scheduler.monitor_and_respond_to_dms()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Monitored conversations and sent {result['responses_sent']} immediate responses",
                'responses_sent': result['responses_sent'],
                'characters_checked': result.get('characters_checked', 0),
                'response_details': result.get('response_details', []),
                'timestamp': result.get('timestamp'),
                'type': 'dm_monitoring'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error'),
                'type': 'dm_monitoring'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in DM monitoring: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'type': 'dm_monitoring'
        }), 500

@app.route('/api/ai/comments/debug', methods=['GET'])
def debug_comments():
    """Debug the structure of comments in postComments collection"""
    try:
        logger.info("Starting comment collection debug")
        
        # Count documents in postComments collection
        comments_docs = list(db.collection('postComments').limit(500).stream())
        logger.info(f"Found {len(comments_docs)} documents in postComments collection")
        
        # Analyze structure
        ai_comments_wrong = 0
        human_comments_proper = 0
        mixed_docs = 0
        unknown_structure = 0
        
        for doc in comments_docs:
            doc_data = doc.to_dict()
            doc_id = doc.id
            
            # Check if this is an AI comment with wrong structure (individual document)
            if 'isAIGenerated' in doc_data or 'is_ai' in doc_data or 'aiUserName' in doc_data:
                ai_comments_wrong += 1
                logger.info(f"AI comment doc {doc_id}: {doc_data.get('content', 'No content')}")
            
            # Check if this is proper structure (has comments array)
            elif 'comments' in doc_data:
                comments_array = doc_data.get('comments', [])
                has_ai = any(comment.get('isAIGenerated') or comment.get('is_ai') for comment in comments_array if isinstance(comment, dict))
                if has_ai:
                    mixed_docs += 1
                else:
                    human_comments_proper += 1
            else:
                unknown_structure += 1
                logger.info(f"Unknown structure doc {doc_id}: {doc_data}")
        
        return jsonify({
            'success': True,
            'total_docs': len(comments_docs),
            'ai_comments_wrong_structure': ai_comments_wrong,
            'human_comments_proper_structure': human_comments_proper,
            'mixed_docs_with_ai_comments': mixed_docs,
            'unknown_structure': unknown_structure
        })
        
    except Exception as e:
        logger.error(f"Error debugging comments: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/comments/cleanup-incorrect-structure', methods=['POST'])
def cleanup_incorrect_ai_comments():
    """
    Remove all AI comments that were incorrectly stored as separate documents
    instead of being added to the comments array of the post document.
    """
    try:
        logger.info("Starting cleanup of incorrectly structured AI comments")
        
        # Get all documents from postComments collection
        comments_docs = list(db.collection('postComments').stream())
        logger.info(f"Found {len(comments_docs)} total documents in postComments collection")
        
        deleted_count = 0
        kept_count = 0
        errors = []
        
        for doc in comments_docs:
            try:
                doc_data = doc.to_dict()
                doc_id = doc.id
                
                # Check if this is an AI comment with wrong structure (individual document)
                is_ai_comment = (
                    doc_data.get('isAIGenerated') == True or 
                    doc_data.get('is_ai') == True or
                    'aiUserName' in doc_data
                )
                
                # Check if this is the correct structure (has comments array)
                has_comments_array = 'comments' in doc_data
                
                if is_ai_comment and not has_comments_array:
                    # This is an incorrectly structured AI comment - delete it
                    logger.info(f"Deleting incorrect AI comment doc {doc_id}: {doc_data.get('content', 'No content')}")
                    db.collection('postComments').document(doc_id).delete()
                    deleted_count += 1
                else:
                    # This is either a proper structure or human comment - keep it
                    kept_count += 1
                    
            except Exception as e:
                error_msg = f"Error processing document {doc_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        result = {
            'success': True,
            'total_documents_processed': len(comments_docs),
            'incorrect_ai_comments_deleted': deleted_count,
            'correct_documents_kept': kept_count,
            'errors': errors
        }
        
        logger.info(f"Cleanup completed: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error during AI comments cleanup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/migrate-post-likes', methods=['POST'])
def migrate_post_likes_collection():
    """
    Migrate all documents from post_likes collection to postLikes collection
    """
    try:
        logger.info("Starting migration from post_likes to postLikes collection")
        
        # Get all documents from post_likes collection
        post_likes_docs = list(db.collection('post_likes').stream())
        logger.info(f"Found {len(post_likes_docs)} documents in post_likes collection")
        
        if len(post_likes_docs) == 0:
            return jsonify({
                'success': True,
                'message': 'No documents found in post_likes collection',
                'migrated_count': 0
            })
        
        migrated_count = 0
        errors = []
        
        # Migrate each document
        for doc in post_likes_docs:
            try:
                doc_data = doc.to_dict()
                doc_id = doc.id
                
                # Add to new postLikes collection with same document ID
                db.collection('postLikes').document(doc_id).set(doc_data)
                
                # Delete from old post_likes collection
                db.collection('post_likes').document(doc_id).delete()
                
                migrated_count += 1
                logger.info(f"Migrated document {doc_id}")
                
            except Exception as e:
                error_msg = f"Error migrating document {doc_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        result = {
            'success': True,
            'total_documents_found': len(post_likes_docs),
            'migrated_count': migrated_count,
            'errors': errors
        }
        
        logger.info(f"Migration completed: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error during post_likes migration: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ai/verify-post-likes-migration', methods=['GET'])
def verify_post_likes_migration():
    """
    Verify the migration by checking both collections
    """
    try:
        # Count documents in old collection
        old_collection_docs = list(db.collection('post_likes').limit(10).stream())
        old_count = len(old_collection_docs)
        
        # Count documents in new collection
        new_collection_docs = list(db.collection('postLikes').limit(500).stream())
        new_count = len(new_collection_docs)
        
        return jsonify({
            'success': True,
            'old_collection_post_likes_count': old_count,
            'new_collection_postLikes_count': new_count,
            'migration_needed': old_count > 0
        })
        
    except Exception as e:
        logger.error(f"Error verifying migration: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# @app.route('/api/ai/test-timestamp-conversion', methods=['GET'])
# def test_timestamp_conversion():
#     """Test timestamp conversion with one example"""
#     try:
#         # Test with the example we saw: "1750328374961"
#         test_timestamp = "1750328374961"
        
#         # Convert millisecond epoch to datetime
#         timestamp_ms = int(test_timestamp)
#         timestamp_sec = timestamp_ms / 1000
#         dt = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
        
#         # Format as proper datetime string
#         formatted_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S.%f')
        
#         return jsonify({
#             'success': True,
#             'original': test_timestamp,
#             'converted': formatted_timestamp,
#             'conversion_type': 'millisecond_epoch_to_datetime'
#         })
        
#     except Exception as e:
#         logger.error(f"Error testing timestamp conversion: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500

# @app.route('/api/ai/fix-comment-timestamps', methods=['POST'])
# def fix_comment_timestamps():
#     """Fix incorrect timestamp formats in postComments collection"""
#     try:
#         # Get all postComments documents
#         posts_ref = db.collection('postComments')
#         posts = list(posts_ref.stream())
        
#         fixed_count = 0
#         total_comments_processed = 0
        
#         for post in posts:
#             post_data = post.to_dict()
#             comments = post_data.get('comments', [])
#             updated_comments = []
#             post_updated = False
            
#             for comment in comments:
#                 total_comments_processed += 1
#                 timestamp = comment.get('timestamp')
                
#                 # Check if timestamp is in wrong format (string starting with 17)
#                 if isinstance(timestamp, str) and timestamp.startswith('17') and timestamp.isdigit():
#                     try:
#                         # Convert millisecond epoch to datetime
#                         timestamp_ms = int(timestamp)
#                         timestamp_sec = timestamp_ms / 1000
#                         dt = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
                        
#                         # Format as proper datetime string
#                         comment['timestamp'] = dt.strftime('%Y-%m-%d %H:%M:%S.%f')
#                         fixed_count += 1
#                         post_updated = True
                        
#                     except (ValueError, OSError) as e:
#                         logger.error(f"Error converting timestamp {timestamp}: {e}")
#                         # Keep original timestamp if conversion fails
#                         pass
                
#                 updated_comments.append(comment)
            
#             # Update the post if any comments were fixed
#             if post_updated:
#                 post.reference.update({'comments': updated_comments})
        
#         return jsonify({
#             'success': True,
#             'total_posts_processed': len(posts),
#             'total_comments_processed': total_comments_processed,
#             'timestamps_fixed': fixed_count
#         })
        
#     except Exception as e:
#         logger.error(f"Error fixing timestamps: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500

# @app.route('/api/ai/test-timestamp-format', methods=['GET'])
# def test_timestamp_format():
#     """Test to see what timestamp format is currently being used in postComments"""
#     try:
#         # Get a few postComments documents to check timestamp format
#         posts_ref = db.collection('postComments').limit(5)
#         posts = list(posts_ref.stream())
        
#         examples = []
#         for post in posts:
#             post_data = post.to_dict()
#             comments = post_data.get('comments', [])
            
#             for comment in comments[:3]:  # Check first 3 comments
#                 timestamp = comment.get('timestamp')
#                 examples.append({
#                     'post_id': post.id,
#                     'timestamp': timestamp,
#                     'timestamp_type': type(timestamp).__name__,
#                     'starts_with_17': str(timestamp).startswith('17') if timestamp else False
#                 })
        
#         return jsonify({
#             'success': True,
#             'timestamp_examples': examples,
#             'total_posts_checked': len(posts)
#         })
        
#     except Exception as e:
#         logger.error(f"Error testing timestamp format: {e}")
#         return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/fix-missing-uid', methods=['POST'])
def fix_missing_uid():
    """Fix humanUsers documents that are missing the 'uid' field"""
    try:
        logger.info("Starting UID fix process...")
        
        # Get all documents from humanUsers collection
        users_ref = db.collection('humanUsers')
        docs = users_ref.stream()
        
        updated_count = 0
        total_count = 0
        errors = []
        
        for doc in docs:
            total_count += 1
            doc_data = doc.to_dict()
            doc_id = doc.id
            
            # Check if the document is missing the 'uid' field entirely
            if 'uid' not in doc_data:
                logger.info(f"Found user without UID field: {doc_id}")
                
                # Update the document to set uid = document_id
                try:
                    users_ref.document(doc_id).update({
                        'uid': doc_id
                    })
                    updated_count += 1
                    logger.info(f"Updated user {doc_id} - set uid to {doc_id}")
                    
                except Exception as e:
                    error_msg = f"Failed to update user {doc_id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        # Verify the fix
        verification_docs = users_ref.stream()
        missing_uid_count = 0
        verification_total = 0
        
        for doc in verification_docs:
            verification_total += 1
            doc_data = doc.to_dict()
            if 'uid' not in doc_data:
                missing_uid_count += 1
        
        logger.info(f"UID fix process completed:")
        logger.info(f"Total users processed: {total_count}")
        logger.info(f"Users updated: {updated_count}")
        logger.info(f"Users still missing UID after fix: {missing_uid_count}")
        
        return jsonify({
            "success": True,
            "message": "UID fix process completed",
            "data": {
                "total_processed": total_count,
                "updated": updated_count,
                "already_had_uid": total_count - updated_count,
                "still_missing_uid": missing_uid_count,
                "errors": errors
            }
        }), 200
        
    except Exception as ex:
        logger.error("Error during UID fix process: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# ---------------------------
# Comment Reply Notification Endpoint
# ---------------------------

@app.route('/api/notifications/events/comment-reply', methods=['POST'])
def trigger_comment_reply_notification():
    """Trigger notification when a user replies to a comment"""
    try:
        data = request.get_json()
        post_id = data.get("postId")
        replier_id = data.get("replierId")  # User who made the reply
        parent_comment_id = data.get("parentCommentId")  # The comment being replied to
        reply_content = data.get("replyContent")
        reply_id = data.get("replyId")
        
        if not all([post_id, replier_id, parent_comment_id, reply_content, reply_id]):
            return jsonify({"success": False, "error": "Missing required fields: postId, replierId, parentCommentId, replyContent, replyId"}), 400
        
        # Get the post comments to find the parent comment
        post_comment_doc = db.collection('postComments').document(post_id).get()
        
        if not post_comment_doc.exists:
            return jsonify({"success": False, "error": "Post comments not found"}), 404
        
        comments = post_comment_doc.to_dict().get('comments', [])
        
        # Find the parent comment
        parent_comment = None
        post_author_id = None
        
        for comment in comments:
            if comment.get('id') == parent_comment_id:
                parent_comment = comment
                break
        
        if not parent_comment:
            return jsonify({"success": False, "error": "Parent comment not found"}), 404
        
        parent_comment_author_id = parent_comment.get('userId')
        parent_comment_author = parent_comment.get('author')
        
        # Validate that both users are human users (not AI)
        try:
            # Check if replier is human user
            replier_doc = db.collection('humanUsers').document(replier_id).get()
            if not replier_doc.exists:
                return jsonify({"success": False, "error": "Replier is not a human user"}), 400
            
            # Check if parent comment author is human user  
            parent_author_doc = db.collection('humanUsers').document(parent_comment_author_id).get()
            if not parent_author_doc.exists:
                return jsonify({"success": False, "error": "Parent comment author is not a human user"}), 400
                
        except Exception as e:
            logger.error(f"Error validating user types: {e}")
            return jsonify({"success": False, "error": "Error validating user types"}), 500
        
        # Don't send notification if user is replying to their own comment
        if replier_id == parent_comment_author_id:
            return jsonify({"success": True, "message": "No notification sent - user replied to own comment"}), 200
        
        # Find the post owner
        collections = ['humanPosts', 'reposts', 'aiPosts']
        for collection in collections:
            try:
                post_doc = db.collection(collection).document(post_id).get()
                if post_doc.exists:
                    post_data = post_doc.to_dict()
                    post_author_id = post_data.get('user_document_id')
                    break
            except Exception as e:
                continue
        
        # Get replier's username
        replier_username = get_user_name(replier_id)
        
        # Create and store notification for the parent comment author
        notification_data = {
            'userId': parent_comment_author_id,
            'type': 'comment_reply',
            'title': '',
            'body': f'{replier_username} replied to your comment',
            'isRead': False,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'data': {
                'postId': post_id,
                'parentCommentId': parent_comment_id,
                'parentCommentAuthor': parent_comment_author,
                'parentCommentAuthorId': parent_comment_author_id,
                'replyId': reply_id,
                'replierId': replier_id,
                'replierUsername': replier_username,
                'replyContent': reply_content,
                'postAuthorId': post_author_id
            }
        }
        
        # Store notification in Firestore
        notification_ref = db.collection('notifications').add(notification_data)
        notification_id = notification_ref[1].id
        
        # Send push notification directly
        try:
            # Get the parent comment author's FCM tokens
            parent_user_doc = db.collection('humanUsers').document(parent_comment_author_id).get()
            if parent_user_doc.exists:
                parent_user_data = parent_user_doc.to_dict()
                fcm_tokens = parent_user_data.get('fcmTokens', [])
                
                if fcm_tokens:
                    # Create push notification message - use replier name as title, reply content as body
                    title = f'{replier_username} replied to your comment'
                    body = reply_content[:100] + ('...' if len(reply_content) > 100 else '')  # Truncate if too long
                    
                    # Send to all user's devices
                    for token in fcm_tokens:
                        try:
                            message = messaging.Message(
                                notification=messaging.Notification(
                                    title=title,
                                    body=body,
                                ),
                                data={
                                    'type': 'comment_reply',
                                    'postId': post_id,
                                    'parentCommentId': parent_comment_id,
                                    'parentCommentAuthor': parent_comment_author,
                                    'parentCommentAuthorId': parent_comment_author_id,
                                    'replyId': reply_id,
                                    'replierId': replier_id,
                                    'replierUsername': replier_username,
                                    'replyContent': reply_content,
                                    'notificationId': notification_id
                                },
                                token=token,
                            )
                            
                            response = messaging.send(message)
                            logger.info(f"Push notification sent successfully: {response}")
                            
                        except messaging.UnregisteredError:
                            # Remove invalid token
                            logger.warning(f"Removing invalid FCM token for user {parent_comment_author_id}")
                            parent_user_ref = db.collection('humanUsers').document(parent_comment_author_id)
                            parent_user_ref.update({
                                'fcmTokens': firestore.ArrayRemove([token])
                            })
                        except Exception as token_error:
                            logger.error(f"Error sending push notification to token {token}: {token_error}")
                else:
                    logger.warning(f"No FCM tokens found for user: {parent_comment_author_id}")
            else:
                logger.warning(f"Parent comment author not found: {parent_comment_author_id}")
            
        except Exception as e:
            logger.error(f"Error sending push notification for comment reply: {e}")
            # Continue even if push notification fails
        
        return jsonify({
            "success": True,
            "message": "Comment reply notification sent successfully",
            "notificationId": notification_id
        }), 200
        
    except Exception as ex:
        logger.error("Error triggering comment reply notification: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

if __name__ == '__main__':
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/key.json"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))