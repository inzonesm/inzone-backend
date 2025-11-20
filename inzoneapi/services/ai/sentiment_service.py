# services/ai/sentiment_service.py
from dependencies import db, openai_client
from typing import Dict, Any
import logging
from flask import jsonify
from services.media.media_analysis_service import MediaAnalysisService
import json
import re

logger = logging.getLogger(__name__)

class SentimentService:
    """Service for sentiment and content analysis"""

    def __init__(self):
        self.media_analysis_service = MediaAnalysisService(openai_client)

    def analyze_sentiment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sentiment of text, images, and videos"""
        try:
            # Extract text, images, and videos from request
            text_content = data.get('text', '')
            image_urls = data.get('image_urls', [])
            video_urls = data.get('video_urls', [])

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
                text_analysis = self._analyze_text(text_content)
                if text_analysis is None:
                    return jsonify({"success": False, "error": "Invalid response format from OpenAI", "code": "SENTIMENT_FORMAT_ERROR"}), 500

                urban_dict_analysis = {"flagged_terms": [], "explanations": [], "has_negative_slang": False}

                # Determine if content is inappropriate based on text analysis ONLY
                harmful_content = text_analysis.get("HarmfulContent", {})
                if harmful_content.get("detected", False):
                    overall_inappropriate = True

            # Analyze images
            if image_urls:
                image_analysis = self.media_analysis_service.analyze_image_content(image_urls)
                if image_analysis.get("has_inappropriate_content", False):
                    overall_inappropriate = True

            # Analyze videos
            if video_urls:
                video_analysis = self.media_analysis_service.analyze_video_content(video_urls)
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
                combined_sentiment = self._combine_sentiments(text_analysis, image_analysis)

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
            logger.error(f"Error analyzing sentiment: {ex}")
            return jsonify({"success": False, "error": "Failed to analyze sentiment", "code": "SENTIMENT_ERROR"}), 500

    def _analyze_text(self, text_content: str) -> Dict[str, Any]:
        """Analyze text sentiment using OpenAI"""
        try:
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
            completion = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an advanced content moderation and sentiment analysis AI. Analyze text for both sentiment and potential harmful content with high accuracy."},
                    {"role": "user", "content": enhanced_prompt}
                ]
            )

            # Extract and parse the response
            chat_response = completion.choices[0].message.content.strip()

            # Remove markdown code blocks if present (more robust handling)
            markdown_pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
            match = re.match(markdown_pattern, chat_response, re.DOTALL)
            if match:
                chat_response = match.group(1).strip()

            try:
                return json.loads(chat_response)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON response from OpenAI: %s", chat_response)
                logger.error("JSON decode error: %s", str(e))
                return None

        except Exception as ex:
            logger.error(f"Error in text analysis: {ex}")
            return None

    def _combine_sentiments(self, text_analysis: Dict[str, Any], image_analysis: Dict[str, Any]) -> str:
        """Combine text and image sentiment scores"""
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

        return combined_sentiment

# Singleton instance
sentiment_service = SentimentService()
