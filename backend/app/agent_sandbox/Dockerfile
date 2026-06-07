# borg-agent-sandbox:latest — locked-down execution image for `active` Locutus skills.
#
# Built to match the invocation in agent_sandbox/service.py::build_docker_run_argv:
# --network=none, --cap-drop=ALL, --read-only, --user 1000:1000, only the
# ephemeral worktree mounted at /workspace. Everything a skill needs to run
# (interpreters, package managers, git for diffing) must already be baked in —
# the container has no network access to fetch anything at runtime.
#
# Build: docker build -t borg-agent-sandbox:latest -f app/agent_sandbox/Dockerfile .

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv pytest

# Match the --user 1000:1000 the sandbox always passes — the container never
# runs as root, even though --read-only/--cap-drop=ALL would also constrain it.
RUN useradd --uid 1000 --create-home --shell /bin/bash sandbox

USER sandbox
WORKDIR /workspace
