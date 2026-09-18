import re

_FENCE_RE = re.compile(r"```(?:markdown|md|text)?", re.I)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_LABEL_RE = re.compile(
    r"^(title|summary|action items|key decisions|open questions|discussion points|executive summary|"
    r"goals?|decisions?|actions?|questions?|notes?|next steps)\s*:?\s*$",
    re.I,
)


def strip_code_fences(text: str) -> str:
    return _FENCE_RE.sub("", text or "").replace("```", "").strip()


def strip_inline_markdown(text: str) -> str:
    cleaned = _LINK_RE.sub(r"\1", text or "")
    cleaned = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", cleaned)
    cleaned = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", cleaned)
    cleaned = cleaned.replace("`", "")
    return cleaned


def strip_heading_markers(text: str) -> str:
    return _HEADING_RE.sub("", text or "")


def clean_plain(text: str) -> str:
    """Remove markdown chrome while keeping list structure."""
    cleaned = strip_code_fences(text)
    cleaned = strip_heading_markers(cleaned)
    cleaned = strip_inline_markdown(cleaned)
    lines: list[str] = []
    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line or _LABEL_RE.match(line):
            continue
        line = re.sub(r"^[-*•]\s+", "- ", line)
        line = re.sub(r"^\d+[.)]\s+", "- ", line)
        lines.append(line)
    return "\n".join(lines).strip()


def clean_title(text: str) -> str:
    if not text:
        return "Meeting Notes"
    line = strip_code_fences(text).splitlines()[0]
    line = strip_heading_markers(line)
    line = strip_inline_markdown(line)
    return line.strip().strip(" \"'") or "Meeting Notes"


def clean_list_item(text: str) -> str:
    cleaned = strip_inline_markdown(strip_heading_markers(text or ""))
    cleaned = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–")
    return cleaned
