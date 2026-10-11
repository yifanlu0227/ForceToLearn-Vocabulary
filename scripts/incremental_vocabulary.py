"""Compile fixed-format additions and corrections into the existing Android catalog."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import unicodedata

import build_vocabulary as wire

ENTRY_FIELDS = ("id", "term", "partsOfSpeech", "definitionZh", "explanationZh", "examples", "usageNotesZh", "tags")
BASELINE_PATH = "baseline/vocabulary-v3.json"


def normalized_term(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-", "–": "-", "—": "-"}))
    return " ".join(value.split())


def _unique_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"JSON 字段重复：{key}")
        value[key] = item
    return value


def load_json(path):
    if path.is_symlink() or path.stat().st_size > wire.MAX_BYTES:
        raise ValueError(f"{path}: 文件必须是普通 JSON，且不超过 5 MiB")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"{path}: {error}") from error


def _validate(value, schema, path):
    from jsonschema import ValidationError
    try:
        wire.validate_schema(value, schema)
    except ValidationError as error:
        field = ".".join(map(str, error.absolute_path)) or "根对象"
        raise ValueError(f"{path}: {field}: {error.message}") from error


def _compiled_entry(entry, date):
    # Pronunciation comes from English TTS. The dash only fills a legacy, hidden field.
    return {"id": entry["id"], "revision": 1, "term": entry["term"],
            "partsOfSpeech": deepcopy(entry["partsOfSpeech"]), "definitionZh": entry["definitionZh"],
            "explanationZh": entry["explanationZh"],
            "forms": [{"text": entry["term"], "locale": "en-CA", "respelling": "—", "ipa": None,
                       "speakText": entry["term"], "audio": None}],
            "examples": deepcopy(entry["examples"]), "usageNotesZh": deepcopy(entry["usageNotesZh"]),
            "tags": deepcopy(entry["tags"]), "listeningPrompt": entry["term"], "homophoneGroup": None,
            "confusableEntryIds": [], "addedOn": date, "updatedOn": date}


@dataclass
class Compilation:
    catalog: dict
    records: dict
    origins: dict
    active: set

    def terms_text(self):
        # Archived primary terms remain reserved, so restoring a word reuses its learning ID.
        terms = sorted((entry["term"] for entry in self.records.values()), key=normalized_term)
        return "\n".join(terms) + "\n"

    def lookup(self, term):
        key = normalized_term(term)
        return [{"source": self.origins[entry_id], "status": "published" if entry_id in self.active else "archived",
                 "revision": entry["revision"], **{name: entry[name] for name in ENTRY_FIELDS}}
                for entry_id, entry in self.records.items() if normalized_term(entry["term"]) == key]


def compile_sources(root):
    root = Path(root).resolve()
    baseline = root / BASELINE_PATH
    if not baseline.is_file():
        raise ValueError(f"初始词库不存在：{baseline}")
    catalog = load_json(baseline)
    wire.validate_catalog(catalog)
    records = {entry["id"]: deepcopy(entry) for entry in catalog["entries"]}
    active = set(records)
    origins = {entry_id: BASELINE_PATH for entry_id in records}
    catalog = deepcopy(catalog)
    lessons = catalog["lessons"]
    lesson_ids = {lesson["id"] for lesson in lessons}

    def check_terms():
        known = {}
        for entry_id, entry in records.items():
            key = normalized_term(entry["term"])
            if key in known:
                other = known[key]
                raise ValueError(f"主词重复：{entry['term']}，{origins[entry_id]} ({entry_id}) 与 {origins[other]} ({other})；同义表达本身允许独立收录")
            known[key] = entry_id

    check_terms()
    batches = []
    for path in sorted((root / "batches").rglob("*.json")):
        batch = load_json(path)
        relative = path.relative_to(root).as_posix()
        _validate(batch, "batch.schema.json", relative)
        batches.append((batch["publishedOn"], batch["batchId"], relative, batch))
    for date, batch_id, relative, batch in sorted(batches):
        if batch_id in lesson_ids:
            raise ValueError(f"{relative}: batchId 与已有批次或主题重复：{batch_id}")
        lesson_ids.add(batch_id)
        ids = []
        for entry in batch["entries"]:
            entry_id = entry["id"]
            if entry_id in records:
                raise ValueError(f"{relative}: id 重复：{entry_id}，已存在于 {origins[entry_id]}；请使用 corrections 修改")
            records[entry_id] = _compiled_entry(entry, date)
            origins[entry_id] = relative
            active.add(entry_id)
            ids.append(entry_id)
        lessons.append({"id": batch_id, "title": batch["title"], "publishedOn": date, "entryIds": ids})
        catalog["updatedOn"] = max(catalog["updatedOn"], date)
    # Check before corrections too: additions cannot hide duplicate source entries by later renaming.
    check_terms()

    corrections = []
    correction_ids = set()
    for path in sorted((root / "corrections").rglob("*.json")):
        correction = load_json(path)
        relative = path.relative_to(root).as_posix()
        _validate(correction, "correction.schema.json", relative)
        if correction["correctionId"] in correction_ids:
            raise ValueError(f"{relative}: correctionId 重复")
        correction_ids.add(correction["correctionId"])
        corrections.append((correction["publishedOn"], correction["correctionId"], relative, correction))
    for date, _, relative, correction in sorted(corrections):
        changed_ids = set()
        for change in correction["changes"]:
            entry_id = change["id"]
            if entry_id in changed_ids:
                raise ValueError(f"{relative}: 同一次纠错不能重复操作 {entry_id}")
            changed_ids.add(entry_id)
            if entry_id not in records:
                raise ValueError(f"{relative}: 词条不存在：{entry_id}")
            entry = records[entry_id]
            if change["expectedRevision"] != entry["revision"]:
                raise ValueError(f"{relative}: {entry_id} 的修订版本已过期，预期 {change['expectedRevision']}，实际 {entry['revision']}")
            if date < entry["updatedOn"]:
                raise ValueError(f"{relative}: {entry_id} 的纠错日期早于上次更新")
            action = change["action"]
            if action == "update":
                replacement = change["entry"]
                if replacement["id"] != entry_id:
                    raise ValueError(f"{relative}: 修改词条必须沿用原 id：{entry_id}")
                previous_term = entry["term"]
                entry.update(deepcopy(replacement))
                if previous_term != entry["term"]:
                    for form in entry["forms"]:
                        if normalized_term(form["text"]) == normalized_term(previous_term):
                            form.update(text=entry["term"], speakText=entry["term"], respelling="—", ipa=None, audio=None)
                    if entry["listeningPrompt"] == previous_term:
                        entry["listeningPrompt"] = entry["term"]
            elif action == "archive":
                if entry_id not in active:
                    raise ValueError(f"{relative}: {entry_id} 已经归档")
                active.remove(entry_id)
            elif action == "restore":
                if entry_id in active:
                    raise ValueError(f"{relative}: {entry_id} 尚未归档")
                active.add(entry_id)
            entry["revision"] += 1
            entry["updatedOn"] = date
            origins[entry_id] = relative
        catalog["updatedOn"] = max(catalog["updatedOn"], date)
        check_terms()

    catalog["entries"] = [deepcopy(entry) for entry_id, entry in records.items() if entry_id in active]
    for entry in catalog["entries"]:
        entry["confusableEntryIds"] = [entry_id for entry_id in entry["confusableEntryIds"] if entry_id in active]
    for lesson in lessons:
        lesson["entryIds"] = [entry_id for entry_id in lesson["entryIds"] if entry_id in active]
    catalog["lessons"] = [lesson for lesson in lessons if lesson["entryIds"]]
    wire.validate_catalog(catalog)
    if len(wire.json_text(catalog).encode("utf-8")) > wire.MAX_BYTES:
        raise ValueError("聚合词库超过当前 App 的 5 MiB 上限")
    return Compilation(catalog, records, origins, active)


def published_catalog(root):
    root = Path(root)
    manifest = load_json(root / "manifest.json")
    _validate(manifest, "manifest.schema.json", "manifest.json")
    data = manifest["catalog"]
    payload = (root / data["path"]).read_bytes()
    if len(payload) != data["byteLength"] or hashlib.sha256(payload).hexdigest() != data["sha256"]:
        raise ValueError("现有发布快照的字节数或 SHA-256 不匹配")
    catalog = load_json(root / data["path"])
    wire.validate_catalog(catalog)
    if catalog["contentVersion"] != manifest["contentVersion"] or len(catalog["entries"]) != data["entryCount"]:
        raise ValueError("现有清单与词库版本或数量不匹配")
    return manifest, catalog


def prepare_incremental_release(root, output, minimum_version=1):
    root, output = Path(root).resolve(), Path(output).resolve()
    if root == output:
        raise ValueError("增量发布请使用独立输出目录；由发布工作流统一更新源仓库")
    compilation = compile_sources(root)
    old_manifest, old_catalog = published_catalog(root)
    catalog = deepcopy(compilation.catalog)
    catalog["contentVersion"] = old_catalog["contentVersion"]
    changed = catalog != old_catalog
    if changed:
        catalog["contentVersion"] = max(catalog["contentVersion"] + 1, minimum_version)
    output.mkdir(parents=True, exist_ok=True)
    (output / "terms.txt").write_text(compilation.terms_text(), encoding="utf-8")
    manifest = wire.prepare_release(root / BASELINE_PATH, output,
                                    min_app_version=old_manifest["minAppVersionCode"], catalog=catalog)
    before = {entry["id"]: entry for entry in old_catalog["entries"]}
    after = {entry["id"]: entry for entry in catalog["entries"]}
    added = sorted(after.keys() - before.keys())
    updated = sorted(entry_id for entry_id in after.keys() & before.keys() if after[entry_id] != before[entry_id])
    archived = sorted(before.keys() - after.keys())
    report = {"changed": changed, "contentVersion": manifest["contentVersion"],
              "entryCount": len(after), "added": added, "updated": updated, "archived": archived}
    (output / "publication.json").write_text(wire.json_text(report), encoding="utf-8")
    return report
