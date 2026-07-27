"""
Smoke test — fills every section of the template with sample data.
Run: python tests/test_pipeline.py    Output: tests/output_test.docx
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from output.builder import build  # noqa: E402

TEMPLATE = Path(__file__).parent.parent / "templates" / "project-plan-template.docx"
OUTPUT = Path(__file__).parent / "output_full.docx"

result = build(
    template_path=TEMPLATE,
    output_path=OUTPUT,
    fields={
        "Project Name": "Riverside Fire Station No. 3 Renovation",
        "Project Contact": "Jane Smith, PE",
        "Project Location": "123 Main Street, Riverside, NY 11001",
        "Project Phone": "(631) 756-8000",
        "Project Fax": "(631) 756-8010",
        "Project E-Mail": "jsmith@h2m.com",
        "Client Company": "Town of Riverside",
        "Client Contact": "Bob Johnson, Director of Public Works",
        "Client Location": "456 Town Hall Road, Riverside, NY 11001",
        "Client Phone": "(631) 555-0100",
        "Client Fax": "(631) 555-0101",
        "Client E-Mail": "bjohnson@riverside.gov",
    },
    team=[
        {"name": "Jane Smith", "organization": "H2M", "role": "Project Manager", "email": "jsmith@h2m.com", "phone": "(631) 756-8000"},
        {"name": "Tom Lee", "organization": "H2M", "role": "Lead Architect", "email": "tlee@h2m.com", "phone": "(631) 756-8001"},
        {"name": "Sara Chen", "organization": "H2M", "role": "Civil Engineer", "email": "schen@h2m.com", "phone": "(631) 756-8002"},
        {"name": "Bob Johnson", "organization": "Town of Riverside", "role": "Client PM", "email": "bjohnson@riverside.gov", "phone": "(631) 555-0100"},
    ],
    client_success=[
        {"factor": "Manage construction costs", "metric": "Keep change orders under 5%"},
        {"factor": "On time delivery", "metric": "Construction start - March 2027"},
        {"factor": "Quality design", "metric": "Minimal RFIs and change orders"},
    ],
    h2m_success=[
        {"factor": "Meets financial goals", "metric": "Achieve at least a 3.1 direct labor multiplier"},
        {"factor": "Adhere to project schedule", "metric": "Meet or exceed scheduled milestones"},
        {"factor": "Manage construction costs", "metric": "Keep change orders under 2%"},
    ],
    meetings=[
        {"type": "Client kick-off", "frequency": "SD", "attendees": "CM, PM"},
        {"type": "Internal Design Progress Meetings", "frequency": "Bi-Weekly", "attendees": "CM, PM - Design Team"},
        {"type": "Construction progress", "frequency": "Bi-Weekly", "attendees": "CM, PM"},
    ],
    drawings=[{"discipline": "Architectural", "number": "A-101", "title": "First Floor Plan"}],
    specifications=[{"section_no": "03 - 3000", "name": "Cast-in-Place Concrete"}],
    cost_opinions=[
        {"milestone": "D.D. Phase", "title": "Preliminary Cost Opinion", "comments": "By CM"},
        {"milestone": "C.D. Phase", "title": "Final Cost Opinion", "comments": "By CM"},
    ],
    reports=[{"milestone": "Monthly", "title": "Progress Report", "comments": "Emailed to client"}],
    milestones=[
        {"description": "Internal Design Team Kick-off Meeting", "date": "2026-08-01"},
        {"description": "External Client Kick-off Meeting", "date": "2026-08-08"},
        {"description": "Submit DD for QA Review", "date": "2026-10-15"},
        {"description": "Issue Bid Documents", "date": "2027-01-15"},
        {"description": "Bid Opening", "date": "2027-02-05"},
        {"description": "Construction Kick-off", "date": "2027-03-01"},
        {"description": "Substantial Completion", "date": "2027-12-31"},
    ],
    risks=[
        {"factor": "Staff availability across disciplines may delay design",
         "impact": "Assumptions made, loss of efficiency and potential rework",
         "severity": 7, "probability": "40%", "priority": "2.8",
         "mitigation": "Monitor progress; look for support opportunities", "by_whom": "JBL", "by_when": "2026-09-01"},
        {"factor": "Construction cost may exceed available funds",
         "impact": "Redesign required, impacting schedule",
         "severity": 8, "probability": "50%", "priority": "4.0",
         "mitigation": "Cost opinion at each phase gate", "by_whom": "CM", "by_when": "Each Phase"},
    ],
    statement_of_purpose=(
        "To provide the Town of Riverside with Design Development through Construction "
        "Administration phase services for the renovation of Fire Station No. 3, including "
        "a full interior renovation, ADA upgrades, MEP systems replacement, and exterior "
        "envelope improvements."
    ),
    hazard_assessment=(
        "Site work occurs at an active fire station. Hazards include live apparatus bays, "
        "existing overhead utilities, and potential asbestos in the 1968 structure. "
        "Pre-construction survey and coordination with the Fire Chief required before mobilization."
    ),
    scope_of_work=(
        "H2M will provide full architectural and engineering services for the renovation of "
        "Fire Station No. 3, including design development through construction administration."
    ),
    scope_of_services=(
        "Services include Schematic Design, Design Development, Construction Documents, "
        "Bidding and Procurement Assistance, and Construction Administration. H2M will "
        "coordinate all disciplines internally and manage all regulatory submissions."
    ),
    qa_qc_plan=(
        "QA led by the Department Manager with formal reviews at DD and CD milestones. "
        "QC performed by discipline leads prior to each submission."
    ),
    wbs_link="https://h2m.sharepoint.com/projects/RIVR-0031/WBS.xlsx",
    schedule_link="https://h2m.sharepoint.com/projects/RIVR-0031/Schedule.mpp",
    bim_link="https://h2m.sharepoint.com/projects/RIVR-0031/BIM-Execution-Plan.docx",
    fee_link="https://h2m.sharepoint.com/projects/RIVR-0031/Project-Setup-Form.xlsx",
    invoice_frequency="Monthly",
    invoice_date="15th of each month",
    progress_frequency="Monthly",
    progress_format="PDF",
    progress_delivery="Email",
)

print(f"Output written to: {result}")
