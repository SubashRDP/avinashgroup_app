#!/usr/bin/env bash
# Parallel transaction seeder — one bench process per doctype (~one CPU core
# each), throttled to MAX_PARALLEL concurrent workers.
#
#   bash loadtest/run_seed.sh <count-per-doctype> <mode> [site]
#
#   bash loadtest/run_seed.sh 1000 full        # logic-crushing seed (all hooks)
#   bash loadtest/run_seed.sh 1000000 fast     # volume-crushing seed (drafts)
#
# Logs land in loadtest/logs/<doctype>.log; a summary JSON is printed at the
# end of each log.

set -u

COUNT="${1:?usage: run_seed.sh <count> <full|fast> [site]}"
MODE="${2:?usage: run_seed.sh <count> <full|fast> [site]}"
SITE="${3:-avinas}"
MAX_PARALLEL="${MAX_PARALLEL:-8}"

BENCH_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"
mkdir -p "$LOG_DIR"

DOCTYPES=(
  "Sales Invoice"
  "Purchase Invoice"
  "Sales Order"
  "Purchase Order"
  "Quotation"
  "Supplier Quotation"
  "Material Request"
  "Delivery Note"
  "Purchase Receipt"
  "Stock Entry"
  "Journal Entry"
  "Payment Entry"
)

echo "Seeding ${COUNT} x ${#DOCTYPES[@]} doctypes on site '${SITE}' (mode=${MODE}, parallel=${MAX_PARALLEL})"

for dt in "${DOCTYPES[@]}"; do
  while (( $(jobs -rp | wc -l) >= MAX_PARALLEL )); do sleep 5; done
  slug="${dt// /_}"
  (
    cd "$BENCH_DIR" || exit 1
    bench --site "$SITE" execute avinashgroup_app.loadtest.seed.seed_one \
      --kwargs "{\"doctype\": \"$dt\", \"count\": $COUNT, \"mode\": \"$MODE\"}"
  ) >"$LOG_DIR/$slug.log" 2>&1 &
  echo "  started: $dt (pid $!) -> loadtest/logs/$slug.log"
done

wait
echo
echo "== all workers finished; summaries: =="
grep -h '"created"\|"failed"\|"doctype"' "$LOG_DIR"/*.log || true
