# Container deployment assets

The root `docker-compose.yml` is the supported workstation lab topology. Component Dockerfiles use multi-stage or dependency-separated builds and unprivileged runtime users. Separate internal data, agent, and reverse-proxy networks limit lateral reach; PostgreSQL and Redis publish no host ports. A fresh database volume creates a separate, non-superuser `KANDOR_DB_USER`; the database-owner credential is supplied only to PostgreSQL, not to the backend.

For production, treat Compose as a reference rather than a complete perimeter:

- use externally managed secrets instead of an `.env` file;
- terminate TLS at a hardened ingress;
- retain a least-privilege application database account and run reviewed migrations under a controlled deployment identity;
- apply memory/CPU/PID limits and an organization-approved container policy;
- pin images by reviewed digest and scan/sign release artifacts;
- export logs and audit events to protected external storage.

The demo agent service drops Linux capabilities, uses a read-only root filesystem, receives a unique anonymous state volume per replica, and can reach only the internal KANDOR network.
