# Contributing to ASHBORNE

Thank you for improving ASHBORNE. Contributions must preserve its authorization-first, transparent, closed-task design.

## Development workflow

1. Create a focused branch from the default branch.
2. Copy `.env.example` to `.env` and use local-only secrets.
3. Run `make install`, then the relevant development service.
4. Add tests for behavior changes, including authorization and audit expectations.
5. Run `make format`, `make lint`, `make test`, and `make build` before opening a pull request.
6. Explain security consequences and migration steps in the pull-request description.

Commits should be small enough to review and should not contain generated dependencies, credentials, `.env` files, live telemetry, or private host details.

## Safety acceptance criteria

Changes that introduce arbitrary commands, uploaded executable handling, scripting interpreters, process injection, persistence, credential access, evasion, exploitation, lateral movement, covert transport, or destructive operations will not be accepted. New lab action types require all of:

- a dedicated, bounded handler with no shell invocation;
- an explicit shared enum entry in API, agent, and UI;
- a typed parameter/result schema and output limits;
- RBAC and audit coverage;
- explicit authorized-scope behavior and documentation;
- unit tests for valid and invalid requests;
- documentation of collected data and platform behavior.

## Database changes

Modify SQLAlchemy models, generate a reviewed Alembic revision, test upgrade from the previous revision, and ensure new query paths have appropriate indexes. Never edit a released migration in place.

## Reporting bugs

Use a minimal reproduction with redacted logs. For vulnerabilities, follow `SECURITY.md` and do not open a public issue before coordinated disclosure.
