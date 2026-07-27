"""
Phase 1 smoke test — fills the template with hardcoded data.
Run: python tests/test_pipeline.py
Output: tests/output_test.docx
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from output.builder import build

TEMPLATE = Path(__file__).parent.parent / "templates" / "project-plan-template.docx"
OUTPUT = Path(__file__).parent / "output_test.docx"

fields = {
    "Project Name": "Riverside Fire Station No. 3 Renovation",
    "Project Contact": "Jane Smith, PE",
    "Project Location": "123 Main Street, Anytown, NY 11000",
    "Project Phone": "(631) 756-8000",
    "Project Fax": "(631) 756-8010",
    "Project E-Mail": "jsmith@h2m.com",
    "Client Company": "Town of Riverside",
    "Client Contact": "Bob Johnson, Director of Public Works",
    "Client Location": "456 Town Hall Road, Riverside, NY 11001",
    "Client Phone": "(631) 555-0100",
    "Client Fax": "(631) 555-0101",
    "Client E-Mail": "bjohnson@riverside.gov",
}

team = [
    {"name": "Jane Smith",    "organization": "H2M", "role": "Project Manager",  "email": "jsmith@h2m.com",   "phone": "(631) 756-8000"},
    {"name": "Tom Lee",       "organization": "H2M", "role": "Lead Architect",   "email": "tlee@h2m.com",     "phone": "(631) 756-8001"},
    {"name": "Sara Chen",     "organization": "H2M", "role": "Civil Engineer",   "email": "schen@h2m.com",    "phone": "(631) 756-8002"},
    {"name": "Bob Johnson",   "organization": "Town of Riverside", "role": "Client PM", "email": "bjohnson@riverside.gov", "phone": "(631) 555-0100"},
]

milestones = [
    {"description": "Internal Design Team Kick-off Meeting", "date": "2026-08-01"},
    {"description": "External Client Kick-off Meeting",      "date": "2026-08-08"},
    {"description": "Submit DD for QA Review",               "date": "2026-10-15"},
    {"description": "DD Set to Owner & Estimator",           "date": "2026-10-30"},
    {"description": "Issue Bid Documents",                   "date": "2027-01-15"},
    {"description": "Bid Opening",                           "date": "2027-02-05"},
    {"description": "Construction Kick-off",                 "date": "2027-03-01"},
    {"description": "Substantial Completion",                "date": "2027-12-31"},
]

scope_of_work = (
    "H2M will provide full architectural and engineering services for the renovation "
    "of Fire Station No. 3, including design development through construction administration. "
    "The project includes a full interior renovation, ADA upgrades, MEP systems replacement, "
    "and exterior envelope improvements."
)

scope_of_services = (
    "Services include: Schematic Design, Design Development, Construction Documents, "
    "Bidding/Procurement Assistance, and Construction Administration. "
    "H2M will coordinate all disciplines internally and manage all regulatory submissions."
)

result = build(
    template_path=TEMPLATE,
    output_path=OUTPUT,
    fields=fields,
    team=team,
    milestones=milestones,
    scope_of_work=scope_of_work,
    scope_of_services=scope_of_services,
)

print(f"Output written to: {result}")
