# URL 与文本去重

URL 规范化会统一 scheme/host、移除默认端口和 fragment、排序 query，并去掉 `utm_*`、`spm`、`from`、`share_from`、`share_source`、`timestamp` 等追踪参数。

文本去重会去除首尾空白、将连续空白合并为单个空格，再计算 SHA256。`normalized_url` 和 `content_hash` 使用唯一部分索引，空值不参与唯一约束。

重复内容不会再次执行抓取或 AI。若已有记录已完成处理但 Notion 状态不是 `synced`，系统只重试 Notion；已同步记录直接返回。处理阶段本身失败的记录保留原状态，避免隐式重复消耗外部服务。
