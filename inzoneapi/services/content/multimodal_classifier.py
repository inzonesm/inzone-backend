"""
Multimodal AI Classifier for Posts

This classifier uses GPT-4o and GPT-4o-mini to classify posts into:
1. subCategories: 1-4 most relevant subcategories (from content/categories)
2. masterCategories: Corresponding master categories (auto-mapped from subcategories)

Strategy:
- Text-first: If text is clear → Use GPT-4o-mini (fast, cheap)
- Multimodal: If text is vague/missing AND has media → Use GPT-4o Vision
- Always returns both subCategories and masterCategories
"""

import logging
from typing import Dict, List, Any
from dependencies import openai_client, db
import json
import re

logger = logging.getLogger(__name__)


class MultimodalCategoryClassifier:
    """
    Intelligent multimodal classifier that assigns posts to subcategories and master categories
    """
    
    # Cache for category mappings (loaded once from Firestore)
    _category_mappings = None
    _subcategory_to_master = None
    
    @classmethod
    def _load_category_mappings(cls):
        """Load category mappings from Firestore content/categories"""
        if cls._category_mappings is not None:
            return
        
        try:
            categories_ref = db.collection('content').document('categories')
            categories_doc = categories_ref.get()
            
            if not categories_doc.exists:
                logger.error("content/categories document not found!")
                cls._category_mappings = {}
                cls._subcategory_to_master = {}
                return
            
            data = categories_doc.to_dict()
            cls._category_mappings = data.get('categories', {})
            
            # Build reverse mapping: subcategory -> master category
            cls._subcategory_to_master = {}
            for master_cat, subcats in cls._category_mappings.items():
                # Normalize master category name
                master_key = cls._normalize_master_key(master_cat)
                
                for subcat in subcats:
                    cls._subcategory_to_master[subcat] = master_key
            
            logger.info(f"Loaded {len(cls._category_mappings)} master categories with {len(cls._subcategory_to_master)} subcategories")
            
        except Exception as e:
            logger.error(f"Error loading category mappings: {e}")
            cls._category_mappings = {}
            cls._subcategory_to_master = {}
    
    @staticmethod
    def _normalize_master_key(emoji_name: str) -> str:
        """
        Convert emoji master category name to underscore format
        e.g., "🍔 Food & Drink" -> "food_drink"
        
        IMPORTANT: This mapping MUST match the keys in utils/master_categories.py
        """
        # Remove emoji and get text part
        text = emoji_name.split(' ', 1)[1] if ' ' in emoji_name else emoji_name
        
        # Manual mapping - MATCHES utils/master_categories.py EXACTLY
        mapping = {
            "Travel & Places": "travel_places",
            "Sports & Fitness": "sports_fitness",
            "Business & Entrepreneurship": "business_entrepreneurship",
            "Mental Health & Mindfulness": "mental_health_mindfulness",
            "Career & Workplace": "career_workplace",
            "News & Politics": "news_politics",
            "Environment & Sustainability": "environment_sustainability",
            "Community, Volunteering & Activism": "community_volunteering_activism",
            "Gaming & Esports": "gaming_esports",
            "Digital Life & Online Safety": "digital_life_online_safety",
            "Pets & Animals": "pets_animals",
            "Personal Finance & Investing": "personal_finance_investing",
            "Science": "science",
            "Comedy, Humor & Memes": "comedy_humor_memes",
            "Fashion & Beauty": "fashion_beauty",
            "Society, Culture & History": "society_culture_history",
            "Education & Learning": "education_learning",
            "Food & Drink": "food_drink",
            "Relationships & Life Skills": "relationships_life_skills",
            "Entertainment & Pop Culture": "entertainment_pop_culture",
            "Arts & Design": "arts_design",
            "Technology & Innovation": "technology_innovation",
            "DIY, Home & Garden": "diy_home_garden",
            "Music & Audio": "music_audio",
            "Health & Wellness": "health_wellness"
        }
        
        return mapping.get(text, text.lower().replace(' & ', '_').replace(' ', '_').replace(',', ''))
    
    @classmethod
    def _get_subcategory_list_for_prompt(cls) -> str:
        """Build formatted list of all subcategories for AI prompt"""
        cls._load_category_mappings()
        
        lines = []
        for master_cat, subcats in cls._category_mappings.items():
            lines.append(f"\n{master_cat}:")
            for subcat in subcats:
                lines.append(f"  - {subcat}")
        
        return "\n".join(lines)
    
    @staticmethod
    def is_text_vague(text: str) -> bool:
        """
        Determine if text is too vague to classify without visual context
        
        Criteria:
        - Very short (< 15 characters)
        - Generic phrases
        - Only emojis
        """
        if not text or len(text.strip()) < 15:
            return True
        
        text_lower = text.lower().strip()
        
        # Generic/vague phrases
        vague_phrases = [
            "this", "that", "look", "check", "wow", "nice", "cool",
            "awesome", "amazing", "lol", "omg", "haha", "😂", "🔥"
        ]
        
        # Check if mostly generic
        words = text_lower.split()
        if len(words) <= 3:
            for phrase in vague_phrases:
                if phrase in text_lower:
                    return True
        
        # Check if only emojis
        text_no_space = text.replace(' ', '')
        if all(ord(c) > 127 for c in text_no_space):  # Non-ASCII (likely emojis)
            return True
        
        return False
    
    @classmethod
    def classify_with_text(cls, text: str) -> Dict[str, Any]:
        """
        Classify using text only (GPT-4o-mini)
        
        Returns: {
            'subCategories': [...],  # 1-4 subcategories
            'masterCategories': [...],  # Corresponding masters
            'confidence': 'high' | 'medium' | 'low',
            'reasoning': '...'
        }
        """
        try:
            cls._load_category_mappings()
            
            if not text:
                return {
                    'subCategories': [],
                    'masterCategories': [],
                    'confidence': 'none',
                    'reasoning': 'No text provided'
                }
            
            subcategories_list = cls._get_subcategory_list_for_prompt()
            
            prompt = (
                f"You are a content classifier. Classify this social media post into 1-4 SUBCATEGORIES from the list below.\n\n"
                f"AVAILABLE SUBCATEGORIES (grouped by master category):\n"
                f"{subcategories_list}\n\n"
                f"IMPORTANT: You MUST select 1-4 SUBCATEGORIES (not master categories).\n"
                f"Choose the most specific and relevant subcategories.\n\n"
                f"Post text: {text}\n\n"
                f"Return a JSON object with:\n"
                f"- subCategories: array of 1-4 subcategory IDs (e.g., ['recipes', 'cooking'])\n"
                f"- confidence: 'high', 'medium', or 'low'\n"
                f"- reasoning: brief explanation\n\n"
                f"Response (JSON only):"
            )
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a precise content classifier. Return only valid JSON with subcategory IDs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            content = content.strip()
            result = json.loads(content)
            
            # Get subcategories
            sub_cats = result.get('subCategories', [])[:4]
            
            # Map to master categories
            master_cats = list(set([
                cls._subcategory_to_master.get(sc)
                for sc in sub_cats
                if sc in cls._subcategory_to_master
            ]))
            
            return {
                'subCategories': sub_cats,
                'masterCategories': master_cats,
                'confidence': result.get('confidence', 'medium'),
                'reasoning': result.get('reasoning', 'Text-based classification')
            }
            
        except Exception as e:
            logger.error(f"Text classification error: {e}")
            return {
                'subCategories': [],
                'masterCategories': [],
                'confidence': 'error',
                'reasoning': f'Error: {e}'
            }
    
    @classmethod
    def classify_with_vision(cls, text: str, image_urls: List[str], video_urls: List[str]) -> Dict[str, Any]:
        """
        Classify using GPT-4o Vision with images and videos
        
        Returns: {
            'subCategories': [...],
            'masterCategories': [...],
            'confidence': '...',
            'reasoning': '...'
        }
        """
        try:
            cls._load_category_mappings()
            
            subcategories_list = cls._get_subcategory_list_for_prompt()
            
            # Build multimodal prompt
            messages = [
                {
                    "role": "system",
                    "content": "You are an advanced multimodal content classifier. Analyze images and videos to accurately categorize social media posts into subcategories."
                }
            ]
            
            user_content = []
            
            # Add text instruction
            user_content.append({
                "type": "text",
                "text": (
                    f"Classify this social media post into 1-4 SUBCATEGORIES based on the visual content and text.\n\n"
                    f"AVAILABLE SUBCATEGORIES:\n"
                    f"{subcategories_list}\n\n"
                    f"Post text: {text if text else '(no text - analyze visual content)'}\n\n"
                    f"Return JSON with:\n"
                    f"- subCategories: array of 1-4 subcategory IDs\n"
                    f"- confidence: 'high', 'medium', or 'low'\n"
                    f"- reasoning: explain what you see and why you chose these categories"
                )
            })
            
            # Add images
            for img_url in image_urls:
                if img_url:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img_url}
                    })
            
            # Add YouTube video thumbnails
            youtube_count = 0
            for video_url in video_urls:
                if video_url and ('youtube.com' in video_url or 'youtu.be' in video_url):
                    video_id = cls._extract_youtube_id(video_url)
                    if video_id:
                        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": thumbnail_url}
                        })
                        youtube_count += 1
            
            # Fallback to text if no visual content
            if len(image_urls) == 0 and youtube_count == 0:
                logger.info("No visual content available, falling back to text classification")
                return cls.classify_with_text(text)
            
            messages.append({"role": "user", "content": user_content})
            
            # Call GPT-4o Vision
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=500,
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean markdown
            if content.startswith("```"):
                parts = content.split("```")
                if len(parts) >= 3:
                    content = parts[1]
                    if content.startswith("json") or content.startswith("JSON"):
                        content = content[4:].strip()
            
            content = content.strip()
            result = json.loads(content)
            
            # Get subcategories
            sub_cats = result.get('subCategories', [])[:4]
            
            # Map to master categories
            master_cats = list(set([
                cls._subcategory_to_master.get(sc)
                for sc in sub_cats
                if sc in cls._subcategory_to_master
            ]))
            
            return {
                'subCategories': sub_cats,
                'masterCategories': master_cats,
                'confidence': result.get('confidence', 'medium'),
                'reasoning': result.get('reasoning', 'Vision-based classification')
            }
            
        except Exception as e:
            logger.error(f"Vision classification error: {e}")
            # Fallback to text
            return cls.classify_with_text(text or "visual content")
    
    @staticmethod
    def _extract_youtube_id(url: str) -> str:
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\s]+)',
            r'youtube\.com\/embed\/([^&\s]+)',
            r'youtube\.com\/v\/([^&\s]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    @classmethod
    def classify_post(cls, post_data: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
        """
        Main entry point for post classification
        
        Args:
            post_data: Full post document from Firestore
            verbose: If True, print detailed classification process
            
        Returns: {
            'subCategories': [...],  # 1-4 subcategories
            'masterCategories': [...],  # Corresponding masters
            'method': 'text' or 'vision'  # Classification method used
        }
        """
        try:
            # Extract content
            post_field = post_data.get('post', {})
            text = post_field.get('text_content', '')
            
            # Filter empty strings
            images = [img for img in post_field.get('image_content', []) if img and img.strip()]
            videos = [vid for vid in post_field.get('video_content', []) if vid and vid.strip()]
            
            has_media = bool(images or videos)
            
            # Decision: Text-first or multimodal?
            if not text or (cls.is_text_vague(text) and has_media):
                # Use vision analysis
                method = 'vision'
                if verbose:
                    print(f"     💡 Strategy: Vision analysis (vague/no text + media)")
                    print(f"        - Text vague: {cls.is_text_vague(text)}")
                    print(f"        - Has media: {has_media} ({len(images)} imgs, {len(videos)} vids)")
                logger.info("Using vision analysis (vague/no text + has media)")
                result = cls.classify_with_vision(text, images, videos)
            else:
                # Use text-only (faster, cheaper)
                method = 'text'
                if verbose:
                    print(f"     💡 Strategy: Text-only classification (clear text)")
                    print(f"        - Text length: {len(text)} chars")
                logger.info("Using text-only classification")
                result = cls.classify_with_text(text)
            
            if verbose:
                print(f"     📝 Raw AI response:")
                print(f"        - Subcategories: {result.get('subCategories', [])}")
                print(f"        - Confidence: {result.get('confidence', 'N/A')}")
                if 'reasoning' in result:
                    print(f"        - Reasoning: {result['reasoning'][:80]}...")
            
            return {
                'subCategories': result.get('subCategories', [])[:4],
                'masterCategories': result.get('masterCategories', []),
                'method': method
            }
            
        except Exception as e:
            logger.error(f"Error in classify_post: {e}")
            if verbose:
                print(f"     ❌ Error: {e}")
            return {
                'subCategories': [],
                'masterCategories': [],
                'method': 'error'
            }


# Quick test
if __name__ == '__main__':
    print("\n" + "="*70)
    print("TESTING MULTIMODAL CATEGORY CLASSIFIER")
    print("="*70 + "\n")
    
    # Test 1: Clear text
    test1 = {
        'post': {
            'text_content': 'Just made the best chocolate chip cookies! Recipe in comments 🍪',
            'image_content': [],
            'video_content': []
        }
    }
    print("Test 1: Food recipe post")
    result1 = MultimodalCategoryClassifier.classify_post(test1)
    print(f"SubCategories: {result1['subCategories']}")
    print(f"MasterCategories: {result1['masterCategories']}\n")
    
    # Test 2: Gaming
    test2 = {
        'post': {
            'text_content': 'Finally hit Diamond rank in League of Legends! 🎮⚡',
            'image_content': [],
            'video_content': []
        }
    }
    print("Test 2: Gaming achievement")
    result2 = MultimodalCategoryClassifier.classify_post(test2)
    print(f"SubCategories: {result2['subCategories']}")
    print(f"MasterCategories: {result2['masterCategories']}\n")
