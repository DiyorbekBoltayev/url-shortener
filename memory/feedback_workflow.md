---
name: Orchestrator-based parallel agent workflow
description: How to run large implementation tasks for this user with parallel teams and review step
type: feedback
---

User wants: orchestrator agent (main Claude) keeps global picture; parallel coding teams per service; each coding agent's output goes to a review agent before being considered done.

**Why:** User explicitly stated "har bir coding agent ishni tugatganda nima soralgandi nima qilindi tekshirib ol va review agentga berib review qldri va bitta agent yuqoridan image ni tasavurida ushlab tursin". Prevents quality drift across parallel streams.

**How to apply:**
- Research phase: spawn parallel research subagents before coding.
- Implementation: one coding agent per service (parallel), each briefed with full spec + deliverables checklist.
- After each coding agent returns, verify outputs, then spawn a review subagent for that service.
- Maintain a tracking doc (ORCHESTRATOR.md) updated after each phase: who did what, what's next, open issues.
- Never delegate synthesis — orchestrator reads results and decides next steps.
