# ASHBORNE Agent

`ashborne-agent` is the visible, lightweight endpoint component for **ASHBORNE —
Adversary Emulation & Offensive Security Lab Platform**. It performs dedicated,
read-only lab actions for authorized local-host reconnaissance and enumeration.
It has no general command runner, never invokes a shell, and does not install
persistence.

## Install and enroll

Python 3.12 or later is required.

```console
python -m pip install .
ashborne-agent enroll --server https://ashborne.local --token TOKEN
ashborne-agent run
```

The UUID and opaque agent credential are written atomically to a local JSON file.
On operating systems and filesystems that support POSIX permission bits, the
directory is mode `0700` and the file is mode `0600`. Use `--config` or the
`ASHBORNE_CONFIG` environment variable to select another location.

TLS certificate validation is always enabled for HTTPS. A private certificate
authority can be supplied with `--ca-bundle` or `ASHBORNE_CA_BUNDLE`. There is no
option to disable certificate checks. Plain HTTP requires the explicit
`--allow-insecure-http` option (or `ASHBORNE_ALLOW_INSECURE_HTTP=true`) and is only
intended for an isolated local Docker lab.

## Safe task surface

The exact typed-action catalog is:

- `QUICK_RECON`
- `SYSTEM_INFO`
- `HOSTNAME`
- `CURRENT_USER`
- `SECURITY_CONTEXT`
- `LINUX_KERNEL_INFO`
- `LINUX_IDENTITY`
- `GROUP_MEMBERSHIP`
- `LINUX_CAPABILITIES`
- `LINUX_MOUNTS`
- `SAFE_ENVIRONMENT_OVERVIEW`
- `SERVICE_OVERVIEW`
- `SCHEDULED_ACTIVITY_OVERVIEW`
- `PRIVILEGE_ENUMERATION`
- `NETWORK_OVERVIEW`
- `HOST_RECON`
- `CPU_INFO`
- `MEMORY_USAGE`
- `DISK_USAGE`
- `FILE_SYSTEM_OVERVIEW`
- `NETWORK_INTERFACES`
- `NETWORK_CONNECTIONS`
- `ROUTE_TABLE`
- `UPTIME`
- `PROCESS_INVENTORY`
- `INSTALLED_SOFTWARE`
- `LISTENING_PORTS`
- `AGENT_HEALTH`
- `PING`

Parameters are typed and reject unknown fields. Collection sizes and serialized
results are capped. Quick Recon is passive and local-only. File actions inspect
fixed-location metadata without content collection; network actions do not resolve
DNS or probe remote targets. Process command lines and environment-variable values
are never collected. The environment overview returns names only and omits any name
containing `PASSWORD`, `PASS`, `TOKEN`, `SECRET`, `KEY`, `AUTH`, or `COOKIE`.
Linux service and scheduled-activity actions inspect bounded entries in fixed
system locations but never read unit, cron, or timer definitions. Unsupported
platform-specific observations return an explicit `supported: false` result.
Task results are saved to a permission-restricted outbox before upload, so a
temporary disconnection does not discard completed work.

## Container demo enrollment

Development Compose deployments may set `ASHBORNE_DEMO_BOOTSTRAP_SECRET` together
with `ASHBORNE_SERVER_URL=http://ashborne-backend:8000` and
`ASHBORNE_ALLOW_INSECURE_HTTP=true`. If no credential exists, the agent calls the
development-only `/api/v1/enrollment/demo` endpoint. The server must keep that
endpoint disabled outside development. Each scaled container derives its visible
name from its unique container hostname.

## Tests

```console
python -m pip install -e ".[dev]"
pytest
ruff check .
mypy ashborne_agent
python -m build
```
