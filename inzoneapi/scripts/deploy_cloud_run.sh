# chmod +x deploy_cloud_run.sh && ./deploy_cloud_run.sh
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi
gcloud run deploy inzoneapi --image gcr.io/inzone-f93e4/inzoneapi --region us-central1 --env-vars-file envs.yaml