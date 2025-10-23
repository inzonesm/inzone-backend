from flask import Flask, request, jsonify
from firebase_admin.firestore import SERVER_TIMESTAMP, ArrayUnion
from dotenv import load_dotenv
from flask_cors import CORS
from openai import OpenAI
import requests
import logging
import base64
import time
import uuid
import os
from firebase_admin import credentials, initialize_app, firestore

load_dotenv()

OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")
if OPENAI_API_KEY is None:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

# Create Flask app

# Initialize Firebase Admin
cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
default_app = initialize_app(cred)

# Initialize Firestore client
db = firestore.client()
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'INZONE1234'


@app.route('/chat/aiUser', methods=['POST'])
def chat_unpopular():
    try:
        data = request.get_json()
        message = data.get('message')

        if not message:
            return jsonify({"success": False, "error": {"message": "Message is required", "code": "INVALID_MESSAGE"}}), 400

        PERSONALITY_TEXT = ""        
        ai_id = data.get('ai_id')
        if not ai_id:
            return jsonify({"success": False, "error": {"message": "AI ID is required", "code": "INVALID_AI_ID"}}), 400

        ai_user_doc = db.collection('aiUsers').document(ai_id).get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": {"message": "AI user not found", "code": "AI_USER_NOT_FOUND"}}), 404
        
        ai_user_data = ai_user_doc.to_dict()

        PERSONALITY_TEXT = ai_user_data.get('personality', '')

        if not PERSONALITY_TEXT:
            return jsonify({"success": False, "error": {"message": "AI user personality not found", "code": "AI_PERSONALITY_NOT_FOUND"}}), 404

        NAME = ai_user_data.get('name', '')
        GENDER = ai_user_data.get('gender', '')
        AGE = ai_user_data.get('age', '')
        
        system_prompt = f"""You are a chatbot designed to engage in natural and meaningful conversations. Your primary goal is to respond to messages input by the user while maintaining a consistent personality.

            Your personality is as follows:
            {PERSONALITY_TEXT}

            When responding:

            Stay true to the defined personality at all times.
            Be engaging, context-aware, and natural in conversation.
            Adapt to the tone of the user while maintaining coherence.
            If unsure, ask clarifying questions instead of making assumptions.
            Keep responses concise and relevant unless a longer explanation is necessary.
            Always ensure a conversational and enjoyable experience while staying aligned with the given personality.
            Keep the responses short and to the point unless needed to generate a long response because your responses will be viewed in a mobile phone screen.

            Your name is {NAME if NAME else "not known"}.
            Your gender is {GENDER if GENDER else "not known"}.
            Your age is {AGE if AGE else "not known"}.
        """

        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )

        response = {
            "success": True,
            "data": {
                "message": completion.choices[0].message.content
            }
        }
        return jsonify(response), 200
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        response = {
            "success": False,
            "error": {"message": str(ex), "code": "CHAT_ERROR"}
        }
        return jsonify(response), 500

@app.route('/chat/popularCharacter', methods=['POST'])
def chat_popular():
    try:
        data = request.get_json()
        message = data.get('message')

        if not message:
            return jsonify({"success": False, "error": {"message": "Message is required", "code": "INVALID_MESSAGE"}}), 400

        PERSONALITY_TEXT = ""        
        ai_id = data.get('ai_id')
        if not ai_id:
            return jsonify({"success": False, "error": {"message": "AI ID is required", "code": "INVALID_AI_ID"}}), 400

        ai_users_ref = db.collection('popularCharacters')
        query = ai_users_ref.where('name', '==', ai_id).limit(1)
        ai_user_docs = list(query.stream())
        if not ai_user_docs:
            return jsonify({"success": False, "error": {"message": "AI user not found", "code": "AI_USER_NOT_FOUND"}}), 404
        ai_user_data = ai_user_docs[0].to_dict()

        PERSONALITY_TEXT = ai_user_data.get('personality', '')

        if not PERSONALITY_TEXT:
            return jsonify({"success": False, "error": {"message": "AI user personality not found", "code": "AI_PERSONALITY_NOT_FOUND"}}), 404

        NAME = ai_user_data.get('name', '')
        GREETING = ai_user_data.get('greeting', 'Hi there!')
        
        system_prompt = f"""You are a chatbot designed to emulate the personality and conversational style of a well-known celebrity. Your primary goal is to engage in natural and meaningful conversations while maintaining an authentic representation of the celebrity's persona.

            Your personality is based on:
            {NAME}

            Personality traits:
            {PERSONALITY_TEXT}

            When responding:

            - Stay true to the defined celebrity's personality, mannerisms, and speech style.
            - Be engaging, context-aware, and natural in conversation.
            - Adapt to the user's tone while maintaining the celebrity's signature communication style.
            - If unsure, ask clarifying questions instead of making assumptions.
            - Keep responses concise and relevant unless a longer explanation is necessary.
            - Always provide an immersive and enjoyable experience that aligns with how {NAME} would naturally interact.
            - Keep the responses short and to the point unless needed to generate a long response because your responses will be viewed in a mobile phone screen.


            Your name is {NAME}, and you respond as they would in real-life interactions.
            """

        try:
            completion = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "assistant", "content": GREETING},
                    {"role": "user", "content": message}
                ]
            )
        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            return jsonify({"success": False, "error": {"message": "Failed to process AI response", "code": "OPENAI_API_ERROR"}}), 500

        response = {
            "success": True,
            "data": {
                "message": completion.choices[0].message.content
            }
        }
        return jsonify(response), 200
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        response = {
            "success": False,
            "error": {"message": str(ex), "code": "CHAT_ERROR"}
        }
        return jsonify(response), 500






if __name__ == '__main__':
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
