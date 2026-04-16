# capstone-proposal-and-architecture — Session Checkpoint

> **Session Date:** 2026-04-15
> **Status:** CAPSTONE-PROPOSAL.html created in library-reading-room/research/ with 5 proposal sections + platform overview. Branding partially corrected but user flagged hallucination on brand colors — needs review against brandkit.html. Architecture decisions locked in but not yet recorded in DECISIONS.md.
> **Next Session:** 1. CRITICAL: Open library-reading-room/branding/brandkit.html in browser and visually match all colors, gradients, and logo usage in CAPSTONE-PROPOSAL.html against the actual brandkit. The current proposal has brand color variables from brandkit but the hero layout and overall styling may still not match the actual brand system. Do NOT guess at branding — open both files side by side. 2. User wants Compliance OS platform overview section in proposal — verify the feature descriptions match current code, not spec aspirations. 3. Address remaining proposal gaps before submission.

---

## 1. What Was Accomplished

- Analyzed full DEIOCAP Jira project: 116 issues mapped (12 epics, 57 tasks, 47 test artifacts)
- Read complete CAPSTONE.md (18 sections), AI-AGENTS.md (full spec), AI-ONBOARDING-UI-SPEC.md, AI-ONBOARDING-COMPONENT-ARCHITECTURE.md, SCOPE.md
- Identified gaps in DEIOCAP: missing Posture Visualizer epic, missing AI Onboarding Frontend epic, missing Capstone Deliverables epic, AI Provider Key Management removed from core scope
- Established revised flow priority: Flow 1 AI Onboarding (core), Flow 2 LangFuse Observability (core), Flow 3 Posture Visualizer (core), Flow 4 Dashboards Part 1 — Agent Command Center + Compliance Posture (core), Flow 5 Pipeline Ingestion (stretch), Flow 6 Threat Correlation (stretch), Flow 7 Threat Dashboard (stretch)
- Locked architecture decisions: FastAPI for agent-core, single frontend with BFF API routes (not two frontends), agent-core internal only (ClusterIP no public Ingress), GCP Pub/Sub for job queue (NOT PostgreSQL as queue — user explicitly rejected pg_notify pattern), Socket.io for result delivery to browser, request-per-message pattern, one-directional communication (agent-core calls compliance-core, never reverse), agent-core direct DB for own tables but MCP for compliance-core tables
- Analyzed compliance-core backend architecture in depth: Express middleware chain, Clerk auth flow, Docker/K8s deployment, Socket.io setup, CORS config, no API gateway pattern
- Created CAPSTONE-PROPOSAL.html with Mermaid diagrams: system architecture, domain ERD, agent data layer ERD, coverage state machine, onboarding sequence diagram, onboarding phases flow, job queue architecture, LangFuse trace structure, pipeline ingestion flow, communication protocol map
- Wrote Success Metrics section: <20 min onboarding, <$3.00 cost, 60%+ coverage, 100% guardrail pass rate, 35-40 min full demo
- Wrote Data Quality section: 7 onboarding guardrails (core), pipeline validation/dedup/error handling/freshness SLAs (stretch)
- Wrote stakeholder value comparison (before/after)
- Added Compliance OS platform overview section with current capabilities

## 3. What's Next

1. FIX BRANDING: Open brandkit.html in browser side by side with CAPSTONE-PROPOSAL.html and correct ALL visual discrepancies — user explicitly called out hallucination on brand colors. The brandkit has base64-encoded logo variants (Icon Mark, Full Lockup, Wordmark in light/dark variants) — extract and use the correct ones instead of guessing
2. VERIFY PLATFORM OVERVIEW: The Compliance OS capabilities section lists features from SCOPE.md — verify each one actually exists in compliance-core and compliance-ui code before claiming it is built. User cares about accuracy
3. RECORD ARCHITECTURE DECISIONS: Add to library-reading-room/specs/DECISIONS.md: DEC-AI-011 FastAPI for agent-core, DEC-AI-012 Single frontend with BFF (not two frontends), DEC-AI-013 GCP Pub/Sub for job queue (rejected pg_notify), DEC-AI-014 agent-core internal only (ClusterIP), DEC-AI-015 Socket.io for result delivery
4. JIRA PLAN: User said wait for command — do NOT create Jira issues until explicitly told. The proposed plan includes: create 3 new epics (AI Onboarding Frontend, Posture Visualizer Agent, Capstone Deliverables), label stretch on DEIOCAP-4/5/6/7/10 and tasks 25/26/55/56, reprioritize dashboard tasks (54=P0, 57=P1, 55=P2, 56=stretch), user will delete 47 test artifacts themselves
5. OPEN QUESTIONS: Vercel plan not confirmed (determines SSE timeout for BFF), OpenClaw deployment model (embedded vs separate container), LangFuse deployment (own Cloud SQL or shared), whether onboarding UI iterates on V4 wizard code (user said yes — reuse existing two-panel/D3/chat components)
6. PROPOSAL SUBMISSION: User said due today (2026-04-15). Remaining gaps: formal Mermaid ER diagram rendering verification, branding accuracy, platform overview accuracy

## 5. Key Context

- User is David Kramer building capstone for DataExpert.io Spring 2026 AI Engineering Boot Camp (instructor Zach Wilson)
- Capstone proposal criteria: 1-Project Description/Scope 2-Conceptual Data Model and Diagram 3-Tools Data Sources Formats 4-Ingestion Strategy Data Quality Checks 5-Success Metrics Stakeholder Value
- User's VP of Engineering recommended BFF pattern — this influenced the single-frontend decision over two-frontend approach
- User STRONGLY rejected using PostgreSQL as a message queue or pg_notify — called it a database killer and rookie decision. Use GCP Pub/Sub only
- User removed AI Provider Key Management from core scope — keys configured via env vars and Secret Manager during deployment, no admin UI needed for capstone
- Dashboard priority: Compliance Posture (P0 hard requirement), Agent Command Center (P1), Threat Intelligence (P2 stretch), GCP Operations (stretch of stretch)
- Existing Wizard V4 code at compliance-ui/src/features/onboarding/ has ~50 files with two-panel layout, D3 vizzes, chat sidebar — user wants to iterate on this, not clean-room rebuild
- The proposal file is at library-reading-room/research/CAPSTONE-PROPOSAL.html — it is an HTML file with embedded Mermaid.js diagrams that render in browser
- Brand colors from brandkit: Cyan #00D4FF, Blue #5AAEE6, Purple #7A82DC, Magenta #D21EDC. Brand gradient: cyan to blue to purple to magenta. Action gradient: pink-600 #db2777 to purple-600 #9333ea. Brand-short gradient: cyan-500 #06b6d4 to blue-600 #2563eb
- The SevenBelow logo is described as a shield with integrated S letterform, circuit nodes, and data particles — available as sevenbelow-logo.png (icon) and sevenbelow-wordmark.png. Compliance OS logomark is at compliance-ui/public/compliance-os-logomark.svg (shield with checkmark and data nodes)
