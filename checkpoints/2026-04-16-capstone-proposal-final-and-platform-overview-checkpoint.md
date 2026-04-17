# capstone-proposal-final-and-platform-overview — Session Checkpoint

> **Session Date:** 2026-04-16
> **Status:** Capstone proposal and platform overview HTML documents finalized, committed, pushed, and bundled as SevenBelow-Capstone-Proposal.zip. Submitted to DataExpert.io bootcamp team. Bug fixes applied to compliance-ui. Architecture decisions locked in.
> **Next Session:** Process capstone proposal feedback from Zach Wilson and bootcamp team. Review any architectural feedback on the multi-agent system, communication protocols, or data model.

---

## 1. What Was Accomplished

- Created COMPLIANCE-OS-PLATFORM-OVERVIEW.html with full product walkthrough, 10 product screenshots, 6 onboarding wizard screenshots, click-to-zoom functionality
- Fixed CAPSTONE-PROPOSAL.html hero branding with actual SevenBelow logo/wordmark and DataExpert.io logo in light pill
- Rewrote platform overview section with product philosophy and accurate copy
- Added multi-agent architecture: Coordinator + Discovery + Document + Controls + Vendor agents with responsibilities and output chain
- Added compliance framework data model ERD showing TENANTS -> TENANT_FRAMEWORKS -> FRAMEWORKS -> FRAMEWORK_DOMAINS -> CRITERIA -> CONTROL_CRITERION_MAPPINGS -> CONTROLS
- Restructured agent data layer schema: replaced AGENT_CONVERSATION + AGENT_MEMORY with ONBOARDING_SESSION + AGENT_MESSAGE + AGENT_JOB + SESSION_ARTIFACT, all with tenant_id FK
- Added onboarding generation flow diagram: Documents -> Activity Run Detection -> Controls -> Vendors -> Monitoring
- Added document approval lifecycle state machine with publish, significance check, effective dates, deprecation
- Added context compaction and session resumption architecture with ~500 token rehydration vs ~30K replay
- Added three-mode agent system: Onboarding core, Resume core, Advisory post-capstone
- Added TipTap JSON/Markdown conversion layer architectural decision with zero-token cost analysis
- Simplified communication protocol: removed Vercel BFF, single entry point via compliance-core api.sevenbelow.com
- Added disclosed scope constraints: POL/SOP only, GCP/AWS only, IdP limits, vendor cap 15-20, all output DRAFT
- Added README.md cover letter with links to both HTML files
- Fixed compliance-ui bugs: preSelectedExcerptId not destructured in CreateActivityModal, document body wiped on activity run save due to re-initializing useEffect, refetchQueries passing GraphQL document objects instead of operation name strings
- Deleted unused compliance-os-logomark.svg and compliance-os-wordmark.svg from compliance-ui/public
- Updated all ERD diagrams to use tenant_id instead of org_id matching actual database schema
- Added tenant_id to EXCERPT, ACTIVITY_RUN, EVIDENCE in domain ERD
- Removed redlining references
- Updated agent table from single Onboarding Consultant to 5-agent architecture
- Fixed Mermaid diagram text to white via JS post-render
- Improved typography with tracking wide and increased spacing

## 3. What's Next

1. Process feedback from Zach Wilson and DataExpert.io bootcamp team on the capstone proposal
2. Address any architectural concerns about multi-agent system, Pub/Sub communication, or data model
3. Record architecture decisions in library-reading-room/specs/DECISIONS.md: DEC-AI-011 through DEC-AI-015 still pending from prior session
4. Begin implementation planning based on approved proposal scope
5. Create Jira epics and tasks for approved capstone work when user gives the command

## 5. Key Context

- Proposal files: library-reading-room/research/CAPSTONE-PROPOSAL.html and COMPLIANCE-OS-PLATFORM-OVERVIEW.html
- Zip bundle built from library-reading-room with sed path rewriting for root-level HTML files
- Brand assets: library-reading-room/branding/sevenbelow-logo.png and sevenbelow-wordmark.png
- DataExpert.io logo: research/platform-overview-assets/dataexpert-wordmark.svg displayed in light pill container
- Architecture locked: FastAPI agent-core ClusterIP in GKE, compliance-core as single public endpoint publishing to Pub/Sub, NO Vercel BFF for agent communication
- Database table is tenants not organizations — all ERDs use tenant_id FK
- Document storage is TipTap JSON with Markdown conversion layer in compliance-backend-mcp for agent I/O
- User strongly rejected pg_notify as job queue — use GCP Pub/Sub only
- All AI-generated content starts as DRAFT — approval workflow required for Effective status
- Document approval lifecycle: first publish always requires approval, subsequent edits check significance, effective dates must be reviewed before expiry
- Vendor cap 15-20 per onboarding, framed as subscription restriction
- ONBOARDING_SESSION.phase_progress JSONB tracks per-department completion for granular resumption
- Context compaction reconstructs ~500 tokens from structured state instead of replaying 30K+ conversation history
- The compliance-ui bug fixes are already committed in bd5f0ea on integration branch
- Mermaid diagram white text requires JS post-render forcing fill #ffffff on all SVG text/tspan elements plus foreignObject divs — CSS !important alone does not work
