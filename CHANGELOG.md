# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses semantic versioning.

## [Unreleased]

### Added

- Multi-host selection and bulk operations that retain an independent task, lifecycle, result, and audit trail for every target.
- Typed Operator Console aliases with history, autocomplete, host selection controls, and explicit scope confirmation.
- Structured summary, raw, timeline, and audit result views plus retry-failed, cancel-queued, rerun, copy, and JSON export workflows.
- Bounded Linux identity, kernel, capability, mount, environment-name, service, scheduled-activity, privilege, network, and host-recon observations.

### Changed

- Simplified Command Center/navigation and reduced the frontend render and initial-loading footprint through route splitting and memoized data transforms.

### Planned

- External identity-provider integration and WebAuthn.
- Mutual TLS for managed agent fleets.
- Signed agent packages and staged upgrades.
- Engagement workspaces and exportable operation reports.

## [0.1.0] - 2026-09-16

### Added

- Authorization-first adversary-emulation lab workflow with per-task scope confirmation.
- Quick Recon, Security Context, File System Overview, Network Connections, and Route Table typed actions.
- FastAPI management plane, PostgreSQL migrations, Redis coordination, JWT sessions, RBAC, audit history, enrollment, heartbeat health, typed tasking, settings, SSE, CLI, and structured logging.
- Cross-platform transparent Python agent with secure enrollment, credential storage, retry/backoff, heartbeat, bounded execution, and structured results.
- React/TypeScript charcoal and crimson operator console for command center, lab hosts, tasks, timeline/audit, users, and settings.
- Docker Compose core and scaled demo profiles with internal data/agent networks and a host-facing proxy network.
- GitHub Actions, tests, developer automation, architecture/security/deployment documentation, and a fresh-install smoke workflow.

[Unreleased]: https://github.com/your-account/ashborne/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-account/ashborne/releases/tag/v0.1.0
