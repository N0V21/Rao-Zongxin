#!/usr/bin/env bash
# Refresh the NTULearn snapshot, or report that an interactive login is needed.
#
# Never prompts for a password: if the saved session is dead it tells the caller to
# run the login flow, which requires a human to complete NTU's MFA.
#
# Usage:  ./refresh.sh
#
# Harvester location, in order of precedence:
#   1. $NTULEARN_HOME
#   2. <workspace>/ntulearn          (the documented default)
#   3. <this repo>/harvester         (when running from a clone)

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_harvester() {
  if [[ -n "${NTULEARN_HOME:-}" ]]; then
    printf '%s\n' "$NTULEARN_HOME"
    return
  fi
  # scripts -> ntulearn -> skills -> workspace root
  local workspace_root
  workspace_root="$(cd "$here/../../.." 2>/dev/null && pwd)"
  if [[ -n "$workspace_root" && -d "$workspace_root/ntulearn" ]]; then
    printf '%s\n' "$workspace_root/ntulearn"
    return
  fi
  # Running from inside the repo itself.
  if [[ -d "$here/../../../harvester" ]]; then
    printf '%s\n' "$(cd "$here/../../../harvester" && pwd)"
    return
  fi
}

TOOL_DIR="$(find_harvester)"

if [[ -z "$TOOL_DIR" || ! -d "$TOOL_DIR" ]]; then
  cat >&2 <<'EOF'
ERROR: could not locate the NTULearn harvester.

Set NTULEARN_HOME to the directory containing src/harvest.mjs, e.g.

    export NTULEARN_HOME="$HOME/ntulearn"

or install the harvester as <workspace>/ntulearn. See harvester/README.md.
EOF
  exit 1
fi

cd "$TOOL_DIR" || exit 1
echo "== harvester: $TOOL_DIR =="

if [[ ! -f src/status.mjs ]]; then
  echo "ERROR: $TOOL_DIR does not look like the harvester (src/status.mjs missing)." >&2
  exit 1
fi

echo
echo "== session check =="
if ! node src/status.mjs; then
  cat >&2 <<'EOF'

The saved NTULearn session is missing or expired, so the snapshot cannot be
refreshed automatically.

Ask the user to run this in their terminal — it opens a real browser window and
needs them to complete NTU's Microsoft sign-in and MFA:

    cd <harvester> && npm run login

Then re-run this script.
EOF
  exit 2
fi

echo
echo "== harvest =="
node src/harvest.mjs
