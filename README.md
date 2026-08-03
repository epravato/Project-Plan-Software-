# H2M Project Plan Generator

Fills out H2M's project plan document (12 required sections) from source project
documents plus a company context layer. Project managers run it at kickoff, then
maintain the resulting Word file themselves.

## Data flow & compliance notes

- **External API calls (Anthropic path only).** When the AI provider is set to Claude
  (Anthropic), the text of uploaded documents and the company context layer is sent to
  Anthropic's API to be processed. The local **Ollama** provider option keeps everything
  on-machine instead, at the cost of speed/quality on long documents. Provider is
  operator-configured per deployment via the Settings gear icon.
- **All testing to date used fictional data.** Every extraction test run against this
  app has used a made-up RFP/proposal bundle (LRSBA/MKAE — both fictional names, no real
  entity). **No real H2M or client project documents have been sent to the Anthropic API
  during development.** A direct consequence: extraction accuracy against *real* H2M RFPs
  is not yet validated — see [Known limitations](#known-limitations).
- **Local-only by default.** The run command below binds uvicorn to `127.0.0.1`
  (no `--host` flag set), so the app is not reachable over the network as shipped. Do not
  expose this to the network or internet without prior IT sign-off.
- **No authentication layer.** The app assumes a single trusted local user (the PM
  running it on their own machine) — there's no login, no per-user access control. This
  is a single-user local tool, not a multi-tenant service.
- **Project data at rest is unencrypted** in the local `data/` folder (uploads, drafts,
  generated plans) — see [Project data](#project-data) below. The Anthropic API key is
  the one credential in this app, and it's kept out of that plaintext folder entirely —
  see [Settings & credentials](#settings--credentials).
- **Company context layer is read-only.** The app reads (never writes to) a shared
  company drive folder (`J:\...`) for standards/directory info used to fill in plans.

## Known limitations

- Accuracy has only been validated against the fictional LRSBA/MKAE test bundle, not
  real H2M documents — the single biggest open risk before a production pilot.
- An invalid/expired Anthropic API key currently produces a fully blank plan with no
  visible error in the UI (logged to stderr as of this fix, not yet surfaced to the UI).
- The clarify step's "don't repeat questions" logic dedupes by target section
  deterministically, but untargeted questions still rely on the model not repeating
  itself verbatim.

## Run it

```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

Then open http://localhost:8000.

## Where things live

```
src/
├── api/main.py          FastAPI app — project CRUD, upload, generate, download
├── api/index.html       Full UI (home screen + 3-step wizard), no framework
├── ingestion/           Markitdown wrapper: PDF/Word/Excel/PPT -> markdown
├── context/loader.py    Reads the H2M Standards context folder
├── output/builder.py    Builds the Word document from scratch (python-docx)
└── ai/                  AI extraction — Anthropic (Claude) and local Ollama backends

context/     H2M Standards files (company.md, employees.md) — read-only
templates/   H2M's original template — REFERENCE ONLY, no longer used to build
tests/       Smoke test
build/       Generated sample documents (gitignored)
data/        Live project data (gitignored) — see below
```

## Project data

Each project plan gets its own folder, created through the app's home screen:

```
data/projects/<project-number-and-name>/
├── meta.json      number, name, client, created/updated timestamps
├── draft.json     every field in the plan; autosaved as you type
├── uploads/       source documents as uploaded
└── output/        generated Project Plan.docx
```

`data/` is gitignored on purpose — project plans contain client information that
must stay inside H2M's compliance boundary and must not reach GitHub. That also
means **it is not recoverable from git**, so deleting a project through the app
moves it to `data/_trash/<project>-<timestamp>/` rather than removing it.

Back up `data/` separately if a project matters.

## Settings & credentials

Configured via the gear icon in the app (AI provider, context folders, Anthropic API
key). Non-secret settings live in `data/settings.json`. The Anthropic API key itself is
never written there — it's stored in the OS credential store (Windows Credential
Manager) via the `keyring` package, encrypted at rest and scoped to the Windows user
account running the app.
