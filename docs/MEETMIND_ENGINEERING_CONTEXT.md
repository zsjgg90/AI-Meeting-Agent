# MeetMind AI Engineering Context v1.0

Version:
v1.0

Status:
FROZEN（冻结）

Last Update:
2026-08-21


# 1. Project Identity（项目身份）


MeetMind AI 是一个 AI Meeting Analyst（AI会议分析系统）。

目标：

将会议录音转换为：

- 会议议程
- 会议总结
- 核心结论
- 待办事项
- 遗留问题
- 风险关注


核心目标：

不是简单会议总结。

而是：

Meeting Semantic Intelligence System
（会议语义智能系统）


---

# 2. Core Architecture（核心架构）


完整流程：


Audio

↓

ASR（语音识别）

↓

Transcript（会议文本）

↓

Semantic Intelligence Layer
（语义智能层）

↓

RAG Pipeline
（检索增强流程）

↓

Agent Reasoning
（智能推理）

↓

Meeting Analysis Schema

↓

PostgreSQL

↓

Mobile App


---

# 3. Module Responsibility（模块职责）


## Semantic Intelligence Layer

目录：

services/worker/app/semantic_intelligence/


负责：

- Event Understanding（事件理解）
- Boundary Engine（边界引擎）
- Rule Planner（规则规划器）
- Retrieval Bridge（检索桥接）


职责：

理解会议语义。

判断：

- 是否是决策
- 是否是任务
- 是否是风险


禁止：

直接生成最终会议结果。


---

## RAG Retriever

文件：

services/worker/app/rag_retriever.py


负责：

规则知识检索。


当前：

Embedding Model（向量模型）:

BAAI/bge-m3


Vector Database（向量数据库）:

Chroma


禁止：

修改业务判断逻辑。


---

## Summary Agent

负责：

最终分析编排。


输入：

Semantic Context

+

Retrieved Evidence


输出：

Meeting Analysis Schema


---

# 4. Semantic Decision Rules（语义判断规则）


## Decision（决策）

只有：

- 确认
- 批准
- 决定
- 执行

才允许进入：

key_conclusions


例如：

允许：

"确认下周上线这个功能"


不允许：

"这个功能后面可以研究一下"



---

## Action Item（待办）

必须具备：

- task
- owner
- commitment


不能根据普通讨论生成任务。


---

## Risk（风险）

必须：

包含：

潜在影响

或者

未来不确定性。


---

# 5. RAG Architecture（RAG架构）


当前：

BGE-M3 Dense Retrieval
（BGE-M3稠密检索）


流程：


Semantic Context

↓

Query Planning
（查询规划）

↓

BGE-M3

↓

Chroma

↓

Rule Evidence


未来：

增加：

Reranker
（重排序）


推荐：

BAAI/bge-reranker-v2-m3


---

# 6. Current Development Phase（当前开发阶段）


Current:

Phase7.5 Retriever Integration
（检索器集成）


目标：

完成：

Semantic Intelligence

↓

RAG Retriever

↓

Evidence


闭环。


---

# 7. Completed Modules（已完成模块）


完成：

✅ ASR Pipeline

✅ Meeting Analysis Schema

✅ Semantic Intelligence 基础模块

✅ Gate B1 Knowledge Base

✅ BGE-M3 Vector Build

✅ Chroma Collection

✅ Retrieval Evaluation Framework


---

# 8. Architecture Decisions（架构决策）


## Decision 1

BGE-M3 is frozen.

原因：

Gate B1知识库已经基于BGE-M3构建。


任何Runtime必须保持一致。


---

## Decision 2

Semantic Intelligence cannot be replaced by LLM.


原因：

会议场景需要：

Boundary Judgment
（边界判断）


防止：

proposal → decision

discussion → conclusion


---

## Decision 3

Dify is Workflow Orchestration Layer.


Dify负责：

- Agent Workflow
- Prompt实验
- 模型测试


Dify不是：

核心RAG

不是：

Semantic Intelligence替代。


---

# 9. Dify Integration Plan（Dify接入规划）


当前：

Gate A


职责：

Candidate Generation
（候选生成）


未来：

Dify Gate A

↓

Semantic Intelligence Gate B

↓

RAG Evidence

↓

Final Agent


---

# 10. Development Rules（开发规则）


所有Codex任务必须：

1.
先理解现有架构。


2.
最小修改原则。


3.
禁止无理由重构。


4.
保持接口兼容。


5.
修改后必须测试。


6.
发现架构冲突：

停止扩大修改范围。


---

# 11. Forbidden Changes（禁止事项）


禁止：

- 替换Vector Database
- 删除评测体系
- 绕过Semantic Intelligence
- 直接让LLM决定业务字段
- 修改冻结接口


未经确认禁止：

- 大规模重构
- 更换Embedding模型
- 修改Schema


---

# 12. Codex Execution Protocol（Codex执行协议）


每次任务：

必须输出：


1.
当前理解


2.
修改计划


3.
影响范围


4.
执行结果


5.
测试结果


---

END
