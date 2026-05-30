# Context Engineering Research

## Status

Research note for Elephant Agent context engineering, prepared in the
`research/elephant-context-engineering` worktree on 2026-05-29.

This document does not replace
[system-layer-model.md](system-layer-model.md). The layer model remains the
canonical product-facing source of truth. This note evaluates the current
design, compares third-party agent projects under `research/`, and proposes
next optimization directions.

Synchronized Chinese companion:
[context-engineering-research.zh-CN.md](context-engineering-research.zh-CN.md).

## Scope

Context engineering means the system behavior that decides what the model sees,
what the system persists, what gets recalled, what is compressed, and what gets
learned for future turns.

For Elephant Agent, that includes:

- Personal Model active claims and four-lens prompt projection.
- Elephant State, Episode, Loop, and Step trail continuity.
- Step and Fact indexing through the SemanticIndexEntry layer.
- Current-turn contextual recall.
- Session projection, frozen prefixes, resume snapshots, and compaction.
- Background reflection and proactive curiosity.
- Tool, skill, and runtime capability disclosure.
- Observability and evaluation of recall, compaction, and learned claims.

## Sources Inspected

Elephant Agent sources:

- `docs/system-design/system-layer-model.md`
- `docs/agent/governance.md`
- `docs/agent/change-surfaces.md`
- `packages/context/**`
- `packages/evidence/**`
- `packages/semantic_index/**`
- `packages/continuity/**`
- `packages/understanding/**`
- `packages/reflect/**`
- `packages/curiosity/**`
- `apps/cli/runtime_cognition.py`

Third-party repositories were fetched from their remotes before comparison:

| Project | HEAD inspected | Context-engineering role |
| --- | --- | --- |
| Codex | `740d942f90` | Thread transcript, context diffing, prompt-cache-aware runtime, memory extension |
| Hermes Agent | `db2ce9e7d` | SQLite session store, compression engine, provider-aware context budgeting |
| OpenClaw | `00ca654c74` | Pluggable context engine contract, prompt-cache diagnostics, session runtime |
| RTK | `5a149a7` | External command-output token reduction |
| LoCoMo / locomotive | `3eb6f2c` | Long-term conversational-memory benchmark and generated-agent memory utilities |
| vLLM | `ff990d0d32` | Serving substrate; not a comparable agent context architecture |

## Elephant Baseline

Elephant Agent has a clear north star: it is an understanding system, not a
memory database. The current system design separates durable understanding from
raw trace and retrieval:

- Personal Model stores governed active claims across `identity`, `world`,
  `pulse`, and `journey`.
- Steps are canonical evidence. Facts reference source episodes instead of
  depending on a separate evidence table.
- SemanticIndexEntry points at Steps or Facts, keeping vector recall as an
  index over canonical records rather than a second source of truth.
- Current-turn recall is volatile model support. Active Personal Model claims
  are stable prompt truth.
- Background learning turns episodes into claims, questions, diary entries,
  skills, compression summaries, and dream-like synthesis.

The implementation largely matches that model:

- `packages/context` owns context assembly, session projection, frozen prefixes,
  token budgets, traces, and compaction.
- `packages/evidence` owns unified recall orchestration and Step-based evidence
  access.
- `packages/understanding` owns foreground Personal Model search and update
  surfaces.
- `packages/continuity` owns episode resume and interruption state.
- `packages/reflect` owns deterministic extraction, feature-composed reflection,
  and compaction support.
- `packages/curiosity` owns proactive question generation and ask policy.
- `apps/cli/runtime_cognition.py` composes the runtime prompt contract without
  becoming the canonical owner of memory behavior.

## Third-Party Comparison

### Codex

Codex centers context engineering around a thread transcript manager. Its
`ContextManager` tracks model-visible history, token usage, history rewrites,
and a `reference_context_item` baseline used for context-state diffing and
reinjection. This is strong runtime engineering: context can be rewritten,
rolled back, normalized for prompt use, and compared against a stable baseline.

Codex memory is extension-shaped. The memories extension contributes developer
policy prompt fragments and optional read tools when the feature is enabled.
That is a compact integration boundary, but the durable user model is not the
core organizing principle.

Useful ideas for Elephant:

- Prompt-state diffing instead of full stable-prefix reinjection where safe.
- Explicit history-versioning around compaction and rollback.
- Prompt-cache-aware context stability diagnostics.

### Hermes Agent

