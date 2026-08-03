import json
import sys

from openai import OpenAI

from ai.settings import load_settings


def _log_usage(label: str, response) -> None:
    """Prints per-call token spend to the server log — cache_read is ~10% the cost of a
    normal input token, cache_creation ~125%, so this line is what actually explains a
    call's cost, not just its output. stop_reason is here because `max_tokens` means the
    JSON was truncated and the call returned nothing usable — a silent, paid-for failure
    that otherwise only shows up as an unexplained extra pass."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    print(
        f"[usage] {label}: input={usage.input_tokens} "
        f"(cache_read={cache_read}, cache_write={cache_write}) output={usage.output_tokens} "
        f"stop={getattr(response, 'stop_reason', '?')}",
        file=sys.stderr,
    )


FIELDS = (
    "Project Name", "Project Contact", "Project Location", "Project Phone", "Project Fax", "Project E-Mail",
    "Client Company", "Client Contact", "Client Location", "Client Phone", "Client Fax", "Client E-Mail",
)

# "Project" = H2M (the firm delivering the work); "Client" = the party that hired H2M.
FIELD_GUIDANCE = """\
Field definitions — "Project" fields belong to H2M (the firm performing the work); \
"Client" fields belong to the party that hired H2M:
- Project Name: the title of the project/proposal, usually on a cover page or RFP title.
- Project Contact: the named H2M staff member serving as point of contact (often in a \
proposal's cover letter, signature block, or org chart as Principal-in-Charge / Project Manager).
- Project Location: H2M's office address, typically in a letterhead or firm-info block.
- Project Phone / Project Fax / Project E-Mail: contact details for that same H2M contact \
or firm office, often near a signature block or letterhead.
- Client Company: the organization that issued the RFP or is receiving the services.
- Client Contact: the named individual at the client organization (e.g. a contracts \
administrator, procurement officer, or project sponsor named in the RFP).
- Client Location: the client organization's address, usually on the RFP cover page or \
in its contact/submission instructions.
- Client Phone / Client Fax / Client E-Mail: contact details for that client contact.

These documents are a bundle of project-related files (e.g. an RFP/solicitation, a technical \
proposal, a fee/work-breakdown-structure sheet, an org chart, a project schedule) — not a single \
form. Contact information for one field may live in a different document than another. Check \
letterheads, cover pages, cover letters, signature blocks, and org charts across ALL documents \
before deciding a field is genuinely absent. Only use an empty string if you have checked \
thoroughly and the information truly does not appear anywhere in the provided documents.

Each field value must be ONLY the literal value itself — a name, title, address, phone/fax \
number, or email address, exactly as written in the source. Never write a sentence, an \
explanation, a parenthetical note, or any reasoning as a field's value. Decide your answer \
silently and output just the value; if you are unsure between two candidates, silently pick \
the single best one rather than describing the ambiguity in the output.

If H2M COMPANY CONTEXT is provided, use it for the Project fields (H2M's own office \
address/phone/fax) when the source documents name an H2M office but don't spell out its \
full contact details — the documents still take priority whenever they do state it directly.\
"""

def _looks_clean(value, allow_long: bool = False) -> bool:
    """Rejects values where reasoning/commentary leaked into the field instead of a literal answer."""
    if not isinstance(value, str) or not value.strip():
        return True
    if "{" in value or "}" in value:
        return False
    if allow_long:
        return True
    if len(value) > 120:
        return False
    if value.count(".") > 2 or value.count(",") > 4:
        return False
    return True


OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_CHUNK_CHARS = 6000
ANTHROPIC_MODEL = "claude-sonnet-5"
# Fixed across every pass and every clarify round — output_config (schema + effort)
# is part of what the API keys the prompt cache on, so varying either one breaks
# the cache even though the cached documents block itself is unchanged.
EXTRACTION_EFFORT = "medium"
EXTRACTION_MAX_PASSES = 2

_ollama_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


# ---------- Ollama (local, chunked — small context window) ----------

def _extract_chunk_ollama(chunk: str) -> dict:
    prompt = (
        "Extract the following fields from the project document excerpt below. "
        "Return ONLY a JSON object with exactly these keys: "
        f"{json.dumps(FIELDS)}. "
        "If a field isn't present in this excerpt, use an empty string — do not guess or invent values.\n\n"
        f"EXCERPT:\n{chunk}"
    )
    try:
        resp = _ollama_client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {}


def _extract_fields_ollama(combined_md: str) -> dict:
    fields = {f: "" for f in FIELDS}
    for start in range(0, len(combined_md), OLLAMA_CHUNK_CHARS):
        if all(fields.values()):
            break
        chunk = combined_md[start:start + OLLAMA_CHUNK_CHARS]
        found = _extract_chunk_ollama(chunk)
        for f in FIELDS:
            value = found.get(f)
            if not fields[f] and isinstance(value, str) and value.strip():
                fields[f] = value
    return fields


# ---------- Anthropic (1M context — no chunking needed) ----------

_CACHE_1H = {"type": "ephemeral", "ttl": "1h"}


def _leading_blocks(context_md: str, combined_md: str) -> list[dict]:
    """Company-context and source-documents blocks, each its own cache breakpoint —
    context changes far less often than documents, so splitting them lets a cache hit
    on context alone even when the document bundle differs call to call. 1-hour TTL
    because a clarify round (PM answering questions) can take minutes — the default
    5-minute cache would otherwise expire between rounds."""
    blocks = []
    if context_md and context_md.strip():
        blocks.append({
            "type": "text",
            "text": f"H2M COMPANY CONTEXT (standards, directory, defaults):\n{context_md}",
            "cache_control": _CACHE_1H,
        })
    blocks.append({
        "type": "text",
        "text": f"DOCUMENTS:\n{combined_md}",
        "cache_control": _CACHE_1H,
    })
    return blocks


def _pm_answers_block(pm_answers: str) -> list[dict]:
    """PM answers from a clarify round, as a block after the cache breakpoint —
    keeps the documents block byte-identical across clarify rounds so it stays
    cacheable, instead of mutating the cached documents text itself."""
    if not pm_answers or not pm_answers.strip():
        return []
    return [{"type": "text", "text": f"### Project Manager Answers\n{pm_answers}"}]


# Fixed and complete — every field required on every call, regardless of what's
# already known. Narrowing this to "remaining" fields per pass (the old behavior)
# changes output_config, which invalidates the prompt cache on the documents block
# even though the block itself didn't change. The "only extract these" instruction
# below (after the cache breakpoint) still tells the model what's left to do.
FIELDS_SCHEMA = {
    "type": "object",
    "properties": {f: {"type": "string"} for f in FIELDS},
    "required": list(FIELDS),
    "additionalProperties": False,
}


def _extract_fields_anthropic(
    combined_md: str, api_key: str, on_progress=lambda stage, pct: None,
    known: dict | None = None, context_md: str = "", pm_answers: str = "",
) -> dict:
    empty = {f: "" for f in FIELDS}
    fields = dict(empty)
    for f in FIELDS:
        value = (known or {}).get(f)
        if isinstance(value, str) and value.strip():
            fields[f] = value
    if all(fields.values()):
        # Already extracted on a previous round — skip the call entirely rather than
        # re-deriving values a clarify round doesn't need.
        return fields
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        # Thinking is on (adaptive) so the model actually reasons over long documents
        # instead of occasionally bailing to all-empty on a single-shot answer.
        # A second pass fills in gaps left by the first — sanitized per-field so a
        # garbled value in one field never discards a clean value in another, and a
        # garbled value is never preferred over an already-clean one. Effort and
        # schema are fixed across passes (see FIELDS_SCHEMA / EXTRACTION_EFFORT) so
        # pass 2 can hit the prompt cache pass 1 wrote instead of re-writing it.
        stage_pct = [15, 30]
        for pass_i in range(EXTRACTION_MAX_PASSES):
            remaining = [f for f in FIELDS if not fields[f]]
            if not remaining:
                break
            on_progress(
                "Extracting contact information" + (" (refining)" if pass_i else "") + "…",
                stage_pct[pass_i],
            )
            messages = [{
                "role": "user",
                "content": _leading_blocks(context_md, combined_md) + [
                    {"type": "text", "text": (
                        f"{FIELD_GUIDANCE}\n\n"
                        "Do not guess or invent values — only report what is actually written in "
                        "the documents.\n\n"
                        f"Only extract these fields — the rest are already known: {json.dumps(remaining)}"
                    )},
                ] + _pm_answers_block(pm_answers),
            }]
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                # max_tokens caps thinking + JSON together, and a truncated response fails
                # json.loads and returns nothing at all. Headroom is cheap here (only tokens
                # actually generated are billed) and it isn't part of the prompt-cache key.
                max_tokens=8192,
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema", "schema": FIELDS_SCHEMA}, "effort": EXTRACTION_EFFORT},
                messages=messages,
            )
            _log_usage(f"fields/pass{pass_i + 1}", response)
            text = next((b.text for b in response.content if b.type == "text"), "")
            try:
                candidate = json.loads(text)
            except json.JSONDecodeError:
                continue
            for f in remaining:
                value = candidate.get(f)
                if isinstance(value, str) and value.strip() and _looks_clean(value):
                    fields[f] = value
    except Exception:
        return fields
    return fields


# ---------- Anthropic: narrative plan sections (Sections II-XII) ----------

# key -> ordered sub-fields, matching the row shape output/builder.py reads with .get()
LIST_SECTIONS = {
    "team": ("name", "organization", "role", "email", "phone"),
    "client_success": ("factor", "metric"),
    "h2m_success": ("factor", "metric"),
    "meetings": ("type", "frequency", "attendees"),
    "drawings": ("discipline", "number", "title"),
    "specifications": ("section_no", "name"),
    "cost_opinions": ("milestone", "title", "comments"),
    "reports": ("milestone", "title", "comments"),
    "milestones": ("description", "date"),
    "risks": ("factor", "impact", "severity", "probability", "mitigation", "by_whom", "by_when"),
}

LONG_TEXT_KEYS = ("statement_of_purpose", "hazard_assessment", "scope_of_work", "scope_of_services", "qa_qc_plan")
SHORT_TEXT_KEYS = ("invoice_frequency", "invoice_date", "progress_frequency", "progress_format", "progress_delivery")

NARRATIVE_KEYS = tuple(LIST_SECTIONS) + LONG_TEXT_KEYS + SHORT_TEXT_KEYS

NARRATIVE_GUIDANCE = """\
You are populating the remaining sections of an H2M project plan from a bundle of source \
documents (e.g. an RFP/solicitation, a technical proposal, a fee/work-breakdown-structure \
sheet, an org chart, and a project schedule). Extract only what these documents actually \
support — never invent names, dates, dollar figures, or safety claims.

- team: every named individual assigned to the project — from an org chart, the proposal's \
team/staffing section, a signature block, or the "Project Manager Answers" section if one is \
present. Record each person's name, their organization (the firm performing the work, or a \
named subconsultant), their role/title, and email/phone if given nearby. If the documents \
name a Principal-in-Charge, Project Manager, or QA/QC lead anywhere, those people belong here.
- client_success / h2m_success: critical success factors — only include if the documents \
explicitly state goals or performance objectives for the client or for H2M. If none are \
explicitly stated, return an empty list rather than inventing generic ones.
- meetings / drawings / specifications / cost_opinions / reports: only include rows the \
documents explicitly describe (e.g. a stated meeting cadence, a listed drawing, a named \
specification section, a stated cost-opinion or reporting milestone). These are commonly \
absent from an RFP/proposal bundle — an empty list is the correct, expected answer if the \
documents don't cover them.
- milestones: the project's key milestones with target dates — this is usually the richest \
section, and should be extracted primarily from the project schedule document (task/phase \
names and their start or finish dates). Prefer major phases and deliverable dates over every \
line item in a detailed schedule.
- risks: any risks identified in the documents (e.g. a risk register, a "constraints" or \
"challenges" section) — include severity/probability/mitigation only if stated; leave those \
sub-fields blank rather than guessing.
- statement_of_purpose: a brief paragraph summarizing the project's purpose and scope, based \
on the RFP's project description or the proposal's introduction — synthesize this from what's \
written, but don't invent specifics that aren't there.
- hazard_assessment: only include content if the documents explicitly discuss safety hazards, \
site conditions, or health & safety requirements. This is a safety-relevant field — if nothing \
explicit is stated, return an empty string; do not guess at hazards.
- scope_of_work / scope_of_services: summarize the RFP's scope-of-work section and the \
proposal's described services, respectively.
- qa_qc_plan: summarize any quality assurance / quality control approach described in the \
technical proposal, if present.
- invoice_frequency / invoice_date / progress_frequency / progress_format / progress_delivery: \
only fill these if the documents state explicit billing or progress-reporting terms (e.g. \
"invoiced monthly", "reports delivered via email"). Otherwise leave as an empty string.

Every value must reflect only what is actually written in the source documents — when in \
doubt, prefer an empty string or empty list over a guess. Do not include any commentary, \
reasoning, or explanation inside a field's value — only the literal content.

If a "Project Manager Answers" section appears at the end of the documents, treat it as \
authoritative, first-hand information from the project manager. Use it to fill the sections \
it speaks to, even when the rest of the documents don't mention that information.

If H2M COMPANY CONTEXT is provided, use it to fill standard/boilerplate fields the project \
documents don't explicitly override — e.g. a stated standard invoice frequency or progress \
report format. Project-document specifics always win over a general company default.\
"""


# Fixed and complete, same rationale as FIELDS_SCHEMA above — every section required
# on every call so schema never varies and breaks the prompt cache.
def _build_narrative_schema() -> dict:
    properties = {}
    for key, subfields in LIST_SECTIONS.items():
        properties[key] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {sf: {"type": "string"} for sf in subfields},
                "required": list(subfields),
                "additionalProperties": False,
            },
        }
    for key in LONG_TEXT_KEYS + SHORT_TEXT_KEYS:
        properties[key] = {"type": "string"}
    return {
        "type": "object",
        "properties": properties,
        "required": list(NARRATIVE_KEYS),
        "additionalProperties": False,
    }


