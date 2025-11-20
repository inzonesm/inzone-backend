import os
from firebase_admin import credentials, initialize_app, firestore, storage as firebase_storage
from openai import OpenAI
from config import Config

# Validate configuration
Config.validate()

# Firebase initialization
credential_path = Config.GOOGLE_APPLICATION_CREDENTIALS
if not os.path.isabs(credential_path):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credential_path = os.path.join(script_dir, credential_path)

cred = credentials.Certificate(credential_path)
default_app = initialize_app(cred)

# Firestore client
db = firestore.client()

# Firebase Storage client (optional - will be None if not configured)
try:
    storage = firebase_storage.bucket()
except ValueError:
    # Storage bucket not configured - this is okay for basic operation
    storage = None

# OpenAI client
openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)

# Import services (will be initialized after services are created)
# These will be imported by routes