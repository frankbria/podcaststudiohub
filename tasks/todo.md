# Issue #218 — Team authz: email-bound invitations + RLS backstop docs

**Title:** [P4.4] fix(api): invitation acceptance not bound to invited email; team tables lack RLS backstop
**Plan source:** self-authored (issue body had acceptance criteria, no step plan)

## Findings (codebase audit)
- `team_service.accept_invitation` (team_service.py:201) creates a `TeamMember` with `invitation.role` and **never checks** the accepting user's email against `invitation.email`. A forwarded/leaked token = anyone joins.
- Every existing team route operating on a team **already** calls `rbac_service.assert_permission` — the mandatory helper already exists. Gap is regression-test coverage, not missing code.
- Team tables (`teams`, `team_members`, `team_invitations`) have **no `tenant_id`** column → per-tenant RLS is inherently inapplicable; isolation relies on RBAC. Needs to be documented as intentional.
- Invitation `role` schema currently allows `owner`; a forwardable owner-invite token is an escalation vector.

## Steps
1. **AC1 — Email-bind acceptance.** `accept_invitation(db, token, user_id, user_email)`: reject with **403** when `invitation.email.lower() != user_email.lower()`. Router passes `current_user.email`.
2. **AC2 — Restrict invitation roles.** `InvitationCreate.role` pattern → `^(editor|viewer|analyst)$` (drop `owner`). Native Pydantic 422. Co-owner promotion stays on `update_member_role` (owner-only, non-forwardable).
3. **AC3 — Membership guard + regression tests.** Helper already present on every route; add non-member→403 regression tests for the mutating/read routes. No redundant helper added (would be dead abstraction).
4. **AC4 — Document RLS exclusion.** Security note in `team_service.py` module docstring + pointer comment in migration 009 explaining team tables are intentionally not RLS-scoped (no tenant_id; RBAC-enforced).
5. **Tests (TDD):** wrong-email→403, case-insensitive match→201, owner-role invite→422, non-member→403 across routes.

## Acceptance criteria
- [x] Email match required before membership; reject otherwise. (Implemented as
      **exact** match, not case-folded — account emails are case-sensitive, so
      case-insensitive matching would let a case-variant account accept a leaked
      token. Follow-up issue: app-wide email canonicalization.)
- [x] Invitation roles restricted (owner not grantable via invitation; enforced
      at creation **and** acceptance for legacy tokens).
- [x] Membership/permission helper on every team route + regression tests
      (non-member → 403 across all routes; helper already present per-route).
- [x] Team tables documented as intentionally not RLS-scoped.
