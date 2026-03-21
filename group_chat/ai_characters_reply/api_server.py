from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
from orchestrator import ChatOrchestrator
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ai_characters_api')

# Load environment variables
load_dotenv()

app = Flask(__name__)

@app.route('/generate-responses', methods=['POST'])
def generate_responses():
    """
    API endpoint that receives messages and AI participants and returns AI responses
    Expected request format:
    {
        "messages": [...],  # Array of message objects
        "aiParticipants": [...]  # Array of AI participant objects
    }
    """
    try:
        # Get data from request
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        messages = data.get('messages')
        ai_participants = data.get('aiParticipants')
        
        if not messages or not ai_participants:
            return jsonify({"error": "Missing required fields: messages or aiParticipants"}), 400
            
        logger.info(f"Received request to generate responses for {len(messages)} messages")
        
        # Initialize orchestrator
        orchestrator = ChatOrchestrator(ai_participants)
        
        # Generate responses
        ai_responses = orchestrator.generate_responses(messages)
        
        # Return the responses
        return jsonify({
            "responses": ai_responses
        })
        
    except Exception as e:
        logger.error(f"Error generating responses: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Get port from environment variable or use 8080 as default
    port = int(os.environ.get('PORT', 8080))
    
    # Start the server
    app.run(host='0.0.0.0', port=port)