# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app

# Set the working directory in the container
WORKDIR $APP_HOME

# Copy the application code into the container
COPY . .

# Install dependencies
RUN pip install Flask gunicorn firebase-admin flask-cors google.cloud python-dotenv openai
# RUN pip install -r requirements.txt

# Expose the port for Flask app (optional)
EXPOSE $PORT
# EXPOSE 8080

# Set environment variable for the key.json file path
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/key.json

# Start the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app