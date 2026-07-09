# #304 — RLS defense-in-depth: hardcoded DB password, USING(true) users SELECT, WITH CHECK(true) inserts, billing/analytics tables without RLS

**Plan source**: self-authored (issue has acceptance criteria but no plan comment).
**Branch**: `feature/issue-304-rls-defense-in-depth`. Migration head is `013` → new migration `014`.

## Findings that shape the design
- The 11 core tables have FORCE RLS + `tenant_isolation_{t}` (FOR ALL, USING + WITH CHECK tenant match) **plus** a redundant permissive `tenant_isolation_insert_{t}` `WITH CHECK (true)` (003:56-60). Policies OR together, so the permissive one nullifies the FOR ALL WITH CHECK on INSERT.
- Registration (`auth_service.create_user`, auth_service.py:252-297) is the **only** pre-tenant INSERT; it generates `tenant_id = uuid4()` itself.
- Login/registration duplicate-check read users by email with no tenant context — this is what `users_auth_lookup USING (true)` (003:69-73) exists for. It also exposes every user row (password_hash, encrypted_api_keys) cross-tenant.
- billing_subscriptions / billing_usage / analytics_events (010/011) carry `tenant_id` but have **no RLS**. All access is request-scoped with tenant context armed, **except** the Stripe webhook (`billing.py:175-191` → `_handle_subscription_updated/deleted`, billing_service.py:256-294) which has no JWT → no tenant context and looks rows up by `stripe_customer_id`.
- Celery workers never touch these three tables and rely on an RLS-exempt role for episodes — out of scope here, unaffected.
- CI pre-creates `podcastfy_app` with its own password (test.yml:164-167), so 003's `CREATE ROLE IF NOT EXISTS` no-ops there. Local conftest defaults to `podcastfy_app:podcastfy_app_password`.

## Design decisions (autonomous — no architectural fork)
1. **Password**: 003 edited so fresh installs read the role password from env `APP_DB_PASSWORD` (fallback to old literal so local dev/CI keep working); new migration 014 does `ALTER ROLE podcastfy_app PASSWORD <env>` **only when `APP_DB_PASSWORD` is set** → rotation on real deploys, no-op in CI/local. Document rotation in deployment/README.md.
2. **DB name**: 003 GRANT CONNECT uses `format('... %I ...', current_database())` in a DO block instead of literal `podcastfy`.
3. **users SELECT**: 014 drops `users_auth_lookup`; adds `SECURITY DEFINER` functions `auth_lookup_user_by_email(text)` / `auth_lookup_user_by_id(uuid)` RETURNS SETOF users, `SET search_path = public, pg_temp`, owner = migration role (BYPASSRLS), REVOKE FROM PUBLIC + GRANT EXECUTE TO podcastfy_app. `auth_service.get_user_by_email` / `get_user_by_id` switch to `select(User).from_statement(text(...))`.
4. **INSERT policies**: 014 **drops** all 11 `tenant_isolation_insert_{t}` policies — the FOR ALL policy's `WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)` then governs INSERT, which is exactly the acceptance criterion's semantics. Registration fix: `create_user` calls `set_tenant_context(session, str(tenant_id))` before `session.add`.
5. **Billing/analytics RLS**: 014 adds ENABLE + FORCE RLS + `tenant_isolation_{t}` (FOR ALL, USING + WITH CHECK tenant match) to billing_subscriptions, billing_usage, analytics_events. Webhook bootstrap: definer function `billing_tenant_for_stripe_customer(text) RETURNS uuid`; webhook handlers resolve tenant, `set_tenant_context`, then reuse existing ORM code (mirrors the auth bootstrap pattern).

## Steps
- [x] Explore codebase (RLS session plumbing, billing/webhook/registration paths, CI role provisioning)
- [x] Branch `feature/issue-304-rls-defense-in-depth`
- [x] TDD RED: tests — cross-tenant SELECT on billing/analytics blocked under podcastfy_app; INSERT with mismatched tenant_id rejected on a core table; users SELECT without context returns nothing; auth definer lookup returns user; registration still works; webhook subscription update works with no pre-set tenant context
- [x] Migration 014 (policies, definer fns, conditional password rotation) + 003 edit (env password, current_database())
- [x] App changes: auth_service lookups via definer fns; create_user arms tenant context; billing webhook resolves tenant via definer fn + set_tenant_context
- [x] Update tests that assert "billing tables have no RLS" (test_usage_concurrency.py, test_episodes.py, test_analytics_aggregation.py) — spec change, not test-weakening
- [x] .env.example / docs/env_inventory.md / deployment/README.md: APP_DB_PASSWORD + rotation note
- [x] Full suite green under podcastfy_app (conftest already enforces), ruff clean
- [ ] Deslop scan → quality gate (opencode pre-PR review) → PR → post-PR review → demo (hard gate) → CI gate → docs sync → merge

## Acceptance criteria (from issue)
- [ ] Role password injected from a secret and rotated
- [ ] Blanket users SELECT replaced with narrow SECURITY DEFINER auth-lookup
- [ ] INSERT WITH CHECK scoped to `tenant_id = current_setting('app.tenant_id')` (achieved by dropping the redundant permissive policy; FOR ALL WITH CHECK governs)
- [ ] FORCE RLS + tenant_isolation policies on billing_subscriptions, billing_usage, analytics_events
- [ ] `current_database()` instead of literal db name
