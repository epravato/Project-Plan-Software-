import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import shutil
import tempfile
import uuid
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from ingestion.converter import convert
from output.builder import build

app = FastAPI()

TEMPLATE = Path(__file__).parent.parent.parent / "templates" / "project-plan-template.docx"
CONTEXT_FOLDER = Path(__file__).parent.parent.parent / "context"
UPLOADS_DIR = Path(tempfile.gettempdir()) / "pps_uploads"
OUTPUTS_DIR = Path(tempfile.gettempdir()) / "pps_outputs"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# ---------- helpers ----------

def extract_fields_from_markdown(combined_md: str) -> dict:
    """Placeholder extraction — returns empty strings so the user can fill manually.
    Replace with real AI extraction in Phase 2."""
    return {
        "Project Name": "",
        "Project Contact": "",
        "Project Location": "",
        "Project Phone": "",
        "Project Fax": "",
        "Project E-Mail": "",
        "Client Company": "",
        "Client Contact": "",
        "Client Location": "",
        "Client Phone": "",
        "Client Fax": "",
        "Client E-Mail": "",
    }


# ---------- routes ----------

@app.get("/", response_class=HTMLResponse)
async def root():
    html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    session_id = str(uuid.uuid4())
    session_dir = UPLOADS_DIR / session_id
    session_dir.mkdir()

    markdowns = {}
    for f in files:
        dest = session_dir / f.filename
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        try:
            markdowns[f.filename] = convert(dest)
        except Exception as e:
            markdowns[f.filename] = f"[Could not convert: {e}]"

    combined = "\n\n".join(f"### {name}\n{md}" for name, md in markdowns.items())
    fields = extract_fields_from_markdown(combined)

    return {"session_id": session_id, "fields": fields, "files": list(markdowns.keys())}


@app.post("/generate")
async def generate(request: Request):
    data = await request.json()
    session_id = data.get("session_id", str(uuid.uuid4()))
    fields = data.get("fields", {})
    team = data.get("team", [])
    milestones = data.get("milestones", [])
    scope_of_work = data.get("scope_of_work", "")
    scope_of_services = data.get("scope_of_services", "")

    output_path = OUTPUTS_DIR / f"{session_id}.docx"
    build(
        template_path=TEMPLATE,
        output_path=output_path,
        fields=fields,
        team=team,
        milestones=milestones,
        scope_of_work=scope_of_work,
        scope_of_services=scope_of_services,
    )
    return {"download_id": session_id}


@app.get("/download/{session_id}")
async def download(session_id: str):
    path = OUTPUTS_DIR / f"{session_id}.docx"
    if not path.exists():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="Project Plan.docx",
    )
