# Context

Swarm: default

## Project Context

Language: Python
Framework: Home Assistant Custom Component
Build command: TBD
Test command: TBD
Lint command: TBD
Entry points: custom_components/rover/

## Decisions

- **Reticulum-архитектура:** новый проект haos-rover — полный реворк BotoVed/Rover c Meshtastic на Reticulum/LXMF
- **Три репозитория:** haos-rover (HA integration), Rover-Card (Lovelace), HaOS-Rover-app (Android)
- **Android-приложение тоже в реворке** — реаленое устройство есть для тестов

## Pending QA Gate Selection

- reviewer: true
- test_engineer: true
- sme_enabled: true
- critic_pre_plan: true
- sast_enabled: true
- council_mode: false
- hallucination_guard: false
- mutation_test: false
- phase_council: false
- drift_check: true
- final_council: false
- recorded_at: 2026-06-24T10:55:00+03:00

## Task Completion Commit Policy

- commit_after_each_completed_task: true
- version_bump:
    after_successful_test_iteration: patch
    after_phase_complete: minor
    after_release: major
- recorded_at: 2026-06-24T10:55:00+03:00

## Phase Transition

- auto_proceed: false (по согласованию)

## Agent Activity

| Tool | Calls | Success | Failed | Avg Duration |
|------|-------|---------|--------|--------------|
| read | 756 | 756 | 0 | 617ms |
| bash | 492 | 492 | 0 | 647ms |
| edit | 201 | 201 | 0 | 28ms |
| glob | 165 | 165 | 0 | 629ms |
| grep | 108 | 108 | 0 | 34ms |
| task | 86 | 86 | 0 | 93373ms |
| write | 69 | 69 | 0 | 21ms |
| syntax_check | 43 | 43 | 0 | 51ms |
| declare_scope | 26 | 26 | 0 | 5ms |
| search | 25 | 25 | 0 | 33ms |
| update_task_status | 20 | 20 | 0 | 33ms |
| retrieve_summary | 15 | 15 | 0 | 5ms |
| summarize_work | 15 | 15 | 0 | 62ms |
| todo_extract | 12 | 12 | 0 | 3ms |
| swarm_command | 11 | 11 | 0 | 44ms |
| test_runner | 11 | 11 | 0 | 776ms |
| knowledge_add | 11 | 11 | 0 | 170ms |
| diff | 10 | 10 | 0 | 31ms |
| web_search | 10 | 10 | 0 | 5ms |
| skill | 6 | 6 | 0 | 44ms |
| get_approved_plan | 5 | 5 | 0 | 4ms |
| check_gate_status | 5 | 5 | 0 | 42ms |
| webfetch | 5 | 5 | 0 | 373ms |
| placeholder_scan | 5 | 5 | 0 | 64ms |
| save_plan | 4 | 4 | 0 | 132ms |
| set_qa_gates | 3 | 3 | 0 | 47ms |
| build_check | 3 | 3 | 0 | 77ms |
| pre_check_batch | 3 | 3 | 0 | 573ms |
| todowrite | 3 | 3 | 0 | 6ms |
| phase_complete | 3 | 3 | 0 | 51984ms |
| get_qa_gate_profile | 2 | 2 | 0 | 10ms |
| lint | 2 | 2 | 0 | 483ms |
| secretscan | 2 | 2 | 0 | 28ms |
| suggest_patch | 2 | 2 | 0 | 3ms |
| evidence_check | 2 | 2 | 0 | 5ms |
| write_retro | 2 | 2 | 0 | 104ms |
| sbom_generate | 2 | 2 | 0 | 2ms |
| write_drift_evidence | 2 | 2 | 0 | 5ms |
| sast_scan | 1 | 1 | 0 | 18ms |
| gitingest | 1 | 1 | 0 | 876966ms |
| diff_summary | 1 | 1 | 0 | 89ms |
| question | 1 | 1 | 0 | 8181ms |
| spec_write | 1 | 1 | 0 | 14ms |
| knowledge_query | 1 | 1 | 0 | 10ms |
| req_coverage | 1 | 1 | 0 | 4ms |
| symbols | 1 | 1 | 0 | 11ms |
| batch_symbols | 1 | 1 | 0 | 18ms |
