# Task：MemFlow 第三阶段增强任务：标签体系标准化、Notion 页面排版、批量同步与导出备份

## 一、项目背景

当前项目名为 MemFlow。

MemFlow 是一个基于 FastAPI 的个人知识整理 Agent，用于自动采集网页链接或手动文本，调用大模型生成结构化中文笔记，并保存到 SQLite，同时在 Notion 配置可用时同步到 Notion 数据库。

目前项目已经完成了第一阶段和第二阶段。

### 第一阶段已经完成

```text
采集输入 → 网页抓取/文本处理 → AI 结构化整理 → SQLite 保存 → Notion 同步
```

已具备能力：

1. `POST /api/collect` 统一采集接口
2. 支持 `input_type=url`
3. 支持 `input_type=text`
4. 支持网页正文抓取和清洗
5. 支持 AI 生成标题、摘要、核心观点、行动建议、分类、关键词和重要程度
6. 支持 SQLite 本地持久化
7. 支持 Notion 数据库同步
8. 支持 URL 规范化和去重
9. 支持文本 hash 去重
10. Notion 不可用时保留本地结果

### 第二阶段已经完成

已具备能力：

1. `GET /api/notion/validate`
2. `POST /api/items/{item_id}/sync-notion`
3. `GET /api/items`
4. `GET /api/items/failed`
5. `GET /api/items/{item_id}`
6. Notion 字段详细校验
7. Notion 同步失败重试
8. SQLite 字段增强和自动迁移
9. 条目分页查询、筛选、关键词搜索
10. 失败记录查询
11. 测试与文档补充

现在进入第三阶段。

本阶段目标是让 MemFlow 从“能用”升级为“长期使用时不混乱、不丢数据、Notion 页面可读性更好”的个人知识整理系统。

---

## 二、本阶段核心目标

请在现有 MemFlow 项目基础上继续增量开发，不要重建项目，不要破坏已有接口。

本阶段需要完成以下四大功能：

```text
1. 标签体系标准化
2. Notion 页面正文排版增强
3. 批量 Notion 同步
4. JSON / Markdown 导出备份
```

这四个功能的目标分别是：

### 1. 标签体系标准化

解决 AI 每次生成不同分类、不同标签，导致 Notion 标签越来越乱的问题。

例如避免出现：

```text
AI Agent
Agent开发
智能体开发
AI智能体
知识管理Agent
```

这些近义词被散乱写入 Notion。

需要通过固定分类词表和规范化映射，让一级分类、二级分类、内容类型、重要程度、平台来源保持稳定。

### 2. Notion 页面正文排版增强

当前 Notion 主要写入数据库属性。现在需要在 Notion 页面正文中写入结构化内容，让打开页面时能看到完整笔记。

页面正文应包含：

```text
摘要
核心观点
行动建议
分类信息
原始信息
本地记录信息
```

### 3. 批量 Notion 同步

当前已有单条重试同步：

```http
POST /api/items/{item_id}/sync-notion
```

现在需要新增批量同步接口，用于一键同步所有 `pending` 或 `failed` 记录。

### 4. 导出备份能力

SQLite 是本地知识数据底座。需要新增导出接口，支持把本地知识条目导出为 JSON 和 Markdown，方便备份、迁移、排查和后续接入 RAG。

---

## 三、本阶段不要做的内容

本阶段明确不要做：

1. 不要开发 Web 页面
2. 不要引入 React/Vue/Next.js
3. 不要开发浏览器插件
4. 不要做小红书自动登录
5. 不要做 B 站账号登录
6. 不要做微信公众号自动抓取
7. 不要做向量数据库
8. 不要做 RAG 问答
9. 不要做多用户系统
10. 不要做 Docker 部署
11. 不要把 SQLite 换成 PostgreSQL
12. 不要重写已有架构
13. 不要删除已有接口
14. 不要改变已有接口返回结构，除非是向后兼容地新增字段

---

# 第一部分：标签体系标准化

## 四、标准标签体系配置

请新增一个标准分类配置模块。

建议文件：

```text
app/taxonomy.py
```

或者：

```text
app/config/taxonomy.py
```

如果项目已有类似目录，请遵循现有结构。

