from app.services.taxonomy_service import *
def test_taxonomy_normalization():
 assert normalize_category_level_1("人工智能")=="AI"
 assert normalize_category_level_1("未知")=="其他"
 assert normalize_category_level_2("智能体开发")=="Agent开发"
 assert normalize_category_level_2("未知")=="未分类"
 assert normalize_content_type("博客")=="文章"
 assert normalize_platform(None,"https://github.com/a/b")=="GitHub"
 assert normalize_importance("very high")=="非常重要"
 assert normalize_keywords("AI、ai, Agent x " + "长"*30,max_count=8)==["AI","Agent","x","长"*20]
def test_complete_result():
 value=normalize_classification_result({"category_level_1":"大模型","category_level_2":"提示词","content_type":"Blog","importance":"high","keywords":["x","x"]})
 assert value["category_level_1"]=="AI" and value["category_level_2"]=="Prompt工程" and value["keywords"]==["x"]

def test_agent_interview_and_text_url_platform():
 assert normalize_category_level_2("面试求职", "AI Agent 岗上岸复盘") == "Agent面试"
 assert normalize_platform("manual", "http://xhslink.com/o/abc", "text") == "小红书"
