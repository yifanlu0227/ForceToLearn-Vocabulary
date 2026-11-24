"""Source-only word analysis, rendered into the existing offline catalog protocol."""
from copy import deepcopy

FIELDS = ("baseFormZh", "rootsZh", "affixesZh", "mnemonicZh")
LABELS = ("原形", "词根／词基", "词缀", "记忆方法（联想）")
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": list(FIELDS),
    "properties": {name: {"type": "string", "minLength": 1, "maxLength": 400, "pattern": r"\S"}
                   for name in FIELDS},
}


def render_analysis(analysis):
    return "构词与记忆（AI 辅助整理）\n" + "\n".join(
        f"{label}：{analysis[name]}" for name, label in zip(FIELDS, LABELS))


def wire_entry(entry):
    """Never modify source records or duplicate generated notes on recompilation."""
    result = deepcopy(entry)
    analysis = result.pop("wordAnalysis", None)
    if analysis is not None:
        notes = result["usageNotesZh"]
        text = render_analysis(analysis)
        if len(notes) < 10:
            notes.append(text)
        else:
            # Older catalogs permit ten usage notes. Preserve all ten verbatim.
            notes[-1] += "\n\n" + text
        if len(notes[-1]) > 3000:
            raise ValueError(f"{entry['id']}: 构词解析与使用说明超过客户端 3000 字符上限，请缩短内容")
    return result
