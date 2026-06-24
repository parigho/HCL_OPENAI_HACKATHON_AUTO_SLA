# Monthly Incident Report - 2026-06

## Executive Summary

- Total incidents: 5
- Auto-resolved: 3
- Escalated: 2
- SLA met: 3 of 3 resolved incidents

## Incidents By Severity

| Severity | Count |
| --- | ---: |
| critical | 1 |
| high | 2 |
| low | 1 |
| medium | 1 |

## Incidents By Category

| Category | Count |
| --- | ---: |
| cpu | 1 |
| disk | 1 |
| memory | 1 |
| network | 1 |
| service | 1 |

## Assignment Load

| Team | Count |
| --- | ---: |
| database-ops | 1 |
| linux-platform | 3 |
| windows-platform | 1 |

## Incident Details

| ID | VM | Priority | Severity | Team | Category | Status | Resolution Time | Priority Status | Resolution |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| INC-1001 | vm-payroll-01 | P2 | high | linux-platform | cpu | resolved | 24 | bridge call invited | Identified noisy process and reduced CPU pressure using safe throttling action. |
| INC-1002 | vm-crm-02 | P3 | medium | windows-platform | disk | resolved | 38 | bridge call invited | Removed temporary files and confirmed free disk space is healthy. |
| INC-1003 | vm-db-01 | P1 | critical | database-ops | service | escalated | - | auto escalated | Escalated to database-ops. Recommended action: restart the failed service during an approved change window |
| INC-1004 | vm-web-03 | P4 | low | linux-platform | memory | resolved | 27 | bridge call invited | Cleared application cache and confirmed memory returned below threshold. |
| INC-1005 | vm-web-03 | P2 | high | linux-platform | network | escalated | - | auto escalated | Escalated to linux-platform. Recommended action: validate NIC, route table, NSG/firewall, and hypervisor health |

## Recommendations

- Add approval workflow for medium/high-risk VM actions.
- Feed real monitoring signals into the intake adapter.
- Connect assignment to team schedules and on-call rotations.
- Review recurring categories and create preventive automation.