### 1. 一级分类标准词表

一级分类必须固定为以下选项：

```python
CATEGORY_LEVEL_1 = [
    "AI",
    "编程开发",
    "英语学习",
    "金融财务",
    "论文写作",
    "工具效率",
    "项目灵感",
    "生活经验",
    "职业发展",
    "其他",
]
```

### 2. 二级分类标准词表

二级分类建议固定为以下选项：

```python
CATEGORY_LEVEL_2 = [
    "Agent开发",
    "大模型应用",
    "Prompt工程",
    "AI工具",
    "机器学习",
    "数据分析",
    "前端开发",
    "后端开发",
    "数据库",
    "DevOps",
    "区块链开发",
    "Python",
    "Java",
    "JavaScript",
    "项目架构",
    "测试运维",
    "英语词汇",
    "英语阅读",
    "英语写作",
    "财务分析",
    "经营分析",
    "论文资料",
    "文献综述",
    "写作方法",
    "效率工具",
    "知识管理",
    "学习方法",
    "产品设计",
    "职业规划",
    "面试求职",
    "生活经验",
    "未分类",
]
```

### 3. 内容类型标准词表

```python
CONTENT_TYPES = [
    "文章",
    "视频",
    "笔记",
    "教程",
    "论文",
    "代码项目",
    "灵感",
    "工具",
    "资料合集",
    "其他",
]
```

### 4. 来源平台标准词表

```python
PLATFORMS = [
    "Web",
    "小红书",
    "B站",
    "微信公众号",
    "知乎",
    "GitHub",
    "论文",
    "手动输入",
    "其他",
]
```

### 5. 重要程度标准词表

```python
IMPORTANCE_LEVELS = [
    "低",
    "中",
    "高",
    "非常重要",
]
```

### 6. 阅读状态标准词表

```python
READING_STATUS = [
    "未读",
    "已读",
    "精读",
    "已归档",
    "待处理",
]
```

### 7. AI 处理状态标准词表

```python
AI_STATUS = [
    "已完成",
    "失败",
    "跳过",
]
```

---

## 五、标签规范化服务

请新增标签规范化模块。

建议文件：

```text
app/services/taxonomy_service.py
```

### 1. 功能目标

该模块负责把 AI 输出的不稳定分类值转换成标准词表中的稳定值。

例如：

```text
AI智能体 → Agent开发
智能体开发 → Agent开发
大模型Agent → Agent开发
提示词工程 → Prompt工程
前端工程 → 前端开发
后端工程 → 后端开发
运维部署 → DevOps
财报分析 → 财务分析
毕业论文 → 论文写作
```

### 2. 需要实现的函数

建议实现：

```python
def normalize_platform(value: str | None) -> str:
    pass

def normalize_content_type(value: str | None) -> str:
    pass

def normalize_category_level_1(value: str | None) -> str:
    pass

def normalize_category_level_2(value: str | None) -> str:
    pass

def normalize_importance(value: str | None) -> str:
    pass

def normalize_keywords(keywords: list[str] | str | None, max_count: int = 8) -> list[str]:
    pass

def normalize_classification_result(result: dict) -> dict:
    pass
```

### 3. 规范化规则要求

#### 一级分类

如果 AI 输出不在标准词表中，需要根据关键词映射。

映射示例：

```python
CATEGORY_LEVEL_1_ALIASES = {
    "人工智能": "AI",
    "大模型": "AI",
    "智能体": "AI",
    "开发": "编程开发",
    "编程": "编程开发",
    "代码": "编程开发",
    "英语": "英语学习",
    "财务": "金融财务",
    "金融": "金融财务",
    "论文": "论文写作",
    "写作": "论文写作",
    "工具": "工具效率",
    "效率": "工具效率",
    "项目": "项目灵感",
    "职业": "职业发展",
    "求职": "职业发展",
}
```

如果无法识别，返回：

```text
其他
```

#### 二级分类

如果 AI 输出不在标准词表中，需要根据关键词映射。

映射示例：

