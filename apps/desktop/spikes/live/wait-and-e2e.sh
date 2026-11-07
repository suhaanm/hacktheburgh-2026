#!/usr/bin/env bash
# Waits until the shared electron lock is free (never takes it while QA holds it), then runs the one-shot e2e.
# QA has priority until ~14:15 (orchestrator rule): do not even try before then, unless QA has already come and gone.
end=$(( $(date +%s) + 1500 ))
while [ $(date +%s) -lt $end ]; do
  if [ ! -d /tmp/alongside-electron.lock ]; then
    (cd ../.. && npm run build >/dev/null 2>&1)
    node electron-e2e.mjs && exit 0
    rc=$?
    [ $rc -ne 75 ] && exit $rc
  fi
  sleep 3
done
echo "gave up waiting for the electron lock"; exit 75
