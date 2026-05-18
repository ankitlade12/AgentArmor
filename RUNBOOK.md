# Head-to-head Benchmark — Runbook

Hand-authored operational procedures for `benchmarks/run_head_to_head.py`
and `BENCHMARKS_HEAD_TO_HEAD.md`. Numbered for quick reference during
incidents. Not generated — edit directly.

Scope: this doc covers **operations**. Methodology decisions live in
[`tasks/head-to-head-report/SPEC.md`](tasks/head-to-head-report/SPEC.md) (v4).

---

## Procedure 0 — First-time setup (D54)

Required before the first real run. One-time per machine.

1. **Install Python deps** (venv already exists):
   ```bash
   uv pip install --python .venv-drift/bin/python -e .
   ```

2. **Install `llama-cpp-python`** for local LlamaGuard (D36):
   ```bash
   # CPU-only build; with BLAS if available:
   CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" \
     uv pip install --python .venv-drift/bin/python llama-cpp-python
   ```
   On success `.venv-drift/bin/python -c "import llama_cpp; print(llama_cpp.__version__)"` prints a version.

3. **Download the Q4_K_M GGUF** (~5 GB):
   ```bash
   huggingface-cli download QuantFactory/Llama-Guard-3-8B-GGUF \
     Llama-Guard-3-8B.Q4_K_M.gguf --local-dir ./models/
   ```
   Update `benchmarks/config.yaml` `baselines.llamaguard.local_model_path` if
   your layout differs.

4. **Provision API keys** (env vars only — never commit to `config.yaml`
   per D51):
   ```bash
   # .envrc or shell profile
   export OPENAI_API_KEY=sk-...
   export PERSPECTIVE_API_KEY=AIz...
   ```

5. **Dry-run preflight** — no API spend, confirms everything wires up:
   ```bash
   .venv-drift/bin/python -m benchmarks.run_head_to_head --dry-run
   ```
   Expect `Projected spend: $0.00 (per SPEC v4 D40)`.

6. **V-gate smoke** (see `tasks/head-to-head-report/TYPE_WALKTHROUGH.md`):
   verify logprobs shape + token format from LlamaGuard before trusting
   score numbers. If logprobs unavailable, score falls back to 0.0/1.0
   (PR curve for LlamaGuard will be skipped).

Expected full-run time: roughly 1-2 hours for 6 datasets × ~200 samples
across 3 baselines on the Ryzen 9 8945HS CPU. LlamaGuard dominates; APIs
are fast.

---

## Procedure 1 — Key / quota error during a run

Symptom: `run.jsonl` shows `phase=error` events concentrated on one
baseline; CLI logs `Missing required environment variables:` or 401/429.

Response:
1. Check env vars: `printenv OPENAI_API_KEY PERSPECTIVE_API_KEY`.
2. If expired → rotate, restart with `--resume --run-dir <same>` (D15).
3. If quota hit → wait out the window, then `--resume`.
4. Completed cells stay; only the failing cell redoes. No spend lost.
5. If a baseline is permanently unavailable (account closed, key
   revoked) → the cell will be blank in the final doc per D35. Do NOT
   paper over with a prior-run number.

---

## Procedure 2 — llama-cpp-python failure / model file missing

Symptom: `LlamaGuardBaseline.is_available()` returns False, or
`llama_cpp.Llama(...)` raises on startup.

Response:
1. Check `ls ./models/Llama-Guard-3-8B-Q4_K_M.gguf`. Re-pull with
   `huggingface-cli` if missing.
2. Verify `llama-cpp-python` import: `.venv-drift/bin/python -c "import llama_cpp"`.
3. Inspect recent events: `python scripts/analyze_run_log.py <run-dir>
   --errors-only --cell llamaguard/<dataset>`.
4. If logprobs return `None`/unexpected shape, the baseline auto-falls
   back to text-parse 0/1 (D36). Accept this for the current run and
   fix in a follow-up commit; do not manually splice scores.

---

## Procedure 3 — Bootstrap divergence from published tolerance

Symptom: Re-run F1 for one cell is outside the published CI by more
than `max(bootstrap_CI, empirical_spread)` tolerance (D16/D39).

