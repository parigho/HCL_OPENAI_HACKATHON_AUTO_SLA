from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
CONFIG_PATH = ROOT / "config.json"
INCIDENTS_PATH = DATA_DIR / "incidents.json"
STATE_PATH = DATA_DIR / "state.json"
SAMPLE_PATH = DATA_DIR / "sample_incidents.json"

RISK_ORDER = {"low": 1, "medium": 2, "high": 3}
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Incident:
    id: str
    created_at: str
    vm_id: str
    severity: str
    title: str
    description: str
    status: str = "open"
    assigned_team: str | None = None
    category: str | None = None
    resolution: str | None = None
    resolved_at: str | None = None
    priority: str | None = None
    priority_status: str | None = None
    resolution_minutes: int | None = None
    escalation_action: str | None = None
    escalated: bool = False
    audit_log: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Incident":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in raw.items() if key in known})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "vm_id": self.vm_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "assigned_team": self.assigned_team,
            "category": self.category,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at,
            "priority": self.priority,
            "priority_status": self.priority_status,
            "resolution_minutes": self.resolution_minutes,
            "escalation_action": self.escalation_action,
            "escalated": self.escalated,
            "audit_log": self.audit_log,
        }


class Store:
    def __init__(self) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        REPORT_DIR.mkdir(exist_ok=True)

    def load_incidents(self) -> list[Incident]:
        if not INCIDENTS_PATH.exists():
            return []
        return [Incident.from_dict(item) for item in json.loads(INCIDENTS_PATH.read_text())]

    def save_incidents(self, incidents: list[Incident]) -> None:
        INCIDENTS_PATH.write_text(json.dumps([item.to_dict() for item in incidents], indent=2))

    def load_state(self) -> dict[str, Any]:
        if not STATE_PATH.exists():
            return {"incidents": []}
        return json.loads(STATE_PATH.read_text())

    def save_state(self, incidents: list[Incident]) -> None:
        STATE_PATH.write_text(json.dumps({"incidents": [item.to_dict() for item in incidents]}, indent=2))


class Policy:
    def __init__(self, config: dict[str, Any]) -> None:
        self.auto_resolve_limit = config.get("auto_resolve_risk_limit", "low")

    def can_auto_resolve(self, risk: str, incident: Incident) -> bool:
        if incident.severity == "critical":
            return False
        return RISK_ORDER[risk] <= RISK_ORDER[self.auto_resolve_limit]


class AssignmentAgent:
    def __init__(self, config: dict[str, Any], incidents: list[Incident]) -> None:
        self.config = config
        self.incidents = incidents

    def assign(self, incident: Incident, category: str) -> str:
        vm = self._vm(incident.vm_id)
        candidates = []
        for team in self.config["teams"]:
            load = self._active_load(team["name"])
            skill_score = int(category in team["skills"]) + int(vm.get("os") in team["skills"])
            owner_bonus = 3 if vm.get("owner_team") == team["name"] else 0
            capacity_penalty = 2 if load >= team.get("max_active", 5) else 0
            score = skill_score + owner_bonus - capacity_penalty - load * 0.1
            candidates.append((score, team["name"]))
        return max(candidates)[1]

    def _vm(self, vm_id: str) -> dict[str, Any]:
        return next((vm for vm in self.config["vms"] if vm["id"] == vm_id), {})

    def _active_load(self, team_name: str) -> int:
        return sum(
            1
            for incident in self.incidents
            if incident.assigned_team == team_name and incident.status in {"open", "in_progress"}
        )


