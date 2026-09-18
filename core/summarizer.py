from core.analyzer import analyze_meeting


def summarize(transcript: str) -> str:
    return analyze_meeting(transcript)["summary"]


def generate_title(transcript: str) -> str:
    return analyze_meeting(transcript)["title"]
