# 小红书扫码认证中心

## 架构与公开 API

小红书认证由通用 Provider 协议、`XiaohongshuLoginService`、`SessionManager` 和 `CookieStore` 组成。收藏抓取只接收 Provider 保存的 Playwright `storage_state`，不读取环境变量 Cookie，前端也不会收到 Cookie。

- `GET /api/xhs/login/qrcode`：打开官方网页并返回 `qrImage`、`qrId`、`expireTime`。
- `GET /api/xhs/login/status`：返回二维码状态、剩余秒数和统一错误。
- `GET /api/xhs/session`：返回登录状态、账号公开信息和时间信息。
- `POST /api/xhs/session/refresh`：验证会话并保存更新后的浏览器状态。
- `POST /api/xhs/logout`：清除内存及持久化会话。
- `POST /api/xhs/sync`：使用已认证会话同步收藏。

错误统一包含 `code`、`message`、`detail`、`retryable`，前端不依赖异常文本判断错误类型。

## 持久化与安全

`MEMFLOW_AUTH_KEY` 是 Fernet 密钥，仅用于本机认证状态加密。`data/cookies/xiaohongshu.json` 保存 `version`、`algorithm` 和 `ciphertext` 信封；密文内部包含 `storageState`、账号摘要、`createdAt`、`updatedAt`、`expireAt`。写入采用同目录临时文件和 `os.replace`，该目录已忽略提交。

日志和 API 不输出 Cookie 或 storage state。密钥缺失时其他 MemFlow 功能可以启动，二维码接口返回不可重试的 `AUTH_KEY_MISSING`。

## 状态与失败行为

状态包括 `idle`、`checking`、`waiting_scan`、`scanned`、`confirming`、`authenticated`、`expired`、`cancelled`、`failed`、`reauth_required`。二维码默认 60 秒失效；新登录会关闭旧浏览器流程。启动时尝试解密并验证会话，失败转为 `reauth_required`，不会阻止服务启动。

二维码生成会先访问官方首页并主动点击登录入口，再识别二维码图片或 canvas；页面结构变化时以可见登录弹窗截图兜底。仍无法定位时返回 `QR_NOT_FOUND`，detail 仅包含页面 URL，不包含页面正文或 Cookie。

官方登录页返回 `website-login/error?error_code=300012` 时映射为不可重试的 `RISK_CONTROL`，提示用户切换正常网络后重试。响应 detail 只保留错误码，不回传风控 URL 中的 UUID、错误正文或其他查询参数。

## 测试覆盖

自动化测试覆盖加密文件不含明文、读写删除、错误密钥、公开会话不泄密、新 API、统一错误结构、登出及旧接口返回 404。真实扫码依赖本机 Chromium、网络和小红书页面结构，需要在正常启动环境进行手工冒烟。