class ResolverAgent:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.policy = Policy(config)

    def resolve(self, incident: Incident) -> Incident:
        category = self.classify(incident)
        playbook = self.select_playbook(category)
        incident.priority = classify_priority(incident.severity)
        incident.category = category
        incident.audit_log.append(f"classified category={category}")
        incident.audit_log.append(f"classified priority={incident.priority}")
        incident.audit_log.append(f"selected playbook={playbook['name']} risk={playbook['risk']}")

        if not self.policy.can_auto_resolve(playbook["risk"], incident):
            incident.status = "escalated"
            incident.escalated = True
            incident.resolution = (
                f"Escalated to {incident.assigned_team}. Recommended action: {playbook['manual_plan']}"
            )
            apply_priority_policy(self.config, incident)
            incident.audit_log.append("policy blocked auto-resolution")
            return incident

        diagnostic = self.run_diagnostics(incident, category)
        remediation = self.apply_remediation(playbook)
        verified = self.verify(diagnostic, remediation)
        incident.audit_log.extend([diagnostic, remediation])

        if verified:
            incident.status = "resolved"
            incident.resolved_at = estimated_resolution_time(incident, category)
            incident.resolution_minutes = elapsed_minutes(incident.created_at, incident.resolved_at)
            incident.resolution = playbook["success"]
            apply_priority_policy(self.config, incident)
            incident.audit_log.append("verification passed")
        else:
            incident.status = "escalated"
            incident.escalated = True
            incident.resolution = f"Auto-remediation failed. Escalated to {incident.assigned_team}."
            apply_priority_policy(self.config, incident)
            incident.audit_log.append("verification failed")
        return incident

    def classify(self, incident: Incident) -> str:
        text = f"{incident.title} {incident.description}".lower()
        rules = {
            "cpu": ["cpu", "processor", "load"],
            "memory": ["memory", "ram"],
            "disk": ["disk", "drive", "storage", "full"],
            "service": ["service", "stopped", "down"],
            "network": ["unreachable", "ping", "network", "http checks failed"],
        }
        for category, keywords in rules.items():
            if any(keyword in text for keyword in keywords):
                return category
        return "unknown"

    def select_playbook(self, category: str) -> dict[str, str]:
        playbooks = {
            "cpu": {
                "name": "cpu-triage",
                "risk": "low",
                "manual_plan": "review top processes, scale VM, or restart noisy service after approval",
                "success": "Identified noisy process and reduced CPU pressure using safe throttling action.",
            },
            "memory": {
                "name": "memory-cache-cleanup",
                "risk": "low",
                "manual_plan": "review memory dump and restart service after approval",
                "success": "Cleared application cache and confirmed memory returned below threshold.",
            },
            "disk": {
                "name": "temp-file-cleanup",
                "risk": "low",
                "manual_plan": "expand disk or remove archived files after owner approval",
                "success": "Removed temporary files and confirmed free disk space is healthy.",
            },
            "service": {
                "name": "service-restart",
                "risk": "medium",
                "manual_plan": "restart the failed service during an approved change window",
                "success": "Restarted failed service and verified health checks.",
            },
            "network": {
                "name": "network-path-check",
                "risk": "medium",
                "manual_plan": "validate NIC, route table, NSG/firewall, and hypervisor health",
                "success": "Restored connectivity after refreshing network path checks.",
            },
            "unknown": {
                "name": "human-triage",
                "risk": "high",
                "manual_plan": "perform manual triage because symptoms are ambiguous",
                "success": "Resolved after manual triage.",
            },
        }
        return playbooks[category]

    def run_diagnostics(self, incident: Incident, category: str) -> str:
        return f"diagnostics on {incident.vm_id}: collected {category} telemetry and recent system events"

    def apply_remediation(self, playbook: dict[str, str]) -> str:
        return f"remediation executed: {playbook['name']}"

    def verify(self, diagnostic: str, remediation: str) -> bool:
        return bool(diagnostic and remediation)


