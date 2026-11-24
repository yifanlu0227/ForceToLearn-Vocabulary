# 2026-11-23 构词与记忆补齐记录

现有词库 v48 的 1,687 条有效词全部补充原形、词根／词基、词缀和记忆方法。没有新增、归档或替换学习 ID；原始 baseline 与 batches 保持原样，通过 17 份 analyze 纠错追加解析，每条 revision 加一。

## 内容与生成

- 维护源字段为 wordAnalysis，下含 baseFormZh、rootsZh、affixesZh、mnemonicZh；每日新词使用 schemaVersion 2 同时填写。
- 使用用户配置的 Azure 部署完成全部词条生成，并做第二轮 AI 复核。第二轮提出 63 条修改，另对抽样内容和复核修改项作进一步检查和修正；去掉 208 条把词条原形泛化为永久不变的含混表述。
- 解析标注「AI 辅助整理」。两轮模型处理不是全库词典核验；不保证所有构词解释无误，可继续通过 analyze 纠错修订。记忆联想单独标明，不当作历史词源。
- 密钥仅在运行进程内通过隐藏输入使用，没有保存到仓库、输出缓存或 APK。每日新增在编写词条时同步给出解析，不需要在 GitHub Actions 或手机配置 Azure 密钥。

## 兼容与验证

发布词库保持客户端 schemaVersion 1、最低 versionCode 3。编译工具将结构化解析渲染成 usageNotesZh 的一项，显示在现有「生活里怎么说」区域，保留原有使用说明。源记录与发布记录分开处理，重复编译不会重复追加解析。

- 全部 1,687 条覆盖，四字段非空、长度与字段集合校验通过。
- 原 ID、addedOn、释义、例句、发音、标签、主题、易混淆关系保持一致；只增加解析、revision 与 updatedOn。
- 37 项 Python 测试通过，覆盖历史来源、v2 必填项、过期修订、漏填发布保护、断点缓存、API 失败与密钥保护、输出冲突和旧协议转换。
- 使用当前 Android App 实际编译的 VocabularyCodec 读取整个新快照，1,687 条均成功，清单长度、版本、SHA-256 与四项说明齐全。
- 预生成 v49 快照为 2,865,184 字节，小于客户端 5 MiB 限制；SHA-256 为 `7f0c980bf0aa06b5d2a2395421767e9ef08c5f9b0e7a6e46940715794f056df5`。

## 抽查参考

以下只用于针对性抽查，并不表示全库有词典依据：

- [crisper](https://en.wiktionary.org/wiki/crisper)：区分器具名词的 -er 与比较级。
- [sparkling](https://en.wiktionary.org/wiki/sparkling)：还原为 sparkle，不能错写为 spark 的分词。
- [committee](https://en.wiktionary.org/wiki/committee)：核对 commit 与 -ee 的构词关系，避免将 -ee 解释为泛指群体。
- [withdraw](https://en.wiktionary.org/wiki/withdraw)：with- 在此保留向后、离开的旧义。
- [refund](https://en.wiktionary.org/wiki/refund)：与现代 fund（资金）区分词源。
- [deglaze](https://en.wiktionary.org/wiki/deglaze)：区分烹饪义与去釉义，不机械按字面翻译。
- [department](https://www.collinsdictionary.com/dictionary/english/department)：核对 -ment，并避免用现代 depart 的离开义硬解释部门。

后续维护说明与模板已更新；vocabulary/analysis-policy.json 阻止任何漏填解析的有效词进入发布快照，包括误用旧源格式的新批次。
