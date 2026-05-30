# 上下文 Token 效率专项研究

## 状态

这是 Elephant Agent 上下文工程的二次深入研究笔记，于 2026-05-29 在
`research/elephant-context-engineering` worktree 中整理。

本文在前一份
[context-engineering-research.zh-CN.md](context-engineering-research.zh-CN.md)
基础上，聚焦 prompt cache hit、context compression 和 token savings。本文
不替代 [system-layer-model.md](system-layer-model.md)。

英文同步版见
[context-token-efficiency-research.md](context-token-efficiency-research.md)。

## 范围

这次研究的问题是：Elephant 如何在保留有用上下文的同时，减少重复 prompt
输入，避免上下文窗口溢出，并且让 token 节省变成可观测、可优化的闭环。

本文聚焦三条循环：

- Prompt-cache 循环：稳定 prompt prefix、provider cache controls、cache
  key、cache hit reporting、cache break diagnosis。
- Compression 循环：触发策略、受保护 head 和 tail、summary 质量、cache
  invalidation、并发控制、压缩后的恢复能力。
- Token-savings 循环：tool output shaping、tool schema budget、retrieval 和
  recall budget、compaction savings、面向用户和 operator 的 scorecard。

## 来源快照

本轮研究前，已对 `/Users/wuhao/work/ai/agents/ws/ws2/research` 下第三方仓库
执行远端更新；存在远端更新的仓库已 fast-forward 到最新。

| 项目 | 本轮检查的 HEAD | 相关角色 |
| --- | --- | --- |
| Codex | `740d942f90` | Prompt cache key、cached-token accounting、remote compaction、internal model context |
| Hermes Agent | `db2ce9e7d` | Compression locks、session token counters、provider-aware context estimation |
| OpenClaw | `00ca654c74` | Prompt-cache observability、cache retention、preemptive compaction、tool-result guard |
| RTK | `5a149a7` | 进入模型前的 command-output reduction 与 savings telemetry |
| LoCoMo / locomotive | `3eb6f2c` | 长期记忆评估视角 |
| vLLM | `ff990d0d32` | Serving substrate；主要提供底层 cache 参考 |

## 核心结论

Elephant 已经具备 token efficiency 的关键零件：

- `packages/kernel/generation_context.py` 中有 stable 与 dynamic context 边界。
- 通过 Anthropic `cache_control` 和 OpenAI-compatible usage parsing 支持 provider
  侧 prompt cache。
- CLI 和 observability 会报告 cache read 与 cache creation tokens。
- CLI 路径在上下文窗口 85% 高水位后执行 after-turn compaction。
- Reflective compression 有 deterministic fallback、protected recent tail、token
  estimates 和 compaction result metadata。

主要缺口不是没有 cache 或 compression，而是这些能力还没有汇成一个优化账本。
Elephant 现在能说“cache hit 多少”，也能在压力高时压缩，但还不够容易回答：

- 这轮 cache hit rate 为什么掉了？
- 到底哪个 prompt bucket 变了：stable prefix、tool schemas、recall、tool
  results、current user input，还是 compacted resume？
- 多少 input tokens 是重复付费，多少来自 cache？
- compaction 节省的 token 是否值得它造成的 cache invalidation？
- 压力主要来自 tool result 还是 tool schema？
- 是否存在两个路径同时压缩同一个 session，造成 transcript fork？

下一步最值得做的是一套一等公民的 token efficiency ledger，把 context pressure
和 cost pressure 分开。Context pressure 要计算全部 input tokens，因为模型窗口
仍然需要容纳它们；cost pressure 应该计算 non-cached input 加 output，并单独
跟踪 cache write 的投资成本。

## Elephant 当前基线

### Prompt Cache

Elephant 已经有 cacheable-prefix 边界：

- `build_prompt_envelope` 在 stable prefix 已经存在时避免额外 wrapper heading。
- `GenerationContextRuntime._augment_with_system_layers` 把稳定 Personal Model
  lines、opening resume、skill disclosure 放进 frozen prefix；volatile recall
  则进入 current-turn loop context。
- `_prefix_cache` 按 `episode_id` 和 input hash 缓存 frozen prefix。
- compaction 之后会调用 `invalidate_prefix_cache`。

