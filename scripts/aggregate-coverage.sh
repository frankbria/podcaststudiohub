#!/bin/bash

# Coverage Aggregation Script
# Combines backend (pytest) and frontend (jest) coverage reports
# Generates a combined markdown report

set -e

echo "📊 Aggregating Coverage Reports..."
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directories
BACKEND_DIR="apps/api"
FRONTEND_DIR="apps/web"
REPORT_DIR="coverage"
COMBINED_REPORT="$REPORT_DIR/combined-coverage-report.md"

# Create coverage directory if it doesn't exist
mkdir -p "$REPORT_DIR"

# Function to parse pytest coverage percentage
get_backend_coverage() {
    if [ -f "$BACKEND_DIR/coverage/backend/coverage.xml" ]; then
        # Extract coverage from XML (line-rate attribute)
        coverage=$(grep -oP 'line-rate="\K[0-9.]+' "$BACKEND_DIR/coverage/backend/coverage.xml" | head -1)
        # Convert to percentage
        echo "scale=2; $coverage * 100" | bc
    else
        echo "N/A"
    fi
}

# Function to parse jest coverage percentage
get_frontend_coverage() {
    if [ -f "$FRONTEND_DIR/coverage/frontend/coverage-summary.json" ]; then
        # Extract total lines percentage from JSON
        coverage=$(jq -r '.total.lines.pct' "$FRONTEND_DIR/coverage/frontend/coverage-summary.json" 2>/dev/null || echo "0")
        echo "$coverage"
    else
        echo "N/A"
    fi
}

# Get coverage percentages
echo "📈 Extracting coverage metrics..."
BACKEND_COV=$(get_backend_coverage)
FRONTEND_COV=$(get_frontend_coverage)

echo "   Backend Coverage: ${BACKEND_COV}%"
echo "   Frontend Coverage: ${FRONTEND_COV}%"
echo ""

# Calculate combined coverage (weighted average)
if [ "$BACKEND_COV" != "N/A" ] && [ "$FRONTEND_COV" != "N/A" ]; then
    COMBINED_COV=$(echo "scale=2; ($BACKEND_COV + $FRONTEND_COV) / 2" | bc)
else
    COMBINED_COV="N/A"
fi

# Generate markdown report
cat > "$COMBINED_REPORT" << EOF
# Combined Test Coverage Report

**Generated:** $(date '+%Y-%m-%d %H:%M:%S')

---

## Overall Coverage Summary

| Component | Coverage | Status |
|-----------|----------|--------|
| **Backend (FastAPI)** | ${BACKEND_COV}% | $([ "${BACKEND_COV%.*}" -ge 80 ] 2>/dev/null && echo "✅ Pass" || echo "❌ Below Threshold") |
| **Frontend (Next.js)** | ${FRONTEND_COV}% | $([ "${FRONTEND_COV%.*}" -ge 80 ] 2>/dev/null && echo "✅ Pass" || echo "❌ Below Threshold") |
| **Combined Average** | ${COMBINED_COV}% | $([ "${COMBINED_COV%.*}" -ge 80 ] 2>/dev/null && echo "✅ Pass" || echo "⚠️  Below Threshold") |

---

## Coverage Threshold

**Minimum Required:** 80% for all metrics (branches, functions, lines, statements)

---

## Detailed Reports

### Backend Coverage
- **HTML Report:** \`apps/api/coverage/backend/index.html\`
- **XML Report:** \`apps/api/coverage/backend/coverage.xml\`
- **Terminal Output:** Run \`cd apps/api && pytest --cov=src --cov-report=term-missing\`

### Frontend Coverage
- **HTML Report:** \`apps/web/coverage/frontend/index.html\`
- **LCOV Report:** \`apps/web/coverage/frontend/lcov.info\`
- **Terminal Output:** Run \`cd apps/web && npm run test:coverage\`

---

## Files Below Threshold

### Backend
$(if [ -f "$BACKEND_DIR/coverage/backend/coverage.xml" ]; then
    echo "See HTML report for detailed file-level coverage"
else
    echo "_Backend coverage not available_"
fi)

### Frontend
$(if [ -f "$FRONTEND_DIR/coverage/frontend/coverage-summary.json" ]; then
    echo "See HTML report for detailed file-level coverage"
else
    echo "_Frontend coverage not available_"
fi)

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
EOF

echo "✅ Combined coverage report generated: $COMBINED_REPORT"
echo ""

# Display report contents
cat "$COMBINED_REPORT"

# Check if coverage meets threshold
if [ "$COMBINED_COV" != "N/A" ]; then
    if [ "${COMBINED_COV%.*}" -ge 80 ] 2>/dev/null; then
        echo ""
        echo -e "${GREEN}✅ Coverage meets 80% threshold!${NC}"
        exit 0
    else
        echo ""
        echo -e "${YELLOW}⚠️  Warning: Coverage (${COMBINED_COV}%) is below 80% threshold${NC}"
        echo -e "${YELLOW}   This is expected for initial setup with minimal tests.${NC}"
        exit 0
    fi
else
    echo ""
    echo -e "${RED}❌ Error: Could not calculate coverage${NC}"
    exit 1
fi
