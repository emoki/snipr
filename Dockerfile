
FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends         curl ca-certificates build-essential         && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pyproject if present (for editable dev installs), then the code
COPY . /app

# Optional extras for server
# If the project uses pyproject.toml with extras, this can be:
#   pip install -e .[webui]
# Here we install minimal runtime deps directly to avoid extras coupling.
RUN pip install --no-cache-dir fastapi uvicorn[standard] monsterui tomli-w

EXPOSE 8000

# Environment: default paths within container
ENV SNIPR_DB_PATH=/data/snipr.db
ENV SNIPR_CONFIG_PATH=/data/snipr.toml

# Create a volume where host can mount snipr.db and snipr.toml
VOLUME ["/data"]

# Start the FastAPI server
CMD ["uvicorn", "snipr.server.main:app", "--host", "0.0.0.0", "--port", "8000"]
