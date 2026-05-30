# Context Token Efficiency Research

## Status

Second-pass research note for Elephant Agent context engineering, prepared in
the `research/elephant-context-engineering` worktree on 2026-05-29.

This document narrows the earlier
[context-engineering-research.md](context-engineering-research.md) review to
prompt cache hit rate, context compression, and token savings. It does not
replace [system-layer-model.md](system-layer-model.md).

Synchronized Chinese companion:
[context-token-efficiency-research.zh-CN.md](context-token-efficiency-research.zh-CN.md).

## Scope

The research question is: how should Elephant keep useful context available
while reducing repeated prompt input, avoiding context-window overflow, and
making token savings measurable?

This note focuses on three loops:

- Prompt-cache loop: stable prompt prefix, provider cache controls, cache keys,
  cache hit reporting, and cache-break diagnosis.
- Compression loop: trigger policy, protected tail and head, summary quality,
  cache invalidation, concurrency, and post-compression recovery.
- Token-savings loop: tool output shaping, tool schema budget, retrieval and
  recall budget, compaction savings, and user-visible scorecards.

## Source Snapshot

Third-party repositories under `/Users/wuhao/work/ai/agents/ws/ws2/research`
were fetched before this second pass. Repositories with remote updates were
fast-forwarded.

| Project | HEAD inspected | Relevant role |
| --- | --- | --- |
| Codex | `740d942f90` | Prompt cache key, cached-token accounting, remote compaction, internal model context |
| Hermes Agent | `db2ce9e7d` | Compression locks, session token counters, provider-aware context estimation |
| OpenClaw | `00ca654c74` | Prompt-cache observability, cache retention, preemptive compaction, tool-result guard |
| RTK | `5a149a7` | Pre-ingest command-output reduction and savings telemetry |
| LoCoMo / locomotive | `3eb6f2c` | Long-horizon memory evaluation lens |
| vLLM | `ff990d0d32` | Serving substrate; useful mainly as lower-level cache context |

## Executive Findings

Elephant already has the hard pieces needed for token efficiency:

- A stable versus dynamic context boundary in `packages/kernel/generation_context.py`.
- Provider cache support through Anthropic `cache_control` and OpenAI-compatible
  cache usage parsing.
- CLI and observability reporting for cache read and cache creation tokens.
- After-turn compaction at a 0.85 context-window threshold.
- Reflective compression with deterministic fallback, protected recent tail,
  token estimates, and compaction result metadata.

The main gap is that these pieces are not yet connected into an optimization
ledger. Elephant can report "cache hit" and can compact, but it cannot yet
answer these operational questions well:

- Why did the cache hit rate drop this turn?
- Which prompt bucket changed: stable prefix, tool schemas, recall, tool
  results, current user input, or compacted resume?
- How many input tokens were paid again versus served from cache?
- Did compaction save enough tokens to justify the cache invalidation it caused?
- Did a tool result or tool schema set cause most of the pressure?
- Did a concurrent compression path race with another path on the same session?

The next useful design target is a first-class token efficiency ledger that
separates context pressure from cost pressure. Context pressure counts all input
tokens because the model still needs them in the window. Cost pressure should
count uncached input plus output, and should track cache write costs separately.

## Elephant Baseline

### Prompt Cache

Elephant has a cacheable-prefix boundary:

- `build_prompt_envelope` avoids extra wrapper headings when a stable prefix is
  already present.
- `GenerationContextRuntime._augment_with_system_layers` keeps stable Personal
  Model lines, opening resume, and skill disclosure in a frozen prefix, while
  volatile recall becomes current-turn loop context.
- `_prefix_cache` caches a frozen prefix by `episode_id` and input hash.
- `invalidate_prefix_cache` is called after compaction.

Provider integration is partially cache-aware:

- The Anthropic provider adds `cache_control: {type: "ephemeral"}` to the
  system content block and to the last tool schema.
- OpenAI-compatible usage parsing reads `cached_tokens`,
  `cache_read_input_tokens`, and cache creation or write token aliases.
- CLI metrics render cache hit rate as cached input over prompt input and show
  cache write tokens.
- Observability records cache read/create tokens and cache hit percentage in
  model-call completion events.

The weakness is cache stability diagnosis. Elephant can show that a hit changed,
but it does not yet snapshot the inputs that explain why: model, provider,
transport, retention, stable prefix digest, tool schema digest, tool count, and
volatile context digest.

### Compression

Elephant has two compression paths:

- The current CLI path in `apps/cli/runtime_turns.py` performs after-turn
  compaction when usage reaches 85% of the context limit.
- The projection compactor in `packages/context/projection.py` has a richer
  policy layer for protected head/tail, tool-result pruning, semantic anchors,
  token estimates, and skipped compaction when savings are too small.

