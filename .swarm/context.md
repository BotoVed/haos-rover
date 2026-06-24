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
