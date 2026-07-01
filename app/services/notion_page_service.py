from __future__ import annotations
import json
from typing import Any

def safe_rich_text(text: object, max_length: int = 1900) -> str:
 value = str(text or "")
 marker = "...（内容过长已截断）"
 return value if len(value) <= max_length else value[:max_length-len(marker)] + marker

def _list(value: object) -> list[str]:
 if isinstance(value, str):
  try: value = json.loads(value)
  except (ValueError, TypeError): return [value] if value.strip() else []
 return [str(x).strip() for x in (value or []) if str(x).strip()] if isinstance(value, list) else []

def _value(data: object, name: str, default: object = "") -> object:
 return data.get(name, default) if isinstance(data, dict) else getattr(data, name, default)

def _text_block(kind: str, text: object) -> dict[str, Any]:
 return {"object":"block","type":kind,kind:{"rich_text":[{"type":"text","text":{"content":safe_rich_text(text)}}]}}

def build_notion_page_children(data: object) -> list[dict[str, Any]]:
 points = _list(_value(data,"key_points",_value(data,"core_points",[])))
 actions = _list(_value(data,"action_items",[])); keywords = _list(_value(data,"keywords",_value(data,"tags",[])))
 if not keywords and hasattr(data,"tags_list"): keywords=data.tags_list()
 platform=getattr(_value(data,"source_platform",""),"value",_value(data,"source_platform",""))
 content_type=getattr(_value(data,"content_type",""),"value",_value(data,"content_type",""))
 importance=getattr(_value(data,"importance",""),"value",_value(data,"importance",""))
 input_type=getattr(_value(data,"input_type",""),"value",_value(data,"input_type",""))
 from app.services.taxonomy_service import normalize_content_type,normalize_importance,normalize_platform
 blocks=[_text_block("heading_2","摘要"),_text_block("paragraph",_value(data,"summary","暂无摘要")),_text_block("heading_2","核心观点")]
 blocks += [_text_block("numbered_list_item",x) for x in points] or [_text_block("paragraph","暂无核心观点")]
 blocks += [_text_block("heading_2","行动建议")]
 blocks += [_text_block("numbered_list_item",x) for x in actions] or [_text_block("paragraph","暂无行动建议")]
 blocks += [{"object":"block","type":"divider","divider":{}}, _text_block("heading_2","分类信息")]
 fields=[("来源平台",normalize_platform(str(platform),str(_value(data,"source_url","")),str(input_type))),("内容类型",normalize_content_type(str(content_type))),("一级分类",_value(data,"category_level_1","其他")),("二级分类",_value(data,"category_level_2","未分类")),("关键词","、".join(keywords)),("重要程度",normalize_importance(str(importance)))]
 blocks += [_text_block("bulleted_list_item",f"{k}：{v or '无'}") for k,v in fields]
 blocks += [_text_block("heading_2","原始信息")]
 raw=[("原始链接",_value(data,"source_url","")),("原文语言",_value(data,"original_language",_value(data,"language","未知"))),("是否翻译",_value(data,"is_translated",False)),("本地条目 ID",_value(data,"id",_value(data,"item_id",""))),("创建时间",_value(data,"created_at",""))]
 blocks += [_text_block("bulleted_list_item",f"{k}：{v if v not in (None,'') else '无'}") for k,v in raw]
 return blocks
