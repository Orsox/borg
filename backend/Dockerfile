# Backend Dockerfile
FROM python:3.12-slim

WORKDIR /app

# git + Docker CLI — required by app.agent_sandbox.service to drive the
# locked-down sandbox containers (Locutus skill execution, Seven's Agent Mode):
# `git clone`/`commit`/`push` happen here in the backend container, and
# `docker run ...` for the sandbox itself needs the CLI talking to the host's
# daemon via the socket mounted in docker-compose.yml. Debian slim's repo only
# ships an old `docker.io` build; pull `docker-ce-cli` from Docker's own apt
# repo instead — same "vendor repo over distro package" pattern already used
# in agent_sandbox/Dockerfile.pi for Node 22.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" && \
    pip install --no-cache-dir apscheduler watchfiles

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