```python
CATEGORY_LEVEL_2_ALIASES = {
    "AI Agent": "Agent开发",
    "Agent": "Agent开发",
    "智能体": "Agent开发",
    "智能体开发": "Agent开发",
    "大模型": "大模型应用",
    "LLM": "大模型应用",
    "提示词": "Prompt工程",
    "Prompt": "Prompt工程",
    "前端": "前端开发",
    "后端": "后端开发",
    "数据库": "数据库",
    "SQL": "数据库",
    "Docker": "DevOps",
    "部署": "DevOps",
    "运维": "DevOps",
    "区块链": "区块链开发",
    "Python": "Python",
    "Java": "Java",
    "JavaScript": "JavaScript",
    "测试": "测试运维",
    "财务": "财务分析",
    "经营": "经营分析",
    "文献": "文献综述",
    "论文": "论文资料",
    "效率": "效率工具",
    "知识管理": "知识管理",
    "学习": "学习方法",
    "产品": "产品设计",
    "面试": "面试求职",
    "求职": "面试求职",
}
```

如果无法识别，返回：

```text
未分类
```

#### 内容类型

映射示例：

```python
CONTENT_TYPE_ALIASES = {
    "Article": "文章",
    "博客": "文章",
    "Blog": "文章",
    "Video": "视频",
    "教程文章": "教程",
    "项目": "代码项目",
    "Repository": "代码项目",
    "Repo": "代码项目",
    "Paper": "论文",
    "灵感记录": "灵感",
    "工具推荐": "工具",
}
```

无法识别返回：

```text
其他
```

#### 平台来源

来源平台优先根据 URL 判断，AI 输出只作为补充。

规则：

```text
xiaohongshu.com → 小红书
bilibili.com / b23.tv → B站
mp.weixin.qq.com → 微信公众号
zhihu.com → 知乎
github.com → GitHub
手动文本 → 手动输入
无法判断 → Web 或 其他
```

#### 重要程度

如果为空，默认：

```text
中
```

如果 AI 输出类似：

```text
important
high
重要
较高
```

统一为：

```text
高
```

如果 AI 输出类似：

```text
critical
very high
非常高
核心
```

统一为：

```text
非常重要
```

如果无法识别，默认：

```text
中
```

#### 关键词

关键词规范化要求：

1. 支持 list 或字符串输入
2. 字符串可按逗号、顿号、空格、换行拆分
3. 去除空值
4. 去除重复值
5. 每个关键词去除前后空白
6. 单个关键词不超过 20 个字符
7. 最多保留 8 个
8. 如果为空，返回空列表

---

## 六、接入分类流程

请将标签规范化接入现有 AI 分类流程。

位置：

```text
classifier.py 或 agent_pipeline.py
```

要求：

1. AI 原始分类结果保留在内存即可，不一定入库
2. 写入 SQLite 和 Notion 前，必须经过标准化
3. Notion Select / Multi-select 写入时必须使用标准化后的值
4. `/api/items`、`/api/items/{item_id}` 返回时也应返回标准化后的值
5. 对历史数据不要求立即批量修复，但新增记录必须标准化

---

## 七、可选：新增重新规范化接口

如果实现成本不高，请新增接口：

```http
POST /api/items/{item_id}/normalize
```

功能：

```text
对已有条目的分类、关键词、重要程度重新执行标准化，并更新 SQLite。
```

返回示例：

```json
{
  "success": true,
  "message": "条目标签已标准化",
  "data": {
    "item_id": 1,
    "category_level_1": "AI",
    "category_level_2": "Agent开发",
    "content_type": "文章",
    "keywords": ["AI", "Agent", "知识管理"],
    "importance": "高"
  }
}
```

如果你认为会影响范围，可以先不做，但请在最终说明中标注未实现。

---

# 第二部分：Notion 页面正文排版增强

## 八、Notion 页面正文目标

当前 Notion 同步主要写数据库属性。请增强 `notion_service.py`，在创建 Notion 页面时，同时写入页面正文内容。

Notion 页面正文应让用户打开页面后直接看到完整结构化笔记。

---

## 九、Notion 页面正文结构

页面正文建议按以下结构创建 blocks。

### 页面正文结构

