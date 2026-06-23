# 测试与验收

## 覆盖范围

- SQLite 旧表增量升级、回填、索引和幂等执行。
- URL 追踪参数清理、文本标准化和 SHA256 去重。
- Notion 未配置、完整字段、缺失字段、类型错误和访问失败诊断。
- pending/failed 手动同步、synced 幂等、失败错误持久化。
- 条目分页、状态/类型/平台筛选、关键词搜索和失败列表。
- 文档文件及索引完整性。
- AI 标题空白清洗、长度兜底及 URL 采集标题优先级。

## 命令

```bash
python -m pytest -q
python -m compileall -q app skills tests
```

最终验收结果在 `00-implementation-log.md` 中记录。

## 本次结果

- pytest：40 passed。
- Python 编译检查：通过。
- OpenAPI 必要路由检查：通过。
- SQLite 新字段和去重索引检查：通过。
- 健康端点回归测试：通过。
