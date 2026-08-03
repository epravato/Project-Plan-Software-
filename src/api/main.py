import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import json
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse

from ai.extractor import (
    DIRECT_FILL_KEYS,
    LIST_SECTIONS,
    NARRATIVE_KEYS,
    SECTION_LABELS,
    extract_fields_from_markdown,
    extract_narrative_from_markdown,
    suggest_gaps,
)
from ai.settings import load_settings, save_settings
from context import loader as context_loader
from ingestion.converter import convert
from output.builder import build

app = FastAPI()

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data" / "projects"
TRASH_DIR = ROOT / "data" / "_trash"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_context_md() -> str:
    """Company-drive folders configured in Settings (default: the J: standards
    folder). Read fresh every call so standards/directory changes take effect without
    a restart; an unreachable network path is skipped, never blocks extraction."""
    settings = load_settings()
    return context_loader.load_sources(settings.get("context_paths") or [])

EXTRACTION_JOBS: dict[str, dict] = {}

BUILD_KEYS = (
    "team", "client_success", "h2m_success", "meetings", "drawings",
    "specifications", "cost_opinions", "reports", "milestones", "risks",
    "statement_of_purpose", "hazard_assessment",
    "scope_of_work", "scope_of_services", "qa_qc_plan",
    "wbs_link", "schedule_link", "bim_link", "fee_link",
    "invoice_frequency", "invoice_date",
    "progress_frequency", "progress_format", "progress_delivery",
)


# ---------- project storage ----------

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "project"


_PROJECT_ID_RE = re.compile(r"^[a-z0-9-]+$")


