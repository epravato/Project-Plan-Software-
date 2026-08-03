# H2M Project Plan Generator

Fills out H2M's project plan document (12 required sections) from source project
documents plus a company context layer. Project managers run it at kickoff, then
maintain the resulting Word file themselves.

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
└── ai/                  Phase 2 — extraction not yet wired in

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
