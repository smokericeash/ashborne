# KANDOR Agent

`kandor-agent` is the visible, lightweight endpoint component for **KANDOR —
Self-Hosted Security Agent Orchestration Platform**. It performs only dedicated,
read-only diagnostic actions. It has no general command runner, never invokes a
shell, and does not install persistence.

## Install and enroll

Python 3.12 or later is required.

```console
python -m pip install .
kandor-agent enroll --server https://kandor.local --token TOKEN
kandor-agent run
```

The UUID and opaque agent credential are written atomically to a local JSON file.
On operating systems and filesystems that support POSIX permission bits, the
directory is mode `0700` and the file is mode `0600`. Use `--config` or the
`KANDOR_CONFIG` environment variable to select another location.

TLS certificate validation is always enabled for HTTPS. A private certificate
authority can be supplied with `--ca-bundle` or `KANDOR_CA_BUNDLE`. There is no
option to disable certificate checks. Plain HTTP requires the explicit
`--allow-insecure-http` option (or `KANDOR_ALLOW_INSECURE_HTTP=true`) and is only
intended for an isolated local Docker lab.

## Safe task surface

The exact allowlist is:

- `SYSTEM_INFO`
- `HOSTNAME`
- `CURRENT_USER`
- `CPU_INFO`
- `MEMORY_USAGE`
- `DISK_USAGE`
- `NETWORK_INTERFACES`
- `UPTIME`
- `PROCESS_INVENTORY`
- `INSTALLED_SOFTWARE`
- `LISTENING_PORTS`
- `AGENT_HEALTH`
- `PING`

Parameters are typed and reject unknown fields. Collection sizes and serialized
results are capped. Process command lines and environment variables are never
collected. Task results are saved to a permission-restricted outbox before upload,
so a temporary disconnection does not discard completed work.

## Container demo enrollment

Development Compose deployments may set `KANDOR_DEMO_BOOTSTRAP_SECRET` together
with `KANDOR_SERVER_URL=http://kandor-backend:8000` and
`KANDOR_ALLOW_INSECURE_HTTP=true`. If no credential exists, the agent calls the
development-only `/api/v1/enrollment/demo` endpoint. The server must keep that
endpoint disabled outside development. Each scaled container derives its visible
name from its unique container hostname.

## Tests

```console
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy kandor_agent
python -m build
```
