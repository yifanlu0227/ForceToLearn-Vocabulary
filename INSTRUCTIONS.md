# Force to Learn 词库维护说明

以下路径相对公开仓库 `yifanlu0227/ForceToLearn-Vocabulary` 的根目录。

## 新增词条

1. 阅读本说明、`vocabulary/schema/batch.schema.json`、`templates/batch.json` 和 `terms.txt`。英文索引只列主词，不含中文释义、例句或其他表达；不必把完整发布词库读进 AI 上下文。
2. 在 `batches/` 新增一个 UTF-8 JSON 文件，建议命名 `YYYY-MM-DD-topic.json`。只包含这次新增内容，不复制旧词条。
3. 每个文件固定包含 `schemaVersion`（2）、`batchId`、`title`、`publishedOn`（YYYY-MM-DD）和 `entries`，全部必填。批次 ID 必须唯一。
4. 每个词条固定包含以下九个字段，全部必填；没有可选字段，也不接受额外字段。

| 字段 | 类型和要求 |
| --- | --- |
| `id` | 唯一、稳定的 ID；3–80 个小写字母、数字、点、下划线或连字符，以字母开头；不包含日期或内容版本 |
| `term` | 英文单词或完整表达 |
| `partsOfSpeech` | 非空数组；noun、verb、adjective、adverb、phrasal_verb、phrase、preposition 或 interjection |
| `definitionZh` | 简明中文释义，最多 160 字符 |
| `explanationZh` | 接地气的中文生活解释，最多 3000 字符 |
| `examples` | 1–10 个例句；每项固定包含 `en`、`zh`、`scenarioZh`，全部必填 |
| `usageNotesZh` | 1–10 条实用搭配、语气或使用说明 |
| `tags` | 1–15 个不重复的主题标签 |
| `wordAnalysis` | 固定包含 `baseFormZh`、`rootsZh`、`affixesZh`、`mnemonicZh` 四个非空字符串，每项最多 400 字符 |

以加拿大日常生活为目标，优先自然、实用的表达。中英例句应准确对应，场景具体，避免为了凑数量提供生硬句子。发音直接使用英文 TTS，不填写音标、读音提示或音频配置。模板中的词只是格式示例，新增时替换为实际候选词及其内容。

同义词使用一致的核心中文释义，语气、地区或使用差异写在 explanationZh 和 usageNotesZh；需要核对时只查询相关词条。App 会排除相同释义的干扰项，避免把另一个同样正确的答案放进选项。

## 原形、词根、词缀和记忆方法

每日新增词在同一次编写时就填写 `wordAnalysis`，不要留给手机实时请求 AI，也不要提交空字符串或待补充占位内容。新增与完整修改使用源文件 schemaVersion 2；历史 schemaVersion 1 文件保持原样。仓库的 `vocabulary/analysis-policy.json` 要求全部有效词都有解析，即使用旧格式添加新词也不能漏填。

- `baseFormZh`：单词的词典原形及实际屈折变化。unhappy 的原形仍是 unhappy；happy 是派生基础，不是 unhappy 的原形。短语说明整体形式及必要的核心动词原形。
- `rootsZh`：可靠的现代词根、词基或复合词组成及其含义。没有适合教学的拆分时明确写整体记忆；不凭字母拼凑，不编造历史词源。
- `affixesZh`：实际存在的前后缀与功能，区分派生和复数、过去式等屈折变化。短语中的独立介词和副词不是词缀；没有明显词缀就直接说明。
- `mnemonicZh`：与当前词义和例句一致的具体场景或构词联想。联想不是词源证据，避免不自然的英语和硬凑谐音。

每项建议 20–70 字，总体尽量不超过 250 字；解释必须与当前释义和例句一致。AI 生成后检查事实、原形是否混淆派生词基、短语是否被硬拆、是否有草稿式自我纠正。不要伪称已查词典。

源文件保存独立的 `wordAnalysis` 对象。发布时自动渲染为现有 `usageNotesZh` 中的一项「构词与记忆（AI 辅助整理）」，兼容当前 Android App；不要自己在 usageNotesZh 重复粘贴解析。手机更新词库后即可在「生活里怎么说」看到四项解析，离线使用，不调用 AI。学习 ID 和历史记录不变。

已有词只补充或修正解析，可使用 schemaVersion 2 的纠错：`{"action":"analyze","id":"原ID","expectedRevision":当前修订号,"wordAnalysis":{四个字段}}`。其余内容和发音数据不变，修订号仍自动递增。修改词义、拼写或例句时，完整 update 必须同时提供核对后的解析，避免保留过期内容。

