"""
Fills the H2M project plan Word template.

The template nests every real table inside a 1x1 wrapper table, so tables are
addressed by a dotted path: "1.0" means wrapper table 1, first nested table.
Table map (see tests/inspect_tables.py to regenerate):

    0.0   Section I    General project info (content controls)
    1.0   Section II   Project team
    2.0   Section IIIB Client's critical success factors
    3.0   Section IIIB H2M's critical success factors
    4.0   Section IVA  Meetings
    5.0   Section IVB  Drawings
    6.0   Section IVC  Specifications
    7.0   Section IVD  Cost opinions
    8.0   Section IVE  Reports
    9.0   Section VIIB Invoice frequency
    10.0  Section VIIB Milestones
    11.0  Section VIIIC Progress reports
    12.0  Section XI   Risk management
"""

import copy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

W_T = qn("w:t")
W_R = qn("w:r")
W_P = qn("w:p")
W_TC = qn("w:tc")
W_TR = qn("w:tr")
W_TBL = qn("w:tbl")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


# ---------------------------------------------------------------- primitives


def _text_of(el) -> str:
    return "".join(t.text or "" for t in el.iter(W_T))


def _set_text(container, text: str):
    """
    Replace all text under `container`, keeping the first run's formatting.
    Searches recursively: content controls wrap a <w:tc>, so their paragraphs
    sit deeper than a direct-child lookup would reach.
    """
    paras = [container] if container.tag == W_P else list(container.iter(W_P))
    if not paras:
        return
    first, *rest = paras

    def strip_runs(p, keep_first: bool):
        """Remove runs anywhere under p (including inside w:hyperlink wrappers)."""
        kept = None
        for r in list(p.iter(W_R)):
            if keep_first and kept is None and r.getparent() is p:
                kept = r
                continue
            r.getparent().remove(r)
        return kept

    keep = strip_runs(first, keep_first=True)
    if keep is None:
        keep = etree.SubElement(first, W_R)
    for t in keep.findall(W_T)[1:]:
        keep.remove(t)
    t = keep.find(W_T)
    if t is None:
        t = etree.SubElement(keep, W_T)
    t.text = text
    t.set(XML_SPACE, "preserve")

    for p in rest:
        strip_runs(p, keep_first=False)


# ------------------------------------------------------------------- tables


def _nested_tables(tbl):
    out = []
    for tr in tbl.findall(W_TR):
        for tc in tr.findall(W_TC):
            out.extend(tc.findall(W_TBL))
    return out


def _resolve(doc, path: str):
    """Resolve a dotted table path like '2.0' to a <w:tbl> element."""
    top, *rest = (int(p) for p in path.split("."))
    tbl = doc.tables[top]._tbl
    for idx in rest:
        nested = _nested_tables(tbl)
        if idx >= len(nested):
            return None
        tbl = nested[idx]
    return tbl


def _fill_rows(tbl, rows: list[list[str]], start: int, cols: list[int]):
    """
    Write `rows` into the table starting at row index `start`.
    `cols` maps each value position to a cell index. Extra template rows are cleared.
    """
    trs = tbl.findall(W_TR)[start:]
    for i, tr in enumerate(trs):
        cells = tr.findall(W_TC)
        values = rows[i] if i < len(rows) else [""] * len(cols)
        for value, col in zip(values, cols):
            if col < len(cells):
                _set_text(cells[col], value)


def fill_table(doc, path: str, rows, start: int, cols: list[int]):
    tbl = _resolve(doc, path)
    if tbl is not None and rows is not None:
        _fill_rows(tbl, rows, start, cols)


# --------------------------------------------------------- content controls


def fill_content_controls(doc, fields: dict[str, str]):
    for sdt in doc.element.body.iter(qn("w:sdt")):
        props = sdt.find(qn("w:sdtPr"))
        if props is None:
            continue
        alias_el = props.find(qn("w:alias"))
        if alias_el is None:
            continue
        alias = alias_el.get(qn("w:val"))
        if alias not in fields:
            continue
        content = sdt.find(qn("w:sdtContent"))
        if content is not None:
            _set_text(content, fields[alias] or "")


