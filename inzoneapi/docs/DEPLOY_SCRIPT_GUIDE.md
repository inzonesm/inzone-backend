# Deploy Script Guide - deploy.py

The `deploy.py` script is an interactive deployment manager that automatically shows you which environment files are being used and their values before any action.

## Features

### 1. Always Shows Environment File Contents

**Before every action**, the script displays:
- Which environment file is being used
- All variables in that file
- Values (with sensitive data partially masked for security)

Example output:
```
============================================================
Environment File: envs.test.yaml (Test Environment)
============================================================

Variable                           Value
------------------------------------------------------------
OPENAI_API_KEY                     sk-pro******************************
GOOGLE_APPLICATION_CREDENTIALS     /app/key.json

Note: Sensitive values (API keys, secrets) are partially masked
============================================================
```

### 2. Security Features

- **API Keys are masked**: Shows only first 6 characters (e.g., `sk-pro******`)
- **Secrets are protected**: Any variable with "KEY", "SECRET", "PASSWORD", "TOKEN", "CREDENTIALS" in the name is masked
- **Non-sensitive values shown fully**: Variables like paths, ports, etc. are shown completely

### 3. When Environment Files Are Displayed

| Action | Environment File Shown |
|--------|------------------------|
| Run Locally (Option 1) | `.env` |
| Deploy to Test (Option 2) | `envs.test.yaml` |
| Deploy to Production (Option 3) | `envs.yaml` |
| View Status (Option 5) | All files (on request) |

## Usage Examples

### Example 1: Running Locally

```bash
$ python deploy.py

# Choose option 1
What would you like to do?
Enter your choice (1-6): 1

============================================================
Environment File: .env (Local Development)
============================================================

Variable                           Value
------------------------------------------------------------
OPENAI_API_KEY                     sk-pro******************************
MESH_API_KEY                       msy_KQ******************************
GOOGLE_APPLICATION_CREDENTIALS     key.json
# Commented line shown in yellow
PACKAGE_NAME                       com.aadeshkheria.inzone
ELEVENLABS_API_KEY                 sk_1df******************************
OPENAI_MODEL                       gpt-4o

Note: Sensitive values (API keys, secrets) are partially masked
============================================================

Enter port to run on (default: 5000): 5000
```

You can now clearly see:
- You're using `.env` for local development
- Which API keys are configured
- What model you're using (gpt-4o)
- All your environment variables at a glance

### Example 2: Deploying to Test

```bash
$ python deploy.py

# Choose option 2
What would you like to do?
Enter your choice (1-6): 2

✓ envs.test.yaml validated

============================================================
Environment File: envs.test.yaml (Test Environment)
============================================================

Variable                           Value
------------------------------------------------------------
OPENAI_API_KEY                     sk-pro******************************
GOOGLE_APPLICATION_CREDENTIALS     /app/key.json
# Optional: Add test-specific variables below
# For example:
# DEBUG: 'true'
# LOG_LEVEL: 'debug'
# TEST_MODE: 'true'

Note: Sensitive values (API keys, secrets) are partially masked
============================================================

✓ gcloud CLI found

⚠ You are about to deploy to TEST environment:
ℹ   - Service: inzoneapi-test
ℹ   - Image: gcr.io/inzone-f93e4/inzoneapi:test
ℹ   - Region: us-central1
ℹ   - Environment: envs.test.yaml

Proceed with deployment? (yes/no):
```

Before deployment, you can verify:
- Correct environment file is selected (`envs.test.yaml`)
- All required variables are present
- API keys are configured
- No mistakes in the configuration

### Example 3: Deploying to Production

```bash
$ python deploy.py

# Choose option 3
What would you like to do?
Enter your choice (1-6): 3

✓ envs.yaml validated

============================================================
Environment File: envs.yaml (Production Environment)
============================================================

Variable                           Value
------------------------------------------------------------
OPENAI_API_KEY                     sk-pro******************************
GOOGLE_APPLICATION_CREDENTIALS     /app/key.json

Note: Sensitive values (API keys, secrets) are partially masked
============================================================

✓ gcloud CLI found

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
WARNING: You are about to deploy to PRODUCTION!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  - Service: inzoneapi
  - Image: gcr.io/inzone-f93e4/inzoneapi:latest
  - Region: us-central1
  - Environment: envs.yaml

This will affect live users!

Type 'deploy-production' to confirm:
```

