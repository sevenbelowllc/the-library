---
name: review
description: "Validate a specific completion claim against running code. Verdict: VERIFIED, PARTIAL, or FAILED — with evidence. Enforces evidence before claims."
---

# library:review — Completion Validation

Verify that claimed work is actually done. Evidence before assertions.

## When to Use

- Before closing a PM task
- Before claiming a feature is complete
- When reviewing another session's work
- Before creating a PR or merging

## Process

### Step 1: Identify Claim
What is being claimed complete? Get specific:
- Task ID (if PM tracked)
- Feature name
- What "done" means for this item

### Step 2: Gather Criteria
From the spec and vault, identify what "complete" requires:
- Code exists?
- Tests exist and pass?
- Endpoint/UI responds correctly?
- Edge cases handled?
- No regressions?

### Step 3: Run Verification
For each criterion, run the actual check:

```
Criterion: "Auth middleware validates JWT"
Command: npm test -- --grep "auth" 
Result: [actual test output]
```

Do NOT rely on:
- Code review alone (code existing ≠ code working)
- Previous session's claims
- Memory entries without fresh verification

### Step 4: Verdict

**VERIFIED** — All criteria pass. Evidence attached.
**PARTIAL** — Some criteria pass, others fail. List what's missing.
**FAILED** — Critical criteria fail. List failures with evidence.

### Step 5: Update Records
- Call `library:pm:update` with verdict and evidence
- If VERIFIED: transition task to done
- If PARTIAL/FAILED: add comment with findings, keep task open
- Update vault wiki article if it had a `[VERIFY]` tag for this item

## Iron Rule

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in THIS session, you cannot claim it passes.

## Token Budget

**Weight:** Light-Medium
**Estimated context cost:** ~1200 tokens
**Subagent delegation:** No

## MCP Tools Used

- `library:pm:update` — update task with verdict
- `library:vault:parse` — check for related [VERIFY] tags
- `library:config:get` — project settings
