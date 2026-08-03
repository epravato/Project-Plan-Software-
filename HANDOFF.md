# Handoff — 2026-07-31

Session focus: token efficiency + wiring the company-drive context layer. Read this
top to bottom before touching `src/ai/extractor.py`.

---

## START HERE — the one thing to do first

**Change `EXTRACTION_EFFORT` from `"high"` to `"medium"` in `src/ai/extractor.py` (~line 85).**

It is currently `"high"` and that is a live regression I introduced. Evidence:

- Output tokens per run went 5x (a `fields/pass1` call went 533 → 2,332 output tokens)
- One call hit `output=4096`, which is exactly `max_tokens` — the response was truncated,
  failed `json.JSONDecodeError`, hit the `continue`, and returned **nothing**. Paid for, zero value.
- That truncation forced a second pass that would otherwise have been skipped.
- This is the same failure mode as the "blank project plan" bug in `Decisions.md`
  (thinking tokens eating the whole budget, leaving none for the answer).

`medium` was the original pass-1 setting and worked fine. The only reason effort is now a
fixed constant at all is cache stability (see below) — the *value* should be `medium`.

Consider also raising `max_tokens` on the fields call (currently 4096) as a belt-and-braces
guard against truncation.

---

## The main discovery of this session

**`output_config` (the JSON schema AND the `effort` value) is part of the prompt-cache key.**

Change either one and the cache misses completely, even when the cached content blocks are
byte-identical. This is not documented anywhere obvious. Verified with a 6-call probe:

| Change vs. baseline | cache_read |
|---|---|
| none (identical repeat) | 5,620 (hit) |
| schema only | 0 (miss) |
| effort only | 0 (miss) |

Consequence: an earlier optimization that narrowed the JSON schema to only the
still-missing fields was silently destroying the caching added minutes earlier. Measured
1% cache hit rate — caching was a **net cost increase** vs not caching at all.

### What was changed to fix it

In `src/ai/extractor.py`:
- `FIELDS_SCHEMA` / `NARRATIVE_SCHEMA` — fixed and complete, built once at import. Never
  narrowed per pass. The "only extract these, the rest are known" instruction now lives in
  a text block placed **after** the cache breakpoint, where varying text is free.
- `EXTRACTION_EFFORT` / `EXTRACTION_MAX_PASSES` — effort held constant across passes.
- `_leading_blocks()` — context + documents blocks, each a cache breakpoint, 1-hour TTL.
- `_pm_answers_block()` — PM clarify answers as their own block **after** the breakpoint.

In `src/api/main.py`:
- The `/clarify` endpoint no longer appends PM answers into `combined`. It passes the
  unmodified `base_combined` plus a separate `pm_answers` kwarg. **This is what makes
  clarify rounds cheap** — the documents block stays byte-identical across every round.

### Do not undo these

Anything that varies the schema, the effort, or the documents text between calls will
silently kill the cache again. If you add a new call type, give it its own fixed schema.

---

## Measured results (real run, 3 clarify rounds)

| | Before fix | After fix |
|---|---|---|
| Calls | 18 | 14 |
| Cache hit rate | ~1% | ~100% after first write |
| Cache reads | 4,740 tok | 297,964 tok |
| **Total** | **~$1.35** | **~$0.78** |
| Per clarify round | ~$0.35 | ~$0.16 |

Cost breakdown of the $0.78 run:

| | Tokens | Cost | Share |
|---|---|---|---|
| Output | 36,909 | $0.369 | 47% |
| Cache writes | 80,608 | $0.322 | 41% |
| Cache reads | 297,964 | $0.060 | 8% |
| Base input | 15,810 | $0.032 | 4% |

Input is solved. **Output is now the dominant cost**, and it is inflated ~4x by the
`effort: "high"` regression above.

Pricing used (Claude Sonnet 5, introductory rates through 2026-08-31): input $2/MTok,
output $10/MTok, 1h cache write $4/MTok, cache read $0.20/MTok. Rates rise to $3/$15
on 2026-09-01 — recompute after that.

### Per-call token logging

