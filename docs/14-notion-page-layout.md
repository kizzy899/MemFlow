# Notion 页面正文排版

数据库属性用于筛选，页面 children 用于阅读。新建页同时写入摘要、核心观点、行动建议、分类信息、原始信息；分别使用 heading_2、paragraph、numbered_list_item、bulleted_list_item 和 divider。

列表字段兼容 list 和 JSON 字符串，空区块显示占位，不输出 `None`。`safe_rich_text` 将单块限制为 1900 字并追加截断标记。带 children 创建失败时降级为仅写 properties；若属性写入也失败，沿用 failed 状态和 notion_error。更新既有页面只更新属性，避免重复正文。测试覆盖结构、JSON 列表、空行动项和截断。
