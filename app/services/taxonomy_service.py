from __future__ import annotations
import re
from urllib.parse import urlsplit
from app.taxonomy import CATEGORY_LEVEL_1, CATEGORY_LEVEL_2, CONTENT_TYPES, PLATFORMS
L1={"人工智能":"AI","大模型":"AI","智能体":"AI","agent":"AI","开发":"编程开发","编程":"编程开发","代码":"编程开发","英语":"英语学习","财务":"金融财务","金融":"金融财务","论文":"论文写作","写作":"论文写作","工具":"工具效率","效率":"工具效率","项目":"项目灵感","职业":"职业发展","求职":"职业发展","生活":"生活经验"}
L2={"ai agent面试":"Agent面试","agent面试":"Agent面试","智能体面试":"Agent面试","agent 岗":"Agent面试","agent岗":"Agent面试","ai agent":"Agent开发","agent":"Agent开发","智能体":"Agent开发","大模型":"大模型应用","llm":"大模型应用","提示词":"Prompt工程","prompt":"Prompt工程","前端":"前端开发","后端":"后端开发","数据库":"数据库","sql":"数据库","docker":"DevOps","部署":"DevOps","运维":"DevOps","区块链":"区块链开发","python":"Python","javascript":"JavaScript","java":"Java","测试":"测试运维","财务":"财务分析","经营":"经营分析","文献":"文献综述","论文":"论文资料","效率":"效率工具","知识管理":"知识管理","学习":"学习方法","产品":"产品设计","面试":"面试求职","求职":"面试求职","生活":"生活经验"}
TYPES={"article":"文章","博客":"文章","blog":"文章","video":"视频","note":"笔记","教程文章":"教程","tutorial":"教程","项目":"代码项目","repository":"代码项目","repo":"代码项目","code_project":"代码项目","paper":"论文","inspiration":"灵感","灵感记录":"灵感","tool":"工具","工具推荐":"工具","resource_collection":"资料合集"}
PLATFORM_ALIASES={"web":"Web","manual":"手动输入","手动文本":"手动输入","xiaohongshu":"小红书","bilibili":"B站","wechat":"微信公众号","zhihu":"知乎","github":"GitHub","paper":"论文"}
def _match(value,allowed,aliases,default):
 text=str(value or "").strip()
 for option in allowed:
  if text.casefold()==option.casefold(): return option
 for alias,target in sorted(aliases.items(),key=lambda x:len(x[0]),reverse=True):
  if alias.casefold() in text.casefold(): return target
 return default
def normalize_category_level_1(value:str|None)->str:return _match(value,CATEGORY_LEVEL_1,L1,"其他")
def normalize_category_level_2(value: str | None, context: str | None = None) -> str:
 combined = f"{value or ''} {context or ''}".casefold()
 if any(word in combined for word in ("agent", "智能体")) and any(word in combined for word in ("面试", "求职", "岗位", "上岸", "agent岗", "agent 岗")):
  return "Agent面试"
 return _match(value,CATEGORY_LEVEL_2,L2,"未分类")
def normalize_content_type(value:str|None)->str:return _match(value,CONTENT_TYPES,TYPES,"其他")
def normalize_platform(value:str|None,source_url:str|None=None,input_type:str|None=None)->str:
 host=(urlsplit(source_url or "").hostname or "").lower()
 for domains,result in [(("xiaohongshu.com","xhslink.com"),"小红书"),(("bilibili.com","b23.tv"),"B站"),(("mp.weixin.qq.com",),"微信公众号"),(("zhihu.com",),"知乎"),(("github.com",),"GitHub")]:
  if any(host==d or host.endswith("."+d) for d in domains):return result
 if host:return "Web"
 if input_type=="text" or str(value or "").strip().casefold() in {"手动文本","手动输入","manual"}:return "手动输入"
 return _match(value,PLATFORMS,PLATFORM_ALIASES,"其他")
def normalize_importance(value:str|None)->str:
 text=str(value or "").strip().casefold()
 if text in {"critical","very high","非常高","非常重要","核心"}:return "非常重要"
 if text in {"important","high","重要","较高","高"}:return "高"
 if text in {"low","低"}:return "低"
 return "中"
def normalize_keywords(keywords:list[str]|str|None,max_count:int=8)->list[str]:
 values=re.split(r"[,，、\s]+",keywords) if isinstance(keywords,str) else (keywords or [])
 result=[];seen=set()
 for value in values:
  item=str(value).strip()[:20]
  if item and item.casefold() not in seen:seen.add(item.casefold());result.append(item)
  if len(result)>=max(0,max_count):break
 return result
def normalize_classification_result(result:dict)->dict:
 data=dict(result);data.update(category_level_1=normalize_category_level_1(data.get("category_level_1") or data.get("category")),category_level_2=normalize_category_level_2(data.get("category_level_2"), " ".join(str(value) for value in data.values())),content_type=normalize_content_type(data.get("content_type")),platform=normalize_platform(data.get("platform"),data.get("source_url"),data.get("input_type")),importance=normalize_importance(data.get("importance")),keywords=normalize_keywords(data.get("keywords") or data.get("tags")));return data
