# Use the official Python image from the Docker Hub
FROM python:3.12-slim
# FROM gcr.io/inzone-f93e4/inzoneapi:latest

# Set environment variables
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libglib2.0-0 \
    libgthread-2.0-0 \
    libstdc++6 \
    ffmpeg \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libxrender1 \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR $APP_HOME

# Copy the application code into the container
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Expose the port for Flask app (optional)
EXPOSE $PORT
EXPOSE 8080

# Set environment variable for the key.json file path
# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/key.json

# Start the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