NARRATIVE_SCHEMA = _build_narrative_schema()


def _extract_narrative_anthropic(
    combined_md: str, api_key: str, on_progress=lambda stage, pct: None,
    known: dict | None = None, context_md: str = "", pm_answers: str = "",
) -> dict:
    empty = {**{k: [] for k in LIST_SECTIONS}, **{k: "" for k in LONG_TEXT_KEYS + SHORT_TEXT_KEYS}}
    result = dict(empty)
    for key in LIST_SECTIONS:
        value = (known or {}).get(key)
        if isinstance(value, list) and value:
            result[key] = value
    for key in LONG_TEXT_KEYS + SHORT_TEXT_KEYS:
        value = (known or {}).get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value
    if not (any(not result[k] for k in LIST_SECTIONS) or any(not result[k] for k in LONG_TEXT_KEYS)):
        # Every section a clarify round would refine is already filled — skip the call.
        return result

    def is_clean_row(row: dict, subfields: tuple[str, ...]) -> bool:
        return isinstance(row, dict) and all(_looks_clean(row.get(sf, "")) for sf in subfields)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        # Effort and schema fixed across passes (see NARRATIVE_SCHEMA /
        # EXTRACTION_EFFORT) — same cache-preservation rationale as fields extraction.
        stage_pct = [45, 75]
        for pass_i in range(EXTRACTION_MAX_PASSES):
            remaining_lists = [k for k in LIST_SECTIONS if not result[k]]
            remaining_long = [k for k in LONG_TEXT_KEYS if not result[k]]
            if not remaining_lists and not remaining_long:
                break
            # Short-text keys are opportunistic — included whenever a pass runs for
            # other reasons, but never trigger a pass on their own (matches the break
            # condition above, which ignores them).
            remaining_short = [k for k in SHORT_TEXT_KEYS if not result[k]]
            remaining = remaining_lists + remaining_long + remaining_short
            on_progress(
                "Extracting project details (scope, milestones, risks)"
                + (" (refining)" if pass_i else "") + "…",
                stage_pct[pass_i],
            )
            # Same cache-marked blocks/ordering as field extraction so this call hits
            # the cache written there instead of re-billing context + the full bundle.
            messages = [{
                "role": "user",
                "content": _leading_blocks(context_md, combined_md) + [
                    {"type": "text", "text": (
                        f"{NARRATIVE_GUIDANCE}\n\n"
                        f"Only extract these sections — the rest are already known: {json.dumps(remaining)}"
                    )},
                ] + _pm_answers_block(pm_answers),
            }]
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=16384,
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema", "schema": NARRATIVE_SCHEMA}, "effort": EXTRACTION_EFFORT},
                messages=messages,
            )
            _log_usage(f"narrative/pass{pass_i + 1}", response)
            text = next((b.text for b in response.content if b.type == "text"), "")
            try:
                candidate = json.loads(text)
            except json.JSONDecodeError:
                continue
            for key in remaining_lists:
                subfields = LIST_SECTIONS[key]
                rows = candidate.get(key)
                if not isinstance(rows, list):
                    continue
                # Filter row-by-row: one garbled row shouldn't discard the whole section.
                clean = [r for r in rows if is_clean_row(r, subfields) and any(str(r.get(sf, "")).strip() for sf in subfields)]
                if clean:
                    result[key] = clean
            for key in remaining_long + remaining_short:
                value = candidate.get(key)
                if isinstance(value, str) and value.strip() and _looks_clean(value, allow_long=True):
                    result[key] = value
        return result
    except Exception:
        return result