```text
摘要

{summary}

核心观点

1. {key_point_1}
2. {key_point_2}
3. {key_point_3}

行动建议

1. {action_item_1}
2. {action_item_2}
3. {action_item_3}

分类信息

- 来源平台：{platform}
- 内容类型：{content_type}
- 一级分类：{category_level_1}
- 二级分类：{category_level_2}
- 关键词：{keywords}
- 重要程度：{importance}

原始信息

- 原始链接：{source_url}
- 原文语言：{language}
- 是否翻译：{is_translated}
- 本地条目 ID：{item_id}
- 创建时间：{created_at}
```

---

## 十、Notion block 类型要求

请使用 Notion API 支持的 block 类型。

建议使用：

```text
heading_2
paragraph
bulleted_list_item
numbered_list_item
divider
```

页面结构示例：

```text
heading_2: 摘要
paragraph: 摘要内容

heading_2: 核心观点
numbered_list_item: 核心观点1
numbered_list_item: 核心观点2

heading_2: 行动建议
numbered_list_item: 行动建议1
numbered_list_item: 行动建议2

heading_2: 分类信息
bulleted_list_item: 来源平台：Web
bulleted_list_item: 内容类型：文章
...

heading_2: 原始信息
bulleted_list_item: 原始链接：...
...
```

---

## 十一、Notion 正文长度处理

Notion block 文本长度需要安全处理。

请实现一个工具函数：

```python
def safe_rich_text(text: str, max_length: int = 1900) -> str:
    pass
```

要求：

1. 空值返回空字符串或默认占位
2. 单个 block 文本建议不超过 1900 字符
3. 超出长度时截断，并追加：

```text
...（内容过长已截断）
```

4. 不要让 Notion API 因正文过长报错

---

## 十二、正文 blocks 构建函数

建议新增函数：

```python
def build_notion_page_children(data: CollectedContent | dict) -> list[dict]:
    pass
```

或者放在：

```text
notion_service.py
```

要求：

1. 能处理字段为空的情况
2. key_points 可能是 list，也可能是 JSON 字符串
3. action_items 可能是 list，也可能是 JSON 字符串
4. keywords 可能是 list，也可能是 JSON 字符串
5. 生成合法 Notion children blocks
6. 创建页面时把 children 一起传给 Notion API

---

## 十三、Notion 写入增强要求

写入 Notion 时应同时包含：

```python
notion.pages.create(
    parent={"database_id": database_id},
    properties=properties,
    children=children,
)
```

如果正文 blocks 创建失败，不应该影响数据库属性写入。

建议策略：

1. 优先尝试带 children 创建页面
2. 如果失败原因明显是 children 格式问题，则降级为只写 properties
3. 记录 warning 或 notion_error
4. 不要让完整同步失败，除非 properties 写入也失败

---

# 第三部分：批量 Notion 同步

## 十四、新增接口：批量同步 Notion

### 1. 接口地址

```http
POST /api/items/sync-notion/batch
```

### 2. 功能说明

批量重试同步本地记录到 Notion。

用于：

1. 用户刚配置好 Notion 后，一键同步所有 `pending`
2. 用户修复字段类型后，一键重试所有 `failed`
3. 用户指定一批 item_id 进行同步

---

## 十五、请求体设计

支持三种模式。

### 模式一：按状态同步

```json
{
  "status": "pending",
  "limit": 20
}
```

或者：

```json
{
  "status": "failed",
  "limit": 20
}
```

### 模式二：同步 pending + failed

```json
{
  "status": "all_unsynced",
  "limit": 50
}
```

其中 `all_unsynced` 表示：

```text
notion_sync_status in ["pending", "failed"]
```

### 模式三：按 item_ids 同步

```json
{
  "item_ids": [1, 2, 3]
}
```

---

## 十六、参数规则

请求体字段：

```text
status: 可选，pending/failed/all_unsynced
item_ids: 可选，整数数组
limit: 可选，默认 20，最大 100
force: 可选，默认 false
```

### 规则

1. `item_ids` 和 `status` 至少提供一个
2. 如果提供 `item_ids`，优先按 `item_ids` 同步
3. 如果没有 `item_ids`，按 `status` 查询本地记录
4. 默认不重复同步已经 `synced` 的记录
5. 如果 `force=true`，允许重新同步 `synced` 记录，但要注意可能会创建重复 Notion 页面
6. `limit` 最大 100，防止一次请求太大
7. 每条记录同步时要独立 try/except，不要因为一条失败中断整个批次