Critical production deployment shows:
- Production environment file (`envs.yaml`)
- All production configuration values
- Strong warning before deployment
- Requires typing `deploy-production` to confirm

### Example 4: View Environment Status

```bash
$ python deploy.py

# Choose option 5
What would you like to do?
Enter your choice (1-6): 5

============================================================
              Environment Files Status
============================================================

File Status Summary:

✓ EXISTS - .env                  (Local development)
✓ EXISTS - .env.example          (Template file)
✓ EXISTS - envs.yaml             (Production cloud)
✓ EXISTS - envs.test.yaml        (Test cloud)
✗ MISSING - key.json             (Firebase credentials)

Would you like to see the contents of the environment files?
1. View .env (Local)
2. View envs.test.yaml (Test)
3. View envs.yaml (Production)
4. View all
5. Back to main menu

Enter your choice (1-5): 4
```

Then it shows all three environment files with their contents!

## What Gets Masked

The script automatically masks these variable types:
- `*API_KEY*` - All API keys
- `*SECRET*` - All secrets
- `*PASSWORD*` - All passwords
- `*TOKEN*` - All tokens
- `*CREDENTIALS*` - Credential files
- `*PRIVATE*` - Private keys
- `*AUTH*` - Auth tokens
- `*KEY*` - Any key

## What's Shown Fully

Non-sensitive variables are shown completely:
- `PORT` - Port numbers
- `PACKAGE_NAME` - App package name
- `OPENAI_MODEL` - Model names
- `GOOGLE_APPLICATION_CREDENTIALS` - Just the path (not the actual credentials)
- Comments in the file

## Benefits

### 1. Prevents Mistakes
- See exactly which environment file is being used
- Verify all variables are set correctly
- Catch configuration errors before deployment

### 2. Transparency
- No guessing what environment is active
- Clear visibility into what's being deployed
- Easy to spot differences between environments

### 3. Security
- Sensitive values are masked (first 6 chars shown)
- Safe to share terminal output
- Can review without exposing secrets

### 4. Debugging
- Quickly see if environment variables are set
- Verify values match expectations
- Easy to spot typos or missing variables

## Quick Reference

| What You Want | Environment File Shown |
|---------------|------------------------|
| Test locally | `.env` |
| Deploy to test cloud | `envs.test.yaml` |
| Deploy to production cloud | `envs.yaml` |
| Compare all environments | Use option 5 → View all |

## Color Coding

- 🟢 **Green** - Success messages, non-sensitive variables
- 🔵 **Blue** - Environment file headers, info messages
- 🟡 **Yellow** - Warnings, comments in files
- 🔴 **Red** - Errors, missing files
- 🔵 **Cyan** - Sensitive variables (masked)

## Tips

1. **Always review the environment display** before confirming deployments
2. **Check the file name** in the header to ensure correct environment
3. **Verify API keys** show the expected prefix (first 6 characters)
4. **Use option 5** to compare all environment files side-by-side
5. **Look for warnings** about missing variables before deploying

## Example: Catching a Configuration Error

```bash
# You run: python deploy.py
# Choose option 2 (Deploy to Test)

============================================================
Environment File: envs.test.yaml (Test Environment)
============================================================

Variable                           Value
------------------------------------------------------------
OPENAI_API_KEY                     your_o******  ← WRONG! Still has placeholder!
GOOGLE_APPLICATION_CREDENTIALS     /app/key.json

⚠ envs.test.yaml is missing variables: MESH_API_KEY  ← MISSING!
```

The script will:
1. Show you the placeholder value is still there
2. Warn about missing variables
3. Prevent deployment until fixed
4. Save you from a failed deployment!

---

This makes `deploy.py` a **safe, transparent, and user-friendly** way to manage your deployments!
