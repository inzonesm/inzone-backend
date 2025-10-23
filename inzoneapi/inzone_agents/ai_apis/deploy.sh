#!/bin/bash
# inzonesm@cloudshell:~ (inzone-f93e4)$ cd /home/inzonesm/inzoneapi/inzone_agents/ai_apis/
# inzonesm@cloudshell:~/inzoneapi/inzone_agents/ai_apis (inzone-f93e4)$ chmod +x deploy.sh
# inzonesm@cloudshell:~/inzoneapi/inzone_agents/ai_apis (inzone-f93e4)$ ./deploy.sh
# Optional: Exit on error
set -e
# chmod +x deploy.sh && ./deploy.sh
PROJECT_ID="inzone-f93e4"  # Replace with your project ID
IMAGE_NAME="ai-apis"
REGION="us-east1" # Replace with your region

# Build and push the Docker image
echo "Building the Docker image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$IMAGE_NAME .

echo "Deploying to Cloud Run..."
gcloud run deploy ai-apis \
  --image gcr.io/$PROJECT_ID/$IMAGE_NAME \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --env-vars-file=envs.yaml # Changed the image name to what you wanted it to be.

echo "Deployment complete!"
