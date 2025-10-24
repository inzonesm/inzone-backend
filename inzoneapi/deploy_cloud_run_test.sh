#!/bin/bash

# Deploy InZone API to TEST Container on Google Cloud Run
# This script deploys to a separate test service for testing before production

echo "Building and deploying InZone API TEST container..."

# Build and push the Docker image with 'test' tag
echo "Step 1: Building Docker image and pushing to GCR with 'test' tag..."
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi:test

# Deploy to Cloud Run with a separate test service name
echo "Step 2: Deploying to Cloud Run test service..."
gcloud run deploy inzoneapi-test \
  --image gcr.io/inzone-f93e4/inzoneapi:test \
  --region us-central1 \
  --env-vars-file envs.test.yaml \
  --allow-unauthenticated

echo "Test deployment complete!"
echo "Your test API is now running at the URL shown above."
