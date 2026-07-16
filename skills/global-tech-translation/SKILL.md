---
name: global-tech-translation
description: 当用户希望把一个或多个海外技术文章 URL 转成可追溯的翻译稿件包（含分析文件、共享提示词、草稿、终稿、来源标注、翻译质检和低成本模型路由）时，使用此技能。
---

# 海外技术文章翻译

## 触发方式

1. 推荐触发方式
- 你可以直接用自然语言触发，不需要背命令行参数。
- 最稳妥的说法，是在需求里明确提到“翻译”以及 URL。
- 如果你想更明确，也可以直接提到 `global-tech-translation` 这个技能名称。

2. 可直接使用的自然语言示例
- `翻译这篇文章：https://example.com/post`
- `把这个 URL 按 global-tech-translation skill 跑一遍：https://example.com/post`
- `用当前翻译 skill 处理这个链接：https://example.com/post`
- `帮我把这篇英文技术文章生成完整翻译稿包：https://example.com/post`
- `抓取并翻译这个页面，结果放到当前文件夹的 output 目录：https://example.com/post`

3. 触发后的默认行为
- 抓取 URL 正文内容。
- 下载正文里实际引用到的图片到结果目录，并保留图片占位与描述信息。
- 生成 `00-source.md`、`01-analysis.md`、`02-shared-prompt.md`、`translation.md`、`qa.json` 等产物。
- 在无 API Key 场景下，额外生成 `08-agent-handoff.md` 和 `09-agent-completion-prompt.md`，明确要求当前 agent 接管剩余翻译步骤并在同一轮完成成稿。
- 默认写入当前文件夹下的 `output/` 目录，也就是本技能仓库内的 `./output/`。
- 若原文含外链，最终 `translation.md` 默认在正文中渲染为 `文本[1]`，并在文末自动生成 `## 引用`；分块翻译阶段应先保留 Markdown 链接，不要在单个 chunk 内手工重编引用号。

## 译风与术语

- 译文要更像成熟中文作者写出来的东西，不要只做到“信息没错”。
- 少用空泛开头、套话转折和直译腔，优先选中文里更顺手的动词、形容词和节奏。
- `human-in-the-loop` 和 `HITL` 默认译为 `人工参与决策`；在上下文更强调协作流程时，也可以写成 `人机协同`。
- `token` 一律译为 `词元`，不要写成英文 `Token`。
- `AI`、`Agent` 等行业通用缩写可以保留原词，但句子整体必须读起来像中文。
- 如果某个说法“对，但不自然”，优先按中文习惯重写，而不是贴着英文语序硬翻。

## 概述

将一个 URL 处理为可复用的稿件包：

1. `00-source.md`：清洗后的原文内容与本地图片链接。
2. `01-analysis.md`：文章结构、术语、风险和风格建议。
3. `02-shared-prompt.md`：共享翻译提示词与分析上下文。
4. `03-chunks.json`：分块信息。
5. `04-chunk-sources/`：每个 chunk 的原文切片。
6. `04-chunk-prompts/`：每个 chunk 对应的执行提示词。
7. `04-drafts/`：每个 chunk 的中文草稿位。
8. `05-merged.md`：按 chunk 草稿合并后的正文。
9. `translation.md`：保留结构的中文译文草稿。
10. `qa.json`：段落与资源检查结果。
11. `08-agent-handoff.md`：无 API Key 时给当前 agent 的接力说明与完成标准。
12. `09-agent-completion-prompt.md`：可直接供当前 agent 执行的接管提示词。
13. `EXTEND.md`：默认语言、目标读者、风格、分块阈值和术语覆盖配置。

当你优先考虑成本、暂时不需要完整 API/后端平台时，优先使用本技能。

## 工作流程

1. 校验范围。
- 优先处理公开可访问、RSS/API 页面或已明确授权的来源。
- 输出中必须保留来源字段。

2. 运行流水线脚本。

- 默认输出目录为当前文件夹下的 `output/`，即本技能仓库内的 `./output/`。
- 只有在你明确需要写入其他位置时，才额外传 `--output-dir`。

```bash
python3 scripts/run_translation_pipeline.py \
  --url "https://example.com/post" \
  --mode deep \
  --translator auto \
  --gemini-api-key "$GEMINI_API_KEY"
```

3. 检查输出结果。
- 确认 `00-source.md`、`translation.md`、`qa.json` 已生成。
- 发布前查看 `qa.json` 的 verdict。

4. 执行编辑审核闸门。
- 仅将 `ready` 或人工确认通过的稿件进入发布流程。
- 每个发布版本都保留原文 URL 与时间信息。
- 若目标渠道是公众号，默认不要替人工最终拍板标题与摘要；应额外产出一个供编辑选择的“人工决策区”。

