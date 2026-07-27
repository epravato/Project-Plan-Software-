import copy
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn


def _set_sdt_value(sdt, text: str):
    """Replace the content of a structured document tag (content control) with text."""
    content = sdt.find(qn("w:sdtContent"))
    if content is None:
        return
    for para in content.findall(qn("w:p")):
        for run in para.findall(qn("w:r")):
            para.remove(run)
        new_run = copy.deepcopy(para)
        # Build a run with the text
        from lxml import etree
        r = etree.SubElement(para, qn("w:r"))
        t = etree.SubElement(r, qn("w:t"))
        t.text = text
        if text.startswith(" ") or text.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        break  # only fix first paragraph


def _get_sdt_alias(sdt) -> str | None:
    props = sdt.find(qn("w:sdtPr"))
    if props is None:
        return None
    alias = props.find(qn("w:alias"))
    if alias is None:
        return None
    return alias.get(qn("w:val"))


def fill_content_controls(doc: Document, fields: dict[str, str]):
    """Fill named content controls by alias."""
    for sdt in doc.element.body.iter(qn("w:sdt")):
        alias = _get_sdt_alias(sdt)
        if alias and alias in fields:
            value = fields[alias] or ""
            _set_sdt_value(sdt, value)


def _find_table_by_description(doc: Document, description: str):
    """Find a table that has a tblDescription matching the given string."""
    for table in doc.tables:
        tbl_pr = table._tbl.find(qn("w:tblPr"))
        if tbl_pr is not None:
            desc = tbl_pr.find(qn("w:tblDescription"))
            if desc is not None and description.lower() in (desc.get(qn("w:val")) or "").lower():
                return table
    return None


def fill_team_table(doc: Document, team: list[dict]):
    """
    Fill the project team table.
    Each team member dict: {name, organization, role, email, phone}
    """
    table = _find_table_by_description(doc, "Team assignments")
    if table is None:
        return

    # Row 0 is the header. Find first data row (the John Doe example row).
    data_rows = [r for r in table.rows if r.cells[0].text.strip() and r.cells[0].text.strip() != "Name"]
    template_row = data_rows[0] if data_rows else None
    if template_row is None:
        return

    # Clear example row and fill with first team member
    members = team[:] if team else []

    for i, row in enumerate(data_rows):
        if i < len(members):
            m = members[i]
            cells = row.cells
            _set_cell_text(cells[0], m.get("name", ""))
            _set_cell_text(cells[1], m.get("organization", "H2M"))
            _set_cell_text(cells[2], m.get("role", ""))
            _set_cell_text(cells[3], m.get("email", ""))
            _set_cell_text(cells[4], m.get("phone", ""))
        else:
            # Clear remaining template rows
            for cell in row.cells:
                _set_cell_text(cell, "")


def _set_cell_text(cell, text: str):
    """Set cell text while preserving paragraph formatting."""
    for para in cell.paragraphs:
        for run in para.runs:
            run.text = ""
        if para.runs:
            para.runs[0].text = text
        else:
            para.add_run(text)
        break


def fill_milestone_table(doc: Document, milestones: list[dict]):
    """
    Fill the milestones table.
    Each milestone dict: {description, date}
    """
    # Find the milestones table by looking for "MILESTONES" header text
    for table in doc.tables:
        if table.rows and "MILESTONE" in table.rows[0].cells[0].text.upper():
            data_rows = table.rows[2:]  # skip header rows
            for i, row in enumerate(data_rows):
                if i < len(milestones):
                    m = milestones[i]
                    cells = row.cells
                    _set_cell_text(cells[1], m.get("description", ""))
                    _set_cell_text(cells[2], m.get("date", "TBD"))
            return


def replace_placeholder(doc: Document, placeholder: str, replacement: str):
    """Replace a <placeholder> text in any paragraph throughout the document."""
    for para in doc.paragraphs:
        if placeholder in para.text:
            for run in para.runs:
                if placeholder in run.text:
                    run.text = run.text.replace(placeholder, replacement)


def build(
    template_path: str | Path,
    output_path: str | Path,
    fields: dict[str, str],
    team: list[dict] | None = None,
    milestones: list[dict] | None = None,
    scope_of_work: str | None = None,
    scope_of_services: str | None = None,
    statement_of_purpose: str | None = None,
):
    """
    Fill the project plan template and save to output_path.

    fields: maps content control alias → value (Section I fields)
    team: list of team member dicts
    milestones: list of milestone dicts
    """
    doc = Document(str(template_path))

    fill_content_controls(doc, fields)

    if team:
        fill_team_table(doc, team)

    if milestones:
        fill_milestone_table(doc, milestones)

    placeholders = {
        "<Describe the work that will take place to achieve the Clients goals>": scope_of_work or "",
        "<Describe in detail, the services that H2M will be providing in support of the above>": scope_of_services or "",
    }
    for placeholder, value in placeholders.items():
        if value:
            replace_placeholder(doc, placeholder, value)

    doc.save(str(output_path))
    return output_path