Response:
1. Run the vendor canary (Procedure 7) first. If canary flags drift →
   cause is upstream, not us.
2. If canary is clean → local compute drift. Check NumPy/Python
   versions against `pyproject.toml` pins (D45).
3. If neither matches → re-run the calibration procedure (5 same-day
   runs + 1 one-week-later) and re-publish the tolerance numbers.
4. Never silently update the published F1 — run a fresh publish cycle.

---

## Procedure 4 — `--resume` after crash

Symptom: Runner died mid-cell (OOM, signal, power). Need to restart
without re-spending on completed cells.

Response:
```bash
.venv-drift/bin/python -m benchmarks.run_head_to_head \
  --run-dir <same run dir> \
  --resume
```

Checks performed automatically:
- Completed cells (sidecar `completed=true`) → skip, reload verdicts.
- Partial cells → resume from `samples_done` offset.
- Adapter source hash changed → hard error ("revert adapter or delete
  sidecars"). This prevents a half-run-old-adapter, half-run-new-adapter
  blend from producing invalid numbers.
- `config.yaml` hash for a baseline changed → same hard error.

If you genuinely intend a fresh run with a different adapter or config
→ delete `benchmarks/results/runs/<ts>/sidecars/` before `--resume`.

---

## Procedure 5 — Publishing a new version

Prerequisites:
- Calibration completed: 5 same-day runs + 1 one-week-later (D39).
- Vendor canary passed (Procedure 7).
- All tests green: `.venv-drift/bin/python -m pytest tests/`.

```bash
scripts/publish_head_to_head.sh v1.5
```

What it does:
1. Validates clean git state.
2. Regenerates `BENCHMARKS_HEAD_TO_HEAD.md` from the published summary JSON.
3. Appends an entry to the Historical Versions section.
4. Shows the diff + prompts for confirmation.
5. Creates a local commit + annotated tag.

The script does not push. Push manually after review.

---

## Procedure 6 — Rollback after bad publish

Symptom: Published numbers are wrong (missed a bug, vendor drift
slipped past canary, calibration was invalid).

Response:
1. `git revert <publish-commit>` — creates a new commit restoring the
   prior doc state. Preserves history.
2. Regenerate from the previous run's summary JSON if needed:
   ```bash
   python -m benchmarks.generate_head_to_head_doc \
     --summary benchmarks/results/runs/<prior-ts>/head_to_head_summary.json \
     --output BENCHMARKS_HEAD_TO_HEAD.md
   ```
3. Commit + push.
4. If external links cite the bad version by tag, they remain pinned —
   no silent rewrite. Post-mortem in the release notes of the revert
   commit. The doc footer instructs external-link authors to pin by tag.

---

## Procedure 7 — Vendor-side canary failure (D46)

Symptom: `benchmarks/canary_check.py` raises `CanaryAbort`:
`Vendor drift detected: <baseline> sample <id> scored X, reference Y,
delta Z, tolerance T`.

Response:
1. Identify which baseline drifted. One baseline alone → vendor-side
   model update; multiple → our code changed something.
2. For one-baseline vendor drift:
   - Confirm with a spot-check (rescore a few canary samples manually).
   - If confirmed, **do not publish**. Document the drift in the
     release notes and delay publication.
   - Re-baseline the canary after 2-3 days (vendor may roll back):
     regenerate reference scores from a fresh run, update
     `benchmarks/fixtures/vendor_canary.jsonl`, commit with a
     description of what changed.
3. For multi-baseline "drift": suspect our side. Compare `git diff`
   against the last good tag; look for `benchmarks/baselines/*.py`,
   `config.yaml`, or NumPy/Python changes.

---

## Appendix — Pricing reference (manual, D23)

As of 2026-04-18:
- **LlamaGuard**: local CPU inference. $0.
- **OpenAI Moderation API**: free (no token billing).
- **Perspective API**: free within quota (1 QPS → 60/min → 3600/hour).

Flagged stale after 3 months — re-verify before publishing. SPEC v4 D40
dropped `--max-usd` from v1; re-add when the first paid baseline joins.

---

## Change log

- **2026-04-18** — Initial version, SPEC v4 procedures 0–7.
