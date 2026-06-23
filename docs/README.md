# MemFlow 文档索引

本目录是 MemFlow 的实现与运维文档入口。每个新增或修改的功能模块必须在同一次变更中更新对应文档及实施日志。

## 文档

- [实施日志](00-implementation-log.md)
- [Notion 手动同步重试](05-notion-sync-retry.md)
- [本地条目 API](06-local-items-api.md)
- [SQLite 数据结构与迁移](07-sqlite-schema.md)
- [URL 与文本去重](08-deduplication.md)
- [Notion 配置验证](09-notion-validation.md)
- [测试与验收](10-testing-and-verification.md)
- [项目启动脚本](11-project-startup.md)
- [简短标题生成](12-concise-title-generation.md)

## 维护规则

功能代码、接口、数据结构或状态流转发生变化时，必须同步更新模块文档、本文索引以及 `00-implementation-log.md`。文档应包含用途、接口或调用方式、数据变化、错误处理和验证方法。
