FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ASHBORNE_CONFIG=/var/lib/ashborne/agent.json \
    ASHBORNE_LOG_FILE=/var/log/ashborne/agent.jsonl

WORKDIR /opt/ashborne-agent

COPY pyproject.toml README.md LICENSE ./
COPY ashborne_agent ./ashborne_agent

RUN pip install --no-cache-dir . \
    && groupadd --system ashborne \
    && useradd --system --gid ashborne --home-dir /var/lib/ashborne --shell /usr/sbin/nologin ashborne \
    && install -d -o ashborne -g ashborne -m 0700 /var/lib/ashborne /var/log/ashborne

USER ashborne:ashborne

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["ashborne-agent", "status", "--config", "/var/lib/ashborne/agent.json", "--json"]

ENTRYPOINT ["ashborne-agent"]
CMD ["run"]
