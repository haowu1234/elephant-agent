# System Design

This directory stores the managed product-facing architecture for `elephant`.

The canonical design fact for the cognition and continuity model now lives in
the two system layer documents below. Older design drafts, graph-heavy target
architecture notes, and plan-shaped design documents were removed so new ADRs,
plans, task cards, and implementation docs can be rebuilt from one source of
truth.

## Current Inventory

- [system-layer-model.md](system-layer-model.md)
  - the implementation mechanism behind the public agency-first, L4 personal-AI
    positioning
  - the canonical Understanding System model for Personal Model claims,
    Evidence, Questions, Episodes, Elephant State, and Steps
  - the canonical prompt boundary for active claims, current-turn recall support, and
    Episode opening resume snapshots
  - the canonical claim-aware search contract for `tool.personal_model.search`,
    including `auto` / `inventory` modes, query variants, no-match status, and
    diagnostics
  - the canonical removal boundary for memory-note, component taxonomy,
    State task fields, and SkillAffinity-style adaptive skill ranking
- [context-engineering-research.md](context-engineering-research.md)
  - research note comparing Elephant Agent context engineering with Codex,
    Hermes Agent, OpenClaw, RTK, LoCoMo / locomotive, and vLLM
  - capability assessment across durable understanding, recall, compaction,
    continuity, prompt-cache stability, tool-output pressure, and evaluation
  - optimization directions for making context behavior measurable, adaptive,
    and robust across long-horizon sessions
  - synchronized Chinese companion:
    [context-engineering-research.zh-CN.md](context-engineering-research.zh-CN.md)
- [context-token-efficiency-research.md](context-token-efficiency-research.md)
  - second-pass research focused on prompt cache hit rate, context compression,
    and token savings
  - compares Elephant with the latest fetched Codex, Hermes Agent, OpenClaw,
    RTK, LoCoMo / locomotive, and vLLM snapshots for cache and compression
    design
  - proposes a token efficiency ledger, cache-break diagnostics, pre-provider
    pressure routing, compression coordination, and tool-output shaping
  - synchronized Chinese companion:
    [context-token-efficiency-research.zh-CN.md](context-token-efficiency-research.zh-CN.md)

## Usage Policy

- treat `system-layer-model.md` as the current product-facing system design truth
  in this directory
- rebuild future ADRs, plans, design notes, and implementation docs from the
  layer model instead of resurrecting deleted historical drafts
- keep this directory for product and system design, not contributor workflow
- keep product-facing setup and onboarding language aligned with the shipped
  runtime under `README.md` and `apps/site/`
- keep operator-facing web references aligned with the shipped dashboard under
  `apps/dashboard/`
