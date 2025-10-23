# __init__.py
from flask import Flask
from flask_cors import CORS
from firebase_admin import credentials, initialize_app, firestore
import firebase_admin
import os
from dotenv import load_dotenv

def create_app():
    load_dotenv()

    OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")
    if OPENAI_API_KEY is None:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

    client = OpenAI(api_key=OPENAI_API_KEY)

    cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    default_app = initialize_app(cred)    
    db = firestore.client()

    app = Flask(__name__)
    
    CORS(app)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "INZONE1234")

    from backend import backend_bp
    from app import app_bp

    app.register_blueprint(app_bp, url_prefix="/inz")
    app.register_blueprint(backend_bp, url_prefix="/inz")

    return app