Provider 集成也已经部分 cache-aware：

- Anthropic provider 会给 system content block 和最后一个 tool schema 添加
  `cache_control: {type: "ephemeral"}`。
- OpenAI-compatible usage parsing 会读取 `cached_tokens`、
  `cache_read_input_tokens`，以及 cache creation / write token aliases。
- CLI metrics 会把 cache hit rate 渲染成 cached input / prompt input，并显示
  cache write tokens。
- Observability 会在 model-call completion event 中记录 cache read/create
  tokens 与 cache hit percentage。

薄弱点是 cache stability diagnosis。Elephant 能显示 hit 变化了，但还不能快
速解释为什么：model、provider、transport、retention、stable prefix digest、
tool schema digest、tool count、volatile context digest 这些快照还没有形成
对比机制。

### Compression

Elephant 现在有两条压缩路径：

- `apps/cli/runtime_turns.py` 的当前 CLI 路径，在 usage 达到 context limit 的
  85% 后执行 after-turn compaction。
- `packages/context/projection.py` 的 projection compactor 有更丰富的 policy
  层：protected head/tail、tool-result pruning、semantic anchors、token
  estimates，以及节省太小时跳过压缩。

Runtime compression 路径会：

- 用 `max(prompt_tokens, total_tokens)` 作为 usage pressure signal；
- 用 protected recent tail 拆分上下文；
- 先尝试 reflective compression；
- 失败时回落到 deterministic hard-truncating summary；
- 写入 summary 加 tail 的 compacted epoch；
- 用 `Reference summary: ...` 更新 frozen prefix resume；
- 让当前 episode 的 prefix cache 失效。

这足以在高压时恢复，但还没有为 cache economics 做到最优。因为 compaction 会
更新 frozen prefix 里的 resume 文本，它可能刷新 provider-side cache 本来希望
稳定保留的 prefix。大状态变化后这样做也许正确，但 Elephant 目前还没有量化
这个取舍。

### Token Savings

Elephant 已经记录了很多原料：

- prompt tokens、completion tokens、total tokens；
- cached prompt tokens 和 cache creation prompt tokens；
- compaction before/after message counts 和 token counts；
- projection compactor 中的 tool-result pruning；
- context budget allocation 和 overflow reporting。

缺的是按 bucket 归因的 savings：

- stable prefix tokens；
- volatile recall tokens；
- tool schema tokens；
- tool call argument tokens；
- shaping 前后的 tool result tokens；
- compacted summary tokens 对比被替换的 history tokens；
- cached input tokens 对比 non-cached input tokens；
- cache write tokens 作为投资成本，而不是立即收益。

没有这些 bucket，优化效果只能靠人工读日志判断。

## 第三方项目启发

### Codex

Codex 在显式 prompt-cache identity 和 accounting 上最强。

- `ModelClient` 会发送 `prompt_cache_key`；默认 key 是 thread id，也支持
  override。
- Guardian review subagents 使用类似 `guardian:{parent_thread_id}` 的 parent
  scoped key，让重复 review call 共享同一个 cache identity。
- Goal accounting 会先从 input tokens 中扣掉 `cached_input_tokens`，再加 output
  tokens。这样清楚地区分了 token budget 消耗和重复 cached input。
- Remote compaction 会复用 normal responses 的 `prompt_cache_key`，并有测试
  保护该行为。
- 新的 internal model context fragment 用
  `<codex_internal_context source="...">` 这类可审计 hidden markers，把
  extension-owned steering 和普通 user-visible content 分开。

对 Elephant 的启发：增加显式 provider cache key policy；在 cost / goal budget
中区别对待 cached input，但在 context-window pressure 中仍然计算全部 input。

### OpenClaw

OpenClaw 在 cache-break observability 和 preemptive pressure routing 上最强。

- Prompt-cache observation 会快照 provider、model、model API、cache retention、
  stream strategy、transport、system prompt digest、排序后的 tool digest、tool
  count 和 tool names。
- 当 cache-read tokens 下降至少 1,000 且低于前一次的 95% 时，认为发生了有意义
  的 cache break。
- Cache break reason 会归类为 model、retention、transport、stream strategy、
  system prompt 或 tools。