---

## 十七、批量同步返回格式

成功返回示例：

```json
{
  "success": true,
  "message": "批量同步完成",
  "data": {
    "total": 3,
    "synced": 2,
    "skipped": 1,
    "failed": 0,
    "results": [
      {
        "item_id": 1,
        "status": "synced",
        "message": "同步成功",
        "notion_page_url": "https://www.notion.so/xxx"
      },
      {
        "item_id": 2,
        "status": "synced",
        "message": "同步成功",
        "notion_page_url": "https://www.notion.so/yyy"
      },
      {
        "item_id": 3,
        "status": "skipped",
        "message": "该条目已同步，跳过",
        "notion_page_url": "https://www.notion.so/zzz"
      }
    ]
  }
}
```

部分失败示例：

```json
{
  "success": true,
  "message": "批量同步完成，部分失败",
  "data": {
    "total": 3,
    "synced": 1,
    "skipped": 0,
    "failed": 2,
    "results": [
      {
        "item_id": 1,
        "status": "synced",
        "message": "同步成功",
        "notion_page_url": "https://www.notion.so/xxx"
      },
      {
        "item_id": 2,
        "status": "failed",
        "message": "字段「摘要」不存在或类型不匹配",
        "notion_page_url": null
      }
    ]
  }
}
```

### 失败返回

如果 Notion 未配置：

```json
{
  "success": false,
  "message": "Notion 未配置：缺少 NOTION_API_KEY 或 NOTION_DATABASE_ID",
  "data": null
}
```

如果参数错误：

```json
{
  "success": false,
  "message": "请提供 status 或 item_ids",
  "data": null
}
```

---

## 十八、批量同步 Service 要求

建议新增或增强 service：

```text
app/services/notion_sync_service.py
```

如果已有相关 service，请复用。

建议函数：

```python
def retry_sync_item_to_notion(item_id: int, force: bool = False) -> dict:
    pass

def batch_sync_items_to_notion(
    status: str | None = None,
    item_ids: list[int] | None = None,
    limit: int = 20,
    force: bool = False,
) -> dict:
    pass
```

要求：

1. 单条同步逻辑复用第二阶段已有 `sync-notion` 逻辑
2. 不要重复实现 Notion 写入代码
3. 每条记录同步后更新 SQLite
4. 每条记录失败后记录 notion_error
5. 批次整体返回统计信息

---

# 第四部分：JSON / Markdown 导出备份

## 十九、新增接口：JSON 导出

### 1. 接口地址

```http
GET /api/export/json
```

### 2. 功能说明

导出 SQLite 中的知识条目为 JSON 文件或 JSON 响应。

第一版可以直接返回 JSON 响应，不一定生成实体文件。

### 3. 查询参数

支持：

```text
notion_sync_status: 可选，pending/synced/failed
category_level_1: 可选
platform: 可选
keyword: 可选
limit: 可选，默认 100，最大 1000
include_raw_content: 可选，默认 false
```

示例：

```http
GET /api/export/json?limit=100
```

```http
GET /api/export/json?category_level_1=AI&include_raw_content=false
```

### 4. 返回示例

```json
{
  "success": true,
  "message": "导出成功",
  "data": {
    "format": "json",
    "total": 2,
    "exported_at": "2026-06-21T12:00:00",
    "items": [
      {
        "item_id": 1,
        "title": "AI Agent 知识管理系统",
        "source_url": "https://example.com/article",
        "platform": "Web",
        "content_type": "文章",
        "category_level_1": "AI",
        "category_level_2": "Agent开发",
        "summary": "这篇文章讨论如何通过 Agent 自动整理知识内容。",
        "key_points": [
          "Agent 可以自动采集网页和文本",
          "结构化摘要有助于复盘"
        ],
        "action_items": [
          "先跑通单条链接采集",
          "再增加重复链接检测"
        ],
        "keywords": ["AI", "Agent", "Notion"],
        "importance": "高",
        "language": "中文",
        "notion_sync_status": "synced",
        "notion_page_url": "https://www.notion.so/xxx",
        "created_at": "2026-06-21T10:00:00",
        "updated_at": "2026-06-21T10:05:00"
      }
    ]
  }
}
```

