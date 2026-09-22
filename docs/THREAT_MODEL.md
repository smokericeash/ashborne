# ASHBORNE threat model

## Scope and assumptions

ASHBORNE manages visible lab agents only on systems the operator is authorized to test. The server host and deployment administrators are trusted but still auditable; browsers, networks, request data, enrollment tokens in transit, and enrolled endpoints may be compromised.

## Assets

- User password verifiers, JWT signing keys, refresh-session hashes, and roles.
- Enrollment-token hashes, agent-credential hashes, and agent identity.
- Host metadata, typed-action results, task history, settings, and audit events.
- Database availability and the integrity of task state transitions.

## Principal threats and controls

| Threat | Primary controls | Residual risk / operations |
|---|---|---|
| Password guessing or credential stuffing | Argon2, generic login errors, rate limiting, short access lifetime, login audit | Add upstream bot controls and MFA for internet-facing deployments |
| Stolen refresh token | Hash at rest, rotation, revocation, expiry, replay rejection | Browser/host compromise may steal a current token; use secure cookies and endpoint hardening |
| Enrollment token theft/replay | High entropy, hash at rest, short expiry, atomic one-time use, revocation, audit | Protect initial transfer; investigate failed replays |
| Agent impersonation | High-entropy per-agent credential, hash at rest, TLS, agent/route ownership checks | Compromised endpoint can act as that endpoint until revoked |
| General operation execution | Only `KALI_OPERATION` carries command text; it is routed to an explicitly tagged/configured Linux controller, requires operator RBAC and scope confirmation, and has bounded timeout, output, and concurrency | The controller is intentionally powerful. Isolate it, use least-privilege SSH keys, restrict reachable lab networks, and forward audit records externally |
| Out-of-scope operator action | Authorized-lab product boundary, target identity in the UI, RBAC, immutable actor/target audit metadata | UI scope language is not a substitute for written authorization or network enforcement |
| Bulk action targets the wrong hosts | Explicit selected-host review, server-side lab-scope invariant, one independent task and audit trail per host, grouping ID used only for display | Operators must verify the reviewed target list before dispatch; a bulk ID never grants authority |
| Operator-console command abuse | Local helpers are parsed separately; every other operation becomes an audited `KALI_OPERATION` for the selected enrolled hosts. The controller uses argument-vector SSH by default and only invokes Bash for explicit `kali:` operations | Authorized operators can run powerful tools. Network isolation, least privilege, written scope, and human review remain required |
| Secret disclosure through environment enumeration | Environment names only, bounded output, denylist for secret-bearing names, no environment values returned | Variable names can still reveal installed tooling; use only on authorized lab hosts |
| Privilege escalation through API | Deny-by-default RBAC dependencies, server-side checks, tests, audit | Application/database administrator remains powerful; separate duties externally |
| Task replay or invalid transition | Transactional claims, ownership and current-state checks, terminal-state immutability | Network retry ambiguity; clients use task IDs/idempotent reads |
| Telemetry poisoning | Schema/range/size validation, server receipt time, authenticated identity | An owned agent can lie about its host; telemetry is observational, not attestation |
| Audit deletion/tampering | No update/delete API, append-only service, restricted DB role, external forwarding | Database administrators can tamper; use WORM storage/signing for stronger assurance |
| Secret leakage in logs/errors | Structured allowlisted context, redaction, sanitized exceptions, no token logging | Reverse proxies must also redact headers and query strings |
| Denial of service | Request/body/output limits, pagination, rate limits, timeouts, bounded agent collection | Resource exhaustion still requires network and infrastructure limits |
| Development feature exposed | Demo endpoint gated on explicit development mode and secret | Misconfiguration is possible; production readiness checks should fail unsafe combinations |

## Out of scope

ASHBORNE does not claim to protect a fully compromised server/database/controller administrator, provide hardware-backed endpoint attestation, detect all hostile endpoint behavior, replace EDR/SIEM, or deliver forensic chain-of-custody guarantees. Kali-backed operations are intended only for transparent administration and authorized lab testing. ASHBORNE must not be extended with covert transport, payload delivery, persistence, evasion, credential theft, or destructive tooling.

## Security review triggers

Require threat-model and security-test updates when adding a task handler, console alias, authentication method, externally reachable service, agent auto-update mechanism, file collection, multi-tenancy, third-party integration, or a data-export path.