批量生成工具 `scripts/enrich_word_analysis.py` 只从环境变量 `AZURE_OPENAI_API_KEY` 或隐藏终端输入读取密钥；部署名称和服务地址分别由 `AZURE_OPENAI_DEPLOYMENT`、`AZURE_OPENAI_BASE_URL` 提供。不要在命令参数、源码、日志、JSON 或 GitHub 提交中保存密钥。缓存目录放在仓库之外。

```sh
# 先设定非敏感的服务地址、部署名；密钥在隐藏提示中输入。
python scripts/enrich_word_analysis.py --cache-dir /tmp/force-word-analysis
# 抽查、复核缓存之后，明确指定此次日期，将已有缓存转成只补解析的纠错文件。
python scripts/enrich_word_analysis.py --cache-dir /tmp/force-word-analysis --write-corrections --published-on YYYY-MM-DD
```

可先用 `scripts/review_word_analysis.py --cache-dir /tmp/force-word-analysis --reviewed-dir /tmp/force-word-analysis-reviewed` 做第二轮 AI 复核，再人工抽查。复核可与生成同时运行，记录修改理由；复核结果写入独立目录。写入纠错时将 `--cache-dir` 指向复核后的目录。两次模型检查仍不是词典核验。

工具按输入内容缓存并可续跑；输入释义或例句变化会失效。输出文件不覆盖，缺少任何待补词缓存时不生成不完整补齐结果。生成和写入均不自动上传，仍需按下方要求完整校验、再走 Actions 发布。

## 查重与同义表达

- 检查词条 ID 和主词 `term`；英文比较统一大小写、连续空格、常见 Unicode 引号和连字符。
- 同义表达可以分别成为词条，各自学习、各自记录进度。`blinker` 和 `turn signal` 可以同时收录。
- 一个表达已经出现在其他词条的历史 `forms` 中，也允许作为新的主词添加。不同词条的 `forms` 重合不构成重复错误。不要把历史 `forms` 加入主词查重名单。
- 相同主词不重复新增；多种用法写在该词的解释和例句里。不同拼写、同义关系、词根关系不会被程序自动合并。
- 已归档的主词和 ID 仍保留在记录中；需要恢复时使用原 ID，不重新创建词条。

按需查询某个主词，只返回相关词条及来源：

```sh
python scripts/build_vocabulary.py --lookup "turn signal"
```

最终查重直接读取全部源文件，包括尚未发布的批次；`terms.txt` 只是帮助筛选，不是校验依据。

## 修改、归档和恢复

已发布的 `baseline/` 和 `batches/` 文件保留为历史。修改已有词时，在 `corrections/` 新增 JSON；参考 `templates/correction.json`，不要将原词再加入新增批次。

纠错文件固定包含 `schemaVersion`（2）、`correctionId`、`publishedOn`、`changes`，全部必填。修改操作固定包含 `action`（update）、`id`、`expectedRevision`、`entry`；entry 填写完整的九个必填字段，必须沿用原 ID。使用 lookup 查询实际 revision，不猜版本。修订号由工具自动递增，addedOn 保留。

归档和恢复操作分别使用 `action` 为 archive 或 restore，两者的格式都是固定的三个字段：action、id、expectedRevision。没有可选字段。归档不删除手机的学习记录，恢复沿用原 ID。

纠错按日期、correctionId 和路径顺序应用。版本已过期、未知 ID、重复操作或日期倒退都会失败，不静默覆盖。改变词条的概念时不要重用旧 ID；简单的拼写和内容纠错可以沿用原 ID。

## 提交前检查

准备 Python 3.10+ 环境并安装 `scripts/requirements-vocabulary.txt`。然后运行：

```sh
python scripts/build_vocabulary.py --check
python -m unittest discover -s scripts/tests -v
```

修复所有格式错误、ID 冲突和主词重复。交付时列出本次文件、词条数量和需要人工确认的内容。只提交新增或纠错源文件，不手工编辑 `terms.txt`、`manifest.json`、`releases/` 或内容版本号。

合入 main 后，GitHub Actions 自动聚合、校验、发布 `vocab-vN` Release，并更新 App 的 Raw 下载入口。没有实际内容变化时不增加词库版本。历史发布文件不可覆盖；撤回错误内容时通过纠错文件发布更高版本。失败的发布可以重跑，不重复创建相同发布内容。

词库只使用 JSON 源文件维护，不维护 SQLite 词库。词库源文件、发布快照与手机学习数据库分别承担维护、分发和个人进度记录；不把学习进度提交到公开仓库。
