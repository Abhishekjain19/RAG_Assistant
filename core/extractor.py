from core.analyzer import analyze_meeting


def extract_meeting_insights(transcript: str) -> dict:
    analysis = analyze_meeting(transcript)
    return {
        "action_items": analysis["action_items"],
        "key_decisions": analysis["key_decisions"],
        "open_questions": analysis.get("discussion_points") or analysis.get("open_questions") or "",
        "discussion_points": analysis.get("discussion_points") or analysis.get("open_questions") or "",
    }


def extract_action_items(transcript: str) -> str:
    return extract_meeting_insights(transcript)["action_items"]


def extract_key_decisions(transcript: str) -> str:
    return extract_meeting_insights(transcript)["key_decisions"]


def extract_questions(transcript: str) -> str:
    return extract_meeting_insights(transcript)["open_questions"]