### 5. 安全要求

默认不要导出：

```text
raw_content
clean_content
```

除非：

```text
include_raw_content=true
```

---

## 二十、新增接口：Markdown 导出

### 1. 接口地址

```http
GET /api/export/markdown
```

### 2. 功能说明

将知识条目导出为 Markdown 格式。

第一版可以返回：

```json
{
  "success": true,
  "message": "导出成功",
  "data": {
    "format": "markdown",
    "total": 1,
    "content": "# MemFlow Export\n\n..."
  }
}
```

不一定要生成 `.md` 文件。

---

## 二十一、Markdown 格式要求

Markdown 输出结构如下：

```markdown
# MemFlow Knowledge Export

导出时间：2026-06-21T12:00:00
导出数量：2

---

## 1. AI Agent 知识管理系统

- 来源平台：Web
- 内容类型：文章
- 一级分类：AI
- 二级分类：Agent开发
- 重要程度：高
- 原文语言：中文
- Notion 状态：synced
- 原始链接：https://example.com/article
- Notion 页面：https://www.notion.so/xxx
- 创建时间：2026-06-21T10:00:00

### 摘要

这篇文章讨论如何通过 Agent 自动整理知识内容。

### 核心观点

1. Agent 可以自动采集网页和文本
2. 结构化摘要有助于复盘

### 行动建议

1. 先跑通单条链接采集
2. 再增加重复链接检测

### 关键词

AI、Agent、Notion

---
```

---

## 二十二、导出 Service 要求

建议新增：

```text
app/services/export_service.py
```

建议函数：

```python
def export_items_as_json(filters: dict) -> dict:
    pass

def export_items_as_markdown(filters: dict) -> str:
    pass
```

要求：

1. 复用现有条目查询逻辑
2. 支持筛选参数
3. 支持 limit 限制
4. JSON 字段要安全解析
5. Markdown 中避免输出 `None`
6. 默认不包含 raw_content
7. 返回内容按 `created_at` 倒序排列

---

# 第五部分：数据库与迁移要求

## 二十三、SQLite 变更要求

本阶段不强制新增字段，但可以根据需要新增以下字段：

```text
taxonomy_version
export_count
last_exported_at
```

如果新增字段，必须使用已有自动迁移机制。

### 字段说明

```text
taxonomy_version：标签体系版本，例如 v1
export_count：该条目被导出的次数
last_exported_at：最近一次导出时间
```

如果实现导出次数统计，则导出接口执行后更新这些字段。

如果实现成本较高，可以暂不做，但请在最终说明中标注未实现。

---

# 第六部分：测试要求

## 二十四、标签体系测试

新增测试文件：

```text
tests/test_taxonomy_service.py
```

测试内容：

```text
1. normalize_category_level_1 能把“人工智能”转为“AI”
2. normalize_category_level_1 对未知值返回“其他”
3. normalize_category_level_2 能把“智能体开发”转为“Agent开发”
4. normalize_category_level_2 对未知值返回“未分类”
5. normalize_content_type 能把“博客”转为“文章”
6. normalize_platform 能把空值转为“其他”或根据 URL 判断为 Web
7. normalize_importance 能把“very high”转为“非常重要”
8. normalize_keywords 能去重、截断、限制数量
9. normalize_classification_result 能返回完整标准化结果
```

---

## 二十五、Notion 页面 children 测试

新增测试文件：

```text
tests/test_notion_page_children.py
```

测试内容：

```text
1. build_notion_page_children 返回 list
2. children 中包含 heading_2：摘要
3. children 中包含 heading_2：核心观点
4. children 中包含 heading_2：行动建议
5. children 中包含分类信息
6. children 中包含原始信息
7. key_points 为 JSON 字符串时也能正确解析
8. action_items 为空时不报错
9. 超长文本会被 safe_rich_text 截断
```

---

## 二十六、批量同步测试

新增测试文件：

```text
tests/test_batch_notion_sync.py
```

测试内容：