# ------------------------------------------------------------- text bodies


def _body_paragraphs(doc):
    return list(doc.element.body.iter(W_P))


def replace_between(doc, after: str, before: str, text: str):
    """
    Replace the paragraphs between the heading containing `after` and the one
    containing `before` with a single paragraph of `text`.
    Used for narrative sections that ship with EXAMPLE copy in the template.
    """
    paras = doc.paragraphs
    start = end = None
    for i, p in enumerate(paras):
        t = p.text.strip()
        if start is None and after.lower() in t.lower():
            start = i
        elif start is not None and before.lower() in t.lower():
            end = i
            break
    if start is None or end is None or end <= start + 1:
        return

    body = paras[start + 1 : end]
    _set_text(body[0]._p, text)
    # Strip the example bullets / trailing copy
    for p in body[1:]:
        p._p.getparent().remove(p._p)


def replace_placeholder(doc, placeholder: str, replacement: str):
    """Replace a <bracketed> placeholder wherever it appears."""
    for p in doc.paragraphs:
        if placeholder in p.text:
            _set_text(p._p, replacement)


def _find_para(doc, text: str, style: str | None = None):
    for p in doc.paragraphs:
        if text.lower() in p.text.strip().lower() and (style is None or p.style.name == style):
            return p
    return None


def insert_health_safety(doc, hazard_assessment: str):
    """
    Insert the Health & Safety section, which the Word template omits but the
    firm's 'Minimum Requirements of a Project Plan' lists as section IV.

    Roman numerals come from the PMP Heading style's numbering, so inserting
    here renumbers the following sections automatically. Headings are cloned
    from existing ones to inherit that numbering.
    """
    anchor = _find_para(doc, "PROJECT DELIVERABLES", "PMP Heading")
    h1_src = _find_para(doc, "OVERVIEW", "PMP Heading")
    h2_src = _find_para(doc, "Statement of Purpose", "PMP Heading 2")
    if anchor is None or h1_src is None or h2_src is None:
        return

    heading = copy.deepcopy(h1_src._p)
    _set_text(heading, "HEALTH & SAFETY")

    sub = copy.deepcopy(h2_src._p)
    _set_text(sub, "Project Hazard Assessment")

    body = copy.deepcopy(h2_src._p)
    body_style = body.find(qn("w:pPr"))
    if body_style is not None:
        num = body_style.find(qn("w:numPr"))
        if num is not None:
            body_style.remove(num)
        st = body_style.find(qn("w:pStyle"))
        if st is not None:
            st.set(qn("w:val"), "PMPNormal")
    _set_text(body, hazard_assessment)

    anchor._p.addprevious(heading)
    anchor._p.addprevious(sub)
    anchor._p.addprevious(body)


# ------------------------------------------------------------------- build


