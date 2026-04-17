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
2. **Vault**: Call `library:vault:parse` for wiki articles and tags
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
- Call `library:graph:query`: "What depends on <item>?"
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
If yes, call `library:pm:create_task` for each actionable gap.

## Subagent Orchestration

For large codebases, delegate file-heavy inventory work to parallel subagents:

### Step 2 (Inventory) — Dispatch 3 parallel Explore subagents:

- **Agent 1 (Specs):** "Inventory the specs/ directory. List each file, extract key claims and requirements. Return a structured summary under 500 words."
- **Agent 2 (Code):** "Inventory the codebase. List GraphQL modules, services, migrations, and key patterns. Return a structured summary under 500 words."
- **Agent 3 (Vault/Wiki):** "Inventory the vault wiki articles. List each article, extract [VERIFY], [CONFLICT], [PLANNED] tags. Return a structured summary under 500 words."

Main context receives ~1500 tokens of structured summaries instead of ~15000+ tokens of raw file reads.

### Step 5 (Verification) — Dispatch targeted verification agents:

For each load-bearing claim in the gap analysis, dispatch a focused Explore subagent:
- "Does compliance-core hardcode DRAFT status anywhere?"
- "Which migrations create the agent_jobs table?"

### Fallback

If the Agent tool is not available (e.g., non-Claude Code environments), fall back to sequential file reads in main context. The skill works either way — subagents are an optimization, not a requirement.

## Token Budget

**Weight:** Medium (was Heavy before subagent refactor)
**Estimated context cost:** ~2000 tokens with subagents, ~15000+ without
**Subagent delegation:** Yes — inventory and verification steps

## MCP Tools Used

- `library:vault:parse` — vault state
- `library:graph:query` — dependency analysis
- `library:pm:create_task` — create tasks for gaps
- `library:config:get` — specs path, project keys
