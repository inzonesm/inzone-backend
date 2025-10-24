# Quick Start Guide

Get the InZone platform running in 5 minutes.

## Prerequisites Checklist

- [ ] Python 3.12+ installed
- [ ] Node.js 16+ installed
- [ ] Firebase project created
- [ ] OpenAI API key obtained

## Quick Setup

### 1. Clone & Install

```bash
git clone <repository-url>
cd inzonesm/inzoneapi

# Setup Python environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Install Node dependencies
npm install
```

### 2. Configure Credentials

**Create `.env` file:**
```bash
cp .env.example .env
```

**Edit `.env` and add your keys:**
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxx
MESH_API_KEY=xxxxxxxxxxxxx
GOOGLE_APPLICATION_CREDENTIALS=./key.json
```

**Add Firebase credentials:**
1. Go to [Firebase Console](https://console.firebase.google.com)
2. Select your project → Settings → Service Accounts
3. Click "Generate New Private Key"
4. Save as `key.json` in the `inzoneapi/` directory

### 3. Run the Application

```bash
# Make sure you're in inzoneapi/ with venv activated
python app.py
```

Visit `http://localhost:8080` 🎉

## Run Other Components

### Agent Dashboard
```bash
cd agent_dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../inzoneapi/key.json .
streamlit run login.py
```

## Common Issues

**ModuleNotFoundError?**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Port 8080 in use?**
```bash
lsof -i :8080
kill -9 <PID>
```

**Firebase auth error?**
- Check `key.json` exists in correct directory
- Verify path in `.env` is correct

## Next Steps

- Read the full [README.md](README.md) for deployment
- Check security notes about API keys
- Review the project structure

## Production Deployment

```bash
# Quick deploy to Google Cloud Run
gcloud builds submit --tag gcr.io/YOUR-PROJECT-ID/inzoneapi
gcloud run deploy --image gcr.io/YOUR-PROJECT-ID/inzoneapi
```

See [README.md](README.md) for detailed deployment instructions.
