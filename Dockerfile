FROM python:3.13-slim

WORKDIR /app

# Install strydcmd from bundled source
COPY strydcmd-src/ /opt/strydcmd/
RUN pip install --no-cache-dir /opt/strydcmd/

# Install runcoach
COPY pyproject.toml .
COPY fit_to_yaml_blocks.py .
COPY workout_yaml_schema.json .
COPY runcoach/ runcoach/
RUN pip install --no-cache-dir .

VOLUME /app/data
EXPOSE 5000

CMD ["python", "-m", "runcoach.web"]
