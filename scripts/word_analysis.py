"""Source-only word analysis, rendered into the existing offline catalog protocol."""
from copy import deepcopy

LEGACY_FIELDS = ("baseFormZh", "rootsZh", "affixesZh", "mnemonicZh")
FIELDS = ("textZh",)
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": list(FIELDS),
    "properties": {"textZh": {
        "type": "string", "maxLength": 180,
        "anyOf": [{"const": ""}, {"pattern": r"^\S(?:[^\r\n]*\S)?$"}],
        "not": {"pattern": r"构词与记忆|AI\s*辅助整理|(?:原形|词根|词缀|记忆方法)[：:]|[\r\n]"},
    }},
}


def render_analysis(analysis):
    if "textZh" in analysis:
        return analysis["textZh"]
    # Historical v2 sources stay readable; current sources use one concise paragraph.
    return " ".join(analysis[name] for name in LEGACY_FIELDS)


def wire_entry(entry):
    """Never modify source records or duplicate generated notes on recompilation."""
    result = deepcopy(entry)
    analysis = result.pop("wordAnalysis", None)
    if analysis is not None:
        notes = result["usageNotesZh"]
        text = render_analysis(analysis)
        if not text:
            return result
        if len(notes) < 10:
            notes.append(text)
        else:
            # Older catalogs permit ten usage notes. Preserve all ten verbatim.
            notes[-1] += "\n\n" + text
        if len(notes[-1]) > 3000:
            raise ValueError(f"{entry['id']}: 构词解析与使用说明超过客户端 3000 字符上限，请缩短内容")
    return result
