# Project Plan Software — Claude Instructions

## Vault context
Read these at session start:
- `C:\Users\epravato\OneDrive - H2M\Obsidian Vault\Projects\Project Plan Software\Overview.md`
- `C:\Users\epravato\OneDrive - H2M\Obsidian Vault\Projects\Project Plan Software\Architecture.md`
- `C:\Users\epravato\OneDrive - H2M\Obsidian Vault\Projects\Project Plan Software\Active.md`

## What this project does
AI-powered document automation tool that fills out H2M's project plan template.
- Reads a context layer (company/employee data) from a shared drive — read-only
- Accepts source documents converted to Markdown via Markitdown
- Uses an LLM to populate the project plan template
- Outputs a completed project plan document

## Project constraints (never re-ask about these)
- Context layer is READ-ONLY — the software never writes to it
- Source documents come in as .md files (via Microsoft Markitdown)
- Output format TBD (likely .docx)
- Target users: QA/QC team at H2M
