# Issue #255 — Canonicalize emails app-wide (case-insensitive identity)

Follow-up to #218/#254. Make email case never identity-significant.

## Plan (adapted to apps/api)

### 1. Service layer — `src/services/auth_service.py`
- `create_user`: lowercase `email` before constructing `User` (single normalization point).
- `get_user_by_email`: match with `func.lower(User.email) == email.lower()`.
- `authenticate_user`: same case-insensitive lookup.

### 2. Invitation match — `src/services/team_service.py`
- `accept_invitation`: relax exact match to case-insensitive
  (`invitation.email.lower() != user_email.lower()`). Update the docstring
  that documented the #218 case-sensitive workaround.

### 3. Migration — `alembic/versions/012_canonicalize_user_emails.py` (down_revision `011`)
- Detect case-variant duplicate `lower(email)` groups; **abort with a clear
  error** if collisions exist (data loss is not auto-resolvable safely).
- `UPDATE users SET email = lower(email)` for mixed-case rows.
- Add functional unique index `uq_users_email_lower` on `lower(email)`.
- downgrade: drop the index.

### 4. Tests
- `tests/test_auth.py`: email stored lowercase at register; duplicate
  case-variant register rejected (400); login is case-insensitive.
- `tests/test_teams.py`: repurpose `test_accept_invitation_case_variant_account_rejected`
  — a case-variant registration is now the SAME canonical account, so accept
  SUCCEEDS; add a case-insensitive invite-accept positive test. Keep
  `test_accept_invitation_wrong_email_rejected` (genuinely different email → 403).

## Acceptance criteria
- [ ] Emails canonical (lowercase) at rest; case-variant accounts cannot be created.
- [ ] Login works case-insensitively for existing and new users.
- [ ] Invitation acceptance matches case-insensitively once identity is canonical.
