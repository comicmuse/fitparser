FROM python:3.13-slim

WORKDIR /app

# Copy everything first (strydcmd-src may or may not exist)
COPY . .

# Install strydcmd if present (for production builds with Stryd integration)
# In CI, strydcmd-src/ won't exist in the repo - that's fine for health checks
RUN if [ -d strydcmd-src ] && [ -f strydcmd-src/pyproject.toml ]; then \
      pip install --no-cache-dir ./strydcmd-src/ && \
      echo "✓ Stryd integration enabled"; \
    else \
      echo "⚠ Stryd integration disabled (strydcmd-src not found - this is expected in CI)"; \
    fi

# Install runcoach and dependencies
RUN pip install --no-cache-dir .

# Data volume for activities, database, etc.
VOLUME /app/data
EXPOSE 5000

# Run the web server
CMD ["python", "-m", "runcoach.web"]
