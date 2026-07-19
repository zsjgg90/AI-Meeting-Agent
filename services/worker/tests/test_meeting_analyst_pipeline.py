import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import TranscriptSegment
from app.summary_agent import (
    build_rule_based_analysis,
    clean_transcript_segments,
    enforce_boundary_rules,
    semantic_label_segments,
)


SAMPLE_DIALOGUE = [
    "产品小A：今天我们快速对齐一下短视频素材工具V2.0的优化需求。目前线上用户反馈最多的两个问题，一是素材批量下载功能卡顿、经常下载失败，二是素材分类标签混乱，用户找素材效率极低。本次迭代的核心目标，就是提升素材工具的使用流畅度，降低用户操作投诉率，同时新增素材智能推荐功能，提升用户留存。本次我提的需求主要有三个，第一，优化批量下载接口，支持一次性最多五十条素材批量下载；第二，重构素材分类标签体系，支持自定义标签、标签筛选、标签搜索；第三，首页新增个性化素材推荐模块，根据用户浏览习惯推送内容。你这边评估下整体落地难度和开发周期。",
    "研发小B：好的，我针对这三个需求逐一评估。首先，批量下载接口优化和素材标签体系重构，这两个功能技术难度不高，现有架构完全可以支撑，没有底层兼容问题。但是首页智能推荐模块有个问题，目前我们后台没有搭建用户行为数据统计体系，没有浏览、点击、收藏的用户数据，直接做智能推荐的话，只能实现随机推荐，达不到个性化推荐的业务效果，属于无效功能迭代。另外我确认一下，本次优化是否需要兼容旧版本历史数据，比如用户之前自定义的旧标签数据？",
    "产品小A：我明白你的问题，数据体系确实还没搭建。那我们做需求取舍，V2.0正式版本先砍掉智能个性化推荐功能，避免功能鸡肋、浪费开发资源，这个功能延后迭代。后续数据体系搭建完成后，我们再单独排期上线。关于旧数据，必须百分百兼容，所有用户历史自定义标签、收藏素材数据，需要无缝迁移，不能出现数据丢失、错乱的情况。另外我这边希望本次版本能在8月1日前上线，配合平台短视频创作活动。",
    "研发小B：没问题，砍掉个性化推荐后，整体开发工作量大幅减少。我梳理了一下，接口优化、标签重构、旧数据适配、页面适配优化，整体开发、自测、联调大概20天，完全可以保证8月1日前上线。另外我补充两个落地细节，第一，新标签体系上线后，需要产品输出明确的默认标签分组规则；第二，批量下载需要限制单次下载频率，防止高频请求导致服务器压力过大，这个限制规则需要产品明确标准。",
    "产品小A：这两个细节我后续全部补充进需求文档，明确标签默认规则、下载频率限制阈值。除此之外，本次迭代还有其他技术风险或者落地难点吗？",
    "研发小B：没有其他技术难点了。唯一需要注意的风险是，本次涉及用户历史数据迁移，如果迭代中途临时修改标签规则、下载逻辑，会导致数据适配返工，延误上线时间。所以我建议本次需求定稿后，全程冻结，不接受临时变更。",
    "产品小A：可以，本次需求正式冻结，全程无变更。那我们今天就敲定所有落地内容，后续按照分工推进即可。",
]


def make_segments() -> list[TranscriptSegment]:
    segments = []
    for index, text in enumerate(SAMPLE_DIALOGUE):
        speaker, content = text.split("：", 1)
        segments.append(
            TranscriptSegment(
                id=f"seg-{index}",
                meeting_id="meeting-1",
                segment_index=index,
                start_time=float(index * 10),
                end_time=float(index * 10 + 8),
                text=content,
                speaker_label=speaker,
                speaker_name=speaker,
            )
        )
    return segments


class MeetingAnalystPipelineTest(unittest.TestCase):
    def test_short_video_v2_analysis_has_six_dimensions_and_boundaries(self) -> None:
        cleaned = clean_transcript_segments(make_segments())
        labels = semantic_label_segments(cleaned)
        analysis = enforce_boundary_rules(build_rule_based_analysis(cleaned, labels, "rules-test"))

        self.assertTrue(analysis.meeting_agenda)
        self.assertTrue(analysis.meeting_summary)
        self.assertTrue(analysis.key_conclusions)
        self.assertTrue(analysis.action_items)
        self.assertTrue(analysis.unresolved_issues)
        self.assertTrue(analysis.risks_and_focus)

        transcript_sentences = [segment.text for segment in cleaned]
        self.assertFalse(any(analysis.meeting_summary == sentence for sentence in transcript_sentences))
        self.assertIn("用户痛点", analysis.meeting_summary)

        conclusions = "；".join(item.conclusion for item in analysis.key_conclusions)
        self.assertIn("个性化推荐功能本次不上线", conclusions)

        actions = "；".join(item.task for item in analysis.action_items)
        self.assertIn("默认标签分组规则", actions)

        issues = "；".join(item.issue for item in analysis.unresolved_issues)
        self.assertIn("用户行为数据", issues)

        risks = "；".join(item.risk for item in analysis.risks_and_focus)
        self.assertIn("数据迁移", risks)
        self.assertIn("返工", risks)

        action_sources = {item.source_text for item in analysis.action_items}
        issue_sources = {item.source_text for item in analysis.unresolved_issues}
        risk_sources = {item.source_text for item in analysis.risks_and_focus}
        self.assertFalse(action_sources & issue_sources)
        self.assertFalse(action_sources & risk_sources)


if __name__ == "__main__":
    unittest.main()
