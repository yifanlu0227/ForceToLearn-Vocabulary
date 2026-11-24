# Force to Learn 词库维护说明

以下路径相对公开仓库 `yifanlu0227/ForceToLearn-Vocabulary` 的根目录。

## 新增词条

1. 阅读本说明、`vocabulary/schema/batch.schema.json`、`templates/batch.json` 和 `terms.txt`。英文索引只列主词，不含中文释义、例句或其他表达；不必把完整发布词库读进 AI 上下文。
2. 在 `batches/` 新增一个 UTF-8 JSON 文件，建议命名 `YYYY-MM-DD-topic.json`。只包含这次新增内容，不复制旧词条。
3. 每个文件固定包含 `schemaVersion`（3）、`batchId`、`title`、`publishedOn`（YYYY-MM-DD）和 `entries`，全部必填。批次 ID 必须唯一。
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
| `wordAnalysis` | 固定为 `{"textZh":"一小段中文或空字符串"}`，最多 180 字符；无需额外解析时明确填空字符串 |

以加拿大日常生活为目标，优先自然、实用的表达。中英例句应准确对应，场景具体，避免为了凑数量提供生硬句子。发音直接使用英文 TTS，不填写音标、读音提示或音频配置。模板中的词只是格式示例，新增时替换为实际候选词及其内容。

同义词使用一致的核心中文释义，语气、地区或使用差异写在 explanationZh 和 usageNotesZh；需要核对时只查询相关词条。App 会排除相同释义的干扰项，避免把另一个同样正确的答案放进选项。

## 按需补充的精简解析

每日新增与完整修改使用源文件 schemaVersion 3。`wordAnalysis` 固定为 `{"textZh":"..."}`；字段必须存在，但 textZh 可以是空字符串 `""`，表示已判断没有额外说明的必要。历史 v1/v2 文件保持原样，通过新的 analyze 纠错迁移；仓库策略要求全部有效词使用精简格式。

解析直接展示为一小段自然中文，没有「构词与记忆（AI 辅助整理）」标题，也没有原形、词根、词缀、记忆方法四项标签。优先删掉没有信息增量的内容，不追求每个词篇幅一致。

- 简单常见词、直白搭配、已有释义和用法讲清楚的词，填 `{"textZh":""}`，不添加多余段落。
- 原形没变就不提原形；不重复词性、普通复数或规则 -s/-ed/-ing，不写「无明显词缀」「整体记忆」等占位套话。
- 简单复合词最多一句；确实有帮助的现代词基、派生关系、关键不规则形式或容易误解的含义可以保留。不要把派生基础当成词典原形。
- 助记必须连接英语词形或读音与含义，帮助回想英文；只重演释义、重复例句或日常使用场景不算助记。先自检：线索对应哪个英文片段／声音？为什么能连到这个含义？遮住英文后能否帮助回想英文，而不只是中文意思？
- hamper 的「把脏袜子放进篮子」只是在描述用途，必须省略。没有可靠构词、也没有有用助记，就留空；不要补一句「没有词根词缀」。long shot 可用「靶子很远（long），这一枪（shot）难打中」连接词形与“希望渺茫”的意思。
- 记忆画面不能冒充真实词源。不要勉强谐音、杜撰词根或引入一串更难的生词；普通构词关系直接解释，不必硬称为“联想”。不重复 definitionZh、explanationZh 和 usageNotesZh。
- 不强拆借词、专名或习语，不把独立介词和副词当词缀，不编造历史词源。不确定就省略，不伪称已查词典。
- 非空说明通常 15–60 字符；复杂词可用两句，通常不超过 100 字符，硬上限 180（含英文）。无换行、编号、Markdown 或标题；不要以空格代替空字符串。

例如 snow、making 可直接留空。snowmaking 最多「snow（雪）＋ making（制造），合起来就是造雪。」；如果原有解释已讲清这个组合，也可留空。blinker 可写「blink 是闪烁，-er 在这里表示装置：一闪一闪提示转弯的灯就是 blinker。」

发布继续兼容现有 Android App 的 schemaVersion 1：非空 textZh 作为一条使用说明追加，空字符串则完全不追加，不留下空项目符号；不向手机传递源字段 wordAnalysis。不要手工在 usageNotesZh 重复填写解析。手机离线阅读，不调用 AI；词条 ID 与学习记录保持不变。

已有词只改解析，使用 schemaVersion 3 的纠错：`{"action":"analyze","id":"原ID","expectedRevision":当前修订号,"wordAnalysis":{"textZh":"...或空字符串"}}`。其余内容保留，revision 加一。修改词义、拼写或例句时，完整 update 同时重新判断解析是否仍需要，不能无意保留过期解释。

批量工具只从环境变量 `AZURE_OPENAI_API_KEY` 或隐藏输入读取密钥；部署与地址由 `AZURE_OPENAI_DEPLOYMENT`、`AZURE_OPENAI_BASE_URL` 提供。密钥不保存到源码、日志、缓存或发布数据。生成器自动处理尚未迁移的旧四项解析或缺少解析的新词；已经精简且有意留空的词不会重复生成。

```sh
python scripts/enrich_word_analysis.py --cache-dir /tmp/force-word-analysis
python scripts/review_word_analysis.py --cache-dir /tmp/force-word-analysis --reviewed-dir /tmp/force-word-analysis-reviewed
# 抽查后使用复核缓存生成纠错；必须指定多伦多当天日期。
python scripts/enrich_word_analysis.py --cache-dir /tmp/force-word-analysis-reviewed --write-corrections --published-on YYYY-MM-DD
```

工具按输入内容缓存，可续跑；输入释义、例句、用法或旧解析变化使缓存失效。第二轮复核检查冗余与构词错误，但不等于全库词典核验。已有来源与缓存输出不覆盖；缺少任何目标词的缓存时，不写入部分纠错。生成后仍须完整校验再提交发布。

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

纠错文件固定包含 `schemaVersion`（3）、`correctionId`、`publishedOn`、`changes`，全部必填。修改操作固定包含 `action`（update）、`id`、`expectedRevision`、`entry`；entry 填写完整的九个必填字段，必须沿用原 ID。使用 lookup 查询实际 revision，不猜版本。修订号由工具自动递增，addedOn 保留。

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
