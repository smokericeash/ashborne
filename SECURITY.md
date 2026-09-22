# ASHBORNE security policy

## Supported versions

Security fixes are provided for the most recent tagged release and the current default branch. This portfolio project does not promise a commercial support SLA.

## Reporting a vulnerability

Do not publish an exploitable report or live credentials in an issue. Use GitHub's private vulnerability reporting feature for the repository, or contact the repository owner through the private address configured in its security settings. Include the affected version, prerequisites, impact, reproduction, and any suggested mitigation. You should receive an acknowledgement within seven days.

## Deployment responsibilities

ASHBORNE ships secure defaults but cannot secure an untrusted host. Production operators must:

- replace every `CHANGE_ME` value and store secrets outside the repository;
- terminate TLS with a valid certificate and redirect HTTP to HTTPS;
- isolate PostgreSQL and Redis from untrusted networks;
- run containers as unprivileged users and keep images/dependencies patched;
- disable development seeding and demo bootstrap;
- restrict CORS and trusted hosts to deployed origins;
- forward audit logs to independently protected storage;
- back up and test restoration of PostgreSQL;
- review roles, enrollment tokens, agents, and refresh sessions regularly.

The agent must only be installed with system-owner authorization. It is intentionally visible, does not create persistence, and should be started through an administrator-chosen service manager if persistent monitoring is desired.

## Security invariants

- User and agent authentication credentials are separate.
- Enrollment secrets, agent credentials, refresh tokens, and passwords are stored as hashes where later plaintext recovery is unnecessary.
- Enrollment tokens expire, are revocable, and are consumed atomically once.
- Access tokens are short lived; refresh tokens rotate and old tokens are rejected.
- Authorization is checked server-side for every protected operation.
- Structured tasks remain closed-enum actions. General operation text is accepted only as the
  `KALI_OPERATION` type and is routed to the explicitly enrolled Kali controller.
- Kali controller mode is opt-in, visible in inventory, authenticated separately, bounded by
  timeout/output/concurrency limits, and must use pre-provisioned non-interactive SSH access.
- Task creation requires an explicit authorized-scope confirmation recorded in audit metadata.
- Audit records have no update/delete API.
- Certificate verification is enabled for production agent traffic.
- Logs redact secrets and sanitized API errors do not disclose internals.

See `docs/THREAT_MODEL.md` for assets, boundaries, abuse cases, and residual risks.