The runtime compression path:

- uses `max(prompt_tokens, total_tokens)` as the usage pressure signal;
- splits context with a protected recent tail;
- tries reflective compression first;
- falls back to a deterministic hard-truncating summary path;
- writes a compacted epoch with summary plus tail;
- updates the frozen prefix resume with `Reference summary: ...`;
- invalidates the episode prefix cache.

This is robust enough to recover from pressure, but not yet optimized for cache
economics. Because compaction updates resume text inside the frozen prefix, it
can refresh the very prefix that provider-side cache wants to keep stable. That
may be correct after large state changes, but Elephant does not measure the
tradeoff.

### Token Savings

Elephant tracks the ingredients:

- prompt tokens, completion tokens, total tokens;
- cached prompt tokens and cache creation prompt tokens;
- compaction before/after message counts and token counts;
- tool-result pruning in the projection compactor;
- context budget allocation and overflow reporting.

What is missing is bucketed savings:

- stable prefix tokens;
- volatile recall tokens;
- tool schema tokens;
- tool call argument tokens;
- tool result tokens before and after shaping;
- compacted summary tokens versus replaced history tokens;
- cached input tokens versus non-cached input tokens;
- cache write tokens that are investments rather than immediate savings.

Without those buckets, optimizations can only be judged after manual inspection.

## Third-Party Lessons

### Codex

Codex is strongest on explicit prompt-cache identity and accounting.

- `ModelClient` sends a `prompt_cache_key`; the default key is the thread id,
  with an override hook.
- Guardian review subagents use a parent-scoped key like
  `guardian:{parent_thread_id}` so repeated review calls share the same cache
  identity.
- Goal accounting subtracts `cached_input_tokens` from input before adding
  output tokens. This cleanly separates token budget consumption from repeated
  cached input.
- Remote compaction reuses the same `prompt_cache_key` as normal responses and
  tests for that behavior.
- The new internal model context fragment uses auditable hidden markers such as
  `<codex_internal_context source="...">`, separating extension-owned steering
  from normal user-visible content.

Implication for Elephant: add an explicit provider cache key policy and count
cached input differently in cost or goal budgets, while still counting it
against context-window pressure.

### OpenClaw

OpenClaw is strongest on cache-break observability and preemptive pressure
routing.

- Prompt-cache observations snapshot provider, model, model API, cache
  retention, stream strategy, transport, system prompt digest, sorted tool
  digest, tool count, and tool names.
- A meaningful cache break is detected when cache-read tokens drop by at least
  1,000 and below 95% of the previous read.
- Cache break reasons are classified as model, retention, transport, stream
  strategy, system prompt, or tools.
- Preemptive compaction estimates boundary tokens before provider calls and
  routes to `fits`, `truncate_tool_results_only`, `compact_then_truncate`, or
  `compact_only`.
- The tool-result guard truncates oversized results mid-turn and raises an
  overflow error before a doomed provider request.
- Context-engine maintenance runs on a deferred per-session lane so expensive
  cleanup can be coalesced outside the hot path.

Implication for Elephant: add a prompt-cache snapshot diff and run a preflight
context-pressure decision before each model boundary, especially in tool loops.

### Hermes Agent

Hermes is strongest on durable session accounting and compression concurrency.

- SQLite sessions track input, output, cache read, cache write, reasoning, cost,
  provider, and billing fields.
- `compression_locks` prevent two paths from rotating the same session at once.
  The latest tests reproduce a parent-turn plus background-review race and
  assert that only one child session is created.
- If the lock is held, the losing compressor returns messages unchanged. If the
  lock subsystem is missing after an update, Hermes fails open so it avoids an
  infinite no-progress compression loop.
- The compression engine estimates requests including system prompt, messages,
  tool schemas, and images. Its metadata comments call out that large tool sets
  can add tens of thousands of tokens.
- Compression has anti-thrashing behavior and manual focused compression.

Implication for Elephant: add session or episode compression locks before
multiple runtime paths can compact the same epoch, and make tool schema tokens a
first-class budget bucket.

### RTK

RTK is strongest on reducing tool output before it ever reaches the model.

- It rewrites command outputs with filtering, grouping, truncation, and
  deduplication while preserving exit-code behavior.
- It reports token savings over 24 hours, 30 days, and total lifetime, plus
  savings percentage, low-savings commands, parse failures, and estimated
  dollar savings.
- Raw output can be retained for debugging and recovery.

Implication for Elephant: compaction should not be the only defense. Add a
pre-ingest tool-output shaping layer that records raw evidence separately from
model-visible summaries.

## Capability Assessment

Scale:

