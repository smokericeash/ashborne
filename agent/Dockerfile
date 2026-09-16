FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KANDOR_CONFIG=/var/lib/kandor/agent.json \
    KANDOR_LOG_FILE=/var/log/kandor/agent.jsonl

WORKDIR /opt/kandor-agent

COPY pyproject.toml README.md LICENSE ./
COPY kandor_agent ./kandor_agent

RUN pip install --no-cache-dir . \
    && groupadd --system kandor \
    && useradd --system --gid kandor --home-dir /var/lib/kandor --shell /usr/sbin/nologin kandor \
    && install -d -o kandor -g kandor -m 0700 /var/lib/kandor /var/log/kandor

USER kandor:kandor

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["kandor-agent", "status", "--config", "/var/lib/kandor/agent.json", "--json"]

ENTRYPOINT ["kandor-agent"]
CMD ["run"]
