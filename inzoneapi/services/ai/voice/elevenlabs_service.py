import logging
import json
import requests
from functools import lru_cache
from config import Config

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
elevenlabs_service = ElevenLabsVoiceService(Config.ELEVENLABS_API_KEY)