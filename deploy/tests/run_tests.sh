#!/usr/bin/env bash
# Run unit + integration tests inside the Docker container and save reports.
# Usage (from repo root):
#   bash deploy/tests/run_tests.sh
# Reports land in deploy/tests/reports/
set -euo pipefail

COMPOSE="docker compose -f deploy/docker_compose.yml"
REPORTS="/zango/tests/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

sg docker -c "$COMPOSE exec -T app bash -s" <<CONTAINERSCRIPT
set -euo pipefail
mkdir -p $REPORTS

echo "========================================"
echo " UNIT TESTS"
echo "========================================"
cd /zango/tests
python -m pytest unit/ \
  -v --tb=short \
  --html=$REPORTS/unit-${TIMESTAMP}.html --self-contained-html \
  --junitxml=$REPORTS/unit-${TIMESTAMP}.xml \
  2>&1 | tee $REPORTS/unit-${TIMESTAMP}.log
UNIT_EXIT=\${PIPESTATUS[0]}

echo ""
echo "========================================"
echo " INTEGRATION TESTS"
echo "========================================"
python -m pytest integration/ \
  -v --tb=short \
  --html=$REPORTS/integration-${TIMESTAMP}.html --self-contained-html \
  --junitxml=$REPORTS/integration-${TIMESTAMP}.xml \
  2>&1 | tee $REPORTS/integration-${TIMESTAMP}.log
INT_EXIT=\${PIPESTATUS[0]}

echo ""
echo "========================================"
echo " SUMMARY"
echo "========================================"
echo "Unit:        exit \$UNIT_EXIT"
echo "Integration: exit \$INT_EXIT"
echo "Reports:     deploy/tests/reports/"
ls -1 $REPORTS/

[ \$UNIT_EXIT -eq 0 ] && [ \$INT_EXIT -eq 0 ]
CONTAINERSCRIPT
