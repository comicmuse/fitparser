FROM python:3.13-slim

RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application source
COPY . .

# Install runcoach and all dependencies
RUN pip install --no-cache-dir '.[fcm,claude]'

# Data volume for activities, database, etc.
VOLUME /app/data
EXPOSE 5000

# Run the web server
CMD ["python", "-m", "runcoach.web"]
