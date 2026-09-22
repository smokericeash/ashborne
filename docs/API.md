# ASHBORNE API and agent protocol

The running server publishes the authoritative OpenAPI description at `/openapi.json`. Development and test deployments also expose interactive Swagger documentation at `/docs`; production disables that CDN-backed HTML route. This document explains protocol invariants that clients must preserve.

## Versioning and media types

All supported application endpoints start with `/api/v1`. JSON request bodies require `Content-Type: application/json`; SSE uses `text/event-stream`. Unknown JSON fields are rejected on security-sensitive schemas. Times are RFC 3339 UTC strings, IDs are UUIDs, and enum values are uppercase.

## User authentication

`POST /api/v1/auth/login` accepts an email and password and returns a short-lived bearer access token plus refresh-session material. `POST /api/v1/auth/refresh` rotates refresh material; presenting an already rotated/revoked token fails. `POST /api/v1/auth/logout` revokes the session.

Use `Authorization: Bearer <access-token>` on management requests. Do not place tokens in URLs, logs, local-storage analytics, or error reports.

| Capability | Administrator | Operator | Viewer |
|---|:---:|:---:|:---:|
| View dashboard, agents, tasks | ✓ | ✓ | ✓ |
| Create authorized single/bulk operation | ✓ | ✓ | — |
| View audit | ✓ | ✓ | ✓ |
| Generate/revoke enrollment token | ✓ | — | — |
| Remove agent | ✓ | — | — |
| Manage users/roles/settings | ✓ | — | — |

## Enrollment

An administrator creates an enrollment token. The response contains the plaintext secret once; only a cryptographic hash is retained. The agent sends the token with its bounded identity and platform metadata to the enrollment endpoint. On success, the API atomically consumes the token and returns an agent UUID and high-entropy credential once.

Normal tokens are always expiring, revocable, and single-use. `/api/v1/enrollment/demo` is a separate convenience path available only when both development mode and a demo secret are configured.

## Agent authentication

After enrollment, the agent authenticates using its returned bearer credential. The API hashes the presented value and selects only an active credential by its indexed digest; plaintext credentials are never stored. The credential authorizes exactly one agent identity, and route IDs and submitted task IDs are checked against it.

Credentials should be rotated through re-enrollment or the explicit administrative lifecycle, never copied into an image. Revoking/removing an agent prevents further heartbeats and task access.

## Heartbeat payload

Heartbeats carry current agent version, monotonic uptime estimate, hostname, observed local addresses, and bounded health facts. The server records receipt time and a sanitized snapshot. Process lists, software inventory, and ports are task results rather than heartbeat fields.

## Task envelopes and transitions

Task creation contains `agent_id`, `task_type`, a small validated `parameters` object, and `authorized_scope_confirmed: true`. ASHBORNE's browser client supplies this invariant from the authorized-lab workflow instead of asking for a repetitive per-command checkbox. The value is retained in the creation audit event. The agent envelope contains the task identity, type, normalized parameters, creation/expiration timestamps, and status; it never contains a command. Polling atomically transitions eligible work from `QUEUED` to `DISPATCHED`, and the assigned agent may start and complete only its own task.

```text
QUEUED ──> DISPATCHED ──> RUNNING ──> SUCCESS
   │            │             └──────> FAILED
   │            └────────────────────> EXPIRED
   ├─────────────────────────────────> CANCELLED
   └─────────────────────────────────> EXPIRED
```

Result bodies are JSON objects with a completion status and either bounded structured data or a sanitized error. Results are size-limited by both agent and API. Retrying an identical completion is handled safely or rejected without changing an existing terminal result.

### Bulk operations

`POST /api/v1/tasks/bulk` accepts a unique, bounded `agent_ids` list plus the
operation fields and `authorized_scope_confirmed: true`. It creates one
ordinary task per agent in one transaction and returns a presentation-only
`bulk_operation_id`. The grouping identifier does not change authorization,
ownership, dispatch, result, or audit semantics.

- `GET /api/v1/tasks/bulk-operations` lists grouped operation summaries.
- `GET /api/v1/tasks/bulk-operations/{id}` returns the independent target tasks.
- `POST .../{id}/retry-failed` creates a new operation containing only failed targets.
- `POST .../{id}/rerun` creates a new operation for all original targets.
- `POST .../{id}/cancel-queued` cancels only tasks that remain `QUEUED`.

Retry and rerun requests carry the same server-required lab-scope invariant.
Every created target task receives its own `TASK_CREATED` audit event containing
both task and bulk IDs; group actions also receive a bulk-operation audit event.

The browser Operator Console sends general operation text only as a validated
`KALI_OPERATION` parameter object. The backend binds each child task to the
selected target host and routes execution to the configured `kali-controller`
agent. Existing structured task types continue to use the same endpoints and
execute on their target agents.

## Pagination, filtering, and errors

Collection endpoints accept bounded page/page-size, search, sort, and resource-specific filters. Responses include items and total/page metadata. Invalid filters return `422`; authentication failures `401`; authorization failures `403`; missing resources `404`; state conflicts `409`; rate limits `429`.

Errors use standard HTTP status codes and bounded, safe `detail` messages. Validation errors identify rejected fields without echoing secret input. Stack traces, SQL details, credential hashes, and secrets never appear in client responses.

## Live events

An authenticated client connects to `/api/v1/events/stream`. Events identify a type and affected resource, prompting the UI to invalidate and re-fetch relevant queries. The stream emits keepalives, and clients reconnect with backoff. Authorization is checked at connection time, revalidated periodically, and bounded by the access-token expiry; deployments should choose a token transport that does not put bearer material into proxy access logs.
