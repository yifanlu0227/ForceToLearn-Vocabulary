# Force to Learn Vocabulary

独立维护的加拿大生活英语词库。全部内容公开读取，与聊天服务无关；这里不存放用户学习记录或任何登录密钥。

App 下载地址：`https://raw.githubusercontent.com/yifanlu0227/ForceToLearn-Vocabulary/main/manifest.json`。

`authoring/lexicon.sqlite3` 是维护用 SQLite 数据库，包含 `entries`（单词、词性、中文释义、生活解释、搭配、标签等）、`forms`（同义表达和读音）、`examples`（中英例句）、`lessons` 和 `lesson_entries`。可使用 SQLite 表格编辑工具或 sqlite3 维护。App 只下载经过校验的 JSON 快照，不下载维护数据库。

## 更新词库

需要 Python 3.10+。首次准备环境：

```sh
python3 -m venv /tmp/force-to-learn-vocabulary-venv
/tmp/force-to-learn-vocabulary-venv/bin/python -m pip install -r scripts/requirements-vocabulary.txt
```

1. 修改数据库；新词用新的稳定 `id`，修改已有词时递增 `revision` 并更新 `updated_on`。只导出 `status=published` 的词条。归档使用 `archived`，不要重命名已有词 ID。
2. 导出新版本。下面的 3 是下一内容版本，日期应换成发布当天：

```sh
/tmp/force-to-learn-vocabulary-venv/bin/python scripts/build_vocabulary.py authoring/lexicon.sqlite3 --from-database --version 3 --updated-on 2026-10-07 --output .
```

3. 把数据库、`manifest.json` 与新快照放在同一次提交，再推送到 GitHub：

```sh
git add authoring/lexicon.sqlite3 manifest.json releases/
git commit -m "Update life English vocabulary"
git push origin main
```

App 打开时及后台约每 24 小时检查；也可在 App 中点击「立即检查更新」。新的内容版本必须递增，旧版本不得覆盖。断网或校验失败时保留旧缓存，稳定 ID 对应的学习记录保持不变。

也可以用符合 `vocabulary/schema/catalog.schema.json` 的 JSON 文件作为维护输入，使用 `python scripts/build_vocabulary.py <文件路径> --output .` 发布。请选择一份输入作为维护来源，避免数据库和 JSON 分别修改。

读音提示（如 KUL-duh-sak）与 IPA 分开；没有核对的 IPA 保持 null。Android 使用本机离线英文 TTS，优先加拿大、备用美国英语。`forms[].audio` 为未来预录音频预留；当前 App 使用 TTS。

同义表达放在同一词条的 forms；不同词义使用不同 id。同音词的听力题用 listeningPrompt 提供上下文，例如 bus fare。
