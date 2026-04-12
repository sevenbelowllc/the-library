---
name: plan
description: "Convert a spec or design document into PM epics and tasks. Parses sections, extracts deliverables, maps to project hierarchy."
---

# library:plan — Spec to PM Tasks

Turn a design spec into a structured set of PM epics and tasks.

## When to Use

- After a design spec is approved (brainstorming output)
- When a new initiative needs to be broken into trackable work
- When importing requirements from external documents

## Process

### Step 1: Read Spec
Take a spec file path as input. Read and parse:
- Sections and subsections
- Deliverables (features, components, modules)
- Dependencies between deliverables
- Build order (if specified)

### Step 2: Map to PM Hierarchy
- Spec → Epic (one epic per major section)
- Section deliverables → Tasks under that epic
- Apply labels based on content: `core`, `ui`, `infra`, `security`

### Step 3: Present Plan
Show the proposed PM structure:
```
Epic: "Vault Module"
  - Task: "Implement vault init" [core]
  - Task: "Implement vault validate" [core]
  - Task: "Implement vault parse" [core]
  - Task: "Write vault tests" [core]
```

### Step 4: Create (with approval)
Ask: "Create these N epics and M tasks?"
- Call `library:pm:create_epic` for each epic
- Call `library:pm:create_task` for each task, linked to its epic

### Step 5: Link Back
Add a comment on each created epic linking to the source spec file.

## MCP Tools Used

- `library:pm:create_epic` — create epics
- `library:pm:create_task` — create tasks
- `library:pm:update` — add link-back comments
- `library:config:get` — project keys
