#!/usr/bin/env bash
# Smoke test against a running API (default http://localhost:8000).
# Usage:  bash scripts/smoke_test.sh  [BASE_URL]
set -euo pipefail

BASE="${1:-http://localhost:8000}"
echo "==> Testing $BASE"

echo "--- health"
curl -fsS "$BASE/health"; echo

echo "--- ready"
curl -fsS "$BASE/ready"; echo

echo "--- sync chat"
curl -fsS -X POST "$BASE/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{
        "messages": [{"role":"user","content":"Reply with the single word: OK"}],
        "model": "fast",
        "max_tokens": 16
      }'; echo

echo "--- work order summary (Field Nation use case)"
curl -fsS -X POST "$BASE/v1/usecases/work-order-summary" \
  -H "Content-Type: application/json" \
  -d '{
        "work_order_id": "WO-10231",
        "site": "Retail Store #482, Dallas TX",
        "skill": "POS / Network",
        "raw_notes": "Arrived 9am. Replaced faulty switch in IDF closet. Two registers were offline, both back up after swap. Tested all 6 lanes, all green. Customer manager signed off. Recommend UPS replacement next visit, battery is old."
      }'; echo

echo "--- async chat -> poll"
JOB=$(curl -fsS -X POST "$BASE/v1/chat/async" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hello"}],"model":"fast","max_tokens":16}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
echo "job_id=$JOB"
sleep 2
curl -fsS "$BASE/v1/jobs/$JOB"; echo

echo "--- usage counters"
curl -fsS "$BASE/v1/admin/usage?tenant=work-order-summary"; echo

echo "==> Smoke test complete."
