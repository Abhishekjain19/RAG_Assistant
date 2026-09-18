import sys
import hashlib
class DummyXXHash:
    def __init__(self, data=b""): self.data = data
    def digest(self): return hashlib.md5(self.data).digest()
class DummyXXHashModule:
    @staticmethod
    def xxh3_128(data): return DummyXXHash(data)
sys.modules['xxhash'] = DummyXXHashModule

from dotenv import load_dotenv
load_dotenv()   # MUST be before any core/ imports

from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.analyzer import analyze_meeting


source = "https://www.youtube.com/watch?v=_Q-e_nczWqM&t=223s"
language = "english"   # "english" → Whisper, "hinglish" → Sarvam



chunks = process_input(source)


transcript = transcribe_all(chunks, language=language)
print("\n" + "=" * 60)
print("📝 TRANSCRIPT")
print("=" * 60)
print(transcript[:500] + "..." if len(transcript) > 500 else transcript)


analysis = analyze_meeting(transcript)
title = analysis["title"]
summary = analysis["summary"]
action_items = analysis["action_items"]
decisions = analysis["key_decisions"]
questions = analysis["open_questions"]

print("\n" + "=" * 60)
print("✅ ACTION ITEMS")
print("=" * 60)
print(action_items)

print("\n" + "=" * 60)
print("🔑 KEY DECISIONS")
print("=" * 60)
print(decisions)

print("\n" + "=" * 60)
print("❓ OPEN QUESTIONS")
print("=" * 60)
print(questions)