# ---------- Anthropic: gap suggestions (what would help fill in the rest) ----------

SECTION_LABELS = {
    "team": "Project Team",
    "client_success": "Client's Critical Success Factors",
    "h2m_success": "H2M's Critical Success Factors",
    "meetings": "Meetings",
    "drawings": "Drawings",
    "specifications": "Specifications",
    "cost_opinions": "Cost Opinions",
    "reports": "Reports",
    "milestones": "Project Milestones",
    "risks": "Risk Management Plan",
    "statement_of_purpose": "Statement of Purpose",
    "hazard_assessment": "Project Hazard Assessment",
    "scope_of_work": "Scope of Work",
    "scope_of_services": "Scope of Services",
    "qa_qc_plan": "QA/QC Plan",
    "invoice_frequency": "Invoice Frequency",
    "invoice_date": "Invoice Send-By Date",
    "progress_frequency": "Progress Report Frequency",
    "progress_format": "Progress Report Format",
    "progress_delivery": "Progress Report Delivery Method",
}

# Sections a typed answer can fill verbatim. These are short factual values ("invoiced
# monthly", "1st of the month") where the PM's words ARE the section content, so the API
# layer writes them straight to the draft with no model call. Every other section is
# either prose to be synthesized or a table of rows — a one-line answer is an input to
# writing those, not the thing itself, so they still go through extraction.
DIRECT_FILL_KEYS = SHORT_TEXT_KEYS