- Preemptive compaction 会在 provider call 前估算 boundary tokens，并路由到
  `fits`、`truncate_tool_results_only`、`compact_then_truncate` 或
  `compact_only`。
- Tool-result guard 会在 mid-turn 截断过大的 result，并在注定溢出的 provider
  request 前抛出 overflow error。
- Context-engine maintenance 运行在 deferred per-session lane 上，昂贵 cleanup
  可以在 hot path 外合并执行。

对 Elephant 的启发：增加 prompt-cache snapshot diff；在每次模型边界前做
context-pressure decision，尤其是 tool loop 中。

### Hermes Agent

Hermes 在 durable session accounting 和 compression concurrency 上最强。

- SQLite sessions 跟踪 input、output、cache read、cache write、reasoning、cost、
  provider 和 billing 字段。
- `compression_locks` 防止两个路径同时 rotate 同一个 session。最新测试复现了
  parent turn 加 background review 的竞态，并断言最终只会产生一个 child
  session。
- 如果 lock 已被占用，失败的一方会原样返回 messages；如果更新后 lock subsystem
  缺失，Hermes 会 fail open，避免陷入无进展的无限 compression loop。
- Compression engine 会估算包含 system prompt、messages、tool schemas、images
  的 request。其 metadata 注释明确指出，大型 tool set 可能额外增加数万 tokens。
- Compression 支持 anti-thrashing 和手动 focused compression。

对 Elephant 的启发：当多个 runtime path 可能压缩同一个 epoch 时，需要 session
或 episode compression lock；tool schema tokens 也应成为一等 budget bucket。

### RTK

RTK 在 tool output 进入模型前减压这一点上最强。

- 它用 filtering、grouping、truncation、deduplication 改写 command output，同时
  保持 exit-code 行为。
- 它报告 24 小时、30 天、累计 token savings、savings percentage、low-savings
  commands、parse failures 和估算美元节省。
- Raw output 可以保留，用于 debug 和恢复。

对 Elephant 的启发：compaction 不应是唯一防线。应该增加 pre-ingest
tool-output shaping，把 raw evidence 与 model-visible summary 分开存储。

## 能力等级评估

等级定义：

- L1：临时机制，主要靠人工检查。
- L2：基础机制存在，但 metrics 或 policy 有限。
- L3：运行时能力完整，并有有意义的 fallback。
- L4：有可测量的优化闭环、diagnostics 和测试。
- L5：provider-aware、可自适应，并有质量评估。

| 维度 | 当前等级 | 判断依据 | 下一目标 |
| --- | --- | --- | --- |
| Cacheable prefix stability | L3 | 已有 stable/dynamic split 和 local prefix cache | 尽量把 volatile resume/summary 移出 provider-cacheable trunk |
| Provider cache exploitation | L2.5 | 有 Anthropic cache control 和 OpenAI-compatible usage parsing | 增加各 provider 的 prompt cache key 与 retention policy |
| Cache-hit observability | L2.5 | CLI 和日志展示 hit/write tokens | 增加 cache-break snapshots 与 reason codes |
| Compression trigger/routing | L3 | After-turn high-water compaction 可用 | 增加 provider 前与 tool-loop 中的 precheck route |
| Compression quality/recovery | L3 | Reflective path、deterministic fallback、protected tail 已有 | 增加 recall probes 与 cache-impact checks |
| Tool-output token savings | L2.5 | Projection pruner 和 hard fallback 能降压 | 增加 pre-ingest shaping 和 per-tool savings telemetry |
| Tool schema accounting | L2 | Tool schemas 可部分 cache，但没有独立 bucket | 每次 model call 估算并报告 schema tokens |
| Concurrency control | L2 | 单 CLI 路径较简单，但缺少 shared lock design | 增加 per-session 或 per-epoch compression coordinator |
| Token economics | L2 | 可解析和展示 cache read/write | 跟踪 non-cached input、cache-write investment、net savings |
| Evaluation | L2 | Prefix cache、provider parsing、projection 有局部单测 | 增加 cache hit preservation 与 compression savings 场景测试 |

## 建议设计

### 1. Token Efficiency Ledger

新增一个每次 model call 都可记录的结构，挂到 Step 或 Episode telemetry：