def build(
    template_path: str | Path,
    output_path: str | Path,
    fields: dict[str, str] | None = None,
    team: list[dict] | None = None,
    client_success: list[dict] | None = None,
    h2m_success: list[dict] | None = None,
    meetings: list[dict] | None = None,
    drawings: list[dict] | None = None,
    specifications: list[dict] | None = None,
    cost_opinions: list[dict] | None = None,
    reports: list[dict] | None = None,
    milestones: list[dict] | None = None,
    risks: list[dict] | None = None,
    statement_of_purpose: str | None = None,
    hazard_assessment: str | None = None,
    scope_of_work: str | None = None,
    scope_of_services: str | None = None,
    qa_qc_plan: str | None = None,
    wbs_link: str | None = None,
    schedule_link: str | None = None,
    bim_link: str | None = None,
    fee_link: str | None = None,
    invoice_frequency: str | None = None,
    invoice_date: str | None = None,
    progress_frequency: str | None = None,
    progress_format: str | None = None,
    progress_delivery: str | None = None,
):
    doc = Document(str(template_path))

    fill_content_controls(doc, fields or {})

    fill_table(
        doc, "1.0", [[m.get("name", ""), m.get("organization", ""), m.get("role", ""),
                      m.get("email", ""), m.get("phone", "")] for m in (team or [])],
        start=1, cols=[0, 1, 2, 3, 4],
    )

    for path, data in (("2.0", client_success), ("3.0", h2m_success)):
        fill_table(
            doc, path,
            [[f.get("factor", ""), f.get("metric", "")] for f in (data or [])],
            start=1, cols=[1, 3],
        )

    fill_table(
        doc, "4.0", [[m.get("type", ""), m.get("frequency", ""), m.get("attendees", "")]
                     for m in (meetings or [])],
        start=1, cols=[0, 1, 2],
    )

    fill_table(
        doc, "5.0", [[d.get("discipline", ""), d.get("number", ""), d.get("title", "")]
                     for d in (drawings or [])],
        start=1, cols=[0, 1, 2],
    )

    fill_table(
        doc, "6.0", [[s.get("section_no", ""), s.get("name", "")] for s in (specifications or [])],
        start=1, cols=[0, 1],
    )

    for path, data in (("7.0", cost_opinions), ("8.0", reports)):
        fill_table(
            doc, path,
            [[r.get("milestone", ""), r.get("title", ""), r.get("comments", "")] for r in (data or [])],
            start=1, cols=[0, 1, 2],
        )

    fill_table(
        doc, "10.0",
        [[str(i + 1), m.get("description", ""), m.get("date", "")]
         for i, m in enumerate(milestones or [])],
        start=2, cols=[0, 1, 2],
    )

    fill_table(
        doc, "12.0",
        [[r.get("factor", ""), r.get("impact", ""), str(r.get("severity", "")),
          str(r.get("probability", "")), str(r.get("priority", "")),
          r.get("mitigation", ""), r.get("by_whom", ""), r.get("by_when", "")]
         for r in (risks or [])],
        start=1, cols=[0, 1, 2, 3, 4, 5, 6, 7],
    )

    # Invoice frequency / date  (row 1: Frequency | <val> | | Date: | <val>)
    if invoice_frequency is not None or invoice_date is not None:
        tbl = _resolve(doc, "9.0")
        if tbl is not None:
            cells = tbl.findall(W_TR)[1].findall(W_TC)
            if invoice_frequency is not None and len(cells) > 1:
                _set_text(cells[1], invoice_frequency)
            if invoice_date is not None and len(cells) > 4:
                _set_text(cells[4], invoice_date)

    # Progress reports (row 1: Frequency: | <v> | Format: | <v> | Delivery Method: | <v>)
    if any(v is not None for v in (progress_frequency, progress_format, progress_delivery)):
        tbl = _resolve(doc, "11.0")
        if tbl is not None:
            cells = tbl.findall(W_TR)[1].findall(W_TC)
            for idx, value in ((1, progress_frequency), (3, progress_format), (5, progress_delivery)):
                if value is not None and idx < len(cells):
                    _set_text(cells[idx], value)

    if statement_of_purpose:
        replace_between(doc, "Statement of Purpose", "Success Factors", statement_of_purpose)

    # Always inserted so the output satisfies the firm's minimum requirements
    # and section numbering stays stable whether or not the PM filled it in.
    insert_health_safety(
        doc,
        hazard_assessment
        or "To be completed — refer to the H2M Project Hazard Assessment Form.",
    )

    if qa_qc_plan:
        replace_between(doc, "QA AND QC PLANS", "RISK MANAGEMENT PLAN", qa_qc_plan)

    for placeholder, value in (
        ("<Describe the work that will take place to achieve the Clients goals>", scope_of_work),
        ("<Describe in detail, the services that H2M will be providing in support of the above>", scope_of_services),
        ("<Insert link to Project Set-up Form>", fee_link),
    ):
        if value:
            replace_placeholder(doc, placeholder, value)

    # Sections V, VIII.A and IX all ship with the same WBS placeholder text.
    wbs_placeholder = "<Insert link to the detailed WBS developed for the project>"
    for value in (wbs_link, schedule_link, bim_link):
        if value:
            for p in doc.paragraphs:
                if wbs_placeholder in p.text:
                    _set_text(p._p, value)
                    break

    doc.save(str(output_path))
    return output_path
