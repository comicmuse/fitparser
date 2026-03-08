FROM python:3.13-slim

# Update base packages and install git (needed to pip install strydcmd from GitHub)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends git && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application source
COPY . .

# Install runcoach and all dependencies (including strydcmd from GitHub)
RUN pip install --no-cache-dir .

# Data volume for activities, database, etc.
VOLUME /app/data
EXPOSE 5000

# Run the web server
CMD ["python", "-m", "runcoach.web"]
