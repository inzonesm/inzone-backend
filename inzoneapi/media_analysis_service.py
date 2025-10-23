"""
Media Analysis Service for content moderation
Analyzes images and videos for inappropriate content using OpenAI Vision API
"""

import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class MediaAnalysisService:
    def __init__(self, openai_client):
        self.client = openai_client
    
    def analyze_image_content(self, image_urls: List[str]) -> Dict:
        """Analyze images for inappropriate content using OpenAI Vision"""
        try:
            if not image_urls:
                return {"has_inappropriate_content": False, "analysis": "No images to analyze"}
            
            analysis_results = []
            overall_inappropriate = False
            
            for image_url in image_urls:
                try:
                    response = self.client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Analyze this image and respond ONLY with valid JSON in this exact format: {\"inappropriate\": false, \"reasons\": [], \"severity\": \"low\", \"description\": \"brief description\", \"sentiment\": \"positive\", \"sentiment_score\": 0.8, \"sentiment_reasoning\": \"why this sentiment\"}. Check for: violence, explicit content, hate symbols, inappropriate gestures. Rate sentiment as positive (happy/cute/uplifting), negative (sad/scary/disturbing), or neutral."
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url}
                                    }
                                ]
                            }
                        ],
                        max_tokens=300
                    )
                    
                    result_text = response.choices[0].message.content.strip()
                    
                    # Remove markdown code blocks if present (same fix as text analysis)
                    import re
                    markdown_pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
                    match = re.match(markdown_pattern, result_text, re.DOTALL)
                    if match:
                        result_text = match.group(1).strip()
                    
                    result = json.loads(result_text)
                    analysis_results.append(result)
                    
                    if result.get("inappropriate", False):
                        overall_inappropriate = True
                        
                except Exception as e:
                    logger.error(f"Error analyzing image {image_url}: {e}")
                    # IMPORTANT: When analysis fails, we should be cautious and block content
                    analysis_results.append({
                        "inappropriate": True,  # Changed to True for safety when analysis fails
                        "reasons": ["Image analysis failed - cannot verify content safety"],
                        "severity": "high",  # High severity for failed analysis
                        "description": "Analysis failed - blocking for safety",
                        "sentiment": "neutral",
                        "sentiment_score": 0.0,
                        "sentiment_reasoning": "Analysis failed"
                    })
                    overall_inappropriate = True  # Block when analysis fails
            
            return {
                "has_inappropriate_content": overall_inappropriate,
                "analysis": analysis_results
            }
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            # IMPORTANT: When analysis completely fails, block for safety
            return {
                "has_inappropriate_content": True, 
                "analysis": [{
                    "inappropriate": True,
                    "reasons": ["Complete image analysis failure - blocking for safety"],
                    "severity": "high",
                    "description": "Analysis system failed",
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "sentiment_reasoning": "Analysis system failed"
                }]
            }
    
    def analyze_video_content(self, video_urls: List[str]) -> Dict:
        """Analyze video thumbnails and metadata for inappropriate content"""
        # For now, we'll analyze video thumbnails if available
        # In the future, this could be expanded to analyze video frames
        try:
            if not video_urls:
                return {"has_inappropriate_content": False, "analysis": "No videos to analyze"}
            
            # For videos, we can analyze thumbnails or use metadata
            # This is a simplified implementation
            return {
                "has_inappropriate_content": False,
                "analysis": "Video content analysis placeholder - implement frame analysis if needed"
            }
            
        except Exception as e:
            logger.error(f"Video analysis failed: {e}")
            return {"has_inappropriate_content": False, "analysis": "Analysis failed"}