def project_dir(project_id: str) -> Path:
    # project_id reaches here straight from the URL — reject anything that isn't a
    # slugify()-shaped id before it ever touches the filesystem, so a value like ".."
    # or "..\\..\\somewhere" can't walk this out of DATA_DIR.
    if not _PROJECT_ID_RE.match(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    d = DATA_DIR / project_id
    if not d.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return d


def load_meta(project_id: str) -> dict:
    return json.loads((project_dir(project_id) / "meta.json").read_text(encoding="utf-8"))


def save_meta(project_id: str, meta: dict):
    (DATA_DIR / project_id / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_draft(project_id: str) -> dict:
    path = project_dir(project_id) / "draft.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_draft(project_id: str, draft: dict):
    (DATA_DIR / project_id / "draft.json").write_text(json.dumps(draft, indent=2), encoding="utf-8")


def touch(project_id: str):
    meta = load_meta(project_id)
    meta["updated"] = datetime.now(timezone.utc).isoformat()
    save_meta(project_id, meta)


# ---------- routes ----------

@app.get("/", response_class=HTMLResponse)
async def root():
    html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/settings")
async def get_settings():
    s = load_settings()
    context_paths = [
        {**p, "reachable": context_loader.is_reachable(p.get("path", ""))}
        for p in (s.get("context_paths") or [])
    ]
    return {
        "ai_provider": s.get("ai_provider", "ollama"),
        "has_anthropic_key": bool(s.get("anthropic_api_key")),
        "context_paths": context_paths,
    }


@app.put("/api/settings")
async def put_settings(request: Request):
    data = await request.json()
    s = load_settings()
    if data.get("ai_provider") in ("ollama", "anthropic"):
        s["ai_provider"] = data["ai_provider"]
    if data.get("anthropic_api_key"):
        s["anthropic_api_key"] = data["anthropic_api_key"]
    if isinstance(data.get("context_paths"), list):
        s["context_paths"] = [
            {"label": str(p.get("label", "")).strip(), "path": str(p.get("path", "")).strip()}
            for p in data["context_paths"]
            if isinstance(p, dict) and str(p.get("path", "")).strip()
        ]
    save_settings(s)
    return {
        "ai_provider": s.get("ai_provider", "ollama"),
        "has_anthropic_key": bool(s.get("anthropic_api_key")),
        "context_paths": s.get("context_paths", []),
    }


@app.get("/api/projects")
async def list_projects():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    projects = [load_meta(d.name) for d in DATA_DIR.iterdir() if d.is_dir() and (d / "meta.json").exists()]
    projects.sort(key=lambda p: p["updated"], reverse=True)
    return projects


@app.post("/api/projects")
async def create_project(request: Request):
    data = await request.json()
    number = (data.get("number") or "").strip()
    name = (data.get("name") or "").strip()
    client = (data.get("client") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    base_slug = slugify(f"{number}-{name}" if number else name)
    project_id = base_slug
    n = 2
    while (DATA_DIR / project_id).exists():
        project_id = f"{base_slug}-{n}"
        n += 1

    d = DATA_DIR / project_id
    (d / "uploads").mkdir(parents=True)
    (d / "output").mkdir()

    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "id": project_id, "number": number, "name": name, "client": client,
        "created": now, "updated": now,
    }
    save_meta(project_id, meta)
    save_draft(project_id, {})
    return meta


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    return {"meta": load_meta(project_id), "draft": load_draft(project_id)}


@app.put("/api/projects/{project_id}/draft")
async def put_draft(project_id: str, request: Request):
    project_dir(project_id)
    draft = await request.json()
    save_draft(project_id, draft)
    touch(project_id)
    return {"ok": True}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Move to data/_trash/ rather than deleting — project data is gitignored,
    so a hard delete is unrecoverable."""
    d = project_dir(project_id)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.move(str(d), str(TRASH_DIR / f"{project_id}-{stamp}"))
    return {"ok": True}


def _is_blank(value) -> bool:
    """True for values that look filled but carry no real content — e.g. the UI's
    placeholder table rows (`{"organization": "H2M"}` with every other cell empty).
    Without this, a placeholder row blocks extraction from ever populating that section."""
    if not value:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return all(_is_blank(v) for v in value)
    if isinstance(value, dict):
        # An org-only row is the table's prefilled default, not user-entered data.
        return all(_is_blank(v) for k, v in value.items() if k != "organization")
    return False


def convert_and_store(path: Path, name: str, markdowns: dict):
    try:
        markdowns[name] = convert(path)
    except Exception as e:
        markdowns[name] = f"[Could not convert: {e}]"


def _run_extraction_job(
    job_id: str, project_id: str, combined: str, file_names: list[str] | None = None,
    pm_answers: str = "", run_extraction: bool = True, suggest_more: bool = True,
):
    """`run_extraction=False` records answers without re-reading the documents — a clarify
    round whose answers were all direct-filled has nothing left for the model to derive.
    `suggest_more=False` skips the gap call on the final round, where new questions would
    only be discarded."""
    job = EXTRACTION_JOBS[job_id]

    def on_progress(stage: str, pct: int):
        job["stage"] = stage
        job["pct"] = pct

    try:
        draft = load_draft(project_id)
        context_md = _load_context_md()

        if run_extraction:
            existing_fields = {k: v for k, v in (draft.get("fields") or {}).items() if str(v).strip()}
            known_narrative = {key: draft.get(key) for key in NARRATIVE_KEYS if not _is_blank(draft.get(key))}

            on_progress("Extracting contact information…", 10)
            fields = extract_fields_from_markdown(
                combined, on_progress, known=existing_fields, context_md=context_md, pm_answers=pm_answers,
            )
            narrative = extract_narrative_from_markdown(
                combined, on_progress, known=known_narrative, context_md=context_md, pm_answers=pm_answers,
            )

            draft["fields"] = {**fields, **existing_fields}
            for key in LIST_SECTIONS:
                if _is_blank(draft.get(key)) and narrative.get(key):
                    draft[key] = narrative[key]
            for key, value in narrative.items():
                if key in LIST_SECTIONS:
                    continue
                if _is_blank(draft.get(key)) and value:
                    draft[key] = value

        if suggest_more:
            on_progress("Checking what else could help…", 90)
            empty_sections = [
                {"key": key, "label": label} for key, label in SECTION_LABELS.items()
                if _is_blank(draft.get(key))
            ]
            draft_fields = draft.get("fields") or {}
            if not draft_fields.get("Client Company") or not draft_fields.get("Project Contact"):
                empty_sections = [{"key": "", "label": "General Info (contact fields)"}] + empty_sections
            already_asked = draft.get("_asked_questions") or []
            draft["ai_suggestions"] = suggest_gaps(
                combined, empty_sections, already_asked, context_md=context_md, pm_answers=pm_answers,
            )
            draft["_asked_questions"] = already_asked + [
                q["question"] for q in draft["ai_suggestions"]["clarifying_questions"]
            ]

        save_draft(project_id, draft)
        touch(project_id)

        job["status"] = "done"
        job["stage"] = "Done"
        job["pct"] = 100
        job["draft"] = draft
        if file_names is not None:
            job["files"] = file_names
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


@app.post("/api/projects/{project_id}/upload")
async def upload(project_id: str, files: list[UploadFile] = File(...)):
    d = project_dir(project_id)
    uploads_dir = d / "uploads"

    markdowns = {}
    for f in files:
        dest = uploads_dir / f.filename
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)

        if dest.suffix.lower() == ".zip":
            extract_dir = uploads_dir / dest.stem
            with zipfile.ZipFile(dest) as zf:
                zf.extractall(extract_dir)
            for path in sorted(extract_dir.rglob("*")):
                if path.is_dir() or "__MACOSX" in path.parts or path.name == ".DS_Store":
                    continue
                convert_and_store(path, f"{dest.stem}/{path.relative_to(extract_dir).as_posix()}", markdowns)
        else:
            convert_and_store(dest, f.filename, markdowns)

    combined = "\n\n".join(f"### {name}\n{md}" for name, md in markdowns.items())
    (d / "_combined.md").write_text(combined, encoding="utf-8")

    job_id = uuid.uuid4().hex
    EXTRACTION_JOBS[job_id] = {"status": "running", "stage": "Converting documents…", "pct": 5}
    thread = threading.Thread(
        target=_run_extraction_job,
        args=(job_id, project_id, combined, list(markdowns.keys())),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/projects/{project_id}/upload/status/{job_id}")
async def upload_status(project_id: str, job_id: str):
    job = EXTRACTION_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/projects/{project_id}/clarify")
async def clarify(project_id: str, request: Request):
    """Records the project manager's answers to the clarifying questions.

    An answer tagged with a direct-fill target is written straight to the draft — typing
    "invoiced on the 1st" is the section's content, and re-reading 26K tokens of RFP to
    learn it back costs the PM minutes for nothing. Only answers that genuinely feed
    synthesis (narrative prose, table rows) start an extraction, so a round of purely
    factual answers now returns instantly instead of running the whole pipeline."""
    d = project_dir(project_id)
    body = await request.json()
    answers = [
        a for a in (body.get("answers") or [])
        if isinstance(a, dict) and (a.get("answer") or "").strip()
    ]
    ask_more = bool(body.get("ask_more"))

    draft = load_draft(project_id)
    # The questions being answered are consumed either way; `suggest_more` decides
    # whether a fresh set replaces them. Document suggestions outlive the round —
    # they're shown alongside Review & Edit, not answered here.
    prior_suggestions = draft.get("ai_suggestions") or {}
    draft["ai_suggestions"] = {
        "document_suggestions": prior_suggestions.get("document_suggestions") or [],
        "clarifying_questions": [],
    }

    needs_synthesis = False
    for a in answers:
        target = a.get("target") or ""
        if target in DIRECT_FILL_KEYS:
            draft[target] = a["answer"].strip()
        else:
            needs_synthesis = True
    # Saved before the job starts: the job re-reads the draft, so direct-filled values
    # arrive as already-known and extraction never pays to re-derive them.
    save_draft(project_id, draft)
    touch(project_id)

    job_id = uuid.uuid4().hex
    if not needs_synthesis and not ask_more:
        EXTRACTION_JOBS[job_id] = {
            "status": "done", "stage": "Done", "pct": 100, "draft": draft,
        }
        return {"job_id": job_id}

    combined_path = d / "_combined.md"
    base_combined = combined_path.read_text(encoding="utf-8") if combined_path.exists() else ""
    # PM answers are passed alongside the documents rather than appended into
    # `combined` — the documents block must stay byte-identical across clarify
    # rounds so the Anthropic prompt cache written on the initial upload (and on
    # each prior clarify round) keeps hitting instead of being invalidated every round.
    pm_answers = "\n\n".join(
        f"Q: {a.get('question', '')}\nA: {a['answer'].strip()}" for a in answers
    )

    EXTRACTION_JOBS[job_id] = {"status": "running", "stage": "Incorporating your answers…", "pct": 10}
    thread = threading.Thread(
        target=_run_extraction_job,
        args=(job_id, project_id, base_combined),
        kwargs={
            "pm_answers": pm_answers,
            "run_extraction": needs_synthesis,
            "suggest_more": ask_more,
        },
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.post("/api/projects/{project_id}/generate")
async def generate(project_id: str, request: Request):
    d = project_dir(project_id)
    data = await request.json()
    save_draft(project_id, data)
    touch(project_id)

    output_path = d / "output" / "Project Plan.docx"
    build(
        output_path=output_path,
        fields=data.get("fields", {}),
        **{k: data.get(k) for k in BUILD_KEYS},
    )
    return {"ok": True}


@app.get("/api/projects/{project_id}/download")
async def download(project_id: str):
    d = project_dir(project_id)
    path = d / "output" / "Project Plan.docx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not generated yet")
    meta = load_meta(project_id)
    filename = f"{meta['name']} - Project Plan.docx"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
