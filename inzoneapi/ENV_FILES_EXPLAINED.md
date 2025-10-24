# Environment Files Explained

Your InZone API project uses different environment files for different purposes. Here's what each one does:

## File Overview

| File | Purpose | Used When | Format | Git Tracked? |
|------|---------|-----------|--------|--------------|
| `.env` | Local development secrets | Running locally | `KEY=value` | No (gitignored) |
| `.env.local` | Local overrides (optional) | Running locally | `KEY=value` | No (gitignored) |
| `.env.example` | Template/documentation | Setting up project | `KEY=placeholder` | Yes |
| `envs.yaml` | Production cloud secrets | Deploying to GCP | `KEY: 'value'` | No (gitignored) |
| `envs.test.yaml` | Test cloud secrets | Deploying to GCP test | `KEY: 'value'` | No (gitignored) |

---

## 1. `.env` File

**Purpose**: Local development environment variables

**Location**: `/inzoneapi/.env`

**Format**: Standard dotenv format
```bash
OPENAI_API_KEY="sk-proj-abc123..."
MESH_API_KEY="msy_xyz789..."
GOOGLE_APPLICATION_CREDENTIALS="key.json"
PACKAGE_NAME="com.aadeshkheria.inzone"
ELEVENLABS_API_KEY="sk_123..."
OPENAI_MODEL="gpt-4o"
```

**How it's loaded**:
```python
from dotenv import load_dotenv
load_dotenv()  # Automatically loads .env file

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
```

