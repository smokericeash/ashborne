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
| Arbitrary code execution through tasks | Closed enum, typed schemas, no command field, server and agent validation, dedicated handlers, result caps | A handler-library vulnerability remains possible; sandbox/containerize agents where appropriate |
| Out-of-scope operator action | Per-task authorization confirmation, target identity in the UI, RBAC, immutable actor/target audit metadata | Confirmation is not a substitute for written authorization or network enforcement |
| Privilege escalation through API | Deny-by-default RBAC dependencies, server-side checks, tests, audit | Application/database administrator remains powerful; separate duties externally |
| Task replay or invalid transition | Transactional claims, ownership and current-state checks, terminal-state immutability | Network retry ambiguity; clients use task IDs/idempotent reads |
| Telemetry poisoning | Schema/range/size validation, server receipt time, authenticated identity | An owned agent can lie about its host; telemetry is observational, not attestation |
| Audit deletion/tampering | No update/delete API, append-only service, restricted DB role, external forwarding | Database administrators can tamper; use WORM storage/signing for stronger assurance |
| Secret leakage in logs/errors | Structured allowlisted context, redaction, sanitized exceptions, no token logging | Reverse proxies must also redact headers and query strings |
| Denial of service | Request/body/output limits, pagination, rate limits, timeouts, bounded agent collection | Resource exhaustion still requires network and infrastructure limits |
| Development feature exposed | Demo endpoint gated on explicit development mode and secret | Misconfiguration is possible; production readiness checks should fail unsafe combinations |

## Out of scope

ASHBORNE does not claim to protect a fully compromised server/database administrator, provide hardware-backed endpoint attestation, detect all hostile endpoint behavior, replace EDR/SIEM, or deliver forensic chain-of-custody guarantees. Its offensive-security scope is limited to transparent, bounded, read-only adversary-emulation training on enrolled lab hosts. It does not execute arbitrary code and must not be extended with covert transport, payload delivery, persistence, evasion, credential theft, lateral movement, or destructive tooling.

## Security review triggers

Require threat-model and security-test updates when adding a task handler, authentication method, externally reachable service, agent auto-update mechanism, file collection, multi-tenancy, third-party integration, or a data-export path.