5. 公众号发布前的默认交付格式。
- 当用户明确提到“公众号”“微信”“发布稿”“formatter”“排版”等场景时，除了完整 `translation.md` 之外，默认还应在回复中给出 5 项人工决策信息。
- 这 5 项依次为：`原英文标题`、`原稿子链接`、`中文标题`、`推荐公众号的中文标题`、`推荐的摘要一句话`。
- 该决策区用于辅助人工挑选，不应把“推荐公众号标题”直接覆盖成唯一正式标题，除非用户明确要求你代为定稿。
- 若正文用于公众号阅读，应尽量避免大段长坨；默认把自然段控制在较短节奏内，单段不超过 3 句话。

## 工作流模式

1. `--mode quick`
- 不分析、不分块，直接翻译。
- 适合快速看大意。

2. `--mode standard`
- 先生成分析文件与共享提示词。
- 长文自动分块，翻译后合并为统一正文。
- 适合大多数发布前翻译场景。

3. `--mode deep`（默认）
- 在 `standard` 的基础上增加 `06-critique.md` 与 `07-revision.md`。
- 若使用 API 后端，可自动生成审校意见并产出修订版。
- 若使用 `codex`/无 API 场景，则生成可续跑的审校文件与修订底稿，便于后续人工或 Codex 接管。

## 无 API Key 时的执行要求

1. 不允许把占位稿当作最终结果交付
- 如果没有 `GEMINI_API_KEY`，脚本可能只会先生成英文源文件、占位 `translation.md` 和审校脚手架。
- 这些文件只能视为中间产物，不能直接当作“翻译已完成”的结果回复给用户。

2. 默认优先由 Codex 继续完成翻译
- 在没有 API Key 的情况下，如果文章长度和上下文允许，必须继续由 Codex 直接把 `translation.md` 和 `07-revision.md` 补成正式中文稿。
- 流水线会额外生成 `08-agent-handoff.md` 与 `09-agent-completion-prompt.md`，当前 agent 必须读取它们并按要求完成剩余翻译与修订步骤。
- `codex` 路径不应再跳过分块流程；应基于 `04-chunk-sources/`、`04-chunk-prompts/`、`04-drafts/` 逐块完成，与 API 路径尽量保持同构。
- 回复用户时，应明确说明最终成品文件路径，而不是只报告流水线跑完。

4. 短文与长文的 agent 接管规则
- 若流水线最终只生成 1 个 chunk，则视为短文，agent 可按单篇文章直接接管。
- 若生成多个 chunk，则按 chunk 工单逐块完成。
- 也就是说：短文单篇，长文分块；判断标准以 `03-chunks.json` / `qa.json.agent_execution_mode` 为准。

3. 只有在确实不适合直接继续时才询问用户
- 例如文章极长、抽取质量明显异常、存在版权/范围风险，或继续翻译会带来明显时间与质量权衡时，才暂停并询问用户。
- 如果需要询问，必须明确说明原因，不能直接留下占位稿就结束。

## 翻译后端

1. `--translator auto`（推荐）
- 若提供 `GEMINI_API_KEY`，自动使用 Gemini API 翻译。
- 若未提供 API Key，自动切换到 `codex` 模式（先生成英文与占位中文，再由 Codex 模型接管翻译）。

2. `--translator gemini`
- 使用 Gemini API 翻译。
- 翻译后执行术语表替换。

3. `--translator codex`
- 不调用外部翻译 API，先产出 `00-source.md` + 占位 `translation.md`。
- 然后让 Codex 直接把 `00-source.md` 翻译改写到 `translation.md`。

4. `--translator passthrough`
- 跳过翻译，直接把原文写入中文文件占位。
- 适用于最低成本试跑与抽取调试。

## 无 API 场景（Codex 接管翻译）

1. 先运行：

```bash
python3 scripts/run_translation_pipeline.py \
  --url "https://example.com/post" \
  --mode deep \
  --translator auto
```

2. 再让 Codex 执行翻译编辑：
- 先读取输出目录中的 `08-agent-handoff.md`，按其中列出的输入文件、修改目标和完成标准接管流程。
- 再读取 `09-agent-completion-prompt.md`，按其中的执行提示完成 `translation.md` / `07-revision.md` / `qa.json` 的收口。
- 若未显式传入 `--output-dir`，上述“输出目录”固定指当前文件夹下的 `output/文章目录/`，不要改写到别的目录。
- 按 `04-chunk-prompts/` 中的提示逐块完成 `04-drafts/`，不要直接跳过 chunk 工单整篇自由改写。
- 若 chunk 源文里保留了 Markdown 链接，chunk 草稿中也继续保留 Markdown 链接；不要在单个 chunk 中手工写局部 `[1]`、`[2]` 编号，避免最终合并时引用号冲突。
- 若 `qa.json.agent_execution_mode` 为 `single_article`，则可把唯一的 chunk 当作整篇任务处理，不必人为拆出更多块。
- 读取输出目录中的 `01-analysis.md` 与 `02-shared-prompt.md`。
- 参考 `04-chunk-sources/`、`04-chunk-prompts/`、`04-drafts/` 与 `05-merged.md` 逐步翻译。
- chunk 完成后，运行 `scripts/rebuild_from_chunk_drafts.py --article-dir ./output/文章目录 --sync-revision`，自动重建 `05-merged.md`、`06-critique.md`、`07-revision.md` 和 `translation.md`。
- 最终写回同目录 `translation.md`，保留 Frontmatter、标题结构与来源字段。
- 若为 `deep` 模式，还应完成 `07-revision.md`，并将修订后的最终正文同步回 `translation.md`。
- 完成正文后，运行 `scripts/finalize_agent_translation.py`，将 `qa.json` 的接管状态收口为完成态。
- 若用户本轮明确要“翻译这篇文章”或“跑一遍技能”，默认应在同一轮里完成这一步，而不是只停在占位文件。

