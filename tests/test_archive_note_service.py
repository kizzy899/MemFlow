from app.models.content_item import ContentItem
from app.services.archive_note_service import build_archive_children, build_archive_markdown


def test_archive_note_has_all_fixed_sections():
    item=ContentItem(title="标题", source_url="https://a", normalized_url="https://a/", summary="摘要", core_points='["观点"]', action_items='["建议"]', key_concepts='[{"name":"概念","explanation":"解释"}]', related_entities='{"people":["人物"],"organizations":[],"projects":[],"tools":[]}', knowledge_relations='[{"title":"旧笔记","relation":"补充","conflict_or_complement":"无冲突"}]', source_type="网页")
    markdown=build_archive_markdown(item); children=build_archive_children(item)
    for heading in ("原文链接","规范链接","摘要","核心观点","关键概念","关联实体","可行动建议","与已有知识的关联","来源信息"):
        assert f"## {heading}" in markdown
        assert any(block.get("heading_2",{}).get("rich_text",[{}])[0].get("text",{}).get("content")==heading for block in children if block["type"]=="heading_2")