import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""

    # API Keys
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    MESHY_API_KEY = os.environ.get("MESH_API_KEY")
    ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "sk_a7adae8a80cf5bfe52afd8e5ca8fb1307cd06c0e4d8e2789")

    # Firebase
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "key.json")

    # Gorse Recommendation System
    GORSE_API_URL = os.getenv('GORSE_API_URL', 'http://localhost:8087')
    GORSE_API_KEY = os.getenv('GORSE_API_KEY', '')

    # Flask
    SECRET_KEY = 'INZONE1234'

    # ElevenLabs
    ELEVEN_MODEL_ID = "eleven_multilingual_v2"

    # Meshy API
    MESHY_HEADERS = {
        "Authorization": f"Bearer {MESHY_API_KEY}",
        "Content-Type": "application/json",
    }

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set")