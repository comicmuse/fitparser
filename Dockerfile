FROM python:3.13-slim

WORKDIR /app

# Install strydcmd from bundled source (copy from your local strydcmd repo before building)
# Run: cp -r /path/to/strydcmd strydcmd-src/
COPY strydcmd-src/ /opt/strydcmd/
RUN pip install --no-cache-dir /opt/strydcmd/

# Install runcoach and dependencies
COPY pyproject.toml .
COPY fit_to_yaml_blocks.py .
COPY workout_yaml_schema.json .
COPY runcoach/ runcoach/
RUN pip install --no-cache-dir .

# Data volume for activities, database, etc.
VOLUME /app/data
EXPOSE 5000

# Run the web server
CMD ["python", "-m", "runcoach.web"]
