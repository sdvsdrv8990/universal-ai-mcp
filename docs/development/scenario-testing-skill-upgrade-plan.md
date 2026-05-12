# Scenario Testing Skill Upgrade Plan

**Status:** temporary working plan  
**Date:** 2026-05-12  
**Owner:** development workflow / skills layer  
**Removal rule:** delete this document after the selected skill changes are implemented, verified, and reflected in the relevant `uai-*` skills.

## Goal

Upgrade the project skills so AI development produces scenario-aware tests and configurable systems instead of shallow unit tests and hardcoded implementation shortcuts.

The target result is not "more tests". The target result is a maintainable scenario matrix that maps real usage paths from user intent through MCP tools, module boundaries, configuration, failure modes, and unit-level invariants.

## Scope

This plan concerns skills and development methodology for `universal-ai-mcp`.

In scope:

- `uai-code-standards`
- `uai-layer-gsd-verification`
- `uai-layer-orchestrator`
- `uai-planning-gate`
- test strategy documentation and control checkpoints

Out of scope:

- shipping skill files inside the server package
- changing runtime code before the skill plan is approved
- adding dependencies before a concrete implementation step needs them
- writing broad test suites without a scenario matrix

## Candidate Skills

| Priority | Skill | Upgrade |
|---|---|---|
| 1 | `uai-code-standards` | Add a full anti-hardcode and AI-code-debt taxonomy |
| 2 | `uai-layer-gsd-verification` | Add scenario matrix verification and test evolution rules |
| 3 | `uai-layer-orchestrator` | Add auditor personas for scenario coverage, architecture risk, and AI-code hardcode patterns |
| 4 | `uai-planning-gate` | Require scenario mapping before implementation for non-trivial code changes |
| 5 | `uai-layer-gsd-state-persist` | Store scenario/test evolution artifacts when persistent planning is needed |

## Scenario Matrix Contract

Every non-trivial feature or module change should produce or update a scenario matrix with these fields:

| Field | Purpose |
|---|---|
| `scenario_id` | Stable identifier, reused when the scenario evolves |
| `user_intent` | Real user/system goal, not a function name |
| `system_phase` | Relevant orchestrator or workflow phase |
| `mcp_tools` | Public tool calls touched by the scenario |
| `module_boundary` | Python module/class/function boundary under test |
| `config_profile_dependency` | YAML profile, provider, timeout, limit, or feature flag dependency |
| `expected_contract` | Observable behavior that must remain true |
| `failure_modes` | Broken inputs, missing providers, invalid state, denied paths, etc. |
| `anti_hardcode_risks` | Literal paths, models, URLs, magic numbers, feature flags in code |
| `test_files` | Existing or planned tests that cover this scenario |
| `update_policy` | `update`, `create`, `deprecate`, or `merge` when requirements change |

## Test Layer Taxonomy

Use the smallest set of tests that covers the scenario across layers:

| Layer | Purpose | Typical Tooling |
|---|---|---|
| User scenario | Proves the real workflow works end to end through MCP-facing behavior | pytest integration tests, pytest-bdd if useful |
| Tool contract | Proves MCP tools return stable JSON and graceful errors | pytest, json schema-style assertions |
| Module integration | Proves module boundaries cooperate without an MCP client | pytest, pytest-httpx for HTTP clients |
| Unit invariant | Proves pure logic and entity lifecycle rules | pytest |
| Property/fuzz | Proves broad input spaces and edge cases | Hypothesis |
| Mutation check | Proves tests fail when behavior is meaningfully changed | mutmut or Cosmic Ray |
| Affected-test selection | Keeps test execution incremental as modules evolve | pytest-testmon |

## Anti-Hardcode Taxonomy

`uai-code-standards` should be extended to flag these patterns:

- hardcoded provider or model names outside YAML config
- hardcoded URLs, ports, paths, artifact roots, cache roots, and hostnames
- magic numbers for limits, thresholds, retries, timeouts, token budgets, and batch sizes
- feature flags implemented as Python literals instead of `workflow_profiles.yaml`
- conditional chains over literal strings where an enum, registry, or config map should exist
- duplicated literal contracts across `tools/`, `modules/`, tests, and docs
- inline fallback chains with no documented removal condition
- AI-generated over-defensiveness: unnecessary `isinstance` walls, broad `except Exception`, silent fallbacks
- direct provider calls that bypass `LLMRouter.complete()`

Allowed literals must be part of an explicit contract, enum, test fixture, or documented default.

## Implementation Phases

### Phase 1 - Skill Contract Updates

Files:

- `/home/admin/.claude/skills/uai-code-standards/SKILL.md`
- `/home/admin/.claude/skills/uai-layer-gsd-verification/SKILL.md`

Actions:

- Add anti-hardcode checklist to `uai-code-standards`.
- Add scenario matrix and test evolution rules to `uai-layer-gsd-verification`.
- Keep skill text concise; skills are loaded into AI context and must stay practical.

Control point:

- A reviewer can use the skills to decide whether to update an existing scenario test or create a new one.

### Phase 2 - Orchestrator Auditor Upgrade

Files:

- `/home/admin/.claude/skills/uai-layer-orchestrator/SKILL.md`
- optionally `config/orchestrator.yaml` only after a runtime change is explicitly approved

Actions:

- Add `Scenario Coverage Auditor`.
- Add `Architect Auditor`.
- Add `AI-Code Hunter`.
- Define what each auditor persona must block on with `severity=high`.

Control point:

- High severity must block only for structural risks: missing scenario coverage for changed public behavior, unconfigured hardcoded runtime values, broken module boundaries, or unsafe fallbacks.

### Phase 3 - Planning Gate Upgrade

Files:

- `/home/admin/.claude/skills/uai-planning-gate/SKILL.md`

Actions:

- Require scenario matrix planning for medium/complex changes.
- Add a planning question: "Which existing scenario should be updated instead of creating a new test?"
- Add a planning output section: "Test evolution decision".

Control point:

- The plan must identify scenario coverage before implementation starts.

### Phase 4 - Optional Tooling Evaluation

External candidates:

- `pytest-bdd` for readable Given/When/Then scenario tests
- `Hypothesis` for property-based tests
- `Pact` for consumer/provider contract tests
- `Schemathesis` for API/schema fuzzing if OpenAPI or GraphQL contracts are introduced
- `mutmut` or `Cosmic Ray` for mutation testing
- `pytest-testmon` for affected-test selection

Control point:

- Do not add a dependency unless it covers a concrete scenario gap in this project.

### Phase 5 - Runtime Test Structure

Files:

- `tests/scenarios/` if accepted as a new test category
- `tests/integration/`
- `tests/unit/`

Actions:

- Introduce scenario tests only after skill updates are in place.
- Map every new scenario test to a scenario matrix entry.
- Prefer updating existing scenario files over creating near-duplicate tests.

Control point:

- Test growth must be explainable by scenario coverage, not by line coverage alone.

## Done Criteria

- `uai-code-standards` contains anti-hardcode review rules for AI-generated code.
- `uai-layer-gsd-verification` contains a scenario matrix contract and test evolution rules.
- `uai-layer-orchestrator` defines auditor personas for scenario, architecture, and AI-code risks.
- `uai-planning-gate` asks for scenario mapping before medium/complex implementation.
- The first runtime test change after this plan references the scenario matrix.
- This temporary document is either deleted or replaced by permanent concise skill content.

## Notes

The project rule still stands: `uai-*` skills are development aids, not server artifacts. They must not be imported, packaged, or referenced by runtime code.
