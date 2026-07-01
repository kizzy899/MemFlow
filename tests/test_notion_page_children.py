from app.services.notion_page_service import build_notion_page_children,safe_rich_text
def test_children_structure_and_json_lists():
 children=build_notion_page_children({"summary":"s","key_points":"[\"p\"]","action_items":[],"keywords":"[\"k\"]"})
 headings=[x["heading_2"]["rich_text"][0]["text"]["content"] for x in children if x["type"]=="heading_2"]
 assert headings==["摘要","核心观点","行动建议","分类信息","原始信息"]
 assert any(x["type"]=="numbered_list_item" for x in children)
def test_safe_text_truncates():
 assert len(safe_rich_text("x"*3000))<=1900 and safe_rich_text("x"*3000).endswith("...（内容过长已截断）")
