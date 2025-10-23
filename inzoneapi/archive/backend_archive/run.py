import os
from __init__ import create_app

# ✅ Ensure Google credentials are set before initializing the app
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("key.json")

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


# gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi
# gcloud run deploy --image gcr.io/inzone-f93e4/inzoneapi --set-env-vars OPENAI_API_KEY='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'

# gcloud run deploy --image gcr.io/inzone-f93e4/inzoneapi --set-env-vars OPENAI_API_KEY='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'

# OPENAI_API_KEY="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"
# GOOGLE_APPLICATION_CREDENTIALS="key.json"