# Asked as a single batch rather than drip-fed a few per round: every round costs the PM
# minutes of waiting, so the expensive thing is the number of rounds, not the number of
# questions in one.
MAX_CLARIFYING_QUESTIONS = 8

# `target` is a plain string, not an enum of the currently-empty keys — an enum would
# change per call, and output_config is part of the prompt-cache key (see FIELDS_SCHEMA).
# The valid keys go in the prompt instead, and the answer is validated below.
GAP_SCHEMA = {
    "type": "object",
    "properties": {
        "document_suggestions": {"type": "array", "items": {"type": "string"}},
        "clarifying_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "target": {"type": "string"},
                },
                "required": ["question", "target"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["document_suggestions", "clarifying_questions"],
    "additionalProperties": False,
}


def suggest_gaps(
    combined_md: str, empty_sections: list[dict], already_asked: list[str] | None = None,
    context_md: str = "", pm_answers: str = "",
) -> dict:
    """Given the uploaded documents and which plan sections are still empty after
    extraction, suggests what additional documents would help and asks direct clarifying
    questions for the kind of info that's rarely in a document (internal staffing, QA/QC
    ownership, billing terms, etc). `empty_sections` is a list of `{key, label}`; each
    returned question carries the `target` key of the section it fills, which is what
    lets the API layer write a factual answer straight to the draft instead of paying for
    a re-extraction. Best-effort — returns empty lists on any failure so the review step
    is never blocked by this."""
    empty = {"document_suggestions": [], "clarifying_questions": []}
    if not empty_sections:
        return empty
    settings = load_settings()
    if not (settings.get("ai_provider") == "anthropic" and settings.get("anthropic_api_key")):
        return empty
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings["anthropic_api_key"])
        already_asked_note = (
            f"\n\nDo not repeat any of these already-asked questions — either ask something "
            f"new or return fewer questions if there's nothing else worth asking:\n{json.dumps(already_asked)}"
            if already_asked else ""
        )
        prompt = (
            "You already extracted what you could from a bundle of project documents for an "
            "H2M project plan. The following sections are still empty, each with the exact "
            "key you must use to tag a question that targets it:\n"
            f"{json.dumps(empty_sections)}\n\n"
            "For each empty section, decide whether it's the kind of thing that's usually "
            "found in a document H2M just hasn't uploaded yet (e.g. a risk register, a safety "
            "plan, a fee proposal), or the kind of thing that's internal/organizational and "
            "won't ever be in a client document (e.g. who at H2M is the QA/QC lead, what "
            "invoicing software to use). Produce:\n"
            "- document_suggestions: up to 4 short suggestions naming a specific kind of "
            "document to upload that would likely fill one or more empty sections. Skip this "
            "list entirely if nothing plausible is missing.\n"
            f"- clarifying_questions: up to {MAX_CLARIFYING_QUESTIONS} short, direct questions "
            "to ask the project manager for information that's unlikely to ever be in an "
            "uploaded document. Ask everything worth asking now, in this one batch — the "
            "project manager answers these in a single sitting, so a question held back for "
            "'later' costs them another round of waiting. Skip this list entirely if there's "
            "nothing worth asking.\n"
            "  `target` must be copied character-for-character from a `key` value in the list "
            "above — never the section's label, never paraphrased, never invented. If you ask "
            "about \"Invoice Frequency\", target must be the string invoice_frequency (the key), "
            "not \"Invoice Frequency\" (the label). Use an empty string only if the answer "
            "genuinely isn't for one specific section. Ask one thing per question so a single "
            "key always applies — do not bundle two sections into one question.\n"
            "Only reference the empty sections listed above — do not invent additional gaps. "
            "If a section is empty simply because it doesn't apply to this kind of project, "
            f"don't suggest anything for it.{already_asked_note}"
        )
        # Same cache-marked blocks/ordering as the extraction calls — this runs right
        # after them in the same job, so it hits the cache they wrote.
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": GAP_SCHEMA}, "effort": "medium"},
            messages=[{
                "role": "user",
                "content": _leading_blocks(context_md, combined_md) + [
                    {"type": "text", "text": prompt},
                ] + _pm_answers_block(pm_answers),
            }],
        )
        _log_usage("gap_suggestions", response)
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        label_to_key = {label.strip().lower(): key for key, label in SECTION_LABELS.items()}
        questions = []
        for item in data.get("clarifying_questions", []):
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            if not isinstance(question, str) or not question.strip() or not _looks_clean(question, allow_long=True):
                continue
            raw_target = item.get("target") if isinstance(item.get("target"), str) else ""
            # Exact match first (the instructed path). Fallback tolerates the model
            # echoing the label instead of the key, or stray whitespace/case — anything
            # else falls back to untargeted rather than misdirecting a write.
            stripped = raw_target.strip()
            if stripped in SECTION_LABELS:
                target = stripped
            elif stripped.lower() in label_to_key:
                target = label_to_key[stripped.lower()]
            else:
                target = ""
            if raw_target and target != raw_target:
                print(
                    f"[clarify] target mismatch — model said {raw_target!r}, "
                    f"resolved to {target!r} for question: {question[:80]!r}",
                    file=sys.stderr,
                )
            questions.append({"question": question, "target": target})
        return {
            "document_suggestions": [s for s in data.get("document_suggestions", []) if _looks_clean(s, allow_long=True)][:4],
            "clarifying_questions": questions[:MAX_CLARIFYING_QUESTIONS],
        }
    except Exception:
        return empty


