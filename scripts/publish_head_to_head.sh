#!/usr/bin/env bash
# Publish a head-to-head comparison doc for a specific AgentArmor version
# (SPEC v4 D54, D57, RUNBOOK #5).
#
# Does NOT push. Operator pushes manually after inspecting the diff.
#
# Usage:
#   scripts/publish_head_to_head.sh v1.5 [path/to/summary.json]
#
# If the summary path is omitted, the most recent run under
# benchmarks/results/runs/ is used.

set -euo pipefail

VERSION="${1:?Usage: publish_head_to_head.sh vX.Y [path/to/summary.json]}"
SUMMARY_ARG="${2:-}"

# 1. Require a clean git working tree so we can attribute all changes to
# this script.
if [[ -n "$(git status --porcelain)" ]]; then
    echo "error: uncommitted changes; commit or stash before publishing" >&2
    exit 1
fi

# 2. Resolve which summary to publish.
if [[ -n "$SUMMARY_ARG" ]]; then
    SUMMARY="$SUMMARY_ARG"
else
    SUMMARY=$(find benchmarks/results/runs -name head_to_head_summary.json \
        -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | awk '{print $2}')
fi

if [[ -z "$SUMMARY" || ! -f "$SUMMARY" ]]; then
    echo "error: summary JSON not found. Run --resume or pass a path." >&2
    exit 2
fi
echo "[publish] summary: $SUMMARY"

# 3. Regenerate the doc deterministically.
.venv-drift/bin/python -m benchmarks.generate_head_to_head_doc \
    --summary "$SUMMARY" \
    --output BENCHMARKS_HEAD_TO_HEAD.md

# 4. Append an entry to the Historical versions section.
RUN_DATE=$(.venv-drift/bin/python -c "
import json, sys
print(json.load(open('$SUMMARY'))['run_date'])
")

# Historical-versions insertion is handled by sed: add a markdown bullet
# under the matching section heading. Idempotent: only adds if the tag
# isn't already present in the file.
if ! grep -q "\[$VERSION\]" BENCHMARKS_HEAD_TO_HEAD.md; then
    MARKER="### Historical versions"
    ENTRY="- [$VERSION] run $RUN_DATE — see \`git tag $VERSION\`"
    awk -v marker="$MARKER" -v entry="$ENTRY" '
        { print }
        $0 == marker {
            # Pass through the title + the "Each published..." paragraph +
            # the bullet block; we append a new bullet at first blank line
            # that occurs after the marker.
            inserted = 0
        }
        $0 == "" && ! inserted && prev_marker {
            print entry
            inserted = 1
        }
        { prev_marker = ($0 == marker) || prev_marker }
    ' BENCHMARKS_HEAD_TO_HEAD.md > BENCHMARKS_HEAD_TO_HEAD.md.tmp
    mv BENCHMARKS_HEAD_TO_HEAD.md.tmp BENCHMARKS_HEAD_TO_HEAD.md
fi

# 5. Show the diff so the operator can review.
echo "[publish] diff preview:"
git --no-pager diff BENCHMARKS_HEAD_TO_HEAD.md | head -80 || true

# 6. Confirm.
read -r -p "Create commit + tag $VERSION? [y/N] " yn
if [[ "${yn,,}" != "y" ]]; then
    echo "[publish] aborted; leaving doc changes staged-in-working-tree."
    exit 1
fi

# 7. Commit + tag locally. Does NOT push.
git add BENCHMARKS_HEAD_TO_HEAD.md
git commit -m "docs: publish head-to-head report $VERSION"
git tag -a "$VERSION" -m "Head-to-head comparison report $VERSION"

echo "[publish] done. Push with: git push origin main $VERSION"
