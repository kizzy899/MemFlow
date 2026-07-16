# MemFlow 文档索引

本目录是 MemFlow 的实现与运维文档入口。每个新增或修改的功能模块必须在同一次变更中更新对应文档及实施日志。

## 文档

- [实施日志](00-implementation-log.md)
- [RawBlock 前端设计系统](../DESIGN.md)
- [Notion 手动同步重试](05-notion-sync-retry.md)
- [本地条目 API](06-local-items-api.md)
- [SQLite 数据结构与迁移](07-sqlite-schema.md)
- [URL 与文本去重](08-deduplication.md)
- [Notion 配置验证与连接降级](09-notion-validation.md)
- [测试与验收](10-testing-and-verification.md)
- [项目启动脚本与 Chrome CDP 自动启动](11-project-startup.md)
- [简短标题生成](12-concise-title-generation.md)
- [标签体系标准化](13-taxonomy-standardization.md)
- [Notion 页面正文排版](14-notion-page-layout.md)
- [批量 Notion 同步](15-batch-sync.md)
- [JSON 与 Markdown 导出备份](16-export-and-backup.md)
- [链接与纯文字 inbox 阅读归档](17-link-inbox-archive.md)
- [Knowledge Console 可视化控制台与外部连接稳定性](18-knowledge-console.md)

## 维护规则

功能代码、接口、数据结构或状态流转发生变化时，必须同步更新模块文档、本文索引以及 `00-implementation-log.md`。文档应包含用途、接口或调用方式、数据变化、错误处理和验证方法。

- [小红书收藏同步与 Windows 登录稳定性](17-xiaohongshu-favorites.md)
- [小红书扫码认证中心](19-xiaohongshu-qr-auth.md)
- [连接现有 Chrome 读取小红书收藏](20-chrome-cdp-auth-flow.md)
- [小红书收藏读取操作流程](21-xhs-favorites-operations-runbook.md)
- [Chrome CDP 启动与小红书 Cookie 探测修复流程](26-chrome-cdp-cookie-probe-runbook.md)
- [Agent Search 视频文字与资源链接提取](22-agent-search-skill.md)
- [小红书后台同步与 Notion 连接稳定性](23-xhs-sync-jobs-notion-stability.md)
- [小红书视频完整内容流水线](24-xhs-video-content-pipeline.md)
- [通用视频知识提取流水线](25-video-knowledge-extraction.md)
- [Global Tech Translation Skill](27-global-tech-translation-skill.md)
- [首页文章翻译后台任务](28-translation-home-task.md)
