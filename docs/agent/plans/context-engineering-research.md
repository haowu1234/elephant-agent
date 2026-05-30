# Context Engineering Optimization Plan

## Goal

Turn the context-engineering research pass into an execution roadmap for making
Elephant Agent's context behavior measurable, adaptive, and robust across long
multi-session use.

The system design source of truth remains
`docs/system-design/system-layer-model.md`. The research assessment lives in
`docs/system-design/context-engineering-research.md`.

Synchronized Chinese companion:
[context-engineering-research.zh-CN.md](context-engineering-research.zh-CN.md).

## Scope

- Context assembly and token budgeting in `packages/context`.
- Recall and evidence ranking in `packages/evidence` and
  `packages/semantic_index`.
- Personal Model search, claim lifecycle, and claim diagnostics in
  `packages/understanding`.
- Continuity and resume behavior in `packages/continuity`.
- Background learning and compression support in `packages/reflect`.
- Proactive question quality in `packages/curiosity`.
- CLI prompt projection and inspectable runtime traces in `apps/cli`.
- Scenario and unit validation under `tests/**`.

## Non-Goals

- Do not replace the canonical Understanding System with a generic memory-table
  design.
- Do not copy third-party architectures into Elephant wholesale.
- Do not add a second evidence source of truth outside Steps, Facts, Episodes,
  and SemanticIndexEntry.
- Do not combine prompt projection, recall ranking, compaction, and tool-output
  shaping in one implementation branch.
- Do not make broad provider or storage-schema changes without an ADR and a
  migration plan.

## Tracks

- Track A: Context Scorecard Baseline
  - Write scope: `packages/context`, `packages/observability`,
    `tests/unit/context`, `tools/agent` only if a harness command is added.
  - Add per-turn metrics for stable prefix tokens, volatile recall tokens,
    active claim count, retrieved evidence IDs, compaction state, prompt-cache
    fingerprints, and final token allocation.
  - Output: a machine-readable context trace plus a human scorecard summary.

- Track B: Long-Horizon Evaluation Suite
  - Write scope: `tests/scenarios/context`, `tests/unit/evidence`,
    `tests/unit/understanding`, fixture files under the same test tree.
  - Add LoCoMo-inspired fixtures for multi-session facts, stale Pulse updates,
    disputed claims, event summaries, compaction after recall, and evidence ID
    grading.
  - Output: recall and compaction quality tests that fail on answer-only
    plausibility when the evidence path is wrong.

- Track C: Recall and Claim Diagnostics
  - Write scope: `packages/evidence`, `packages/understanding`, focused CLI
    rendering under `apps/cli`.
  - Extend strong/weak/no-match diagnostics with reasons for missing evidence,
    low-confidence semantic matches, stale evidence, polarity conflicts, and
    active-vs-retired claim separation.
  - Output: model-facing diagnostics remain opt-in, while developer traces show
    why recall behaved the way it did.

- Track D: Compaction Quality and Recovery
  - Write scope: `packages/context`, `packages/reflect`,
    `tests/unit/context`, `tests/unit/reflect`.
  - Add summary loss checks, semantic anchors, post-compaction recall probes,
    raw Step recovery references, and deterministic-vs-reflect fallback metrics.
  - Output: compaction is scored by preservation and recoverability, not only by
    token reduction.

- Track E: Prompt-Cache and Hot-Path Stability
  - Write scope: `packages/context`, `apps/cli/runtime_cognition.py`,
    `tests/unit/context`, `tests/unit/cli`.
  - Add stable-prefix fingerprints, tool-set digests, model/provider change
    markers, and cache-break diagnostics inspired by Codex and OpenClaw.
  - Output: prompt-cache regressions become explainable in traces.

- Track F: Tool-Output Pressure Control
  - Write scope: `packages/tools`, `packages/context`, `packages/evidence`,
    focused CLI projection tests.
  - Add RTK-inspired pre-ingest summaries for large tool outputs while keeping
    raw Step evidence available for audit and "why" traces.
  - Output: large command/tool results stop dominating the prompt before
    compaction is needed.

- Track G: Lazy Tool and Skill Disclosure
  - Write scope: `packages/skills`, `packages/context`, `apps/cli`, focused
    tests for prompt projection and tool schema cost.
  - Track schema token cost separately and retrieve detailed skill/tool context
    only when a task needs it.
  - Output: stable prompts remain compact without hiding available capability.

- Track H: Context Modes
  - Write scope: config/contracts for context options, `packages/context`,
    `packages/evidence`, `packages/curiosity`, `apps/cli`.
  - Define `narrow`, `balanced`, `research`, and `continuity-heavy` policies for
    recall breadth, claim inclusion, compaction aggressiveness, and question
    cadence.
  - Output: users and runtimes can choose context behavior explicitly.

## Dependencies

- Track A should land before Tracks C through H so later tracks can expose
  comparable metrics.
- Track B can start in parallel with Track A but should not lock in metric names
  until Track A defines the baseline trace schema.
- Track D depends on the current reflect compression surface and should avoid
  changing Personal Model claim rules.
- Track F depends on preserving raw Step evidence; any raw-output storage
  changes need a narrow ADR before implementation.
- Track H should wait until at least one scorecard pass shows how current
  recall breadth and compaction aggressiveness behave.

## Validation

Every implementation track should run the repo-native route first:

```bash
make agent-report CHANGED_FILES="<changed files>"
```

Minimum validation by track:

- Track A: focused unit tests plus `make agent-validate`.
- Track B: scenario tests plus `make agent-test`.
- Track C: recall and Personal Model unit tests plus `make agent-validate`.
- Track D: context and reflect unit tests plus `make agent-test`.
- Track E: CLI/context projection unit tests plus `make agent-validate`.
- Track F: tool-output, context, and evidence tests plus `make agent-test`.
- Track G: skill/tool projection tests plus `make agent-validate`.
- Track H: context policy tests plus a focused CLI smoke path.

Before shipping any complete branch, use the repo-native ship path when
validation is green:

```bash
make agent-ship AGENT_COMMIT_MESSAGE="<type>(<scope>): <summary>"
```

## Exit Criteria

- A context engineering scorecard exists and is used by later context changes.
- Long-horizon evaluation fixtures cover recall, compaction, correction,
  disputed claims, and evidence traceability.
- Personal Model search can explain strong, weak, and no-match outcomes.
- Compaction has preservation checks and recovery references.
- Prompt-cache stability regressions are visible in context traces.
- Large tool outputs have a pre-ingest shaping policy with raw evidence
  preservation.
- Tool and skill context can be disclosed lazily with measured schema cost.
- Context modes are documented, tested, and visible in CLI runtime traces.
