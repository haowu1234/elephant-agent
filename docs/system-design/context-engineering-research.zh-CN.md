# 上下文工程研究

## 状态

这是 Elephant Agent 上下文工程研究笔记，于 2026-05-29 在
`research/elephant-context-engineering` worktree 中整理。

本文档不替代 [system-layer-model.md](system-layer-model.md)。系统层模型仍然
是当前产品级设计事实来源。本文用于评估当前设计，对比 `research/` 下第三
方 agent 项目，并提出下一步优化方向。

英文同步版见
[context-engineering-research.md](context-engineering-research.md)。

## 范围

这里的上下文工程指系统如何决定模型看到什么、系统持久化什么、哪些信息被
召回、哪些内容被压缩，以及哪些理解会沉淀到未来轮次。

对 Elephant Agent 来说，这包括：

- Personal Model 活跃 claims 和四镜头 prompt 投影。
- Elephant State、Episode、Loop、Step trail 连续性。
- Step 和 Fact 通过 SemanticIndexEntry 进入索引。
- 当前轮上下文召回。
- Session projection、frozen prefix、resume snapshot 和 compaction。
- 后台 reflection 与主动 curiosity。
- Tool、skill 和 runtime capability disclosure。
- 对 recall、compaction、learned claims 的可观测性和评估。

## 已检查来源

Elephant Agent 来源：

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

第三方仓库在对比前均已从远端更新：

| 项目 | 检查的 HEAD | 上下文工程相关角色 |
| --- | --- | --- |
| Codex | `740d942f90` | Thread transcript、context diffing、prompt-cache-aware runtime、memory extension |
| Hermes Agent | `db2ce9e7d` | SQLite session store、compression engine、provider-aware context budgeting |
| OpenClaw | `00ca654c74` | Pluggable context engine contract、prompt-cache diagnostics、session runtime |
| RTK | `5a149a7` | 外部 command output token reduction |
| LoCoMo / locomotive | `3eb6f2c` | 长期对话记忆 benchmark 与 generated-agent memory utilities |
| vLLM | `ff990d0d32` | Serving substrate；不是可直接对比的 agent context architecture |

## Elephant 基线

Elephant Agent 的北极星很清楚：它是理解系统，不是 memory database。当前
系统设计把 durable understanding、raw trace 和 retrieval 分开：

- Personal Model 以 `identity`、`world`、`pulse`、`journey` 四个镜头
  存储受治理的活跃 claims。
- Steps 是 canonical evidence。Facts 引用 source episodes，而不是依赖
  单独的 evidence table。
- SemanticIndexEntry 指向 Steps 或 Facts，让 vector recall 成为 canonical
  records 之上的索引，而不是第二套事实来源。
- 当前轮 recall 是 volatile model support。活跃 Personal Model claims 才是
  stable prompt truth。
- Background learning 把 episodes 转化为 claims、questions、diary entries、
  skills、compression summaries 和 dream-like synthesis。

实现基本匹配这套模型：

- `packages/context` 负责 context assembly、session projection、frozen
  prefixes、token budgets、traces 和 compaction。
- `packages/evidence` 负责 unified recall orchestration 和 Step-based
  evidence access。
- `packages/understanding` 负责前台 Personal Model search 和 update surface。
- `packages/continuity` 负责 episode resume 和 interruption state。
- `packages/reflect` 负责 deterministic extraction、feature-composed
  reflection 和 compression support。
- `packages/curiosity` 负责 proactive question generation 和 ask policy。
- `apps/cli/runtime_cognition.py` 组合 runtime prompt contract，但不成为
  memory behavior 的 canonical owner。

## 第三方对比

### Codex

Codex 的上下文工程以 thread transcript manager 为中心。它的
`ContextManager` 跟踪 model-visible history、token usage、history rewrites，
并维护一个 `reference_context_item` 基线，用于 context-state diffing 和
reinjection。这是很强的 runtime engineering：上下文可以 rewrite、rollback、
normalize 后进入 prompt，并和稳定基线比较。

Codex 的 memory 是 extension-shaped。memories extension 在功能启用时注入
developer policy prompt fragments，并提供可选 read tools。这是紧凑的集成边界，
但 durable user model 并不是核心组织原则。

对 Elephant 有用的启发：

- 在安全处用 prompt-state diffing 代替完整 stable-prefix reinjection。
- 为 compaction 和 rollback 显式记录 history version。
- 引入 prompt-cache-aware context stability diagnostics。

### Hermes Agent

Hermes 很务实，偏运维型。它用 SQLite 存 full session history、session
metadata、model configuration 和 FTS5 search。它的 context compressor 会保护
head 和 recent tail，裁剪旧 tool results，做 provider-aware context-length
detection，估算包含 tool schemas 在内的完整 request tokens，并在 compression
效果不足时 back off。

