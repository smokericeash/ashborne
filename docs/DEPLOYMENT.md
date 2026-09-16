# Deploying KANDOR

## Local Compose deployment

1. Copy `.env.example` to `.env`.
2. Replace every `CHANGE_ME` value. Generate independent random values; do not reuse the database, JWT, demo, or account secrets.
3. Run `docker compose config` and inspect the resolved service definitions without sharing its secret-bearing output.
4. Start with `docker compose up --build -d`.
5. Confirm `docker compose ps`, `/health/ready`, the login page, and `docker compose logs --since=5m`.
6. Sign in, change/bootstrap accounts as appropriate, and disable development seeding after the first controlled setup.

Compose binds the frontend and development API to loopback. PostgreSQL and Redis have no host-published ports. Named volumes preserve database state; anonymous per-replica volumes preserve separate demo-agent identities.

The frontend and backend share a dedicated internal proxy network. Compose gives the frontend the address declared by `KANDOR_FRONTEND_PROXY_IP`, and Uvicorn trusts forwarded headers only from the matching `KANDOR_FORWARDED_ALLOW_IPS`. If `KANDOR_PROXY_SUBNET` must change to avoid a local route conflict, update all three values together. Production ingress addresses must be configured explicitly; never use a wildcard while the API is directly reachable.

On the first start of a fresh PostgreSQL volume, `docker/postgres/init-app-role.sh` creates the `KANDOR_DB_USER` login with `NOSUPERUSER`, `NOCREATEDB`, and `NOCREATEROLE`. The backend and its Alembic migration use that account; `POSTGRES_USER` remains a separate database-owner account and is not injected into the backend container. Initialization scripts do not run again for an existing volume, so later credential rotation requires a controlled database role update (or an intentional lab-volume reset) as well as an updated `KANDOR_DATABASE_URL`.

## Production checklist

- Set `KANDOR_ENVIRONMENT=production`, `KANDOR_AUTO_CREATE_TABLES=false`, and `KANDOR_SEED_DEVELOPMENT=false`; omit all three seed-password variables and the demo bootstrap secret, and remove `KANDOR_ALLOW_INSECURE_HTTP` from every agent environment.
- Build immutable, version-tagged images in CI; scan and sign them before promotion.
- Terminate TLS 1.2+ at a maintained ingress. Redirect HTTP, enable HSTS after validation, and pass trusted proxy headers deliberately.
- Use a managed or separately backed-up PostgreSQL service and a private authenticated Redis service. Give KANDOR a non-superuser database role limited to its schema.
- Inject secrets from a secret manager. Rotate the JWT signing key with an explicit session invalidation plan.
- Restrict `KANDOR_CORS_ORIGINS` and `KANDOR_TRUSTED_HOSTS` to exact deployed origins and hostnames.
- Run as non-root with a read-only root filesystem where supported, writable mounts only for required state, dropped Linux capabilities, resource limits, and a seccomp/AppArmor/SELinux policy.
- Send JSON logs and audit exports to independently protected, retention-managed storage. Alert on login failures, role changes, token creation, agent removal, and repeated task failures.
- Back up PostgreSQL with encryption and regularly restore into an isolated environment.
- Monitor readiness, event-loop latency, database connections, Redis availability, task age, offline-agent counts, and certificate expiry.

## TLS for agents

Set the agent server URL to an `https://` endpoint whose hostname matches its certificate. For an internal CA, install the CA into the operating-system trust store or configure the agent with a CA bundle path. Do not set certificate verification off in production. Mutual TLS can be added at the ingress as defense in depth; the KANDOR agent credential is still required at the API.

## Migrations

Run `alembic upgrade head` once per release before serving new application code. Back up first, review generated SQL, and use a deployment lock so multiple replicas do not race migrations. Downgrades are not a substitute for backups; prefer a tested forward fix.

## Scaling

API replicas are stateless except for in-process connection bookkeeping. PostgreSQL is authoritative and Redis coordinates live-event publication and distributed rate state. When scaling API replicas, use a load balancer that supports streaming responses and disables buffering for SSE. Agent polling does not require sticky sessions.

## Backup and recovery

Back up the database, deployment configuration, TLS material, and necessary secret-manager metadata. Agent credentials cannot be recovered from server-side hashes; after a total secret/state loss, revoke old identities and re-enroll agents. Validate recovery time, restored audit history, migrations, login, and one agent task in a scheduled exercise.

## Upgrades

Read `CHANGELOG.md`, run all tests, take a backup, migrate a staging copy, and exercise login/enrollment/heartbeat/task/audit flows. Roll the API and UI together when their contracts change. Agents should be backward compatible within a documented version window; KANDOR never silently installs agent updates.
