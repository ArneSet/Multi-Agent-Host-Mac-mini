# External Intake Readiness

> Sprint 5 — HYBRIS Agent Host

## What Is Now Safe Enough for Future External Intake

After Sprint 5, the orchestrator has every production-safety layer needed to receive tickets from external sources:

### Implemented Safety Layers

| Layer | Sprint | Status |
|-------|--------|--------|
| Input sanitization (ticket ID, paths, branches) | 1 | ✓ Hardened |
| Concurrency control (fcntl locks, atomic moves) | 1 | ✓ Hardened |
| Worker allowlist (double gate: config + code) | 1 | ✓ Hardened |
| Ticket state machine (validated transitions) | 1 | ✓ Hardened |
| Domain model (aggregate root, immutable records) | 2 | ✓ Documented |
| Dual repo architecture (test/prod separation) | 3 | ✓ Enforced |
| Review + approval gate | 3 | ✓ Enforced |
| Physical repo separation | 4 | ✓ Enforced |
| Promotion readiness checks | 4 | ✓ Enforced |
| **QA gate** | **5** | **✓ Enforced** |
| **Manual promotion execution** | **5** | **✓ Enforced** |
| **Promotion status tracking** | **5** | **✓ Enforced** |
| **Promotion audit trail** | **5** | **✓ Enforced** |

### What This Means

- A ticket cannot reach production without explicit review, approval, QA, and manual promotion
- prod_repo is unreachable through normal agent execution
- Every promotion attempt is audited
- The operator has full visibility through CLI commands

## What Still Must Remain Protected

Even with all safety layers in place, the following boundaries must hold:

| Boundary | Rationale |
|----------|-----------|
| No auto-promotion | Creative Director must explicitly approve AND execute |
| No auto-push | Git push to remote must be a manual CD action |
| No daemon/background mode | System runs on explicit operator invocation only |
| No external network services | No HTTP endpoints, no webhook receivers |
| Prod repo is code-protected | `validate_repo_separation()` + `validate_repo_target()` |

## Remaining Blockers Before WhatsApp/OpenClaw Intake

### Must Be Built First

| Blocker | Description | Priority |
|---------|-------------|----------|
| Intake adapter | Parse incoming messages (WhatsApp/SMS/OpenClaw) into ticket format | Required |
| Intake validation | Sanitize and validate external input beyond current ticket ID validation | Required |
| Rate limiting | Prevent ticket flooding from external sources | Required |
| Source tracking | Record which external channel created each ticket | Required |
| Intake authentication | Verify the source is authorized to create tickets | Required |

### Should Be Built

| Item | Description | Priority |
|------|-------------|----------|
| Ticket priority from intake | Map external urgency to ticket priority | Recommended |
| Acknowledgment flow | Confirm receipt of externally created tickets | Recommended |
| Error feedback | Report intake failures back to the external channel | Recommended |

### Nice to Have

| Item | Description |
|------|-------------|
| Auto-triage | Automatically classify incoming tickets by type |
| Intake dashboard | Visual overview of external ticket flow |

## Readiness Assessment

**The orchestrator core is production-safe.** The remaining work for external intake is purely about building the ingestion layer — message parsing, validation, and channel adapters. The internal ticket processing, review, approval, QA, promotion, and audit flows are complete and hardened.

The next sprint toward external intake should focus on:
1. Designing the intake adapter interface
2. Implementing WhatsApp message → ticket conversion
3. Adding intake-specific input validation
4. Adding rate limiting and source authentication
