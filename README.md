# Force to Learn Vocabulary

公开维护的加拿大日常生活英语词库。个人学习进度只存在手机上，与聊天服务无关；这里不存放登录密钥。

## 新增词条

日常只需要新增一个 JSON 文件。先读 [维护说明](INSTRUCTIONS.md)、[主词索引](terms.txt) 和 [固定模板](templates/batch.json)，然后在 `batches/` 放入本次新增词条。所有字段必填，没有可选字段。

同义表达可以分别收录，例如 blinker 与 turn signal，各自记录学习进度。只检查主词 term 和 ID，不把历史 forms 当成重复主词。主词列表不包含释义和例句；需要查询详情时使用 lookup。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-vocabulary.txt
.venv/bin/python scripts/build_vocabulary.py --check
.venv/bin/python scripts/build_vocabulary.py --lookup "turn signal"
```

检查直接扫描全部源文件，不依赖英文索引是否已经更新。修改已有词时，在 `corrections/` 新增文件，参考 [纠错模板](templates/correction.json)，沿用原 ID 和正确的 expectedRevision。

## 自动发布

PR 执行格式、全库查重和发布工具测试。合入 main 后，Actions 从 `baseline/vocabulary-v3.json`、`batches/` 和 `corrections/` 聚合内容，自动递增内容版本，发布 `vocab-vN` Release，并一次性更新 Raw 快照与 manifest。完整发布包由程序生成，不需要维护者复制旧版本。

`terms.txt`、`manifest.json` 与 `releases/` 都由程序维护。历史发布不可覆盖；任务重跑可恢复未完成的发布。发布串行运行，上传并回读校验通过后才更新 App 下载清单；并发提交使用普通快进推送保护，避免旧任务覆盖新提交。公开 Release 已完成但清单推送失败时，重跑会复用匹配内容，或为新内容分配更高版本，不覆盖原 Release。

本地生成发布包用于检查，不上传：

```sh
.venv/bin/python scripts/build_vocabulary.py --output /tmp/force-vocabulary-preview
.venv/bin/python -m unittest discover -s scripts/tests -v
```

GitHub Actions 使用标准 Ubuntu runner。仓库 Settings → Actions 的策略需要允许 GitHub Actions 运行；发布任务使用内置 GITHUB_TOKEN 的 contents:write 权限，不需要个人 token。可在 Actions 中手动重跑 Publish vocabulary。

## App 下载入口

词库保持现有协议：

`https://raw.githubusercontent.com/yifanlu0227/ForceToLearn-Vocabulary/main/manifest.json`

App 启动、后台约每 24 小时及手动操作检查更新；下载完整 JSON 并验证长度、SHA-256、内容版本和引用。更新失败继续使用旧缓存，已有学习记录按稳定 ID 保留。当前 App 协议上限为 5 MiB、10000 个有效词条，发布工具会在超限时阻止发布。

[应用安装包](https://github.com/yifanlu0227/ForceToLearn-Vocabulary/releases) 使用 app-vX.Y.Z 标签，词库使用 vocab-vN。App 0.4.2 起从独立的 [app-manifest.json](app-manifest.json) 获取 APK 更新，避免词库发版挤出最近 Release 列表。词库 Release 不设为 Latest。

新增源文件只写固定内容字段，默认使用本机英文 TTS。编译工具补齐旧客户端协议字段；历史词条及其发音元数据原样保留，不恢复音标 UI。单词或表达分别收录后具有独立的学习 ID。

`authoring/lexicon.sqlite3` 是 v3 以前的历史维护数据库；后续以 JSON 源文件为唯一维护依据，不再编辑数据库发布。