```text
1. 不传 status 和 item_ids 时返回参数错误
2. status=pending 时只同步 pending 记录
3. status=failed 时只同步 failed 记录
4. status=all_unsynced 时同步 pending 和 failed
5. item_ids 存在时优先按 item_ids 同步
6. synced 记录默认跳过
7. force=true 时允许处理 synced 记录
8. 单条失败不影响其他记录继续同步
9. 返回 total/synced/skipped/failed/results 统计
```

---

## 二十七、导出测试

新增测试文件：

```text
tests/test_export_service.py
```

测试内容：

```text
1. JSON 导出返回 format=json
2. JSON 导出默认不包含 raw_content
3. include_raw_content=true 时包含 raw_content
4. Markdown 导出返回 content
5. Markdown 中包含标题、摘要、核心观点、行动建议
6. 按 category_level_1 筛选有效
7. 按 notion_sync_status 筛选有效
8. limit 超过 1000 时自动限制或返回校验错误
```

---

# 第七部分：README 更新要求

请更新 README.md，新增第三阶段功能说明。

## 二十八、README 需要新增内容

### 1. 标签体系标准化

说明：

```text
MemFlow 会对 AI 生成的分类、平台、内容类型、关键词、重要程度进行标准化，避免 Notion 标签过度发散。
```

列出标准一级分类：

```text
AI、编程开发、英语学习、金融财务、论文写作、工具效率、项目灵感、生活经验、职业发展、其他
```

### 2. Notion 页面正文排版

说明：

```text
同步到 Notion 时，除了写入数据库属性，还会在页面正文中写入摘要、核心观点、行动建议、分类信息和原始信息。
```

### 3. 批量同步

增加命令：

```bash
curl -X POST "http://127.0.0.1:8000/api/items/sync-notion/batch" \
  -H "Content-Type: application/json" \
  -d '{"status":"all_unsynced","limit":50}'
```

Windows PowerShell：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/items/sync-notion/batch" `
  -H "Content-Type: application/json" `
  -d "{\"status\":\"all_unsynced\",\"limit\":50}"
```

### 4. JSON 导出

增加命令：

```bash
curl "http://127.0.0.1:8000/api/export/json?limit=100"
```

### 5. Markdown 导出

增加命令：

```bash
curl "http://127.0.0.1:8000/api/export/markdown?limit=100"
```

### 6. 常见问题

补充：

```text
为什么 Notion 里的分类会被改成固定值？
因为 MemFlow 会进行标签标准化，避免长期使用后标签失控。

为什么二级分类变成“未分类”？
因为 AI 输出无法映射到标准二级分类。可以在 taxonomy aliases 中增加映射规则。

为什么 Markdown 导出没有原文？
默认不导出 raw_content。需要 JSON 导出时加 include_raw_content=true。
```

---

# 第八部分：docs 文档更新要求

请新增或更新以下文档：

```text
docs/08-taxonomy-standardization.md
docs/09-notion-page-layout.md
docs/10-batch-sync.md
docs/11-export-and-backup.md
```

---

## 二十九、docs/08-taxonomy-standardization.md

内容包括：

```text
1. 为什么需要标签标准化
2. 标准一级分类
3. 标准二级分类
4. 内容类型标准词表
5. 平台来源标准词表
6. 重要程度标准词表
7. 别名映射规则
8. 新增分类时如何维护
```

---

## 三十、docs/09-notion-page-layout.md

内容包括：

```text
1. Notion 数据库属性和页面正文的区别
2. 页面正文 block 结构
3. 摘要区
4. 核心观点区
5. 行动建议区
6. 分类信息区
7. 原始信息区
8. 长文本截断策略
```

---

## 三十一、docs/10-batch-sync.md

内容包括：

```text
1. 为什么需要批量同步
2. POST /api/items/sync-notion/batch 接口说明
3. status=pending
4. status=failed
5. status=all_unsynced
6. item_ids 模式
7. force 参数风险
8. 批量同步返回统计说明
```

---

## 三十二、docs/11-export-and-backup.md

内容包括：

