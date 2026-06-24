# Agentic Incident Resolution System

Prototype system for automatically assigning and resolving incidents on VMs, then generating a month-end operations report.

## What It Does

- Ingests incidents from a JSON file.
- Assigns incidents to the best resolver team based on VM ownership, symptoms, severity, and current load.
- Runs an agentic resolver loop:
  - classifies the incident
  - classifies priority as P1, P2, P3, or P4
  - selects a safe playbook
  - simulates VM diagnostics/remediation
  - verifies the result
  - escalates when confidence is low or action risk is high
- Applies priority timer logic:
  - P1: 5 minutes
  - P2: 10 minutes
  - P3: 15 minutes
  - P4: 20 minutes
  - unresolved incidents auto-escalate
  - resolved-but-late incidents create a bridge call invite
- Stores incident history in a local JSON database.
- Maintains a browser-side knowledge base that learns from previous incidents and feedback.
- Provides a demo incident generator for CPU, memory, disk, service, and network incidents.
- Generates an end-of-month Markdown report with SLA, assignment, resolution, and escalation metrics.

## Quick Start

```powershell
cd outputs\agentic-incident-resolution-system
python .\incident_system.py seed
python .\incident_system.py run
python .\incident_system.py report --month 2026-06
```

Generated files:

- `data/incidents.json` - sample/open incidents
- `data/state.json` - resolved system state
- `reports/monthly-report-YYYY-MM.md` - month-end report
- `dashboard.html` - static operations dashboard for the sample run
- `knowledge.html` - separate knowledge base page
- `demo-lab.html` - separate incident generator page with toast and chime notifications
- `data/knowledge_base_seed.json` - example schema for learned incident patterns

## Dashboard

Open `dashboard.html` in a browser to view the incident queue, VM fleet, assignment metrics, SLA status, resolver audit trail, and report preview. Use `knowledge.html` for learned patterns and `demo-lab.html` to generate demo incidents.

## Architecture

```text
Incident Source
      |
      v
Incident Intake -> Assignment Agent -> Resolver Agent -> Verification
      |                  |                  |              |
      v                  v                  v              v
Local State       Team/VM Rules      VM Playbooks      Close/Escalate
      |
      v
Month-End Report Generator
```

## Production Integration Points

Replace these prototype adapters when connecting to real systems:

- `VmAdapter`: connect to Azure, AWS, GCP, VMware, or SSH/WinRM.
- `TicketAdapter`: connect to ServiceNow, Jira Service Management, PagerDuty, Opsgenie, or Freshservice.
- `Notifier`: connect to Slack, Teams, email, or SMS.
- `Policy`: add approval gates for risky actions like restarts, disk cleanup, package changes, or failover.

## Safety Model

The resolver only auto-executes low-risk playbooks. High-risk actions are escalated with a recommended remediation plan. This prevents the agent from rebooting or changing production VMs without approval.

## Example Incident Types

- CPU saturation
- Memory pressure
- Disk full
- Service down
- Network unreachable
- Unknown or mixed symptoms
"# HCL_OPENAI_HACKATHON_AUTO_SLA" 
# HCL_OPENAI_HACKATHON_AUTO_SLA
