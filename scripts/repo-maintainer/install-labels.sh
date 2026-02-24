#!/usr/bin/env bash
# install-labels.sh — Creates all required GitHub labels for the repo maintainer.
# Safe to run multiple times (uses --force to update existing labels).
set -euo pipefail

echo "Creating repo-maintainer labels..."

# Priority labels
gh label create "priority-p0" --color "B60205" --description "Critical priority" --force
gh label create "priority-p1" --color "D93F0B" --description "High priority" --force
gh label create "priority-p2" --color "FBCA04" --description "Medium priority" --force
gh label create "priority-p3" --color "0E8A16" --description "Low priority" --force

# Phase labels
gh label create "phase-1" --color "1D76DB" --description "Phase 1: Core Pipeline" --force
gh label create "phase-2" --color "1D76DB" --description "Phase 2: API Completeness" --force
gh label create "phase-3" --color "1D76DB" --description "Phase 3: Reliability & Security" --force
gh label create "phase-4" --color "1D76DB" --description "Phase 4: Platform Features" --force
gh label create "phase-5" --color "1D76DB" --description "Phase 5: UI/UX Polish" --force

# Governance tier labels
gh label create "maintainer-autonomous" --color "0E8A16" --description "T0: Fully autonomous implementation" --force
gh label create "maintainer-notify" --color "FBCA04" --description "T1: Implement and notify human" --force
gh label create "maintainer-approve" --color "D93F0B" --description "T2: Draft PR, human must approve" --force
gh label create "maintainer-human-only" --color "B60205" --description "T3: Human only, no auto-implementation" --force
gh label create "maintainer-skip" --color "EEEEEE" --description "Skip this issue in maintainer loop" --force

# Status labels
gh label create "plan-ready" --color "C2E0C6" --description "Implementation plan exists, ready for auto-implementation" --force
gh label create "needs-info" --color "D4C5F9" --description "Needs more information before implementation" --force
gh label create "needs-discussion" --color "D4C5F9" --description "Requires human discussion" --force

# Classification labels
gh label create "breaking-change" --color "B60205" --description "Contains breaking API changes" --force
gh label create "security" --color "B60205" --description "Security-related change" --force
gh label create "architecture" --color "D93F0B" --description "Architectural change" --force

echo "All labels created successfully."