# ---------- dispatch ----------

def extract_fields_from_markdown(
    combined_md: str, on_progress=lambda stage, pct: None,
    known: dict | None = None, context_md: str = "", pm_answers: str = "",
) -> dict:
    """Pulls the Section I contact fields out of uploaded source documents.
    `known` seeds already-extracted values (e.g. from a prior clarify round) so the
    model is never asked to re-derive fields we already have — if `known` already
    covers every field, no API call is made at all. `context_md` is H2M's own
    standards/directory content (see context/loader.py), used to fill boilerplate
    fields the documents don't override. `pm_answers` carries clarify-round PM answers
    as a separate string, kept out of `combined_md` so the cached documents block
    stays byte-identical across clarify rounds.
    Falls back to empty strings on any provider error, so upload never hard-fails."""
    if not combined_md.strip():
        return {f: "" for f in FIELDS}
    settings = load_settings()
    if settings.get("ai_provider") == "anthropic" and settings.get("anthropic_api_key"):
        return _extract_fields_anthropic(combined_md, settings["anthropic_api_key"], on_progress, known, context_md, pm_answers)
    on_progress("Extracting contact information…", 15)
    return _extract_fields_ollama(combined_md)


def extract_narrative_from_markdown(
    combined_md: str, on_progress=lambda stage, pct: None,
    known: dict | None = None, context_md: str = "", pm_answers: str = "",
) -> dict:
    """Pulls the narrative plan sections (team, milestones, risks, scope, etc.) out of
    uploaded source documents. `known` seeds already-extracted sections so a clarify
    round only pays for genuinely empty sections, not a full re-extraction. `context_md`
    is H2M's own standards/directory content, used to fill boilerplate fields the
    documents don't override. `pm_answers` carries clarify-round PM answers as a
    separate string — see `extract_fields_from_markdown` for why. Anthropic-only for
    now; returns empty values otherwise so upload never hard-fails and the review step
    remains fully editable."""
    empty = {**{k: [] for k in LIST_SECTIONS}, **{k: "" for k in LONG_TEXT_KEYS + SHORT_TEXT_KEYS}}
    if not combined_md.strip():
        return empty
    settings = load_settings()
    if settings.get("ai_provider") == "anthropic" and settings.get("anthropic_api_key"):
        return _extract_narrative_anthropic(combined_md, settings["anthropic_api_key"], on_progress, known, context_md, pm_answers)
    return empty
