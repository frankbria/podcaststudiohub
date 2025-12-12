# Combined Test Coverage Report

**Generated:** 2025-11-11 17:35:33

---

## Overall Coverage Summary

| Component | Coverage | Status |
|-----------|----------|--------|
| **Backend (FastAPI)** | 52.8200% | ❌ Below Threshold |
| **Frontend (Next.js)** | 7.47% | ❌ Below Threshold |
| **Combined Average** | 30.14% | ⚠️  Below Threshold |

---

## Coverage Threshold

**Minimum Required:** 80% for all metrics (branches, functions, lines, statements)

---

## Detailed Reports

### Backend Coverage
- **HTML Report:** `apps/api/coverage/backend/index.html`
- **XML Report:** `apps/api/coverage/backend/coverage.xml`
- **Terminal Output:** Run `cd apps/api && pytest --cov=src --cov-report=term-missing`

### Frontend Coverage
- **HTML Report:** `apps/web/coverage/frontend/index.html`
- **LCOV Report:** `apps/web/coverage/frontend/lcov.info`
- **Terminal Output:** Run `cd apps/web && npm run test:coverage`

---

## Files Below Threshold

### Backend
See HTML report for detailed file-level coverage

### Frontend
See HTML report for detailed file-level coverage

---

## Next Steps for Improving Coverage

1. **Backend (FastAPI):**
   - Add tests for routers (auth, projects, episodes, content, generation)
   - Add tests for services (auth_service, podcast_service, storage_service)
   - Add tests for Celery tasks (podcast_generation, audio_composition, s3_upload)
   - Add tests for utilities (encryption, jwt, validators)

2. **Frontend (Next.js):**
   - Add tests for all UI components (currently only Button tested)
   - Add tests for providers (auth-provider)
   - Add tests for API client functions
   - Add tests for utility functions beyond utils.ts

3. **E2E Testing:**
   - Add comprehensive user flow tests
   - Test authentication flows
   - Test podcast creation workflows
   - Test error handling and edge cases

---

## CI/CD Integration

Coverage reports are automatically generated in CI/CD pipeline:
- Reports uploaded as GitHub Actions artifacts
- Coverage thresholds enforced (80% minimum)
- Build fails if coverage drops below threshold
- All tests must pass (100% pass rate required)

---

**Note:** This report combines backend and frontend coverage. For E2E test results, see Playwright HTML report.
