#!/usr/bin/env python3
"""Validate a catalog and prepare an immutable GitHub-downloadable release.

This is local preparation only: it does not create repositories or upload files.
An optional fresh SQLite database demonstrates the independent editorial schema.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def validate_schema(value, name):
    schema = json.loads((ROOT / "vocabulary/schema" / name).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def validate_catalog(catalog):
    validate_schema(catalog, "catalog.schema.json")
    entries = catalog["entries"]
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("词条 id 必须唯一")
    known = set(ids)
    for entry in entries:
        forms = [form["text"].casefold() for form in entry["forms"]]
        if entry["term"].casefold() not in forms or len(forms) != len(set(forms)):
            raise ValueError(f"{entry['id']}: forms 必须包含 term，且不能重复")
        if set(entry["confusableEntryIds"]) - (known - {entry["id"]}):
            raise ValueError(f"{entry['id']}: 易混淆词引用无效")
        if entry["addedOn"] > entry["updatedOn"] or entry["updatedOn"] > catalog["updatedOn"]:
            raise ValueError(f"{entry['id']}: 日期顺序无效")
    if len({entry["definitionZh"] for entry in entries}) < 4:
        raise ValueError("词库需要至少 4 个不同释义以生成四选一题目")
    lesson_ids = [lesson["id"] for lesson in catalog["lessons"]]
    if len(lesson_ids) != len(set(lesson_ids)):
        raise ValueError("主题 id 必须唯一")
    for lesson in catalog["lessons"]:
        if set(lesson["entryIds"]) - known:
            raise ValueError(f"{lesson['id']}: 主题引用了不存在的词条")


def write_sample_database(path, catalog, payload, digest):
    if path.exists():
        raise ValueError("示例数据库已存在；请指定新的路径，避免覆盖维护中的数据库")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript((ROOT / "vocabulary/schema/lexicon.sql").read_text())
        for entry in catalog["entries"]:
            db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                entry["id"], entry["revision"], entry["term"], json_text(entry["partsOfSpeech"]),
                entry["definitionZh"], entry["explanationZh"], json_text(entry["usageNotesZh"]),
                json_text(entry["tags"]), entry["listeningPrompt"], entry["homophoneGroup"],
                json_text(entry["confusableEntryIds"]), entry["addedOn"], entry["updatedOn"], "published"))
            for position, form in enumerate(entry["forms"]):
                audio = form["audio"] or {}
                db.execute("INSERT INTO forms VALUES (?,?,?,?,?,?,?,?,?)", (
                    entry["id"], position, form["text"], form["locale"], form["respelling"],
                    form["ipa"], form["speakText"], audio.get("path"), audio.get("sha256")))
            for position, example in enumerate(entry["examples"]):
                db.execute("INSERT INTO examples VALUES (?,?,?,?,?)", (
                    entry["id"], position, example["en"], example["zh"], example["scenarioZh"]))
        for lesson in catalog["lessons"]:
            db.execute("INSERT INTO lessons VALUES (?,?,?)", (lesson["id"], lesson["title"], lesson["publishedOn"]))
            for position, entry_id in enumerate(lesson["entryIds"]):
                db.execute("INSERT INTO lesson_entries VALUES (?,?,?)", (lesson["id"], entry_id, position))
        db.execute("INSERT INTO releases VALUES (?,?,?,?,?,?,?)", (
            catalog["contentVersion"], catalog["schemaVersion"], catalog["updatedOn"], digest,
            len(payload), len(catalog["entries"]), payload.decode("utf-8")))


def read_database(path, version, updated_on):
    if not path.is_file():
        raise ValueError("词库数据库不存在")
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        entries = []
        for row in db.execute("SELECT * FROM entries WHERE status = 'published' ORDER BY added_on, id"):
            forms = []
            for form in db.execute("SELECT * FROM forms WHERE entry_id = ? ORDER BY position", (row["id"],)):
                audio = {"path": form["audio_path"], "sha256": form["audio_sha256"]} if form["audio_path"] else None
                forms.append({"text": form["text"], "locale": form["locale"], "respelling": form["respelling"],
                              "ipa": form["ipa"], "speakText": form["speak_text"], "audio": audio})
            examples = [{"en": item["english"], "zh": item["chinese"], "scenarioZh": item["scenario_zh"]}
                        for item in db.execute("SELECT * FROM examples WHERE entry_id = ? ORDER BY position", (row["id"],))]
            entries.append({"id": row["id"], "revision": row["revision"], "term": row["term"],
                            "partsOfSpeech": json.loads(row["parts_of_speech_json"]), "definitionZh": row["definition_zh"],
                            "explanationZh": row["explanation_zh"], "forms": forms, "examples": examples,
                            "usageNotesZh": json.loads(row["usage_notes_zh_json"]), "tags": json.loads(row["tags_json"]),
                            "listeningPrompt": row["listening_prompt"], "homophoneGroup": row["homophone_group"],
                            "confusableEntryIds": json.loads(row["confusable_entry_ids_json"]),
                            "addedOn": row["added_on"], "updatedOn": row["updated_on"]})
        lessons = []
        for row in db.execute("SELECT * FROM lessons ORDER BY published_on, id"):
            ids = [item[0] for item in db.execute(
                "SELECT le.entry_id FROM lesson_entries le JOIN entries e ON e.id = le.entry_id "
                "WHERE le.lesson_id = ? AND e.status = 'published' ORDER BY le.position", (row["id"],))]
            if ids:
                lessons.append({"id": row["id"], "title": row["title"], "publishedOn": row["published_on"], "entryIds": ids})
    return {"schemaVersion": 1, "contentVersion": version, "locale": "en-CA", "definitionLocale": "zh-CN",
            "updatedOn": updated_on, "lessons": lessons, "entries": entries}


def prepare_release(source, output, database=None, min_app_version=3, catalog=None):
    if catalog is None:
        catalog = json.loads(source.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    payload = json_text(catalog).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("词库超过 5 MiB，请在扩大客户端限制前拆分词库")
    digest = hashlib.sha256(payload).hexdigest()
    version = catalog["contentVersion"]
    relative = f"releases/v{version}-{digest[:12]}.json"
    manifest = {"schemaVersion": 1, "contentVersion": version,
                "minAppVersionCode": min_app_version, "publishedOn": catalog["updatedOn"],
                "catalog": {"path": relative, "sha256": digest,
                            "byteLength": len(payload), "entryCount": len(catalog["entries"])}}
    validate_schema(manifest, "manifest.schema.json")
    old_manifest = output / "manifest.json"
    if old_manifest.exists():
        old = json.loads(old_manifest.read_text())
        if version < old["contentVersion"] or (version == old["contentVersion"] and old != manifest):
            raise ValueError("内容变更需提高 contentVersion；不能覆盖已发布版本")
    if output.exists() and any(output.glob(f"releases/v{version}-*.json")):
        for previous in output.glob(f"releases/v{version}-*.json"):
            if previous.name != Path(relative).name or previous.read_bytes() != payload:
                raise ValueError("相同版本已有不同快照，请提高 contentVersion")
    audio_files = {}
    for entry in catalog["entries"]:
        for form in entry["forms"]:
            if form["audio"]:
                audio = form["audio"]
                local = (source.parent / audio["path"]).resolve()
                if not local.is_relative_to(source.parent.resolve()):
                    raise ValueError("音频路径必须位于词库目录中")
                if not local.is_file() or hashlib.sha256(local.read_bytes()).hexdigest() != audio["sha256"]:
                    raise ValueError(f"音频缺失或校验失败：{audio['path']}")
                if local.stat().st_size > MAX_BYTES:
                    raise ValueError("单个音频超过 5 MiB")
                audio_files[audio["path"]] = local
                destination = output / audio["path"]
                if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != audio["sha256"]:
                    raise ValueError("已发布音频不可覆盖；请使用新的文件路径")
    if database:
        write_sample_database(database, catalog, payload, digest)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    for relative_audio, local in audio_files.items():
        target = output / relative_audio
        target.parent.mkdir(parents=True, exist_ok=True)
        if local.resolve() != target.resolve():
            shutil.copyfile(local, target)
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json_text(manifest), encoding="utf-8")
    temporary.replace(old_manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "vocabulary/dist")
    parser.add_argument("--database", type=Path, help="创建一个新的本地示例词库数据库")
    parser.add_argument("--min-app-version", type=int, default=3)
    parser.add_argument("--from-database", action="store_true", help="从已维护的 SQLite 词库导出")
    parser.add_argument("--version", type=int, help="数据库导出时的新内容版本号")
    parser.add_argument("--updated-on", help="数据库导出时的日期 YYYY-MM-DD")
    parser.add_argument("--check", action="store_true", help="仅校验，不生成文件")
    args = parser.parse_args()
    if args.from_database and (args.version is None or args.updated_on is None or args.database):
        parser.error("数据库导出需指定 --version 和 --updated-on，并且不能同时创建示例数据库")
    catalog = read_database(args.source, args.version, args.updated_on) if args.from_database else None
    if args.check:
        if catalog is None:
            catalog = json.loads(args.source.read_text(encoding="utf-8"))
        validate_catalog(catalog)
        print(f"校验通过：{len(catalog['entries'])} 个词条")
    else:
        manifest = prepare_release(args.source, args.output, args.database, args.min_app_version, catalog)
        print(f"本地发布包已生成：v{manifest['contentVersion']}，{manifest['catalog']['entryCount']} 个词条，{manifest['catalog']['byteLength']} 字节")


if __name__ == "__main__":
    main()
