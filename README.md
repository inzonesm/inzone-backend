# InZone Social Media Platform

A multi-component social media platform with AI-powered features, agent management, and content generation capabilities.

## Project Structure

```
inzonesm/
├── inzoneapi/          # Main Flask API backend
├── agent_dashboard/    # Streamlit admin dashboard
├── agents_backend/     # AI agent management service
└── gopath/            # Go dependencies (auto-generated)
```

## Prerequisites

### Required Software
- **Python 3.12+** - Primary runtime
- **Node.js 16+** - For some dependencies
- **Docker** (optional) - For containerized deployment
- **Git** - For version control

### Required API Keys & Credentials
1. **Google Cloud / Firebase**
   - Firebase Admin SDK credentials (`key.json`)
   - Enable Firestore Database
   - Enable Cloud Run (for deployment)

2. **OpenAI API**
   - API key from [platform.openai.com](https://platform.openai.com)

3. **ElevenLabs API** (optional)
   - API key from [elevenlabs.io](https://elevenlabs.io)

4. **Meshy API** (optional)
   - API key from Meshy platform

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd inzonesm
```

### 2. Set Up InZone API (Main Backend)

```bash
cd inzoneapi

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env  # If example exists, otherwise create manually
```

Edit `.env` file with credentials from Jayme:
```env
OPENAI_API_KEY=your_openai_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
MESH_API_KEY=your_meshy_api_key_here
GOOGLE_APPLICATION_CREDENTIALS=./key.json
OPENAI_MODEL=gpt-4
PACKAGE_NAME=inzone
```

Add Firebase credentials (ask Jayme):
```bash
# Place your Firebase Admin SDK key.json file in the inzoneapi directory
# Download from: Firebase Console > Project Settings > Service Accounts
```

### 3. Set Up Agent Dashboard

```bash
cd ../agent_dashboard

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Add Firebase credentials
# Copy key.json to this directory
cp ../inzoneapi/key.json .

# Configure envs.yaml or config.yaml as needed
```

### 4. Set Up Agents Backend

```bash
cd ../agents_backend

# Install dependencies (if requirements.txt exists)
# Add API keys
# Copy key.json and openai_key.txt to this directory
```

## Running the Application

### Run InZone API (Main Backend)

```bash
cd inzoneapi
source venv/bin/activate

# Development mode
python app.py

# Production mode (with Gunicorn)
gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 0 app:app
```

The API will be available at `http://localhost:8080`

### Run Agent Dashboard

```bash
cd agent_dashboard
source venv/bin/activate

streamlit run login.py --server.port 8080 --server.address 0.0.0.0
```

The dashboard will be available at `http://localhost:8080`

## Docker Deployment

### Build and Run with Docker

**InZone API:**
```bash
cd inzoneapi

# Build Docker image
docker build -t inzoneapi .

# Run container
docker run -p 8080:8080 \
  -e OPENAI_API_KEY=your_key \
  -e ELEVENLABS_API_KEY=your_key \
  -e MESH_API_KEY=your_key \
  -v $(pwd)/key.json:/app/key.json \
  inzoneapi
```

**Agent Dashboard:**
```bash
cd agent_dashboard

# Build Docker image
docker build -t agent-dashboard .

# Run container
docker run -p 8080:8080 \
  -v $(pwd)/key.json:/app/key.json \
  agent-dashboard
```

## Google Cloud Run Deployment

### Deploy InZone API

```bash
cd inzoneapi

# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/YOUR-PROJECT-ID/inzoneapi

# Deploy to Cloud Run
gcloud run deploy inzoneapi \
  --image gcr.io/YOUR-PROJECT-ID/inzoneapi \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=your_key,ELEVENLABS_API_KEY=your_key,MESH_API_KEY=your_key

# Or use the deploy script
chmod +x deploy_cloud_run.sh
./deploy_cloud_run.sh
```

### Deploy Agent Dashboard

```bash
cd agent_dashboard

# Build and deploy
gcloud builds submit --tag gcr.io/YOUR-PROJECT-ID/agent-dashboard
gcloud run deploy agent-dashboard \
  --image gcr.io/YOUR-PROJECT-ID/agent-dashboard \
  --platform managed \
  --region us-central1

# Or use the deploy script
chmod +x deploy.sh
./deploy.sh
```

## Configuration Files

### Environment Variables (.env)
Create `.env` files in each component directory:
- `inzoneapi/.env` - Main API configuration
- Add all required API keys and credentials

### Firebase Credentials (key.json)
- Download from Firebase Console
- Place in each component directory that needs it
- **NEVER commit to Git** (already in .gitignore)

### YAML Configuration
- `config.yaml` - Application configuration
- `envs.yaml` - Environment-specific settings

## Development Workflow

### 1. Make Changes
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes to code
# Test locally
```

### 2. Test Locally
```bash
# Test each component individually
cd inzoneapi && python app.py
cd agent_dashboard && streamlit run login.py
```

### 3. Commit Changes
```bash
git add .
git commit -m "Description of changes"
git push origin feature/your-feature-name
```

## Important Security Notes

### Files to NEVER Commit:
- `.env` files
- `key.json` files
- `*_key.txt` files
- Any files containing API keys or secrets

These are already in `.gitignore` - ensure they stay there!

### Rotating Secrets:
If you accidentally commit secrets:
1. Revoke the compromised keys immediately
2. Generate new keys
3. Update all deployment configurations
4. Use `git filter-branch` or BFG Repo-Cleaner to remove from history

## Troubleshooting

### Python Module Not Found
```bash
# Ensure virtual environment is activated
source venv/bin/activate
pip install -r requirements.txt
```

### Port Already in Use
```bash
# Find process using port 8080
lsof -i :8080
# Kill the process
kill -9 <PID>
```

### Firebase Authentication Error
- Verify `key.json` is in the correct directory
- Check file permissions: `chmod 600 key.json`
- Ensure GOOGLE_APPLICATION_CREDENTIALS points to correct path

### OpenCV Installation Issues
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y libglib2.0-0 libsm6 libxext6 libxrender1

# macOS
brew install ffmpeg
```

## Component Details

### InZone API (`inzoneapi/`)
- **Type:** Flask REST API
- **Port:** 8080
- **Features:**
  - User authentication
  - AI engagement scheduling
  - Media analysis
  - Notification service
  - AI nudge system

### Agent Dashboard (`agent_dashboard/`)
- **Type:** Streamlit web app
- **Port:** 8080
- **Features:**
  - Agent management
  - Video caption generation
  - YouTube shorts fetching
  - Content posting

### Agents Backend (`agents_backend/`)
- **Type:** Python backend
- **Features:**
  - AI agent creation
  - Image generation
  - Live agent management

## Support

For issues or questions:
1. Check existing issues in the repository
2. Review logs: `docker logs <container-id>`
3. Enable debug mode in Flask: `app.run(debug=True)`

## License

[Add your license information here]