Hermes is pragmatic and operations-heavy. It stores full session history,
session metadata, model configuration, and FTS5 search in SQLite. Its context
compressor protects the head and recent tail, prunes old tool results, uses
provider-aware context-length detection, estimates full request tokens including
tool schemas, and backs off when compression is ineffective.

Hermes has broad provider support and durable session mechanics, but the core
loop is more monolithic than Elephant's package-layered design. Memory,
context, compression, provider behavior, and CLI/runtime concerns sit closer
together.

Useful ideas for Elephant:

- Track tool-schema token cost as a first-class budget bucket.
- Surface compression ineffectiveness and manual focused compression paths.
- Keep provider context-length discovery visible to context planning.

### OpenClaw

OpenClaw has the strongest pluggable context-engine contract among the
third-party agent projects inspected. Its `ContextEngine` interface defines
bootstrap, ingest, ingestBatch, afterTurn, assemble, compact, maintenance,
runtime LLM capabilities, safe transcript rewrite hooks, and subagent spawn
preparation. It also models prompt-cache snapshots and cache-break diagnostics
across system prompt, tool set, model, transport, and stream strategy.

OpenClaw emphasizes hot-path discipline: prepared facts move forward through
runtime surfaces, prompt capability IDs are normalized and sorted, and context
engines declare host requirements rather than relying on hidden coupling.

Useful ideas for Elephant:

- Treat context runtime capabilities as an explicit contract.
- Add prompt-cache break diagnostics to context traces.
- Consider safe transcript rewrite helpers for compaction and maintenance.
- Make background context maintenance schedulable and observable.

### RTK

RTK is not a memory system. It is a command proxy that reduces command output
before it reaches the agent context. Its design is still relevant because tool
output is one of the fastest ways to blow a context budget. RTK uses
command-specific filtering, grouping, truncation, deduplication, token-savings
tracking, transparent raw-output escape hatches, and fail-safe fallback to
original output.

Useful ideas for Elephant:

- Add a tool-output context policy before outputs enter Step projection.
- Track per-tool token savings, not only final prompt token counts.
- Preserve a raw-output recovery path for audit.

### LoCoMo / locomotive

LoCoMo is best treated as an evaluation lens. Its data model includes long-term
sessions, observations, session summaries, event summaries, evidence IDs, and
QA tasks. The generative-agent utilities extract session facts, generate
self/other reflections, and retrieve relevant facts by embedding similarity.

Useful ideas for Elephant:

- Build long-horizon QA tests where answers require evidence across sessions.
- Evaluate event-summary and session-summary preservation after compaction.
- Score recall by evidence IDs, not only by answer plausibility.

### vLLM

vLLM is a model-serving and inference performance project. It can inform
deployment choices for large-context local or hosted models, but it does not
provide comparable agent context engineering logic.

## Capability Assessment

Scale:

- L0: absent
- L1: ad hoc
- L2: present but local or weakly governed
- L3: coherent implementation with gaps
- L4: strong, inspectable, and mostly product-aligned
- L5: benchmarked, adaptive, and production-proven across long horizons

| Dimension | Level | Assessment |
| --- | ---: | --- |
| Architecture source of truth | L4 | The five-layer Understanding System is clear and repo-native. Remaining risk is drift between design, CLI projection, and tests. |
| Durable personal understanding | L4 | Four-lens active claims, provenance, status, confidence, and claim-aware search form a strong Personal Model. Needs stronger expiry, conflict, and correction lifecycle metrics. |
| Evidence and provenance | L4 | Steps as evidence is a clean model. Fact source episodes and index pointers avoid duplicate truth. Needs richer user-facing "why" traces and quality scoring. |
| Current-turn recall | L3.5 | Hybrid semantic, lexical, CJK, fuzzy, confidence, and polarity signals are strong. Needs benchmarked recall precision/recency/conflict behavior. |
| Context assembly and token budgeting | L4 | Layered planner, frozen prefix, session projection, request attachments, source traces, and budgets are strong. Needs dynamic budget adaptation from observed outcomes. |
| Compaction and overflow recovery | L3.5 | Reflect-first compression with deterministic fallback and protected tails is sound. Needs loss audits, recovery checks, and benchmarked summary quality. |
| Continuity and resume | L3.5 | Episode continuity state, frozen epochs, resume snapshots, and interruption modes are coherent. Needs long-horizon resume tests across compaction and provider changes. |
| Background learning | L3.5 | Feature-composed reflect jobs are flexible. Needs stronger review gates, rollback paths, and calibration for high-impact learned claims. |
| Proactive curiosity | L3 | Lens/topic-bound question policy avoids profile-filling. Needs outcome scoring, cadence learning, and user-fatigue telemetry. |
| Tool and skill disclosure | L3.5 | Frozen skill/tool projection avoids eager churn. Needs lazy retrieval and schema-cost accounting to reduce prompt bloat. |
| Prompt-cache stability | L2.5 | Stable prefix design helps, but explicit cache-break measurement is less developed than OpenClaw/Codex patterns. |
| Observability and evaluation | L2.5 | The harness and traces are good, but context-quality benchmarks are still early. Needs LoCoMo-style evidence-scored suites and production scorecards. |
| Plugin/provider scalability | L3 | Core package boundaries are clean. Needs more explicit context-engine capability contracts and hot-path prepared facts for external providers/plugins. |
| Tool-output pressure control | L2.5 | Context compaction handles outputs after the fact. RTK-style pre-ingest output shaping is an open opportunity. |

