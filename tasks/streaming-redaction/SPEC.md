# SPEC: streaming-response redaction holdback

Resolves #85. Spec-first per CONTRIBUTING; mirrors the `tasks/head-to-head-report` precedent.

## Problem (corrected from the audit)

The audit claimed streaming redaction scans each chunk in isolation with no
carry-over. **That is wrong.** `_handle_stream_sync` / `_handle_stream_async`
accumulate the full text and re-scan all of it every chunk
(`execute_on_stream_chunk(accumulated_text)`), and the per-stream state lives in
the generator **closure** — so there is no stateless-hook or concurrency
problem, and no architecture change is needed.

The real bug is **premature emission**. Each chunk emits
`new_safe_text[len(current_safe_text):]` — the newly-safe-looking suffix —
*immediately*. A secret whose pattern only completes in a later chunk has its
prefix already streamed to the caller and cannot be recalled:

```
chunk 1 delta "...user"        -> "user" not yet an email -> EMITTED
chunk 2 delta "@example.com"   -> now redactable, but "user@" already sent  -> LEAK
```

## Guarantees (what this change delivers)

- A redactable pattern up to `HOLDBACK` characters long that straddles chunk
  boundaries is redacted **before** any of it is emitted.
- The caller-visible concatenation of streamed deltas equals the redaction of
  the full response text (for patterns within the holdback window).
- Behavior is per-stream and unaffected by concurrent streams (state is closure-local).
- Non-streaming redaction, `after_response`, and early-close (`GeneratorExit`)
  semantics are unchanged.

## Non-guarantees (stated honestly; redaction stays defense-in-depth)

- Patterns **longer than `HOLDBACK`** (e.g. unbounded `generic_secrets \S+`,
  long JWT/base64) split pathologically across the boundary may still leak.
- Redaction remains regex-based and **output-only** — it never prevents prompt
  egress (see #84). This is hardening, not a security boundary.
- Streaming gains a bounded latency cost: up to `HOLDBACK` chars are held back
  until more text arrives or the stream ends.

## Design

- `HOLDBACK = 48` chars — covers email/SSN/phone/credit-card/most key formats;
  balances leak-coverage vs. streaming latency.
- During the stream: only commit `accumulated_text[:-HOLDBACK]` (redacted); hold
  the trailing window. Emit only the *new committed* delta, guarded by
  `redacted.startswith(current_safe_text)` so we never emit a non-prefix splice.
- At stream end (after the loop, NOT in `finally` — generators can't yield while
  closing): scan the full accumulated text and flush the remaining redacted tail
  on a final yield of the last chunk.
- `after_response` stays in `finally` (unchanged on early close).
- Logic factored into `_streaming_safe_delta(accumulated, current_safe, final)`
  so sync and async share one implementation.

## Test plan

1. A secret (email) split across two deltas: caller-visible output is redacted, raw secret absent.
2. Clean text streams through unchanged (flushed correctly at end).
3. Long clean stream (> HOLDBACK) releases incrementally, not only at the end.
4. Full suite: no regression to existing streaming tests / `after_response`.
