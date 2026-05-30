# 上下文工程优化计划

## 目标

把上下文工程研究转化为可执行路线图，让 Elephant Agent 的 context behavior 在
长期多 session 使用中变得可测量、可自适应、可硬化。

系统设计事实来源仍然是 `docs/system-design/system-layer-model.md`。研究评估见
`docs/system-design/context-engineering-research.zh-CN.md`。

英文同步版见
[context-engineering-research.md](context-engineering-research.md)。

## 范围

- `packages/context` 中的 context assembly 和 token budgeting。
- `packages/evidence` 与 `packages/semantic_index` 中的 recall 和 evidence ranking。
- `packages/understanding` 中的 Personal Model search、claim lifecycle 和 claim diagnostics。
- `packages/continuity` 中的 continuity 和 resume behavior。
- `packages/reflect` 中的 background learning 和 compression support。
- `packages/curiosity` 中的 proactive question quality。
- `apps/cli` 中的 CLI prompt projection 和可检查 runtime traces。
- `tests/**` 下的 scenario 和 unit validation。

## 非目标

- 不用通用 memory-table design 替代 canonical Understanding System。
- 不把第三方架构整套复制进 Elephant。
- 不在 Steps、Facts、Episodes、SemanticIndexEntry 之外增加第二套 evidence source of truth。
- 不在同一个 implementation branch 里混合 prompt projection、recall ranking、
  compaction 和 tool-output shaping。
- 没有 ADR 和 migration plan 时，不做广泛 provider 或 storage-schema 变更。

## Tracks

- Track A: Context Scorecard Baseline
  - 写入范围：`packages/context`、`packages/observability`、`tests/unit/context`；
    只有新增 harness command 时才碰 `tools/agent`。
  - 增加 per-turn metrics：stable prefix tokens、volatile recall tokens、active
    claim count、retrieved evidence IDs、compaction state、prompt-cache
    fingerprints、final token allocation。
  - 产出：machine-readable context trace 和 human scorecard summary。

- Track B: Long-Horizon Evaluation Suite
  - 写入范围：`tests/scenarios/context`、`tests/unit/evidence`、
    `tests/unit/understanding`，以及同测试树下 fixtures。
  - 增加 LoCoMo-inspired fixtures：multi-session facts、stale Pulse updates、
    disputed claims、event summaries、compaction after recall、evidence ID grading。
  - 产出：recall 和 compaction quality tests。只要 evidence path 错了，即使答案
    看起来合理也要失败。

- Track C: Recall and Claim Diagnostics
  - 写入范围：`packages/evidence`、`packages/understanding`，以及 `apps/cli`
    下聚焦的 rendering。
  - 扩展 strong/weak/no-match diagnostics：missing evidence、low-confidence
    semantic matches、stale evidence、polarity conflicts、active-vs-retired
    claim separation。
  - 产出：model-facing diagnostics 仍为 opt-in；developer traces 能解释 recall
    为什么这样表现。

- Track D: Compaction Quality and Recovery
  - 写入范围：`packages/context`、`packages/reflect`、`tests/unit/context`、
    `tests/unit/reflect`。
  - 增加 summary loss checks、semantic anchors、post-compaction recall probes、
    raw Step recovery references、deterministic-vs-reflect fallback metrics。
  - 产出：compaction 不只按 token reduction 评分，也按 preservation 和
    recoverability 评分。

- Track E: Prompt-Cache and Hot-Path Stability
  - 写入范围：`packages/context`、`apps/cli/runtime_cognition.py`、
    `tests/unit/context`、`tests/unit/cli`。
  - 增加 stable-prefix fingerprints、tool-set digests、model/provider change
    markers，以及受 Codex/OpenClaw 启发的 cache-break diagnostics。
  - 产出：prompt-cache regressions 在 traces 中可解释。

- Track F: Tool-Output Pressure Control
  - 写入范围：`packages/tools`、`packages/context`、`packages/evidence`，以及
    聚焦的 CLI projection tests。
  - 增加 RTK-inspired pre-ingest summaries，用于大型 tool outputs，同时保留
    raw Step evidence 以支持 audit 和 "why" traces。
  - 产出：大型 command/tool results 在需要 compaction 之前就不会主导 prompt。

- Track G: Lazy Tool and Skill Disclosure
  - 写入范围：`packages/skills`、`packages/context`、`apps/cli`，以及 prompt
    projection 和 tool schema cost 的聚焦 tests。
  - 单独跟踪 schema token cost，只在 task 需要时检索详细 skill/tool context。
  - 产出：stable prompts 保持紧凑，同时不隐藏可用能力。

- Track H: Context Modes
  - 写入范围：context options 的 config/contracts、`packages/context`、
    `packages/evidence`、`packages/curiosity`、`apps/cli`。
  - 定义 `narrow`、`balanced`、`research`、`continuity-heavy` 策略，对应 recall
    breadth、claim inclusion、compaction aggressiveness、question cadence。
  - 产出：用户和 runtimes 可以显式选择 context behavior。

## 依赖

- Track A 应先于 Tracks C 到 H 落地，让后续 tracks 能暴露可比 metrics。
- Track B 可以和 Track A 并行启动，但在 Track A 定义 baseline trace schema 前，
  不应锁定 metric names。
- Track D 依赖当前 reflect compression surface，并应避免改变 Personal Model
  claim rules。
- Track F 依赖 raw Step evidence preservation；任何 raw-output storage 变更都
  需要先做窄 ADR。
- Track H 应等至少一次 scorecard pass 说明当前 recall breadth 和 compaction
  aggressiveness 后再落地。

## 验证

每个 implementation track 先走 repo-native route：

```bash
make agent-report CHANGED_FILES="<changed files>"
```

各 track 最小验证：

- Track A：focused unit tests 加 `make agent-validate`。
- Track B：scenario tests 加 `make agent-test`。
- Track C：recall 和 Personal Model unit tests 加 `make agent-validate`。
- Track D：context 和 reflect unit tests 加 `make agent-test`。
- Track E：CLI/context projection unit tests 加 `make agent-validate`。
- Track F：tool-output、context、evidence tests 加 `make agent-test`。
- Track G：skill/tool projection tests 加 `make agent-validate`。
- Track H：context policy tests 加 focused CLI smoke path。

任何完整 branch 在 validation 为 green 时，使用 repo-native ship path：

```bash
make agent-ship AGENT_COMMIT_MESSAGE="<type>(<scope>): <summary>"
```

## 退出标准

- 已有 context engineering scorecard，并被后续 context changes 使用。
- Long-horizon evaluation fixtures 覆盖 recall、compaction、correction、
  disputed claims 和 evidence traceability。
- Personal Model search 能解释 strong、weak、no-match outcomes。
- Compaction 有 preservation checks 和 recovery references。
- Prompt-cache stability regressions 在 context traces 中可见。
- 大型 tool outputs 有 pre-ingest shaping policy，并保留 raw evidence。
- Tool 和 skill context 能 lazy disclosure，并测量 schema cost。
- Context modes 已文档化、测试覆盖，并在 CLI runtime traces 中可见。

