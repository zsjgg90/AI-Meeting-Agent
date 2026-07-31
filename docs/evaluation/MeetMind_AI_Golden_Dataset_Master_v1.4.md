# MeetMind AI Golden Dataset Master Specification v1.4

## Version Purpose（版本目标）

本文件是 MeetMind AI Golden Dataset（黄金数据集）的长期规范文档。

定位：

-   Specification Layer（规范层）
-   Golden Dataset Design Standard（黄金数据集设计标准）
-   Evaluation Governance（评测治理规范）

本文件不作为直接评测数据使用。

实际评测数据位于：

    data/eval/meeting_cases/

------------------------------------------------------------------------

# 1. Golden Dataset Architecture（黄金数据集架构）

Golden Dataset 由三层组成：

    Golden Dataset Specification（规范层）

                ↓

    Golden Cases（案例层）

                ↓

    Evaluation System（评测层）

## Specification Layer（规范层）

负责定义：

-   数据标准
-   标注规则
-   评测指标
-   版本策略

## Golden Cases（案例层）

实际测试案例：

    case/

    ├── transcript.txt
    ├── metadata.json
    ├── expected.json
    ├── traps.json
    └── annotation.md

## Evaluation System（评测层）

负责：

-   执行模型测试
-   对比 expected.json
-   生成评测报告

------------------------------------------------------------------------

# 2. Transcript Standard（会议原文标准）

## Speaker Format（说话人格式）

统一：

    [时间][角色]

    会议内容

要求：

包含：

-   Speaker（说话人）
-   Timestamp（时间）
-   Natural Conversation（自然表达）

## Natural Conversation（真实会议）

必须保留：

-   讨论过程
-   意见冲突
-   澄清过程
-   决策变化

禁止：

-   直接写总结
-   提前生成结论
-   人工归纳答案

------------------------------------------------------------------------

# 3. Decision State Model（决策状态模型）

会议中的信息状态：

    Proposal（建议）

    ↓

    Discussion（讨论）

    ↓

    Evaluation（评估）

    ↓

    Pending（待确认）

    ↓

    Decision（最终决定）

规则：

禁止：

-   Proposal → Decision
-   Hypothesis → Fact
-   Discussion → Conclusion

------------------------------------------------------------------------

# 4. Evaluation Capability（评测能力）

## Intent Classification（意图分类）

识别：

-   信息同步
-   建议
-   问题
-   决策
-   风险

## Decision Intelligence（决策智能）

判断：

-   是否形成决定
-   决策内容
-   决策依据

## Action Extraction（任务抽取）

识别：

-   Task
-   Owner
-   Deadline

## Evidence Grounding（证据对齐）

所有输出必须包含：

-   source_text
-   speaker
-   timestamp

## Hallucination Control（幻觉控制）

禁止：

-   编造任务
-   编造负责人
-   编造风险
-   添加无依据结论

## Agent Memory（智能体记忆）

测试：

-   跨会议状态变化
-   历史任务追踪
-   风险演进

------------------------------------------------------------------------

# 5. Evaluation Trap（评测陷阱）

每个 Golden Case 应包含：

## Proposal vs Decision

防止建议被识别为决定。

## Hypothesis vs Fact

防止假设被识别为事实。

## Hidden Risk

测试隐含风险识别。

## Deadline Conflict

测试时间冲突。

## Missing Owner

防止自动生成负责人。

## Unresolved Issue

测试遗留问题识别。

------------------------------------------------------------------------

# 6. Negative Cases（负样本）

维护：

    edge_cases/

包括：

-   false_decision
-   false_task
-   hidden_risk
-   deadline_conflict
-   unresolved_issue

用于测试模型边界能力。

------------------------------------------------------------------------

# 7. Cross Meeting Memory（跨会议记忆）

维护：

    memory_cases/

用于测试：

-   状态变化
-   历史任务
-   风险持续性
-   决策演进

示例：

    project_v25/

    week1

    week2

    week3

------------------------------------------------------------------------

# 8. Annotation Layer（标注层）

每个 Case 必须包含：

    annotation.md

记录：

-   Intent Trap（意图陷阱）
-   Decision State（决策状态）
-   Evidence Location（证据位置）
-   Expected Reasoning（预期推理）
-   Common Errors（常见错误）

------------------------------------------------------------------------

# 9. Evaluation Metrics（评测指标）

## Decision Precision（决策准确率）

AI识别出的决策中正确比例。

## Task Recall（任务召回率）

真实任务被识别比例。

## Risk Recall（风险召回率）

真实风险被识别比例。

## Hallucination Rate（幻觉率）

无证据输出比例。

## Evidence Coverage（证据覆盖率）

输出是否有原文支撑。

------------------------------------------------------------------------

# 10. Dataset Governance（数据治理）

## Maintainer（维护责任）

Golden Dataset 需要明确维护者。

负责：

-   新增案例审核
-   Schema检查
-   版本发布

## Update Process（更新流程）

新增 Case：

    Case设计

    ↓

    人工审核

    ↓

    Schema验证

    ↓

    Baseline测试

    ↓

    正式发布

## Freeze Policy（冻结策略）

Benchmark版本冻结后：

禁止直接修改：

-   expected.json
-   evaluation rules

如需修改：

必须升级版本。

------------------------------------------------------------------------

# 11. Golden Case Quality Checklist（案例质量检查）

## Transcript

检查：

□ 是否真实会议表达

□ 是否包含讨论过程

□ 是否存在决策状态变化

## Expected

检查：

□ 是否六维完整

□ 是否包含source_text

□ 是否包含speaker

□ 是否包含timestamp

## Trap

检查：

□ 是否包含错误模式

□ 是否覆盖模型容易犯错场景

## Annotation

检查：

□ 是否解释正确原因

□ 是否记录失败模式

------------------------------------------------------------------------

# 12. Model Evaluation Lifecycle（模型评测生命周期）

标准流程：

    Baseline Evaluation（基线评测）

    ↓

    Experiment（实验优化）

    ↓

    Evaluation（重新评测）

    ↓

    Failure Analysis（失败分析）

    ↓

    Improvement（优化）

    ↓

    Regression Test（回归测试）

适用于：

-   Prompt优化
-   RAG优化
-   Model升级
-   Validator优化

------------------------------------------------------------------------

# 13. Failure Taxonomy（失败分类）

AI失败分为：

## Intent Error（意图错误）

例如：

建议识别为决定。

## Evidence Error（证据错误）

例如：

输出无原文依据。

## Extraction Error（抽取错误）

例如：

遗漏任务。

## Reasoning Error（推理错误）

例如：

错误判断风险。

## Memory Error（记忆错误）

例如：

跨会议状态错误。

------------------------------------------------------------------------

# 14. Dataset Expansion Strategy（数据扩展策略）

版本规划：

    v1.4

    Benchmark冻结版本


    v1.5

    增加真实ASR噪声案例


    v1.6

    增加跨会议Memory案例


    v2.0

    增加企业级长期会议知识案例

------------------------------------------------------------------------

# Final Structure（最终结构）

    docs/

    └── evaluation/

        ├── MeetMind_AI_Golden_Dataset_Master_v1.4.md
        ├── Evaluation_Metrics.md
        └── Annotation_Guide.md


    data/

    └── eval/

        └── meeting_cases/

            ├── standard_cases/
            ├── edge_cases/
            └── memory_cases/

该规范作为：

-   Qwen3优化
-   RAG优化
-   Validator优化
-   Intent优化
-   Agent Memory优化

的长期 Benchmark Specification（评测规范）。
