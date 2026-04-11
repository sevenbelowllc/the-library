---
name: audit
description: "Three-way gap analysis: canonical specs vs vault wiki vs actual code. Finds missing features, claimed-but-broken, and undocumented implementations."
---

# library:audit — Spec vs Code Gap Analysis

The skill that prevents "features claimed complete but actually broken."

## When to Use

- Before starting a new development cycle
- After claiming a milestone is complete
- Periodically to detect drift between spec, docs, and code
- When onboarding to understand true project state

## Process

### Step 1: Load Sources
1. **Specs**: Read files from `specs.path` in config
2. **Vault**: Call `library_vault_parse` for wiki articles and tags
3. **Code**: Read project structure, test files, key source files

### Step 2: Extract Claims
From specs: what SHOULD exist (features, endpoints, behaviors)
From vault wiki: what is CLAIMED to exist
From code: what ACTUALLY exists (files, functions, tests, routes)

### Step 3: Three-Way Diff

| Spec Says | Vault Says | Code Shows | Verdict |
|-----------|-----------|------------|---------|
| Feature X | Implemented | Code exists, tests pass | VERIFIED |
| Feature X | Implemented | Code exists, no tests | UNVERIFIED |
| Feature X | Implemented | Code missing | CLAIMED-BUT-BROKEN |
| Feature X | Not mentioned | Code exists | UNDOCUMENTED |
| Feature X | Not mentioned | Code missing | MISSING |
| Not in spec | Implemented | Code exists | SCOPE CREEP |

### Step 4: Dependency Analysis (if Graphify enabled)
For each broken/missing item:
- Call `library_graph_query`: "What depends on <item>?"
- Report cascade impact

### Step 5: Generate Report
Output structured gap report:
- VERIFIED: N items (green)
- UNVERIFIED: N items (yellow — need tests)
- CLAIMED-BUT-BROKEN: N items (red — urgent)
- MISSING: N items (red — not started)
- UNDOCUMENTED: N items (yellow — need vault update)
- SCOPE CREEP: N items (orange — discuss)

### Step 6: Create Tasks (optional)
Ask: "Create PM tasks for gaps?"
If yes, call `library_pm_create_task` for each actionable gap.

## MCP Tools Used

- `library_vault_parse` — vault state
- `library_graph_query` — dependency analysis
- `library_pm_create_task` — create tasks for gaps
- `library_config_get` — specs path, project keys
