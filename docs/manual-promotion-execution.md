# Manual Promotion Execution

> Sprint 5 — HYBRIS Agent Host

## Current Promotion Model

Promotion transfers a branch from `test_repo` to `prod_repo`. It is:
- **Never automatic** — always operator-invoked
- **Never silent** — requires explicit `--execute` flag
- **Always audited** — every attempt produces an audit record
- **Prerequisite-gated** — requires review + approval + QA + repo separation

## Operator Flow

```
1. Ticket completes work → review state
2. Creative Director: review-show TICKET_ID
3. Creative Director: approve TICKET_ID
4. Creative Director: qa-pass TICKET_ID
5. Creative Director: promotion-check TICKET_ID     ← verify readiness
6. Creative Director: promote TICKET_ID              ← create request (pending)
7. Creative Director: promote TICKET_ID --preview    ← preview (no changes)
8. Creative Director: promote TICKET_ID --execute    ← execute (git fetch)
9. Creative Director: audit-show TICKET_ID           ← verify audit trail
```

## Command Semantics

| Command | Action | Writes to prod_repo? |
|---------|--------|:--------------------:|
| `promote TICKET_ID` | Create promotion request (status: pending) | No |
| `promote TICKET_ID --dry-run` | Simulate request creation | No |
| `promote TICKET_ID --preview` | Preview execution, verify branch, record audit | No |
| `promote TICKET_ID --execute` | Fetch branch into prod_repo | **Yes** |

### What `--execute` Does

```bash
git -C <prod_repo> fetch <test_repo> <branch>:<branch>
```

This fetches the specified branch from `test_repo` into `prod_repo` as a local branch. It does **not**:
- Merge into any branch
- Push to any remote
- Delete branches
- Modify the working tree

The Creative Director must manually merge and push if desired.

## Safety Boundaries

| Boundary | Enforcement |
|----------|-------------|
| No auto-promotion | `execute_promotion()` is never called by `process_ticket()` |
| No silent writes | `--execute` flag is explicitly required |
| No auto-push | No `git push` is ever executed |
| No auto-merge | No `git merge` is ever executed |
| Precondition gated | Review + approval + QA + separation all verified |
| Single execution | Already-executed promotions cannot be re-executed |
| Audit trail | Every attempt (preview and execute) is recorded |
| Timeout | Git operations time out after 120s |

## Rollback / Failure Considerations

If a promotion fails:
- Promotion status is set to `failed`
- Audit record captures the failure reason
- The branch in prod_repo is NOT modified (failed fetch is atomic)
- Operator can investigate and retry after fixing the issue

If a promotion succeeds but the result is unwanted:
- The fetched branch can be deleted from prod_repo: `git -C <prod_repo> branch -D <branch>`
- No merge was performed, so no rollback of main is needed
- Create a new ticket if rework is needed

## Limitations

- Only fetches branches, does not merge or cherry-pick
- Does not verify that prod_repo is clean before fetching
- Does not handle conflicts (no merge = no conflicts)
- Does not push to remote — operator must push manually
- No multi-file promotion (always entire branch)
