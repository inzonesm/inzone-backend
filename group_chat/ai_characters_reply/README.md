# AI Characters Reply - Firebase Cloud Function

This project implements a Firebase Cloud Function in Python that monitors your Firestore `groupChats` collection and generates AI character responses to new user messages using AutoGen.

## How It Works

1. When a user sends a message to a group chat in Firestore:
   - The Firebase Cloud Function is automatically triggered
   - It extracts new messages and AI participants from the updated document
   - It passes these to the ChatOrchestrator

2. The ChatOrchestrator:
   - Evaluates which AI character(s) should respond based on the conversation
   - Generates contextually appropriate responses for selected characters
   - Returns the responses to be added to Firestore

3. The Cloud Function:
   - Adds the AI responses to the group chat document
   - Updates the `lastProcessedMessageId` to prevent duplicate processing

## Setup Instructions

### Prerequisites

- Firebase project with Firestore enabled
- Python 3.11 or later
- Firebase CLI installed (`npm install -g firebase-tools`)
- OpenAI API key

### Local Development

1. Create a `.env` file based on `.env.example`:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. To test locally with Firebase Emulators:
   ```
   firebase emulators:start
   ```

### Deployment

Deploy the Cloud Function to Firebase:

```bash
# Login to Firebase
firebase login

# Select your project
firebase use your-project-id

# Deploy the function
firebase deploy --only functions
```
$envFile = '.env'; $openaiKey = ((Get-Content $envFile | Where-Object { $_ -match '^OPENAI_API_KEY=' } | Select-Object -First 1) -replace '^OPENAI_API_KEY=', '').Trim('"'); $openaiModel = ((Get-Content $envFile | Where-Object { $_ -match '^OPENAI_MODEL=' } | Select-Object -First 1) -replace '^OPENAI_MODEL=', '').Trim('"'); gcloud functions deploy add_ai_message_on_update --gen2 --project inzone-f93e4 --region us-central1 --runtime python312 --source . --entry-point add_ai_message_on_update --trigger-location nam5 --trigger-event-filters "type=google.cloud.firestore.document.v1.updated" --trigger-event-filters "database=(default)" --trigger-event-filters "namespace=(default)" --trigger-event-filters-path-pattern "document=groupChats/{groupChatId}" --set-env-vars "OPENAI_API_KEY=$openaiKey,OPENAI_MODEL=$openaiModel"

## Project Structure

- `main.py` - The main Cloud Function that triggers on Firestore document updates
- `orchestrator.py` - Manages AI character responses using AutoGen
- `utils.py` - Helper functions and utilities
- `requirements.txt` - Python dependencies
- `firebase.json` - Firebase configuration

## Notes

- The Cloud Function is more efficient than a continuous listener as it only runs when document changes occur
- Functions have built-in retry mechanisms and error handling
- No need for a separate server to host the listener

## Monitoring

You can monitor your Cloud Function's execution in the Firebase Console under Functions > Logs.