Overall: Elephant is already L4 in product model clarity and core layered
architecture, L3 to L3.5 in adaptive runtime quality, and L2.5 to L3 in
benchmarked observability. The next step is less "invent memory" and more
"measure, adapt, and harden context behavior under long-horizon pressure."

## Priority Optimization Directions

1. Add a context engineering scorecard.
   Track stable-prefix size, current-turn recall size, active claims injected,
   prompt-cache continuity, compaction count, retrieved evidence IDs, no-match
   rates, question outcomes, and final token budget allocation per turn.

2. Build a LoCoMo-inspired evaluation suite.
   Include multi-session facts, stale Pulse correction, disputed claims,
   long-horizon event summaries, compaction-after-recall cases, and evidence ID
   grading.

3. Strengthen claim lifecycle governance.
   Add claim volatility, expiry, correction precedence, conflict handling,
   claim-local aliases, and multilingual pivot text generated at write time.

4. Improve recall diagnostics.
   Report why strong, weak, or no match happened; distinguish missing evidence,
   stale evidence, conflicting evidence, and low-confidence semantic matches.

5. Harden compaction quality.
   Add summary loss checks, semantic anchors, post-compaction recall probes,
   raw Step recovery references, and metrics comparing reflect compression with
   deterministic fallback.

6. Make prompt-cache stability observable.
   Track stable-prefix fingerprints, tool-set digests, model/provider changes,
   and cache read/write deltas so runtime context changes can be explained.

7. Add pre-ingest tool-output shaping.
   Apply command/tool-specific summaries before large outputs become prompt
   pressure, while preserving raw Step evidence for audit.

8. Make context runtime capabilities explicit.
   Borrow the useful part of OpenClaw's contract shape: declare whether a
   context engine supports bootstrap, assemble, after-turn maintenance,
   compact, runtime LLM calls, thread bootstrap, and safe transcript rewrite.

9. Expand lazy tool and skill disclosure.
   Keep the stable prompt compact while retrieving tool/skill details only when
   the active task needs them. Track schema token cost separately.

10. Add user-controllable context modes.
    Modes such as `narrow`, `balanced`, `research`, and `continuity-heavy`
    should map to recall breadth, claim inclusion, compaction aggressiveness,
    and question cadence.

## Recommended Next Worktree Slices

| Slice | Write scope | Outcome |
| --- | --- | --- |
| Scorecard baseline | `packages/context`, `packages/observability`, `tests/unit/context` | Per-turn context trace metrics and a repo-native scorecard command |
| Long-horizon evals | `tests/scenarios/context`, `tests/unit/evidence`, `tests/unit/understanding` | Evidence-scored recall and compaction fixtures |
| Recall diagnostics | `packages/evidence`, `packages/understanding`, `apps/cli` | Strong/weak/no-match reasons and conflict/staleness labels |
| Compaction audit | `packages/context`, `packages/reflect`, `tests/unit/context` | Summary loss checks and post-compaction recall probes |
| Prompt-cache observability | `packages/context`, `apps/cli/runtime_cognition.py` | Stable-prefix/tool/model fingerprints and cache-break reporting |
| Tool-output pressure | `packages/tools`, `packages/context`, `packages/evidence` | Pre-ingest output shaping with raw evidence preservation |