class MonthlyReport:
    def __init__(self, config: dict[str, Any], incidents: list[Incident]) -> None:
        self.config = config
        self.incidents = incidents

    def generate(self, month: str) -> Path:
        monthly = [item for item in self.incidents if item.created_at.startswith(month)]
        resolved = [item for item in monthly if item.status == "resolved"]
        escalated = [item for item in monthly if item.escalated]
        sla_hits = [item for item in resolved if self._within_sla(item)]
        by_team = self._count_by(monthly, "assigned_team")
        by_category = self._count_by(monthly, "category")
        by_severity = self._count_by(monthly, "severity")

        report = [
            f"# Monthly Incident Report - {month}",
            "",
            "## Executive Summary",
            "",
            f"- Total incidents: {len(monthly)}",
            f"- Auto-resolved: {len(resolved)}",
            f"- Escalated: {len(escalated)}",
            f"- SLA met: {len(sla_hits)} of {len(resolved)} resolved incidents",
            "",
            "## Incidents By Severity",
            "",
            self._table(by_severity, ["Severity", "Count"]),
            "",
            "## Incidents By Category",
            "",
            self._table(by_category, ["Category", "Count"]),
            "",
            "## Assignment Load",
            "",
            self._table(by_team, ["Team", "Count"]),
            "",
            "## Incident Details",
            "",
            "| ID | VM | Priority | Severity | Team | Category | Status | Resolution Time | Priority Status | Resolution |",
            "| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
        for incident in monthly:
            report.append(
                "| {id} | {vm} | {priority} | {severity} | {team} | {category} | {status} | {minutes} | {priority_status} | {resolution} |".format(
                    id=incident.id,
                    vm=incident.vm_id,
                    priority=incident.priority or "-",
                    severity=incident.severity,
                    team=incident.assigned_team or "-",
                    category=incident.category or "-",
                    status=incident.status,
                    minutes=incident.resolution_minutes if incident.resolution_minutes is not None else "-",
                    priority_status=incident.priority_status or "-",
                    resolution=(incident.resolution or "-").replace("|", "/"),
                )
            )

        report.extend(
            [
                "",
                "## Recommendations",
                "",
                "- Add approval workflow for medium/high-risk VM actions.",
                "- Feed real monitoring signals into the intake adapter.",
                "- Connect assignment to team schedules and on-call rotations.",
                "- Review recurring categories and create preventive automation.",
            ]
        )

        REPORT_DIR.mkdir(exist_ok=True)
        path = REPORT_DIR / f"monthly-report-{month}.md"
        path.write_text("\n".join(report))
        return path

    def _within_sla(self, incident: Incident) -> bool:
        if not incident.resolved_at:
            return False
        start = parse_dt(incident.created_at)
        end = parse_dt(incident.resolved_at)
        elapsed_minutes = (end - start).total_seconds() / 60
        return elapsed_minutes <= self.config["sla_minutes"][incident.severity]

    def _count_by(self, incidents: list[Incident], attr: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for incident in incidents:
            key = str(getattr(incident, attr) or "unassigned")
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def _table(self, counts: dict[str, int], headers: list[str]) -> str:
        lines = [
            f"| {headers[0]} | {headers[1]} |",
            "| --- | ---: |",
        ]
        for key, value in counts.items():
            lines.append(f"| {key} | {value} |")
        return "\n".join(lines)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def seed() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    shutil.copyfile(SAMPLE_PATH, INCIDENTS_PATH)
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    print(f"Seeded sample incidents at {INCIDENTS_PATH}")


def run() -> None:
    store = Store()
    config = load_config()
    incidents = store.load_incidents()
    assigner = AssignmentAgent(config, incidents)
    resolver = ResolverAgent(config)

    for incident in incidents:
        if incident.status not in {"open", "in_progress"}:
            continue
        incident.status = "in_progress"
        category = resolver.classify(incident)
        incident.assigned_team = assigner.assign(incident, category)
        incident.audit_log.append(f"assigned team={incident.assigned_team}")
        resolver.resolve(incident)
        print(f"{incident.id}: {incident.status} -> {incident.assigned_team}")

    store.save_incidents(incidents)
    store.save_state(incidents)
    print(f"Saved state at {STATE_PATH}")


def report(month: str) -> None:
    store = Store()
    config = load_config()
    state = store.load_state()
    incidents = [Incident.from_dict(item) for item in state.get("incidents", [])]
    path = MonthlyReport(config, incidents).generate(month)
    print(f"Generated report at {path}")


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def classify_priority(severity: str) -> str:
    return {
        "critical": "P1",
        "high": "P2",
        "medium": "P3",
        "low": "P4",
    }.get(severity, "P4")


def elapsed_minutes(start: str, end: str) -> int:
    return int((parse_dt(end) - parse_dt(start)).total_seconds() / 60)


def apply_priority_policy(config: dict[str, Any], incident: Incident) -> None:
    if not incident.priority:
        incident.priority = classify_priority(incident.severity)

    threshold = config["priority_response_minutes"][incident.priority]
    if incident.resolved_at:
        incident.resolution_minutes = elapsed_minutes(incident.created_at, incident.resolved_at)

    if incident.status == "resolved" and incident.resolution_minutes is not None:
        if incident.resolution_minutes <= threshold:
            incident.priority_status = "within target"
            incident.escalation_action = "none"
            incident.audit_log.append(
                f"priority timer ok: resolved in {incident.resolution_minutes}m within {threshold}m"
            )
            return

        incident.priority_status = "bridge call invited"
        incident.escalation_action = (
            f"Created bridge call invite because {incident.priority} exceeded {threshold}m target"
        )
        incident.audit_log.append(incident.escalation_action)
        return

    incident.priority_status = "auto escalated"
    incident.escalation_action = (
        f"Auto-escalated to {incident.assigned_team} because {incident.priority} was not resolved within {threshold}m"
    )
    incident.audit_log.append(incident.escalation_action)


def estimated_resolution_time(incident: Incident, category: str) -> str:
    base_minutes = {
        "cpu": 24,
        "memory": 18,
        "disk": 32,
        "service": 75,
        "network": 90,
        "unknown": 120,
    }
    severity_multiplier = {
        "critical": 0.7,
        "high": 1.0,
        "medium": 1.2,
        "low": 1.5,
    }
    minutes = int(base_minutes.get(category, 60) * severity_multiplier[incident.severity])
    return (parse_dt(incident.created_at) + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic VM incident resolution prototype")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("seed", help="copy sample incidents into the working incident queue")
    subcommands.add_parser("run", help="assign and resolve open incidents")
    report_parser = subcommands.add_parser("report", help="generate a month-end report")
    report_parser.add_argument("--month", required=True, help="month in YYYY-MM format")
    args = parser.parse_args()

    if args.command == "seed":
        seed()
    elif args.command == "run":
        run()
    elif args.command == "report":
        report(args.month)


if __name__ == "__main__":
    main()