| 字段组 | 示例字段 |
| --- | --- |
| Provider | provider、model、context window、transport、stream strategy |
| Input buckets | stable prefix tokens、volatile recall tokens、resume tokens、tool schema tokens、tool result tokens、user prompt tokens |
| Cache | prompt cache key、retention、stable prefix digest、tool digest、cache read tokens、cache write tokens、hit rate |
| Cost | prompt tokens、non-cached input tokens、completion tokens、reasoning tokens、estimated cost、cache write investment |
| Compression | before tokens、after tokens、method、protected tail turns、summary hash、savings tokens、trigger reason |
| Diagnostics | cache break reason、pressure source、overflow estimate、fallback used、skipped reason |
| Dashboard projection | turn index、wall-clock time、episode id、model call id、chart series id、event markers |

关键区别：

- Context pressure = 所有 prompt tokens，不管是否 cached。
- Cost pressure = non-cached input tokens 加 output tokens，cache writes 单独跟踪。

### 2. Dashboard Token Charts

Ledger 不应该只停留在日志或表格里，它应该投影到 dashboard，成为多轮对话的
token 变化图。这个图表是让 context economics 在 episode 维度可见的产品入口。

建议首版视图：

- X 轴：默认按 turn index，也可切换到 wall-clock time 或 model-call sequence。
- Stacked area：context-pressure buckets，例如 stable prefix、volatile recall、
  resume、tool schemas、tool results、current user input。
- Line series：total context pressure、non-cached input、output tokens、cache
  write tokens。
- Secondary axis：cache hit rate 与 cache read tokens。
- Event markers：compaction、cache-break detection、tool-output shaping、
  provider/model change、context-window warning。
- Hover drilldown：展示该轮的 bucket values、cache key、digest changes、
  compression before/after tokens。

这个图能把两个容易混在一起的 operator 问题拆开：

- “模型窗口快爆了吗？”看 stacked context pressure。
- “重复输入是不是太贵？”看 non-cached input、cache hit、cache write payback。

同一套数据还能支持更高层的 dashboard：

- per-episode token trajectory；
- per-provider cache efficiency；
- top pressure sources across sessions；
- compaction savings versus cache-hit loss；
- tool-output raw versus shaped savings。

### 3. Prompt Cache Policy

新增 provider cache policy layer：

- 默认 cache key：稳定 thread 或 episode lineage id。
- Subagent key：按 parent episode 加 role 进行 scope，例如 `reflect:{episode_id}`
  或 `review:{episode_id}`。
- Retention：provider-specific 的 `none`、`short` 或 `long`。
- Cacheable trunk：base developer/system contract、稳定 Personal Model projection、
  稳定 tool schema bundle、稳定 skill disclosure。
- Volatile suffix：current-turn recall、active tool results、fresh compression
  summary、current user task。

Policy 需要暴露每个 cache-relevant component 的 digest。hit rate 下跌时，
Elephant 应该能说明哪个 digest 变化了。

### 4. Cache-Break Detector

增加类似 OpenClaw 的 tracker，按 prompt cache key 记录：

- snapshot provider/model/transport/retention；
- digest stable prefix 和排序后的 tool schemas；
- 比较 previous 与 current snapshot；
- 对变化分类；
- 只有当 cache read tokens 发生实质下降时才发出 cache-break event。

初始规则可采用：cache read 至少下降 1,000 tokens，且低于前一次 cache read 的
95%。后续用真实 traces 调参。

### 5. Context Pressure Precheck

每次模型边界前执行 precheck：

- 按 bucket 估算 rendered prompt tokens。
- 与 context limit 减 reserve 后的预算比较。
- 估算压力中有多少来自可削减 tool output。
- 选择一个 route：`fits`、`truncate_tool_results_only`、
  `compact_then_truncate` 或 `compact_only`。

这应该发生在 provider call 前，而不是只发生在 turn 结束后。它在 tool loop 里
尤其重要，因为一个巨大 tool result 就可能让下一次请求失败。

### 6. Compression Coordinator

新增 per-session 或 per-epoch compression coordinator：

- rotate 或 replace epoch 前获取 lock。
- 如果已有压缩正在进行，返回 unchanged context，并合并下一次 maintenance pass。
- 成功或失败都释放 lock。
- 记录 lock skip events，让 operator 能区分“不需要压缩”和“已有压缩在进行”。