`_log_usage()` in `extractor.py` prints `input / cache_read / cache_write / output` to
stderr for every Anthropic call. **Keep this.** It is the only reason the caching bug was
caught — the code looked correct and the numbers said otherwise.

Reading it: the server log is flooded by status-poll `INFO` lines, so a small tail window
will show nothing. Search for `usage` with a large line count (thousands).

---

## Next piece of work: rebuild the clarify flow

This is designed but **not built**. It is the biggest remaining win and it is about
*time*, not money.

### The problem

Answering a clarify question re-runs the entire extraction pipeline — up to 5 API calls
and 2-3 minutes — to record facts the PM already typed. Observed across 3 rounds. Typing
"invoice day = 1st of the month" should not require re-reading 26K tokens of RFP.

### The design

1. **Tag each question with its target field key.** `suggest_gaps()` already knows which
   empty section prompted each question (it receives `empty_section_labels` and narrows
   correctly — 4 → 4 → 2 questions across rounds) and then throws that mapping away. Have
   it return the key alongside the question text.
2. **Factual answers write straight to the draft.** No API call. Instant.
3. **Ask all questions in one round** instead of drip-feeding 2-4 at a time across 3+ rounds.
4. **Run re-extraction once at the end**, not after every round.

### Important caveat — do not skip this

Do **not** simply delete re-extraction. Round 2's `narrative/pass2` produced 5,225 output
tokens, meaning it was generating real narrative content, not spinning. Some answers
(critical success factors, scope clarifications) genuinely feed prose synthesis in a way a
direct field-write cannot replace. Hence direct-fill for *factual* fields, one final
synthesis pass for narrative.

---

## Also wired up this session: company-drive context layer

Production Plan §5, previously unbuilt, now working.

- **Live source:** `J:\AIR AI Taskforce\EAP\Projects\Project plan software`
  (contains `company.md`, `employees.md`, `README.md`)
- This **replaced** the local repo `context/` folder as the source of truth. The local
  folder still exists but is no longer read.
- `src/context/loader.py` — `load_sources()` reads a list of `{label, path}` fresh on every
  extraction; unreachable paths are skipped silently, never block a plan. `is_reachable()`
  does an existence check for the Settings UI.
- `src/ai/settings.py` — `context_paths` in `DEFAULTS`, seeded with the J: path.
- Settings modal (gear icon) has a UI to add/remove context folders.

### RULES FOR THE J: DRIVE — non-negotiable

- Work **only** inside `J:\AIR AI Taskforce\EAP\Projects\Project plan software`. Not the
  parent tree, not sibling folders, nothing else on J:.
- **Never delete anything** on J:, confirmed or not. Shared company drive.
- Writes there need explicit per-action confirmation.

### Known gap

`GET /api/settings` returns a `reachable: true/false` flag per context path, but the
Settings UI **does not render it yet**. The user explicitly asked for a "not connected to
context folder" warning. Backend is done; the frontend row rendering in `index.html`
(`renderContextRows()`) needs to show it.

---

## Environment gotchas

- Dev server: `.claude/launch.json` → `project-plan-app`, port 8000. Start it through the
  preview tooling, not raw `uvicorn`.
- **`uvicorn --reload` restarts wipe in-memory `EXTRACTION_JOBS`.** Editing any source file
  mid-run kills the user's in-flight extraction. Do not edit while a run is in progress.
- An **orphaned server process** was serving stale code on port 8000 earlier in this
  session, which made a correct fix look broken. If behaviour does not match the code,
  stop and restart the preview server before debugging anything else.
- API key lives in plaintext at `data/settings.json`. Still needs rotating and moving to a
  secret store before production (long-standing item).

---

## Priority order for next session

1. `EXTRACTION_EFFORT` → `"medium"`; consider raising `max_tokens` on the fields call.
2. Re-run one extraction, read the `[usage]` lines, confirm output tokens dropped ~4x and
   no call hits the `max_tokens` ceiling.
3. Build the clarify redesign above.
4. Finish the Settings "not connected" warning.
5. **Still the biggest unvalidated risk in the whole project:** accuracy has only ever been
   tested against fictional documents (LRSBA/MKAE test bundle). Validating against real H2M
   RFPs matters more than any further optimization. See Production Plan §8.