- L1: ad hoc behavior, mostly manual inspection.
- L2: basic mechanism exists, limited metrics or policy.
- L3: integrated runtime behavior with meaningful fallback.
- L4: measurable optimization loop with diagnostics and tests.
- L5: adaptive, provider-aware, quality-evaluated optimization.

| Dimension | Current level | Why | Next target |
| --- | --- | --- | --- |
| Cacheable prefix stability | L3 | Stable/dynamic split and local prefix cache exist | Move volatile resume/summary outside the provider-cacheable trunk where possible |
| Provider cache exploitation | L2.5 | Anthropic cache control and OpenAI-compatible usage parsing exist | Add explicit prompt cache key and retention policy per provider |
| Cache-hit observability | L2.5 | CLI and logs show hit/write tokens | Add cache-break snapshots and reason codes |
| Compression trigger and routing | L3 | After-turn high-water compaction works | Add pre-provider and mid-tool-loop routing |
| Compression quality and recovery | L3 | Reflective path plus deterministic fallback and protected tail | Add recall probes and cache-impact checks after compaction |
| Tool-output token savings | L2.5 | Projection pruner and hard fallback reduce pressure | Add pre-ingest shaping and per-tool savings telemetry |
| Tool schema accounting | L2 | Tool schemas can be cached partially but are not bucketed | Estimate and report schema tokens per model call |
| Concurrency control | L2 | Single CLI path is simple; no shared lock design is visible | Add per-session or per-epoch compression coordinator |
| Token economics | L2 | Cache read/write values are parsed and displayed | Track non-cached input, cache-write investment, and net savings |
| Evaluation | L2 | Unit tests cover pieces of prefix cache, provider parsing, and projection | Add scenario tests for cache hit preservation and compression savings |

## Recommended Design

### 1. Token Efficiency Ledger

Add a per-model-call record that can be stored with Step or Episode telemetry:

| Field group | Example fields |
| --- | --- |
| Provider | provider, model, context window, transport, stream strategy |
| Input buckets | stable prefix tokens, volatile recall tokens, resume tokens, tool schema tokens, tool result tokens, user prompt tokens |
| Cache | prompt cache key, retention, stable prefix digest, tool digest, cache read tokens, cache write tokens, hit rate |
| Cost | prompt tokens, non-cached input tokens, completion tokens, reasoning tokens, estimated cost, cache write investment |
| Compression | before tokens, after tokens, method, protected tail turns, summary hash, savings tokens, trigger reason |
| Diagnostics | cache break reason, pressure source, overflow estimate, fallback used, skipped reason |
| Dashboard projection | turn index, wall-clock time, episode id, model call id, chart series id, event markers |

The key distinction:

- Context pressure = all prompt tokens, cached or not.
- Cost pressure = non-cached input tokens plus output tokens, with cache writes
  tracked separately.

### 2. Dashboard Token Charts

The ledger should project into the dashboard as a multi-turn token chart, not
only as logs. The chart is the product surface that makes context economics
visible across an episode.

Recommended first view:

- X axis: turn index by default, with wall-clock time and model-call sequence as
  alternate groupings.
- Stacked area: context-pressure buckets such as stable prefix, volatile recall,
  resume, tool schemas, tool results, and current user input.
- Line series: total context pressure, non-cached input, output tokens, and
  cache write tokens.
- Secondary axis: cache hit rate and cache read tokens.
- Event markers: compaction, cache-break detection, tool-output shaping,
  provider/model change, and context-window warning.
- Hover drilldown: show the exact bucket values, cache key, digest changes, and
  compression before/after tokens for that turn.

This separates two operator questions that are easy to conflate:

- "Are we close to overflowing the model window?" Use the stacked context
  pressure view.
- "Are we paying too much repeated input?" Use non-cached input, cache hit, and
  cache write payback views.

The same data can support higher-level dashboards:

- per-episode token trajectory;
- per-provider cache efficiency;
- top pressure sources across sessions;
- compaction savings versus cache-hit loss;
- tool-output raw versus shaped savings.

### 3. Prompt Cache Policy

Introduce a provider cache policy layer:

- Cache key default: stable thread or episode lineage id.
- Subagent key: scoped to parent episode plus role, for example
  `reflect:{episode_id}` or `review:{episode_id}`.
- Retention: provider-specific `none`, `short`, or `long`.
- Cacheable trunk: base developer/system contract, stable Personal Model
  projection, stable tool schema bundle, and stable skill disclosure.
- Volatile suffix: current-turn recall, active tool results, fresh compression
  summary, and current user task.

The policy should expose a digest for every cache-relevant component. When hit
rate drops, Elephant should be able to say which digest changed.

### 4. Cache-Break Detector

Add an OpenClaw-style tracker keyed by prompt cache key:

- snapshot provider/model/transport/retention;
- digest stable prefix and sorted tool schemas;
- compare previous and current snapshots;
- classify changes;
- emit a cache-break event only when cache read tokens materially drop.

Suggested initial rule: cache read drops by at least 1,000 tokens and below 95%
of the previous cache read. Tune after collecting real traces.

### 5. Context Pressure Precheck

Run a precheck before each model boundary:

- Estimate rendered prompt tokens by bucket.
- Compare against context limit minus reserve.
- Estimate how much of the pressure is reducible tool output.
- Pick one route: `fits`, `truncate_tool_results_only`,
  `compact_then_truncate`, or `compact_only`.

This should run before provider calls, not only after a turn. It is most
valuable during tool loops where a single large tool result can make the next
request fail.

### 6. Compression Coordinator

Add a per-session or per-epoch compression coordinator:

- Acquire a lock before rotating or replacing an epoch.
- If another compression is active, return unchanged context and coalesce the
  next maintenance pass.
- Release on success or failure.
- Record lock skip events so operators can tell the difference between "did not
  need compression" and "compression already in progress".

This becomes important once background reflection, proactive maintenance, or
parallel subagents can touch the same session lineage.

### 7. Tool Output Shaper

Add a tool-output shaping boundary before output enters the model-visible trail:

- tool-specific filters for command output, search results, JSON, diffs, and
  logs;
- raw artifact retention for recovery;
- shaped output plus evidence pointer in Step metadata;
- per-tool savings report: raw estimated tokens, shaped estimated tokens,
  savings percentage, fallback reason.

Compaction should handle long history. Tool output shaping should prevent
avoidable pressure from entering history.

### 8. Compression Quality Checks

After compaction, validate more than token count:

- Prompt estimate is below the target threshold.
- Stable cache trunk did not change unless expected.
- The next call's cache read did not collapse unexpectedly.
- Protected tail still contains the active task and latest tool state.
- A small recall probe can recover key facts from the compressed summary.

## Suggested Milestones

### Milestone A: Measure

- Add token bucket estimation to the context assembly path.
- Store and render non-cached input tokens.
- Add prompt-cache snapshots, tool schema digests, and cache-break reason codes.
- Project ledger records into the dashboard as a per-episode token trajectory
  chart with turn index, cache hit, context pressure, cost pressure, cache write,
  and compaction markers.
- Extend CLI output from "cache hit X%" to "cache hit X%, non-cached input Y,
  break reason Z" when available.

### Milestone B: Protect Cache

- Split provider-cacheable trunk from volatile resume and current recall.
- Add provider cache key and retention policy.
- Keep manual and automatic compaction requests on the same cache key as normal
  responses when provider semantics allow it.
- Add tests that repeated stable turns keep the same cache key and digest.

### Milestone C: Compress Earlier

- Add pre-provider context pressure routing.
- Add mid-tool-loop tool-result guard.
- Use prompt/input pressure rather than `max(prompt_tokens, total_tokens)` for
  context-window triggers.
- Add anti-thrashing: if recent compactions save less than 10%, skip automatic
  compaction and recommend a focused or fresh-session path.

### Milestone D: Save Before History

- Add tool-output shapers for shell output, diffs, search results, and JSON.
- Track raw versus shaped token estimates.
- Surface low-savings tools so filters can improve over time.

### Milestone E: Evaluate

Create scenario tests for:

- repeated stable turns with high prompt-cache hit rate;
- compaction that preserves cacheable trunk digest;
- large tool output handled before provider overflow;
- many tool schemas with measurable schema token bucket;
- subagent reflection sharing parent-scoped cache identity;
- concurrent compression on the same episode;
- Chinese/CJK conversations where token estimates differ from ASCII-heavy
  assumptions;
- compressed sessions that still answer recall probes correctly.

## Open Questions

- Should the Episode opening resume be part of the provider-cacheable trunk, or
  should it move to a volatile suffix so compaction summaries do not refresh the
  trunk?
- Should cache creation tokens be treated as an investment budget with a
  payback window?
- Should background reflection use the same prompt cache key as the foreground
  episode, or a parent-scoped subagent key?
- Where should raw tool output live when the model-visible version is shaped:
  Step artifacts, evidence payload, or a dedicated tool-output store?
- Should old semantic-anchor compaction code be reconnected to the runtime
  compression path, or retired to reduce confusion?

## Bottom Line

Elephant is close to a strong token-efficiency architecture. The next leap is
not another summarizer. It is a measurable control loop:

1. bucket what enters the prompt;
2. stabilize the cacheable trunk;
3. diagnose cache breaks;
4. compress before overflow;
5. shape tool output before history;
6. count non-cached input separately from context pressure.

That would let Elephant optimize for long-running usefulness, not only for
surviving the next context-window limit.