Hermes 的 provider support 和 durable session mechanics 很强，但 core loop 比
Elephant 的 package-layered design 更单体。Memory、context、compression、
provider behavior 和 CLI/runtime concerns 更靠近彼此。

对 Elephant 有用的启发：

- 把 tool-schema token cost 作为一等 budget bucket。
- 暴露 compression ineffective 状态和手动 focused compression 路径。
- 让 provider context-length discovery 对 context planning 可见。

### OpenClaw

OpenClaw 是已检查第三方 agent 项目里 pluggable context-engine contract 最强的。
它的 `ContextEngine` interface 定义了 bootstrap、ingest、ingestBatch、
afterTurn、assemble、compact、maintenance、runtime LLM capabilities、safe
transcript rewrite hooks 和 subagent spawn preparation。它还建模了 prompt-cache
snapshots 与 cache-break diagnostics，覆盖 system prompt、tool set、model、
transport 和 stream strategy。

OpenClaw 强调 hot-path discipline：prepared facts 通过 runtime surfaces 向前流动，
prompt capability IDs 被 normalize 并排序，context engines 声明 host
requirements，而不是依赖隐式耦合。

对 Elephant 有用的启发：

- 把 context runtime capabilities 做成显式 contract。
- 在 context traces 中加入 prompt-cache break diagnostics。
- 为 compaction 和 maintenance 考虑 safe transcript rewrite helpers。
- 让 background context maintenance 可调度、可观测。

### RTK

RTK 不是 memory system。它是 command proxy，在输出进入 agent context 之前减少
token。它仍然相关，因为 tool output 是最容易撑爆 context budget 的来源之一。
RTK 使用 command-specific filtering、grouping、truncation、deduplication、
token-savings tracking、透明 raw-output escape hatch，以及失败时回退到原始输出。

对 Elephant 有用的启发：

- 在输出进入 Step projection 之前增加 tool-output context policy。
- 跟踪 per-tool token savings，而不只看最终 prompt token count。
- 保留 raw-output recovery path 供审计使用。

### LoCoMo / locomotive

LoCoMo 最适合作为 evaluation lens。它的数据模型包含 long-term sessions、
observations、session summaries、event summaries、evidence IDs 和 QA tasks。
它的 generative-agent utilities 会抽取 session facts，生成 self/other
reflections，并通过 embedding similarity 召回相关 facts。

对 Elephant 有用的启发：

- 建 long-horizon QA tests，答案必须跨 sessions 找 evidence。
- 评估 compaction 之后 event-summary 和 session-summary 的保存质量。
- 用 evidence IDs 给 recall 打分，而不只看答案是否“像是对的”。

### vLLM

vLLM 是 model serving 和 inference performance 项目。它可以影响 large-context
local/hosted models 的部署选择，但不提供可直接对比的 agent context engineering
逻辑。

## 能力评估

等级：

- L0：不存在
- L1：临时实现
- L2：存在，但局部或治理较弱
- L3：实现连贯，但有明显缺口
- L4：强、可检查、基本产品对齐
- L5：经过 benchmark、可自适应，并在长期生产场景中证明过

| 维度 | 等级 | 评估 |
| --- | ---: | --- |
| 架构事实来源 | L4 | 五层 Understanding System 清晰且 repo-native。剩余风险是 design、CLI projection 和 tests 之间漂移。 |
| 持久个人理解 | L4 | 四镜头活跃 claims、provenance、status、confidence 和 claim-aware search 形成强 Personal Model。还需要更强的 expiry、conflict、correction lifecycle metrics。 |
| Evidence 和 provenance | L4 | Steps as evidence 模型很干净。Fact source episodes 和 index pointers 避免重复事实来源。需要更丰富的用户可见 "why" traces 和质量评分。 |
| 当前轮 recall | L3.5 | Hybrid semantic、lexical、CJK、fuzzy、confidence、polarity signals 很强。需要 benchmark recall precision、recency、conflict behavior。 |
| Context assembly 和 token budgeting | L4 | Layered planner、frozen prefix、session projection、request attachments、source traces 和 budgets 很强。需要从 observed outcomes 中动态调预算。 |
| Compaction 和 overflow recovery | L3.5 | Reflect-first compression 加 deterministic fallback 和 protected tails 是合理的。需要 loss audits、recovery checks 和 summary quality benchmark。 |
| Continuity 和 resume | L3.5 | Episode continuity state、frozen epochs、resume snapshots 和 interruption modes 连贯。需要跨 compaction 和 provider changes 的 long-horizon resume tests。 |
| Background learning | L3.5 | Feature-composed reflect jobs 很灵活。需要更强 review gates、rollback paths，以及高影响 learned claims 的 calibration。 |
| Proactive curiosity | L3 | Lens/topic-bound question policy 避免机械填 profile。需要 outcome scoring、cadence learning 和 user-fatigue telemetry。 |
| Tool 和 skill disclosure | L3.5 | Frozen skill/tool projection 避免 eager churn。需要 lazy retrieval 和 schema-cost accounting 以减少 prompt bloat。 |
| Prompt-cache stability | L2.5 | Stable prefix design 有帮助，但 explicit cache-break measurement 还不如 OpenClaw/Codex 模式成熟。 |
| Observability 和 evaluation | L2.5 | Harness 和 traces 不错，但 context-quality benchmarks 仍早期。需要 LoCoMo-style evidence-scored suites 和 production scorecards。 |
| Plugin/provider scalability | L3 | Core package boundaries 清楚。需要更显式的 context-engine capability contracts 和面向 external providers/plugins 的 hot-path prepared facts。 |
| Tool-output pressure control | L2.5 | Context compaction 事后处理输出压力。RTK-style pre-ingest output shaping 是明显机会。 |

