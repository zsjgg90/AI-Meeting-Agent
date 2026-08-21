# Semantic Pipeline Comparison: d31b3d49-016e-4251-9993-e139c774eb70

## Original

张伟: 人都到了吧？ 赵敏，你声音正常吗？
赵敏: 可以，能听到。
张伟: 行，那我们开始。 今天不用讲特别细，主要看几个问题。 上周那个 AI 分析稳定性，还有录音流程。 另外测试那边也反馈了一些真实场景的问题。
李娜: 我先说产品这边吧。 整体需求其实没有大的变化。 但是用户反馈有两个比较明显。 第一个就是会议结束以后，用户不知道是不是还在生成。 有些人一直点刷新。 第二个就是 AI 纪要里面，待办和问题有时候混在一起。
张伟: 这个待办混乱的问题，上周不是已经看过一次了吗？
李娜: 对，看过。 但是现在感觉还是有。
比如用户说: “这个事情后面关注一下。”
模型有时候直接变成: “负责人跟进这个事情。” 但是实际上用户只是提醒一下。
陈涛: 嗯，这个我补充一下。 其实这个不完全是 Prompt 的问题。 昨天我们跑了一批数据。 同一个会议文本，第一次出来三个待办。 第二次可能只有一个。
王强: 这个用户其实感知会很明显。 他们不会管你后面有多少层流程。
他们看到的就是: 第一次三个任务，刷新一下变两个。 然后觉得 AI 不稳定。
陈涛: 对，我理解。 但是这里可能不是一个点的问题。 现在流程比较长。 语义事件、RAG、模型生成、后处理、Validator。 都有可能影响。
李娜: 但是如果用户已经觉得不准了，技术原因其实解释不了。 他们只看结果。
陈涛: 嗯，这个我同意。 我的意思是先定位。 不要直接改一个地方，可能改完引入其他问题。
张伟: 这个优先级先确定一下。 稳定性问题最高。 标题那些优化先放一下。 先把六维输出稳定。
赵敏: 我说一下测试。 现在测试数据有一个问题。 我们之前准备的数据太规范了。 不像真实会议。
张伟: 什么意思？
比如真实会议里面不会说: “我将在8月15日前完成接口开发。”
更多是: “这个我这周尽量看一下。” “应该问题不大。” “后面有时间处理一下。”
陈涛: 对。 这种其实最难判断。 因为有些是真任务。 有些只是表达。
赵敏: 还有一个。 之前测试发现一个情况。
产品说: “是不是可以考虑增加导出功能？”
结果 AI 直接生成: “增加PDF导出功能。” 但是会议根本没决定。
李娜: 这个确实。 我们只是讨论方向。
张伟: 这个先记录。 proposal 和 decision 区分问题，需要技术评估。 但是今天不要展开。
王强: 我同步一下前端。 录音页面现在基本完成。 结束会议以后增加了二次确认。 生成状态也增加了处理中。
张伟: 什么时候可以测试？
王强: 下午吧。 不过有个小问题。 长会议详情页可能会慢一点。
陈涛: 是接口问题？
王强: 不完全是。 现在全文记录和分析结果一起加载。 长文本可能压力比较大。
陈涛: 这个后面可以拆。 但是不是 V2.6 必须。
张伟: 嗯，这个先作为优化项。 不要影响版本。
陈涛: 还有一个事情提前说一下。 现在本地14B模型测试没问题。 但是以后如果用户量起来，我感觉服务器压力可能会比较明显。 现在还没有做压测。 所以这个方案不能完全保证。
李娜: 这个会影响上线吗？
陈涛: 目前不会。 只是提前提醒。 后面需要考虑云GPU或者其他方案。
张伟: 好，这个放风险里面。
李娜: 还有一个用户体验风险。 有客户希望会议结束几分钟内看到结果。 但是长会议现在生成时间可能比较久。
张伟: 这个也是风险。 先记录，不作为当前版本任务。
张伟: 我总结一下。 第一，AI分析稳定性优先级最高。 第二，测试数据增加真实会议表达。 第三，proposal和decision区分问题技术评估。 第四，前端录音流程下午测试。 第五，生产环境模型资源风险提前关注。
张伟: 任务确认一下。 陈涛，你负责排查AI分析结果波动原因。 重点看模型输出和后处理链路。
陈涛: 可以。 我今天先跑一批Golden Dataset。 看每个阶段输出。
张伟: 什么时候给结果？
陈涛: 明天下午之前。
张伟: 赵敏，你补充真实会议测试样本。
赵敏: 好的。 我整理5个典型场景。 不过时间是今天还是明天？
张伟: 明天吧。
赵敏: 好的。
张伟: 王强，下午安排录音流程测试。
王强: 没问题。
张伟: 还有一个性能优化先不要急。 等版本稳定以后再看。 （短暂停顿）
张伟: 没有其他事情的话，今天先这样。 散会。 【会议结束】

## First Error Stage

| error_type | first_stage | suggestion | evidence |
| --- | --- | --- | --- |
| greeting_as_agenda | not_found | Fix six-dimension mapper/validator routing. |  |
| progress_as_decision | not_found | Fix six-dimension mapper/validator routing. |  |
| flow_talk_as_summary | not_found | Fix six-dimension mapper/validator routing. |  |
| commitment_inflated_as_action | 05_six_dimension_mapped | Fix six-dimension mapper/validator routing. | 可以。 我今天先跑一批Golden Dataset。 看每个阶段输出。 |
| agenda_as_risk | not_found | Fix six-dimension mapper/validator routing. |  |
| mitigation_as_risk | not_found | Fix six-dimension mapper/validator routing. |  |
| confirmed_conclusion_as_summary | not_found | Fix six-dimension mapper/validator routing. |  |

## Stage Files

- `00_speaker_contexts.json`
- `01_utterances.json`
- `02_semantic_events_raw.json`
- `03_semantic_events_validated.json`
- `04_topic_groups.json`
- `05_six_dimension_mapped.json`
- `06_six_dimension_validated.json`
- `08_responsibility_evidence_matrix.json`
- `memory_snapshot.json`
- `retrieved_memory_context.json`
- `memory_retrieval_audit.json`
- `reasoning_contexts.json`
- `reasoning_audit.json`
- `unresolved_candidates.json`
- `action_candidates.json`
- `tool_action_contracts.json`
- `action_audit.json`
- `workflow_state_observations.json`
- `workflow_recommendations.json`
- `workflow_audit.json`
- `07_final_meeting_analysis.json`