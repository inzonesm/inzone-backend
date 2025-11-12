# Environment Configuration Guide

This project uses YAML files for environment configuration. Here's how the different environment files work:

## File Structure

```
inzoneapi/
├── .env.example              # Python dotenv example (safe to commit)
├── envs.example.yaml         # YAML env example (safe to commit)
├── envs.local.yaml           # Local development template (safe to commit)
├── envs.test.yaml            # Test environment template (safe to commit)
├── envs.yaml                 # ACTUAL secrets (GITIGNORED - DO NOT COMMIT)
├── envs.dev.yaml            # Development secrets (GITIGNORED)
├── envs.staging.yaml        # Staging secrets (GITIGNORED)
└── envs.prod.yaml           # Production secrets (GITIGNORED)
```

## Environment Files Explained

### Template Files (Safe to Commit)
These files contain placeholder values and serve as documentation:
- **`envs.example.yaml`** - General template showing all required variables
- **`envs.local.yaml`** - Template for local development setup
- **`envs.test.yaml`** - Template for test environment

### Secret Files (NEVER Commit)
These files contain actual credentials and are gitignored:
- **`envs.yaml`** - Main environment file with actual secrets
- **`envs.dev.yaml`** - Development environment secrets
- **`envs.staging.yaml`** - Staging environment secrets
- **`envs.prod.yaml`** - Production environment secrets

## Setup Instructions

### For Local Development

1. Copy the template:
   ```bash
   cp envs.local.yaml envs.yaml
   ```

2. Edit `envs.yaml` and replace placeholder values with your actual credentials:
   ```yaml
   OPENAI_API_KEY: 'sk-proj-your-actual-key-here'
   ELEVENLABS_API_KEY: 'your-actual-key-here'
   # ... etc
   ```

3. Never commit `envs.yaml` - it's automatically ignored by git

### For Testing

1. Use `envs.test.yaml` as-is or create a copy:
   ```bash
   cp envs.test.yaml envs.yaml
   ```

2. Update with test-specific credentials if needed

### For Deployment

The deployment scripts use environment-specific files:
- Development: `envs.dev.yaml`
- Staging: `envs.staging.yaml`
- Production: `envs.prod.yaml`

## Security Best Practices

✅ **DO:**
- Keep template files (`.example`, `.local`, `.test`) in version control
- Store actual secrets in gitignored files (`envs.yaml`, `envs.prod.yaml`, etc.)
- Use different credentials for each environment
- Rotate keys regularly
- Use secret management services (Google Secret Manager, AWS Secrets Manager)

❌ **DON'T:**
- Commit files with actual secrets
- Share secret files via email or chat
- Use production credentials in development
- Hardcode secrets in source code

## Checking Your Setup

Verify your gitignore is working:
```bash
git status
```

If you see `envs.yaml` listed, something is wrong with your `.gitignore`.

## Required Variables

All environments need these variables:

### OpenAI
- `OPENAI_API_KEY` - OpenAI API key for AI features
- `OPENAI_MODEL` - Model to use (e.g., 'gpt-4o')

### ElevenLabs
- `ELEVENLABS_API_KEY` - Text-to-speech API key

### Meshy
- `MESH_API_KEY` - 3D generation API key

### Google Cloud / Firebase
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON

### Application
- `PACKAGE_NAME` - App package identifier

### Gorse (Recommendation Engine)
- `GORSE_API_URL` - Gorse API endpoint
- `GORSE_API_KEY` - Gorse API key
- `GORSE_LABEL_RATIO` - Recommendation label ratio (default: 0.7)

## Troubleshooting

**"File not found" error when running the app:**
- Make sure `envs.yaml` exists in the root directory
- Check that all required variables are present

**"Invalid credentials" errors:**
- Verify your API keys are correct and active
- Check that you're using the right environment file

**Git is trying to commit secrets:**
- Check your `.gitignore` is up to date
- Run `git rm --cached envs.yaml` if it was previously tracked
- Verify with `git status` before committing

## See Also

- [ENV_FILES_EXPLAINED.md](docs/ENV_FILES_EXPLAINED.md) - Detailed explanation of each variable
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - Deployment guide
- [.env.example](.env.example) - Python dotenv format alternative