```text
1. 为什么需要导出备份
2. JSON 导出接口
3. Markdown 导出接口
4. 支持的筛选条件
5. raw_content 默认不导出的原因
6. 如何用导出结果迁移到其他系统
7. 后续如何接入 RAG 或向量数据库
```

---

# 第九部分：统一响应格式要求

所有新增接口必须保持统一响应格式。

成功：

```json
{
  "success": true,
  "message": "操作成功",
  "data": {}
}
```

失败：

```json
{
  "success": false,
  "message": "错误原因",
  "data": null
}
```

如果是批量操作，部分失败时：

```text
HTTP 状态码仍然可以是 200
success 可以为 true
message 写“批量处理完成，部分失败”
data 中返回 failed 数量和每条失败原因
```

---

# 第十部分：接口清单

本阶段新增或增强接口如下。

## 新增接口

```http
POST /api/items/sync-notion/batch
GET /api/export/json
GET /api/export/markdown
```

## 可选接口

```http
POST /api/items/{item_id}/normalize
```

## 已有接口需要保持兼容

```http
GET /health
POST /api/collect
GET /api/notion/validate
POST /api/items/{item_id}/sync-notion
GET /api/items
GET /api/items/failed
GET /api/items/{item_id}
```

---

# 第十一部分：代码质量要求

请遵守以下要求：

1. 不要把新逻辑都写在 `main.py`
2. `main.py` 只负责注册路由和调用 service
3. 标签规范化逻辑独立成 service
4. 导出逻辑独立成 service
5. 批量同步逻辑复用已有单条同步逻辑
6. Notion 页面正文构建逻辑可测试
7. 不要重复写 Notion 字段映射
8. 不要泄露 API Key
9. 不要提交 `.env`
10. 所有新增函数尽量有类型标注
11. 所有外部 API 调用都要 try/except
12. 所有 JSON 字符串字段读取都要安全解析
13. 不要破坏已有测试
14. 新增功能必须补充测试
15. README 和 docs 必须同步更新

---

# 第十二部分：验收标准

完成后必须满足以下条件。

## 1. 项目能正常启动

```bash
uvicorn app.main:app --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

返回正常。

---

## 2. 现有测试通过

```bash
python -m pytest -q
python -m compileall -q app skills tests
```

必须全部通过。

---

## 3. 标签标准化生效

提交一条含有 AI Agent、智能体开发、知识管理相关内容的文本后：

```text
一级分类应尽量规范为：AI
二级分类应尽量规范为：Agent开发 或 知识管理
内容类型应使用标准词表
关键词应去重且数量不超过 8
```

---

## 4. Notion 页面正文增强生效

同步到 Notion 后，打开页面应能看到正文区域包含：

```text
摘要
核心观点
行动建议
分类信息
原始信息
```

---

## 5. 批量同步接口可用

测试：

```bash
curl -X POST "http://127.0.0.1:8000/api/items/sync-notion/batch" \
  -H "Content-Type: application/json" \
  -d '{"status":"all_unsynced","limit":50}'
```

应返回：

```text
total
synced
skipped
failed
results
```

---

## 6. JSON 导出可用

测试：

```bash
curl "http://127.0.0.1:8000/api/export/json?limit=100"
```

应返回 JSON 格式知识条目列表。

---

## 7. Markdown 导出可用

测试：

```bash
curl "http://127.0.0.1:8000/api/export/markdown?limit=100"
```

应返回 Markdown 字符串内容。

---

# 第十三部分：最终输出要求

完成后，请输出以下内容：

1. 本次新增了哪些文件
2. 本次修改了哪些文件
3. 每个新增文件的作用
4. 每个修改文件的变化
5. 新增接口清单
6. 每个新增接口的请求示例
7. 每个新增接口的返回示例
8. 标签标准化规则如何工作
9. Notion 页面正文 blocks 如何构建
10. 批量同步如何避免单条失败影响整个批次
11. JSON 导出包含哪些字段
12. Markdown 导出格式是什么
13. 是否新增 SQLite 字段
14. 是否补充自动迁移
15. 新增了哪些测试
16. 如何运行测试
17. 哪些功能未实现或暂缓
18. 下一阶段建议做什么

请直接在当前 MemFlow 项目中增量实现，不要创建新项目，不要开发 Web 页面。
