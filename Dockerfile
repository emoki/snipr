
FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /snipr

COPY . /snipr

RUN pip install .[webui]

EXPOSE 8000

# Environment: default paths within container
ENV SNIPR_ROOT=/snipr

# Create a volume where host can mount snipr.db and snipr.toml
VOLUME ["/snipr/data"]

# Start the FastAPI server
CMD ["uvicorn", "snipr.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
