FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent

WORKDIR /app
COPY pyproject.toml ./
COPY agent ./agent
RUN pip install --no-cache-dir . pytest ruff

USER agent
# The target repository's requirements install into the user site (PIP_USER=1) and
# shadow the image's packages on import, so its console scripts must win on PATH
# too: otherwise the image's pytest launcher runs against the repository's pytest.
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_USER=1 \
    PATH=/home/agent/.local/bin:$PATH
ENTRYPOINT ["python", "-m", "agent.runner"]
