# InZone API Deployment Guide

This guide covers how to deploy the InZone API to Google Cloud Run for both production and test environments.

## Quick Start (Interactive Script) ⭐ RECOMMENDED

The easiest way to deploy is using the interactive deployment manager:

```bash
python deploy.py
```

or

```bash
./deploy.py
```

### Key Features

**✨ Always Shows Environment Variables**: Before any action (running locally, deploying to test/production), the script displays:
- Which environment file is being used (`.env`, `envs.test.yaml`, or `envs.yaml`)
- All variables and their values
- Sensitive values (API keys) are partially masked for security

**The script guides you through:**
- Running locally with the correct `.env` file
- Deploying to test environment with `envs.test.yaml`
- Deploying to production with `envs.yaml`
- Building Docker images
- Viewing all environment files and their contents

**Benefits:**
- ✅ No more guessing which environment file is being used
- ✅ See all configuration before deployment
- ✅ Catch configuration errors before they happen
- ✅ Transparent and safe

See [DEPLOY_SCRIPT_GUIDE.md](DEPLOY_SCRIPT_GUIDE.md) for detailed examples and screenshots.

This is the **recommended method** for managing deployments!

---

## Prerequisites

1. Google Cloud SDK (`gcloud`) installed and configured
2. Authenticated with the correct GCP project (`inzone-f93e4`)
3. Appropriate permissions to deploy to Cloud Run and push to Container Registry

## Deployment Environments

The InZone API supports two deployment environments:

### 1. Production Environment

- **Service Name**: `inzoneapi`
- **Container Registry**: `gcr.io/inzone-f93e4/inzoneapi:latest`
- **Cloud Run Service**: `inzoneapi`
- **Region**: `us-central1`
- **Environment Variables**: `envs.yaml`

### 2. Test Environment

- **Service Name**: `inzoneapi-test`
- **Container Registry**: `gcr.io/inzone-f93e4/inzoneapi:test`
- **Cloud Run Service**: `inzoneapi-test`
- **Region**: `us-central1`
- **Environment Variables**: `envs.test.yaml`

## How to Deploy

### Deploy to TEST Container

Use this when you want to test changes before pushing to production:

```bash
./deploy_cloud_run_test.sh
```

This script will:
1. Build your Docker image from the current code
2. Tag it as `test` and push to `gcr.io/inzone-f93e4/inzoneapi:test`
3. Deploy to a separate Cloud Run service named `inzoneapi-test`
4. Use environment variables from `envs.test.yaml`

**Benefits of using the test container:**
- Test changes in a cloud environment without affecting production
- Validate container builds and deployment process
- Test with production-like resources and scaling
- Get a separate URL for testing (e.g., `https://inzoneapi-test-xyz.run.app`)

### Deploy to PRODUCTION Container

Use this only when you're ready to update the live production API:

```bash
./deploy_cloud_run.sh
```

This script will:
1. Build your Docker image from the current code
2. Tag it as `latest` and push to `gcr.io/inzone-f93e4/inzoneapi:latest`
3. Deploy to the production Cloud Run service named `inzoneapi`
4. Use environment variables from `envs.yaml`

## Environment Variables

### Production (`envs.yaml`)
Contains production API keys and credentials. **Do not modify** unless updating production configuration.

### Test (`envs.test.yaml`)
Contains test environment API keys and credentials. You can:
- Use the same credentials as production (current default)
- Use separate test API keys for isolated testing
- Add test-specific variables like `DEBUG: 'true'` or `LOG_LEVEL: 'debug'`

## Recommended Workflow

1. **Develop Locally**: Make changes to the code on your local machine
2. **Deploy to Test**: Run `./deploy_cloud_run_test.sh` to deploy to the test environment
3. **Test**: Validate your changes using the test Cloud Run URL
4. **Deploy to Production**: Once verified, run `./deploy_cloud_run.sh` to deploy to production

## Deployment Scripts

### deploy_cloud_run_test.sh
```bash
#!/bin/bash
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi:test
gcloud run deploy inzoneapi-test \
  --image gcr.io/inzone-f93e4/inzoneapi:test \
  --region us-central1 \
  --env-vars-file envs.test.yaml \
  --allow-unauthenticated
```

### deploy_cloud_run.sh
```bash
#!/bin/bash
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi
gcloud run deploy inzoneapi \
  --image gcr.io/inzone-f93e4/inzoneapi \
  --region us-central1 \
  --env-vars-file envs.yaml
```

## Troubleshooting

### Authentication Issues
```bash
gcloud auth login
gcloud config set project inzone-f93e4
```

### View Logs
```bash
# Production logs
gcloud run logs read --service inzoneapi --region us-central1

# Test logs
gcloud run logs read --service inzoneapi-test --region us-central1
```

### List Deployments
```bash
gcloud run services list --region us-central1
```

### Delete Test Service (cleanup)
```bash
gcloud run services delete inzoneapi-test --region us-central1
```

## Container Registry Management

### View All Images
```bash
gcloud container images list --repository=gcr.io/inzone-f93e4
```

### View Image Tags
```bash
# Production images
gcloud container images list-tags gcr.io/inzone-f93e4/inzoneapi

# Test images
gcloud container images list-tags gcr.io/inzone-f93e4/inzoneapi --filter="tags:test"
```

### Delete Old Images
```bash
gcloud container images delete gcr.io/inzone-f93e4/inzoneapi:test --quiet
```

## Security Notes

- Never commit `envs.yaml` or `envs.test.yaml` with real API keys to version control
- The `key.json` file is excluded via `.gitignore` - keep it secure
- Use separate API keys for test and production when possible
- Review Cloud Run IAM permissions regularly

## Additional Resources

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Container Registry Documentation](https://cloud.google.com/container-registry/docs)
- [gcloud CLI Reference](https://cloud.google.com/sdk/gcloud/reference)