**When it's used**:
- Running the Flask app locally on your machine
- Testing and development on localhost
- Your code calls `load_dotenv()` at the top of [app.py:38](app.py#L38)

**Git status**: Ignored (via `.gitignore`)

---

## 2. `.env.local` File

**Purpose**: Local overrides (optional, not currently used in your project)

**Location**: Would be `/inzoneapi/.env.local` if created

**How it works**:
- `python-dotenv` loads `.env` first, then `.env.local`
- Variables in `.env.local` override those in `.env`
- Useful when multiple developers need different local settings

**Example use case**:
```bash
# .env (shared settings)
OPENAI_MODEL="gpt-4o"

# .env.local (your personal override)
OPENAI_MODEL="gpt-3.5-turbo"  # You want to use cheaper model locally
```

**When to create it**:
- Only if you need personal overrides different from `.env`
- Not required for your current setup

**Git status**: Would be ignored (via `.gitignore`)

---

## 3. `.env.example` File

**Purpose**: Template showing what environment variables are needed

**Location**: `/inzoneapi/.env.example`

**Format**: Same as `.env` but with placeholder values
```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4

# ElevenLabs Text-to-Speech
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Meshy API for 3D Generation
MESH_API_KEY=your_meshy_api_key_here

# Google Cloud / Firebase
GOOGLE_APPLICATION_CREDENTIALS=./key.json
```

**When it's used**:
- Documentation for new developers
- When setting up the project for the first time
- To create your own `.env` file: `cp .env.example .env`

**Git status**: Tracked in Git (safe to commit, no secrets)

---

## 4. `envs.yaml` File

**Purpose**: Production environment variables for Google Cloud Run

**Location**: `/inzoneapi/envs.yaml`

**Format**: YAML format (required by Google Cloud)
```yaml
OPENAI_API_KEY: 'sk-proj-abc123...'
GOOGLE_APPLICATION_CREDENTIALS: '/app/key.json'
```

**How it's loaded**:
```bash
gcloud run deploy inzoneapi \
  --image gcr.io/inzone-f93e4/inzoneapi \
  --region us-central1 \
  --env-vars-file envs.yaml  # <-- Loaded here
```

**When it's used**:
- Deploying to **production** Google Cloud Run
- Via [deploy_cloud_run.sh](deploy_cloud_run.sh)
- Variables are injected into the container as environment variables
- Your Flask app reads them using `os.environ.get()`

**Important notes**:
- NOT loaded by `python-dotenv` (it's not a `.env` file)
- Only used during Cloud Run deployment
- Variables are set at the container level by Google Cloud

**Git status**: Should be ignored (contains production secrets)

---

## 5. `envs.test.yaml` File

**Purpose**: Test environment variables for Google Cloud Run test container

**Location**: `/inzoneapi/envs.test.yaml`

**Format**: YAML format (same as `envs.yaml`)
```yaml
# Test Environment Variables for InZone API
OPENAI_API_KEY: 'sk-proj-abc123...'
GOOGLE_APPLICATION_CREDENTIALS: '/app/key.json'

# Optional test-specific variables
# DEBUG: 'true'
# LOG_LEVEL: 'debug'
# TEST_MODE: 'true'
```

**How it's loaded**:
```bash
gcloud run deploy inzoneapi-test \
  --image gcr.io/inzone-f93e4/inzoneapi:test \
  --region us-central1 \
  --env-vars-file envs.test.yaml  # <-- Loaded here
```

**When it's used**:
- Deploying to **test** Google Cloud Run environment
- Via [deploy_cloud_run_test.sh](deploy_cloud_run_test.sh)
- Testing changes before production deployment

**Best practices**:
- Can use same API keys as production (current setup)
- Or use separate test API keys for isolation
- Add test-specific flags like `DEBUG: 'true'`

**Git status**: Should be ignored (contains secrets)

---

## Summary: When Each File is Used

### Local Development Flow
```
1. You run: python app.py
2. Code executes: load_dotenv()
3. Loads: .env (and .env.local if it exists)
4. App runs on localhost with local environment variables
```

### Test Deployment Flow
```
1. You run: ./deploy_cloud_run_test.sh
2. Script builds Docker image
3. Script runs: gcloud run deploy inzoneapi-test --env-vars-file envs.test.yaml
4. Google Cloud injects envs.test.yaml variables into container
5. App runs on Cloud Run with test environment variables
```

### Production Deployment Flow
```
1. You run: ./deploy_cloud_run.sh
2. Script builds Docker image
3. Script runs: gcloud run deploy inzoneapi --env-vars-file envs.yaml
4. Google Cloud injects envs.yaml variables into container
5. App runs on Cloud Run with production environment variables
```

---

## Key Differences

### `.env` vs `envs.yaml`

| Feature | `.env` | `envs.yaml` |
|---------|--------|-------------|
| Format | `KEY=value` | `KEY: 'value'` |
| Loaded by | Python `load_dotenv()` | Google Cloud CLI |
| Used for | Local development | Cloud deployment |
| When | Running on your machine | Running on Cloud Run |
| Quotes | Optional | Required for YAML |

### `envs.yaml` vs `envs.test.yaml`

| Feature | `envs.yaml` | `envs.test.yaml` |
|---------|-------------|------------------|
| Environment | Production | Test |
| Service name | `inzoneapi` | `inzoneapi-test` |
| Container tag | `:latest` | `:test` |
| Deploy script | `deploy_cloud_run.sh` | `deploy_cloud_run_test.sh` |
| Purpose | Live users | Pre-production testing |

---

## Current .gitignore Settings

Your project ignores these environment files:
```gitignore
.env
.env.*
*.env
!.env.example  # Exception: .env.example IS tracked
```

This means:
- `.env` ❌ Not tracked (good - has secrets)
- `.env.local` ❌ Not tracked (good - personal overrides)
- `.env.example` ✅ Tracked (good - no secrets, just template)
- `envs.yaml` ❌ Should not be tracked (has production secrets)
- `envs.test.yaml` ❌ Should not be tracked (has test secrets)

---

## Best Practices

1. **Never commit secrets**
   - Keep `.env`, `envs.yaml`, and `envs.test.yaml` out of Git
   - Only commit `.env.example` as a template

2. **Keep environments separate**
   - `.env` for local development
   - `envs.test.yaml` for cloud testing
   - `envs.yaml` for production

3. **Document required variables**
   - Update `.env.example` when you add new environment variables
   - This helps other developers know what's needed

4. **Use different API keys** (recommended)
   - Local development: Use development API keys
   - Test environment: Use test API keys (or same as production if safe)
   - Production: Use production API keys

5. **Test flow**
   - Develop locally with `.env`
   - Deploy to test with `envs.test.yaml`
   - Deploy to production with `envs.yaml`

---

## Quick Reference

**Running locally?** → Uses `.env`
```bash
python app.py
# Loads .env automatically via load_dotenv()
```

**Deploying to test?** → Uses `envs.test.yaml`
```bash
./deploy_cloud_run_test.sh
# Passes envs.test.yaml to Google Cloud
```

**Deploying to production?** → Uses `envs.yaml`
```bash
./deploy_cloud_run.sh
# Passes envs.yaml to Google Cloud
```
