# InZone Social Media Platform

A multi-component social media platform with AI-powered features, agent management, and content generation capabilities.

## Quick Start for InZone API

**Want to run, test, or deploy the InZone API?** Use the interactive deployment script:

```bash
cd inzoneapi/scripts
python deploy.py
```

This single command handles:
- 🚀 Running locally
- 🧪 Deploying to test environment
- 📦 Deploying to production
- 🔍 Viewing environment configuration
- ✅ Validating before deployment

**Always use `deploy.py` for InZone API** - it prevents configuration errors and shows you exactly what's being deployed!

See full setup instructions below ↓

---

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

All API keys and credentials should be configured in your local environment files. See the [Environment Files Guide](inzoneapi/ENV_FILES_EXPLAINED.md) for detailed setup instructions.

**Quick Setup:**
- Copy `.env.example` to `.env.local` for local development
- Create `envs.local.yaml` for local cloud testing
- Follow the environment files guide for proper configuration

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd inzonesm
```

### 2. Set Up InZone API (Main Backend)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

cd inzoneapi

# Set up environment files - env and key.json (see ENV_FILES_EXPLAINED.md for details)
cp .env.example .env.local
# Edit .env.local with API keys and credentials (from Jayme)
```

Configure your local environment by editing `.env.local` with your credentials. See [inzoneapi/ENV_FILES_EXPLAINED.md](inzoneapi/ENV_FILES_EXPLAINED.md) for detailed instructions on setting up all required API keys and Firebase credentials.

### 3. Set Up Agent Dashboard

```bash
cd ../agent_dashboard

# Add Firebase credentials
# Copy key.json to this directory
cp ../inzoneapi/key.json .

# Configure envs.yaml or config.yaml as needed
```

### 4. Set Up Agents Backend

```bash
cd ../agents_backend

# Add API keys
# Copy key.json and openai_key.txt to this directory
```

## Running the Application

### Run InZone API (Main Backend)

#### ⭐ Preferred Method: Interactive Script

```bash
cd inzoneapi

# Use the interactive deployment manager
python deploy.py

# Then choose option 1: "Run locally"
```

This will:
- Show all environment variables from `.env`
- Validate your configuration
- Let you choose the port
- Run the Flask app

#### Alternative: Direct Command

```bash
cd inzoneapi

# Development mode
python app.py

# Production mode (with Gunicorn)
gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 0 app:app
```

The API will be available at `http://localhost:8080` (or your chosen port)

### Run Agent Dashboard

```bash
cd agent_dashboard

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

### Deploy InZone API ⭐ PREFERRED METHOD

**Always use the interactive deployment script** - it shows you which environment files are being used and validates configuration before deployment:

```bash
cd inzoneapi

# Interactive deployment manager (RECOMMENDED)
python deploy.py
```

The script will:
- ✅ Show you all environment variables before deployment
- ✅ Let you choose: Local Development, Test Environment, or Production
- ✅ Display which environment file is active (`.env`, `envs.test.yaml`, `envs.yaml`)
- ✅ Validate configuration and prevent errors
- ✅ Mask sensitive API keys for security
- ✅ Guide you through safe deployments

**Options available in deploy.py:**
1. **Run Locally** - Uses `.env` file for local development
2. **Deploy to Test** - Uses `envs.test.yaml` for test environment (`inzoneapi-test` service)
3. **Deploy to Production** - Uses `envs.yaml` for production (`inzoneapi` service)
4. **Build Docker Only** - Build without deploying
5. **View Environment Status** - Check all environment files

See [inzoneapi/DEPLOY_SCRIPT_GUIDE.md](inzoneapi/DEPLOY_SCRIPT_GUIDE.md) for detailed usage examples.

---

#### Manual Deployment (Backup Method)

If you need to deploy manually without the interactive script:

**Test Environment:**
```bash
cd inzoneapi

# Using the shell script
chmod +x deploy_cloud_run_test.sh
./deploy_cloud_run_test.sh

# Or manually
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi:test
gcloud run deploy inzoneapi-test \
  --image gcr.io/inzone-f93e4/inzoneapi:test \
  --region us-central1 \
  --env-vars-file envs.test.yaml
```

**Production Environment:**
```bash
cd inzoneapi

# Using the shell script
chmod +x deploy_cloud_run.sh
./deploy_cloud_run.sh

# Or manually
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi
gcloud run deploy inzoneapi \
  --image gcr.io/inzone-f93e4/inzoneapi \
  --region us-central1 \
  --env-vars-file envs.yaml
```

**Note:** Manual deployment requires you to manage environment files yourself and won't show validation warnings.

---

### Deploy Agent Dashboard

```bash
cd agent_dashboard

# Build and deploy
gcloud builds submit --tag gcr.io/inzone-f93e4/agent-dashboard
gcloud run deploy agent-dashboard \
  --image gcr.io/inzone-f93e4/agent-dashboard \
  --platform managed \
  --region us-east1 \
  --env-vars-file envs.yaml

# Or use the deploy script
chmod +x deploy.sh
./deploy.sh
```

## Configuration Files

### Environment Variables

The InZone API uses different environment files for different purposes:

| File | Purpose | Used When |
|------|---------|-----------|
| `.env` | Local development | Running `python app.py` locally |
| `envs.yaml` | Production cloud | Deploying to production Cloud Run |
| `envs.test.yaml` | Test cloud | Deploying to test Cloud Run |
| `.env.example` | Template/documentation | Setting up the project |

**See [inzoneapi/ENV_FILES_EXPLAINED.md](inzoneapi/ENV_FILES_EXPLAINED.md) for detailed explanations and examples.**

#### Quick Setup:

1. **Local Development:**
   ```bash
   cd inzoneapi
   cp .env.example .env
   # Edit .env with your actual API keys
   ```

2. **Test Deployment:**
   ```bash
   # envs.test.yaml already exists
   # Edit if you need test-specific configuration
   ```

3. **Production Deployment:**
   ```bash
   # envs.yaml already exists
   # Edit with production API keys (ask Jayme)
   ```

### Firebase Credentials (key.json)
- Download from Firebase Console
- Place in each component directory that needs it
- **NEVER commit to Git** (already in .gitignore)

### YAML Configuration
- `config.yaml` - Application configuration (Agent Dashboard)
- `envs.yaml` - Environment-specific settings for Cloud Run

## Development Workflow

### Recommended Workflow for InZone API

1. **Develop locally** with `deploy.py` (option 1)
2. **Test in cloud** with `deploy.py` (option 2 - test environment)
3. **Deploy to production** with `deploy.py` (option 3 - after testing)

### Detailed Steps

#### 1. Make Changes
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes to code in your editor
```

#### 2. Test Locally
```bash
# Use the interactive script (RECOMMENDED)
cd inzoneapi
python deploy.py
# Choose option 1: Run locally

# Alternative: Direct command
cd inzoneapi && python app.py
```

#### 3. Test in Cloud (Before Production)
```bash
# Deploy to test environment first
cd inzoneapi
python deploy.py
# Choose option 2: Deploy to TEST environment

# Test your changes at the test URL
# Verify everything works correctly
```

#### 4. Deploy to Production
```bash
# After testing succeeds, deploy to production
cd inzoneapi
python deploy.py
# Choose option 3: Deploy to PRODUCTION environment
```

#### 5. Commit Changes
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