当 background reflection、proactive maintenance 或 parallel subagents 都可能
触碰同一条 session lineage 时，这会变得重要。

### 7. Tool Output Shaper

在 tool output 进入 model-visible trail 前增加 shaping 边界：

- 针对 command output、search results、JSON、diffs、logs 的 tool-specific filters；
- raw artifact retention，用于恢复；
- shaped output 加 evidence pointer 写入 Step metadata；
- per-tool savings report：raw estimated tokens、shaped estimated tokens、
  savings percentage、fallback reason。

Compaction 应该处理长历史；tool output shaping 应该阻止可避免的压力进入历史。

### 8. Compression Quality Checks

Compaction 之后不只验证 token count：

- Prompt estimate 低于目标阈值。
- Stable cache trunk 没有非预期变化。
- 下一次调用的 cache read 没有异常崩掉。
- Protected tail 仍包含当前任务和最新 tool state。
- 小型 recall probe 能从 compressed summary 中恢复关键事实。

## 建议里程碑

### Milestone A: Measure

- 在 context assembly 路径加入 token bucket estimation。
- 存储并渲染 non-cached input tokens。
- 增加 prompt-cache snapshots、tool schema digests、cache-break reason codes。
- 把 ledger records 投影到 dashboard，形成 per-episode token trajectory chart，
  包含 turn index、cache hit、context pressure、cost pressure、cache write 和
  compaction markers。
- 把 CLI 输出从“cache hit X%”扩展到可用时显示“cache hit X%，non-cached
  input Y，break reason Z”。

### Milestone B: Protect Cache

- 把 provider-cacheable trunk 与 volatile resume/current recall 拆开。
- 增加 provider cache key 与 retention policy。
- 在 provider 语义允许时，让 manual/automatic compaction request 复用 normal
  responses 的 cache key。
- 增加测试，确保稳定重复轮次保持同一个 cache key 和 digest。

### Milestone C: Compress Earlier

- 增加 provider 前 context pressure routing。
- 增加 tool loop 中的 tool-result guard。
- 用 prompt/input pressure 触发 context-window compaction，而不是
  `max(prompt_tokens, total_tokens)`。
- 增加 anti-thrashing：如果近期压缩节省低于 10%，跳过自动压缩，并建议 focused
  compress 或 fresh-session path。

### Milestone D: Save Before History

- 为 shell output、diffs、search results、JSON 增加 tool-output shapers。
- 记录 raw 与 shaped token estimates。
- 暴露 low-savings tools，后续逐步改进 filters。

### Milestone E: Evaluate

建立场景测试：

- 稳定重复轮次保持高 prompt-cache hit rate；
- compaction 后 provider-cacheable trunk digest 不变；
- 大 tool output 在 provider overflow 前被处理；
- 多 tool schemas 时 schema token bucket 可测；
- subagent reflection 共享 parent-scoped cache identity；
- 同一 episode 的 concurrent compression；
- 中文/CJK 对话中 token estimates 不依赖 ASCII 假设；
- 压缩后仍能正确回答 recall probes。

## 未决问题

- Episode opening resume 应该属于 provider-cacheable trunk，还是应该移到 volatile
  suffix，避免 compaction summary 刷新 trunk？
- Cache creation tokens 是否应作为有 payback window 的投资预算？
- Background reflection 应该使用 foreground episode 的同一个 prompt cache key，
  还是 parent-scoped subagent key？
- 当 model-visible 版本被 shaping 后，raw tool output 应该放在 Step artifacts、
  evidence payload，还是专门的 tool-output store？
- 旧的 semantic-anchor compaction 代码应该重新接入 runtime compression path，
  还是应该退休以减少概念负担？

## 结论

Elephant 已经很接近一套强 token-efficiency architecture。下一跃迁不是再做一个
summarizer，而是建立可测量的控制循环：

1. 对进入 prompt 的内容分 bucket；
2. 稳定 cacheable trunk；
3. 诊断 cache breaks；
4. 在 overflow 前压缩；
5. 让 tool output 进入历史前先降压；
6. 把 non-cached input 与 context pressure 分开计算。

这样 Elephant 优化的目标就不只是“撑过下一次 context-window limit”，而是长期
运行时持续保持有用、便宜、可解释。
