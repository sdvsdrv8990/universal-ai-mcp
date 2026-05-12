# MCP Tool API Reference

All tools are exposed via MCP. Connect via HTTP/SSE with Bearer auth.

---

## Planning Module

### `task_analyze`
Classify task complexity and return clarifying questions.
- **Required before**: `task_plan_build`
- **Input**: `task_description: str`, `session_id: str?`
- **Output**: `{session_id, complexity, questions[], instruction}`

### `task_plan_build`
Build an ExecutionPlan from task + answered questions.
- **Input**: `task_description`, `complexity`, `answers (JSON)`, `session_id`
- **Output**: `{plan_id, title, steps[], selected_tools[], justifications, estimated_tokens}`

### `task_plan_approve`
Approve plan — enables execution.
- **Input**: `plan_id`, `session_id`
- **Output**: `{approved: true, plan_id}`

### `task_plan_status`
Get current plan progress.
- **Input**: `session_id`
- **Output**: `{plan_id, approved, steps_total, steps_completed, steps_pending}`

---

## Context Module

### `context_add_content`
Convert raw text/code to IdeaBlocks.
- **Input**: `content`, `session_id`, `source_ref?`
- **Output**: `{blocks_created, source_tokens, compressed_tokens, compression_ratio}`

### `context_get_xml`
Get context as compact IdeaBlock XML.
- **Input**: `session_id`, `tags_filter?`
- **Output**: XML string

### `context_token_usage`
Report token budget status.
- **Input**: `session_id`
- **Output**: `{used_tokens, budget_tokens, utilization, status}`

### `context_compress_now`
Force immediate compression.
- **Input**: `session_id`
- **Output**: `{before_tokens, after_tokens, blocks_removed}`

---

## LLM Module

### `llm_complete`
Send prompt to configured provider.
- **Input**: `prompt`, `system_prompt?`, `tier?`, `provider?`, `max_tokens?`
- **Output**: `{content, provider, model, input_tokens, output_tokens}`

### `llm_list_providers`
List configured providers.
- **Output**: `{providers: [{name, enabled, default_model, priority}]}`

### `llm_list_models`
List available models for a provider.
- **Input**: `provider`
- **Output**: `{provider, models[]}`

---

## Project Detection Module

### `project_detect`
Auto-detect project stack and conventions.
- **Input**: `project_path`, `session_id?`
- **Output**: `{session_id, project, language, frameworks[], conventions, has_docker, has_ci}`

### `project_recommend_stack`
Get AI-powered stack recommendation.
- **Input**: `project_description`, `team_size?`, `deployment_target?`, `constraints?`
- **Output**: Stack recommendation JSON (see `config/stack_templates.yaml` for format)

### `project_adapt_name`
Rewrite a name to match project conventions.
- **Input**: `name`, `session_id`, `kind?` (file | test_file | directory)
- **Output**: `{original, adapted, convention}`

---

## Solutions Module

### `solutions_find`
Search GitHub for ready solutions.
- **Input**: `requirement`, `language?`, `min_stars?`
- **Output**: `{results: [{name, stars, description, url, license}]}`

### `solutions_optimize_deps`
Identify minimum required dependencies.
- **Input**: `library_name`, `features_used`, `dependency_tree`
- **Output**: `{required[], optional_omit[], lighter_alternatives[], security_flags[]}`

### `solutions_plan_integration`
Generate layer-by-layer integration plan.
- **Input**: `solution_name`, `target_feature`, `session_id`
- **Output**: `{layers: [{name, order, source_code, integration_code, target_file, docs}]}`

---

## Workflow Module

### `workflow_execute_plan`
Execute approved plan.
- **Requires**: approved plan in session
- **Input**: `session_id`, `project_path`
- **Output**: `{tasks_total, tasks_completed, tasks_failed, results[]}`

### `workflow_verify_work`
Verify completed work against objective.
- **Input**: `session_id`
- **Output**: `{objective_achieved, gaps[], overall_status, next_actions[]}`

### `workflow_save_state`
Persist state to `.planning/`.
- **Input**: `session_id`, `project_path`

### `workflow_load_state`
Restore plan from `.planning/`.
- **Input**: `plan_id`, `session_id`, `project_path`

### `workflow_append_context`
Add decision to `CONTEXT.md`.
- **Input**: `key`, `value`, `project_path`