3. 若普通模式跑完后要升级到 `deep`：

```bash
python3 scripts/run_translation_pipeline.py \
  --resume-from ./output/文章目录 \
  --mode deep \
  --translator auto \
  --gemini-api-key "$GEMINI_API_KEY"
```

- 该命令会复用已有的分析、共享提示词、分块和合并稿，不重新抓取原文。

## 产物约定

1. `00-source.md`
- 原始清洗内容，便于回溯抽取质量。

2. `01-analysis.md`
- 记录文章结构、术语、风险和风格建议。

3. `02-shared-prompt.md`
- 记录本次翻译任务共享提示词，可检查、可修改、可复用。

4. `03-chunks.json`
- 记录分块范围，便于后续并行或局部重跑。

5. `04-chunk-sources/`
- 每个分块一个原文切片文件，供 API/agent 路径共享。

6. `04-chunk-prompts/`
- 每个分块一个执行提示词文件，供当前 agent 按固定流程接管。

7. `04-drafts/`
- 每个分块一个草稿文件。
- 在 `codex` / 无 API Key 场景下，初始会写入标准草稿骨架，而不是把整段原文直接当成译文。

8. `05-merged.md`
- 合并后的正文草稿，不带 Frontmatter。
- 在 `codex` / 无 API Key 场景下，它应反映 chunk 草稿区的汇总结果，而不是伪装成已完成译文。

9. `translation.md`
- 当前推荐主产物。
- 若面向公众号发布，正文应保留适合阅读的短段结构；标题与摘要的最终取舍默认留给人工。

## 图片处理

- 默认保留图片出现的位置占位，不要把图片直接删成纯文本。
- 图片链接继续使用当前抓取到的本地路径，方便后续在公众号编辑器里人工替换。
- 如果源图有 `alt` 或 `title`，请保留为图片描述；如果没有，就补一个清楚的占位描述，方便人工补齐。
- 不要只输出孤零零的图片链接，至少保留一行说明文字，避免后续编辑时丢失上下文。

10. `06-critique.md` / `07-revision.md`
- 仅在 `deep` 模式下生成。
- 用于记录审校意见与修订结果，支持从中间步骤继续迭代。

11. `08-agent-handoff.md`
- 在 `codex` / 无 API Key 场景下生成。
- 用于明确提示当前 agent：哪些文件要读、哪些文件必须改写、何时才算完成，不可把占位稿直接交付给用户。

12. `09-agent-completion-prompt.md`
- 在 `codex` / 无 API Key 场景下生成。
- 提供可直接执行的交接提示词，帮助当前 agent 在同一轮继续完成翻译、修订与 QA 收口。

13. `scripts/rebuild_from_chunk_drafts.py`
- 在 chunk 草稿完成后运行。
- 用于把 `04-drafts/` 自动汇总回 `05-merged.md`，并同步刷新 `06-critique.md`、`07-revision.md` 和 `translation.md`，让 agent 路径更接近 API 路径的闭环。

14. `scripts/finalize_agent_translation.py`
- 在当前 agent 已完成 `translation.md` / `07-revision.md` 后运行。
- 用于验证产物不是占位稿，并把 `qa.json.requires_agent_completion` 更新为 `false`、将 verdict 收口为 `ready`。

## 个性化配置

1. 默认读取技能目录下的 `EXTEND.md`
- 可设置 `source_language`、`target_language`、`audience`、`style`、`annotation_preference`
- 可设置 `chunk_threshold`、`max_chunk_chars`
- 可追加术语覆盖项
- `codex` 后端会自动放宽分块阈值，优先整篇处理较短和中等长度文章

2. 如需切换配置文件：

```bash
python3 scripts/run_translation_pipeline.py \
  --url "https://example.com/post" \
  --mode deep \
  --translator auto \
  --extend-file ./你的配置文件.md
```

3. 如需覆盖默认输出目录：

```bash
python3 scripts/run_translation_pipeline.py \
  --url "https://example.com/post" \
  --output-dir ./output \
  --mode deep \
  --translator auto
```

## 成本控制

1. 保留输出目录下的默认缓存文件，启用段落级缓存。
2. 通过 `--max-chars` 限制翻译字符量。
3. 预算耗尽时改用 `passthrough` 模式。

## 参考资料

1. 术语表：`references/glossary.csv`
2. 翻译角色设定：`references/women-stack-translator.md`
3. 来源合规策略：`references/source-policy.md`
4. 默认配置：`EXTEND.md`

## 资源

1. 脚本：`scripts/run_translation_pipeline.py`
