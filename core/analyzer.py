from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from core.llm import get_llm, invoke_with_fallback
from core.text_clean import clean_plain, clean_title, strip_code_fences

_SECTION_MARKERS = (
    ("title", "## TITLE"),
    ("summary", "## SUMMARY"),
    ("action_items", "## ACTION ITEMS"),
    ("key_decisions", "## KEY DECISIONS"),
    ("discussion_points", "## DISCUSSION POINTS"),
    ("open_questions", "## OPEN QUESTIONS"),
    ("suggested_questions", "## SUGGESTED QUESTIONS"),
)

_EMPTY = {
    "title": "Meeting Notes",
    "summary": "",
    "action_items": "No action items found.",
    "key_decisions": "No key decisions found.",
    "discussion_points": "",
    "open_questions": "",
    "suggested_questions": "",
}

_cache: dict[int, dict] = {}


def _chain(llm):
    return (
        RunnablePassthrough()
        | RunnableLambda(lambda x: {"text": x})
        | ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert meeting analyst. From the transcript produce ALL of the following.\n"
                    "Use exactly these headings, in this order, each on its own line:\n"
                    "## TITLE\n"
                    "## SUMMARY\n"
                    "## ACTION ITEMS\n"
                    "## KEY DECISIONS\n"
                    "## DISCUSSION POINTS\n"
                    "## SUGGESTED QUESTIONS\n\n"
                    "Rules for the content under each heading:\n"
                    "- Plain text only. Do not use # headings, **, __, or code fences in the content.\n"
                    "- TITLE: max 8 words, no quotes, no markdown.\n"
                    "- SUMMARY: lines that start with '- ' covering goals, discussion, decisions, next steps.\n"
                    "- ACTION ITEMS: numbered list. Each item on one or more lines using labels "
                    "Task:, Owner:, Deadline:, Priority: (High/Medium/Low). Deadline may be 'Not specified'.\n"
                    "- KEY DECISIONS: numbered list of plain sentences.\n"
                    "- DISCUSSION POINTS: 4 to 8 numbered topics actually discussed in the meeting. "
                    "Each item is one or two sentences. Do not write 'No open questions found.'\n"
                    "- SUGGESTED QUESTIONS: 3 to 5 insightful, relevant follow-up questions someone might ask about this specific meeting transcript. Each as a numbered question ending with a question mark.\n"
                    "If a section truly has nothing, write a single line like 'No action items found.'",
                ),
                ("human", "{text}"),
            ]
        )
        | llm
        | StrOutputParser()
    )


def _find_marker(upper: str, marker: str) -> int:
    idx = upper.find(marker)
    if idx != -1:
        return idx
    alt = marker.replace("## ", "# ")
    return upper.find(alt)


def _parse_sections(raw: str) -> dict:
    text = strip_code_fences(raw)
    upper = text.upper()
    positions = []
    for key, marker in _SECTION_MARKERS:
        idx = _find_marker(upper, marker)
        if idx != -1:
            found = text[idx:].splitlines()[0]
            positions.append((idx, key, len(found)))
    positions.sort()

    result = dict(_EMPTY)
    if not positions:
        result["summary"] = clean_plain(text)
        return result

    for i, (idx, key, marker_len) in enumerate(positions):
        start = idx + marker_len
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        if key == "title":
            result[key] = clean_title(body)
        else:
            result[key] = clean_plain(body)
    result["title"] = clean_title(result["title"])
    if not result.get("discussion_points"):
        result["discussion_points"] = result.get("open_questions") or ""
    return result


def analyze_meeting(transcript: str) -> dict:
    """One Gemini request for title, summary, and extractions. Cached per transcript."""
    key = hash(transcript)
    if key not in _cache:
        raw = invoke_with_fallback(
            lambda llm: _chain(llm),
            transcript,
            temperature=0.2,
        )
        _cache[key] = _parse_sections(raw)
    return _cache[key]