整体判断：Elephant 在产品模型清晰度和核心分层架构上已经接近 L4；在自适应
runtime quality 上大约 L3 到 L3.5；在 benchmarked observability 上大约 L2.5 到
L3。下一步不是“重新发明 memory”，而是测量、适配，并在长期上下文压力下硬化
context behavior。

## 优先优化方向

1. 增加 context engineering scorecard。
   跟踪 stable-prefix size、current-turn recall size、active claims injected、
   prompt-cache continuity、compaction count、retrieved evidence IDs、no-match
   rates、question outcomes，以及每轮最终 token budget allocation。

2. 建 LoCoMo-inspired evaluation suite。
   覆盖 multi-session facts、stale Pulse correction、disputed claims、
   long-horizon event summaries、compaction-after-recall cases 和 evidence ID
   grading。

3. 强化 claim lifecycle governance。
   增加 claim volatility、expiry、correction precedence、conflict handling、
   claim-local aliases，以及 write-time 生成的 multilingual pivot text。

4. 改进 recall diagnostics。
   报告 strong、weak、no match 的原因；区分 missing evidence、stale evidence、
   conflicting evidence 和 low-confidence semantic matches。

5. 硬化 compaction quality。
   增加 summary loss checks、semantic anchors、post-compaction recall probes、
   raw Step recovery references，以及 reflect compression 与 deterministic
   fallback 的对比 metrics。

6. 让 prompt-cache stability 可观测。
   跟踪 stable-prefix fingerprints、tool-set digests、model/provider changes、
   cache read/write deltas，让 runtime context changes 可解释。

7. 增加 pre-ingest tool-output shaping。
   在大输出形成 prompt pressure 之前应用 command/tool-specific summaries，同时
   为审计保留 raw Step evidence。

8. 显式化 context runtime capabilities。
   借鉴 OpenClaw contract 中有用的部分：声明 context engine 是否支持 bootstrap、
   assemble、after-turn maintenance、compact、runtime LLM calls、thread
   bootstrap 和 safe transcript rewrite。

9. 扩展 lazy tool 和 skill disclosure。
   保持 stable prompt 紧凑，只在 active task 需要时检索 tool/skill details。
   单独跟踪 schema token cost。

10. 增加用户可控 context modes。
    例如 `narrow`、`balanced`、`research`、`continuity-heavy`，映射到 recall
    breadth、claim inclusion、compaction aggressiveness 和 question cadence。

## 建议的后续 worktree 切片

| 切片 | 写入范围 | 产出 |
| --- | --- | --- |
| Scorecard baseline | `packages/context`, `packages/observability`, `tests/unit/context` | Per-turn context trace metrics 和 repo-native scorecard command |
| Long-horizon evals | `tests/scenarios/context`, `tests/unit/evidence`, `tests/unit/understanding` | Evidence-scored recall 和 compaction fixtures |
| Recall diagnostics | `packages/evidence`, `packages/understanding`, `apps/cli` | Strong/weak/no-match reasons 和 conflict/staleness labels |
| Compaction audit | `packages/context`, `packages/reflect`, `tests/unit/context` | Summary loss checks 和 post-compaction recall probes |
| Prompt-cache observability | `packages/context`, `apps/cli/runtime_cognition.py` | Stable-prefix/tool/model fingerprints 和 cache-break reporting |
| Tool-output pressure | `packages/tools`, `packages/context`, `packages/evidence` | 保留 raw evidence 的 pre-ingest output shaping |
