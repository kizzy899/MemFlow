# 连接现有 Chrome 读取小红书收藏

## 工作原理

MemFlow 通过 Chrome DevTools Protocol（CDP）连接用户已经登录的真实 Chrome。连接仅使用 `CHROME_CDP_URL`（默认 `http://127.0.0.1:9223`），不要求用户复制 Cookie。

```text
用户在 Chrome 登录小红书
        ↓
Chrome 在 127.0.0.1 开启 CDP
        ↓
POST /api/xhs/login/chrome
        ↓
MemFlow 连接默认浏览器上下文并验证 web_session/a1
        ↓
登录态加密保存，前端只收到账号摘要
        ↓
收藏同步在真实 Chrome 新建临时标签页
        ↓
读取完成后只关闭临时标签，不关闭 Chrome
```

## 启用与连接流程

1. 在仓库根目录运行 `.\scripts\start_chrome_cdp.ps1`。脚本使用忽略提交的 `data/chrome-cdp-profile` 启动真实 Chrome，并将 CDP 限定到 `127.0.0.1:9223`。
2. 首次在该 Chrome 窗口登录小红书，手动确认个人主页的“收藏”页可访问；以后会复用该资料目录。
3. 在 PowerShell 验证 `http://127.0.0.1:9223/json/version` 可以访问；如果使用其他端口，同时为脚本传入 `-Port` 并在 `.env` 设置 `CHROME_CDP_URL`。
4. 重启 MemFlow，打开 `/console/login/xiaohongshu`，点击“连接当前 Chrome”。
5. 连接成功后可调用 `POST /api/xhs/sync`；Chrome 必须保持运行且 CDP 仍可连接。

账号管理页提供“本次读取数量”输入框，范围 1–100。点击“开始读取收藏”后，浏览器直接发送 `POST /api/xhs/sync`，请求体为 `{"limit": N}`；无需生成或执行 PowerShell 命令。页面在请求期间禁用按钮，并显示成功整理条数或后端错误。

当前机器若未真正监听 9223，连接接口返回 `CDP_UNAVAILABLE`。现代 Chrome 可能拒绝为默认资料目录开启调试端口，因此项目脚本固定使用独立持久资料目录。Chrome 自身的 `chrome://inspect` 授权服务可能占用 9222，但它不一定提供 Playwright 所需的 `/json/version`，所以项目避开该端口。

## API、状态与失败

- `POST /api/xhs/login/chrome`：连接 Chrome、验证小红书登录、捕获账号摘要并加密保存 storage state。
- `GET /api/xhs/session`：返回登录状态和账号公开信息，不返回 Cookie。
- `POST /api/xhs/session/refresh`：CDP 已连接时重新验证真实 Chrome。
- `POST /api/xhs/logout`：删除 MemFlow 保存的会话，不退出 Chrome 中的小红书账号。
- `POST /api/xhs/sync`：在真实 Chrome 的默认上下文创建临时标签读取收藏。

`limit` 默认 20，后端强制限制为 1–100；越界请求返回 HTTP 422。

成功状态为 `authenticated`；常见错误包括 `CDP_UNAVAILABLE`、`CDP_NO_CONTEXT`、`CHROME_NOT_LOGGED_IN`。错误统一包含 `code/message/detail/retryable`。

## 安全与持久化

CDP 必须只监听 `127.0.0.1`，不得暴露到局域网或公网。连接权限等同于控制浏览器，因此只连接用户明确授权的本机 Chrome。MemFlow 只关闭自己创建的临时标签。

`data/chrome-cdp-profile` 可能包含完整浏览器登录态，已加入 `.gitignore`，不得提交、备份到公开位置或与其他用户共享。

`data/cookies/xiaohongshu.json` 延续加密信封格式，密文内部保存 storage state、账号摘要和时间字段；API、前端和日志不输出 Cookie。退出登录删除该文件，但不修改 Chrome 资料目录。

## 测试覆盖

后端覆盖 CDP 连接 API、统一错误、加密存储与旧接口移除；前端覆盖连接入口且 DOM 不出现 Cookie 字段。真实 CDP 和收藏页读取依赖用户本机 Chrome、小红书账号和网络，只能进行本机冒烟验证。
