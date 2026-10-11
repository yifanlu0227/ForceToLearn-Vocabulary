#!/usr/bin/env python3
"""Validate JSON vocabulary and prepare an immutable GitHub-downloadable release.

This is local preparation only: it does not create repositories or upload files.
"""
import argparse
import hashlib
import json
import shutil
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


def prepare_release(source, output, min_app_version=3, catalog=None):
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
    parser.add_argument("source", type=Path, nargs="?", help="完整 JSON 词库；省略时聚合增量源文件")
    parser.add_argument("--output", type=Path, default=ROOT / "vocabulary/dist")
    parser.add_argument("--min-app-version", type=int, default=3)
    parser.add_argument("--check", action="store_true", help="仅校验，不生成文件")
    parser.add_argument("--source-root", type=Path, default=ROOT, help="增量词库仓库目录")
    parser.add_argument("--lookup", help="只查询匹配主词及来源，不读取整份词库到输出")
    args = parser.parse_args()
    if args.source is None:
        from incremental_vocabulary import compile_sources, prepare_incremental_release
        try:
            if args.lookup is not None:
                print(json_text(compile_sources(args.source_root).lookup(args.lookup)), end="")
            elif args.check:
                result = compile_sources(args.source_root)
                print(f"校验通过：{len(result.active)} 个有效词条，{len(result.records) - len(result.active)} 个归档词条；查重只比较主词 term")
            else:
                report = prepare_incremental_release(args.source_root, args.output)
                print(json_text(report), end="")
        except (ValueError, OSError) as error:
            parser.exit(1, f"词库检查失败：{error}\n")
        return
    if args.lookup is not None:
        parser.error("--lookup 用于增量源文件查询，请省略 source 参数")
    if args.check:
        catalog = json.loads(args.source.read_text(encoding="utf-8"))
        validate_catalog(catalog)
        print(f"校验通过：{len(catalog['entries'])} 个词条")
    else:
        manifest = prepare_release(args.source, args.output, min_app_version=args.min_app_version)
        print(f"本地发布包已生成：v{manifest['contentVersion']}，{manifest['catalog']['entryCount']} 个词条，{manifest['catalog']['byteLength']} 字节")


if __name__ == "__main__":
    main()
