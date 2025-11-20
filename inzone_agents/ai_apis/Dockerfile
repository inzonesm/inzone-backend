# Use the official Python image from the Docker Hub
FROM gcr.io/inzone-f93e4/ai-apis:latest

# Set environment variables
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app

# Set the working directory in the container
WORKDIR $APP_HOME

# Copy the application code into the container
COPY . .

# Install dependencies
# RUN pip3 install -r requirements.txt

# Expose the port for Flask app (optional)
EXPOSE $PORT
# EXPOSE 8080

# Set environment variable for the key.json file path
# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/key.json

# Start the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
