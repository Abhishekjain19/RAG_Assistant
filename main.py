import asyncio
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fpdf import FPDF
from pydantic import BaseModel
from pydub import AudioSegment

from core.analyzer import analyze_meeting
from core.text_clean import clean_list_item, clean_plain, strip_inline_markdown
from core.rag_engine import ask_question, build_rag_chain
from core.transcriber import transcribe_chunk
from core.vector_store import get_retriever, load_vector_store
from utils.audio_processor import DOWNLOAD_DIR, process_input

load_dotenv()

SESSION_TTL = timedelta(hours=2)
PIPELINE_STEPS = [
    "downloading",
    "extracting",
    "transcribing",
    "translating",
    "generating_title",
    "summarising",
    "indexing",
]
UPLOAD_DIR = os.path.join(DOWNLOAD_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Existing CLI pipeline (unchanged orchestration of core modules)
# ---------------------------------------------------------------------------
def run_pipeline(source: str, language: str = "english") -> dict:
    print("starting AI Video Assistant")

    chunks = process_input(source)

    transcript = transcribe_all_compat(chunks, language)
    print(f"raw transcription (first 300 characters ) {transcript[:300]}")

    analysis = analyze_meeting(transcript)
    title = analysis["title"]
    summary = analysis["summary"]
    action_item = analysis["action_items"]
    decisions = analysis["key_decisions"]
    questions = analysis.get("discussion_points") or analysis.get("open_questions") or ""

    rag_chain = build_rag_chain(transcript)

    return {
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "action_items": action_item,
        "key_decisions": decisions,
        "open_questions": questions,
        "rag_chain": rag_chain,
    }


def transcribe_all_compat(chunks: list, language: str = "english") -> str:
    from core.transcriber import transcribe_all

    return transcribe_all(chunks, language)


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------
class Session:
    def __init__(self, source: str, language: str, quality: str):
        self.id = str(uuid.uuid4())
        self.source = source
        self.language = language
        self.quality = quality
        self.created_at = datetime.now(timezone.utc)
        self.started_at = datetime.now(timezone.utc)
        self.steps: list[dict] = [
            {"step": name, "status": "pending", "detail": "", "elapsed_ms": 0}
            for name in PIPELINE_STEPS
        ]
        self.results: Optional[dict] = None
        self.rag_chain = None
        self.chat_history: list[dict] = []
        self.error: Optional[str] = None
        self.subscribers: list[asyncio.Queue] = []
        self.lock = threading.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None


sessions: dict[str, Session] = {}
sessions_lock = threading.Lock()


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    with sessions_lock:
        expired = [
            sid for sid, sess in sessions.items() if now - sess.created_at > SESSION_TTL
        ]
        for sid in expired:
            sessions.pop(sid, None)


def get_session(session_id: str) -> Session:
    _purge_expired()
    with sessions_lock:
        sess = sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return sess


def _elapsed_ms(session: Session) -> int:
    return int((datetime.now(timezone.utc) - session.started_at).total_seconds() * 1000)


def emit(session: Session, step: str, status: str, detail: str = "") -> None:
    event = {
        "step": step,
        "status": status,
        "detail": detail,
        "elapsed_ms": _elapsed_ms(session),
    }
    with session.lock:
        for item in session.steps:
            if item["step"] == step:
                item.update(event)
                break
        else:
            session.steps.append(event)
        queues = list(session.subscribers)
    loop = session.loop
    if loop is not None:
        for queue in queues:
            loop.call_soon_threadsafe(queue.put_nowait, event)


# ---------------------------------------------------------------------------
# Parsing (API-layer only — core extractors still return strings)
# ---------------------------------------------------------------------------
def _is_none_found(text: str) -> bool:
    cleaned = clean_list_item(text).lower()
    return cleaned.startswith("no ") and "found" in cleaned


def _split_list(text: str) -> list[str]:
    if not text or _is_none_found(text):
        return []
    items: list[str] = []
    current: list[str] = []
    pattern = re.compile(r"^\s*(?:\d+[\.\)]|[-*•])\s+")
    for line in text.splitlines():
        stripped = clean_list_item(line) if not pattern.match(line) else None
        if pattern.match(line):
            if current:
                items.append(" ".join(current).strip())
            current = [pattern.sub("", strip_inline_markdown(line)).strip()]
        elif current:
            if line.strip():
                current.append(strip_inline_markdown(line).strip())
        elif line.strip():
            if stripped:
                current = [stripped]
    if current:
        items.append(" ".join(current).strip())
    cleaned = [clean_list_item(i) for i in items if i and not _is_none_found(i)]
    return [i for i in cleaned if i]


def _parse_action_item(raw: str) -> dict:
    owner = "Unassigned"
    due = "Not specified"
    priority = "Medium"
    source = strip_inline_markdown(raw or "")

    owner_m = re.search(
        r"Owner\s*[:\-]\s*(.+?)(?=(?:Deadline|Due|Priority|Task|$))", source, re.I
    )
    due_m = re.search(
        r"(?:Deadline|Due date|Due)\s*[:\-]\s*(.+?)(?=(?:Owner|Priority|Task|$))",
        source,
        re.I,
    )
    prio_m = re.search(r"Priority\s*[:\-]\s*(High|Medium|Low)", source, re.I)
    task_m = re.search(
        r"Task\s*[:\-]\s*(.+?)(?=(?:Owner|Deadline|Due|Priority|$))", source, re.I
    )
    if owner_m:
        owner = clean_list_item(owner_m.group(1))
    if due_m:
        due = clean_list_item(due_m.group(1))
    if prio_m:
        priority = prio_m.group(1).capitalize()
    elif re.search(r"\bhigh\b", source, re.I):
        priority = "High"
    elif re.search(r"\blow\b", source, re.I):
        priority = "Low"

    task = task_m.group(1) if task_m else source
    task = re.sub(r"Owner\s*[:\-].*?(?=(?:Deadline|Due|Priority|Task|$))", "", task, flags=re.I)
    task = re.sub(
        r"(?:Deadline|Due date|Due)\s*[:\-].*?(?=(?:Owner|Priority|Task|$))",
        "",
        task,
        flags=re.I,
    )
    task = re.sub(r"Priority\s*[:\-]\s*(High|Medium|Low)", "", task, flags=re.I)
    task = re.sub(r"^\s*Task\s*[:\-]\s*", "", task, flags=re.I)
    task = clean_list_item(task)
    return {
        "owner": owner or "Unassigned",
        "task": task or clean_list_item(source),
        "due": due,
        "priority": priority,
    }


def _audio_duration_seconds(chunks: list) -> float:
    total_ms = 0
    for path in chunks:
        try:
            total_ms += len(AudioSegment.from_wav(path))
        except Exception:
            continue
    return round(total_ms / 1000, 1)


def _language_to_engine(language: str) -> str:
    value = (language or "english").strip().lower()
    if value in {"hindi", "hinglish", "hi"}:
        return "hinglish"
    return "english"


def build_public_results(session: Session) -> dict:
    if not session.results:
        raise HTTPException(status_code=409, detail="Results not ready yet")
    return session.results


# ---------------------------------------------------------------------------
# PDF export (no existing export module — generated here with fpdf2)
# ---------------------------------------------------------------------------
def _pdf_safe(text: str) -> str:
    return (text or "").encode("latin-1", "replace").decode("latin-1")


class MeetingPDF(FPDF):
    def __init__(self, title: str):
        super().__init__()
        self.meeting_title = title
        self.is_cover = True
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(107, 106, 102)
        self.cell(0, 8, _pdf_safe(self.meeting_title)[:80], align="L")
        self.ln(10)
        self.set_draw_color(200, 200, 198)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)
        self.set_text_color(26, 25, 23)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(157, 156, 153)
        if self.page_no() == 1:
            self.cell(0, 8, "Generated by AI Meeting Assistant", align="C")
        else:
            self.cell(0, 8, str(self.page_no()), align="C")


def build_pdf(results: dict) -> bytes:
    pdf = MeetingPDF(results.get("title") or "Meeting")
    pdf.add_page()
    pdf.set_y(90)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(26, 25, 23)
    pdf.multi_cell(0, 14, _pdf_safe(results.get("title") or "Meeting"), align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(107, 106, 102)
    meta = f"{results.get('created_at', '')}   ·   {results.get('duration_seconds', 0)}s"
    pdf.multi_cell(0, 8, _pdf_safe(meta), align="C")
    pdf.ln(12)
    pdf.set_draw_color(91, 91, 214)
    y = pdf.get_y()
    pdf.line(60, y, 150, y)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(26, 25, 23)
    pdf.cell(0, 12, "Executive Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(26, 25, 23)
    pdf.multi_cell(0, 7, _pdf_safe(clean_plain(results.get("summary") or "")))

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Key Decisions", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    decisions = results.get("key_decisions") or []
    if not decisions:
        pdf.multi_cell(0, 7, "No key decisions found.")
    else:
        for item in decisions:
            pdf.multi_cell(0, 7, _pdf_safe(f"- {item}"))
            pdf.ln(1)

    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Action Items", new_x="LMARGIN", new_y="NEXT")
    col_w = [38, 82, 35, 25]
    headers = ["Owner", "Task", "Due Date", "Priority"]
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(241, 240, 237)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 8, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    rows = results.get("action_items") or []
    if not rows:
        pdf.cell(sum(col_w), 8, "No action items found.", border=1, new_x="LMARGIN", new_y="NEXT")
    else:
        for i, row in enumerate(rows):
            fill = i % 2 == 1
            pdf.set_fill_color(248, 247, 244)
            values = [
                _pdf_safe(str(row.get("owner", "")))[:28],
                _pdf_safe(str(row.get("task", "")))[:70],
                _pdf_safe(str(row.get("due", "")))[:18],
                _pdf_safe(str(row.get("priority", "")))[:10],
            ]
            for w, val in zip(col_w, values):
                pdf.cell(w, 8, val, border=1, fill=fill)
            pdf.ln()

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Full Transcript", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    left_margin = 20
    pdf.set_left_margin(left_margin)
    pdf.set_x(left_margin)
    pdf.set_font("Courier", "", 9)
    pdf.set_text_color(107, 106, 102)
    transcript = results.get("transcript") or ""
    for paragraph in transcript.split("\n"):
        pdf.set_text_color(26, 25, 23)
        pdf.multi_cell(0, 5, _pdf_safe(paragraph or " "))

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return bytes(out.encode("latin-1"))


def build_chat_pdf(results: dict, messages: list[dict]) -> bytes:
    pdf = MeetingPDF(results.get("title") or "Meeting")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(26, 25, 23)
    pdf.cell(0, 12, "Chat with transcript", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(107, 106, 102)
    pdf.multi_cell(0, 7, _pdf_safe(results.get("title") or "Meeting"))
    pdf.ln(6)
    pdf.set_text_color(26, 25, 23)
    if not messages:
        pdf.multi_cell(0, 7, "No chat messages yet.")
    else:
        for item in messages:
            role = "You" if item.get("role") == "user" else "Assistant"
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, role, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, _pdf_safe(item.get("content") or ""))
            pdf.ln(4)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Full Transcript", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Courier", "", 9)
    transcript = results.get("transcript") or ""
    for paragraph in transcript.split("\n"):
        pdf.multi_cell(0, 5, _pdf_safe(paragraph or " "))
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return bytes(out.encode("latin-1"))


# ---------------------------------------------------------------------------
# Background pipeline wrapping existing functions
# ---------------------------------------------------------------------------
def run_session_job(session_id: str) -> None:
    session = sessions.get(session_id)
    if not session:
        return
    try:
        os.environ["WHISPER_MODEL"] = session.quality
        engine_language = _language_to_engine(session.language)

        emit(session, "downloading", "active", "Fetching audio source…")
        chunks = process_input(session.source)
        emit(session, "downloading", "done", "Audio downloaded")
        emit(session, "extracting", "active", "Converting and chunking audio…")
        duration = _audio_duration_seconds(chunks)
        emit(session, "extracting", "done", f"{len(chunks)} chunk(s) ready")

        emit(session, "transcribing", "active", "Starting transcription…")
        parts: list[str] = []
        for i, chunk in enumerate(chunks):
            emit(
                session,
                "transcribing",
                "active",
                f"Transcribing segment {i + 1} / {len(chunks)}…",
            )
            parts.append(transcribe_chunk(chunk, language=engine_language))
        transcript = " ".join(parts).strip()
        emit(session, "transcribing", "done", "Transcription complete")

        if engine_language == "hinglish":
            emit(session, "translating", "active", "Translated to English via Sarvam")
            emit(session, "translating", "done", "English transcript ready")
        else:
            emit(session, "translating", "done", "No translation needed")

        emit(session, "generating_title", "active", "Analyzing transcript with Gemini…")
        analysis = analyze_meeting(transcript)
        title = analysis["title"]
        emit(session, "generating_title", "done", title)

        emit(session, "summarising", "active", "Writing summary and extracting insights…")
        summary = analysis["summary"]
        insights = {
            "action_items": analysis["action_items"],
            "key_decisions": analysis["key_decisions"],
            "discussion_points": analysis.get("discussion_points")
            or analysis.get("open_questions")
            or "",
            "suggested_questions": analysis.get("suggested_questions") or "",
        }
        emit(session, "summarising", "done", "Summary ready")

        emit(session, "indexing", "active", "Building vector index…")
        rag_chain = build_rag_chain(transcript)
        emit(session, "indexing", "done", "Index ready")

        action_items = [_parse_action_item(x) for x in _split_list(insights["action_items"])]
        results = {
            "title": title.strip(),
            "summary": clean_plain(summary),
            "key_decisions": _split_list(insights["key_decisions"]),
            "action_items": action_items,
            "discussion_points": _split_list(insights["discussion_points"]),
            "suggested_questions": _split_list(insights["suggested_questions"]),
            "transcript": transcript,
            "duration_seconds": duration,
            "word_count": len(transcript.split()),
            "created_at": session.created_at.isoformat(),
        }
        session.results = results
        session.rag_chain = rag_chain
    except Exception as exc:
        session.error = str(exc)
        active = next((s["step"] for s in session.steps if s["status"] == "active"), "indexing")
        emit(session, active, "error", str(exc))


async def run_session_job_async(session_id: str) -> None:
    await asyncio.to_thread(run_session_job, session_id)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="MeetingAI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    app.state.loop = asyncio.get_running_loop()


@app.post("/api/upload")
async def upload(request: Request, background_tasks: BackgroundTasks):
    _purge_expired()
    content_type = request.headers.get("content-type", "") or ""
    language = "english"
    quality = "small"
    source = None

    if "application/json" in content_type:
        body = await request.json()
        source = str(body.get("url") or "").strip()
        language = body.get("language") or language
        quality = body.get("quality") or quality
    else:
        form = await request.form()
        language = str(form.get("language") or language)
        quality = str(form.get("quality") or quality)
        uploaded = form.get("file")
        url_value = form.get("url")
        if uploaded is not None and getattr(uploaded, "filename", None):
            dest = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{uploaded.filename}")
            with open(dest, "wb") as handle:
                handle.write(await uploaded.read())
            source = dest
        elif url_value:
            source = str(url_value).strip()

    if not source:
        raise HTTPException(status_code=400, detail="Provide a file or a URL")

    quality = (quality or "small").lower()
    if quality not in {"tiny", "base", "small", "medium"}:
        quality = "small"

    session = Session(source=source, language=language, quality=quality)
    session.loop = asyncio.get_running_loop()
    with sessions_lock:
        sessions[session.id] = session
    background_tasks.add_task(run_session_job_async, session.id)
    return {"session_id": session.id}


@app.websocket("/ws/{session_id}")
async def pipeline_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        session = get_session(session_id)
    except HTTPException:
        await websocket.close(code=4404)
        return
    queue: asyncio.Queue = asyncio.Queue()
    with session.lock:
        snapshot = [dict(s) for s in session.steps]
        session.subscribers.append(queue)
    try:
        for event in snapshot:
            await websocket.send_json(event)
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        with session.lock:
            if queue in session.subscribers:
                session.subscribers.remove(queue)


@app.get("/api/results/{session_id}")
def results(session_id: str):
    session = get_session(session_id)
    if session.error and not session.results:
        raise HTTPException(status_code=500, detail=session.error)
    return build_public_results(session)


class ChatPayload(BaseModel):
    message: str


def _source_cards(question: str) -> list[dict]:
    try:
        store = load_vector_store()
        retriever = get_retriever(store, k=3)
        docs = retriever.invoke(question)
        cards = []
        try:
            scored = store.similarity_search_with_relevance_scores(question, k=3)
        except Exception:
            scored = [(d, None) for d in docs]
        for doc, score in scored[:3]:
            pct = 80
            if isinstance(score, (int, float)):
                pct = int(max(1, min(99, float(score) * 100)))
            excerpt = (doc.page_content or "")[:120]
            cards.append(
                {
                    "score": pct,
                    "excerpt": excerpt,
                    "timestamp": doc.metadata.get("chunk_index"),
                }
            )
        return cards
    except Exception:
        return []


@app.post("/api/chat/{session_id}")
async def chat(session_id: str, payload: ChatPayload):
    session = get_session(session_id)
    if not session.rag_chain:
        raise HTTPException(status_code=409, detail="Index is not ready yet")
    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message is required")

    async def event_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            parts: list[str] = []
            try:
                streamed = False
                try:
                    for chunk in session.rag_chain.stream(question):
                        streamed = True
                        token = chunk if isinstance(chunk, str) else str(chunk)
                        parts.append(token)
                        asyncio.run_coroutine_threadsafe(queue.put(token), loop).result()
                except Exception:
                    if not streamed:
                        token = ask_question(session.rag_chain, question)
                        parts.append(token)
                        asyncio.run_coroutine_threadsafe(queue.put(token), loop).result()
                answer = "".join(parts).strip()
                with session.lock:
                    now = datetime.now(timezone.utc).isoformat()
                    session.chat_history.append({"role": "user", "content": question, "ts": now})
                    session.chat_history.append({"role": "assistant", "content": answer, "ts": now})
                sources = _source_cards(question)
                asyncio.run_coroutine_threadsafe(queue.put({"done": True, "sources": sources}), loop).result()
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put({"done": True, "sources": [], "error": str(exc)}), loop).result()

        threading.Thread(target=produce, daemon=True).start()
        while True:
            item = await queue.get()
            if isinstance(item, dict) and item.get("done"):
                payload = {"token": "", "sources": item.get("sources") or [], "done": True}
                yield f"data: {json.dumps(payload)}\n\n"
                break
            yield f"data: {json.dumps({'token': item or '', 'sources': []})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/export/pdf/{session_id}")
def export_pdf(session_id: str):
    session = get_session(session_id)
    data = build_public_results(session)
    payload = build_pdf(data)
    filename = re.sub(r"[^\w\-]+", "_", data.get("title") or "meeting")[:60]
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


@app.get("/api/export/txt/{session_id}")
def export_txt(session_id: str):
    session = get_session(session_id)
    data = build_public_results(session)
    filename = re.sub(r"[^\w\-]+", "_", data.get("title") or "transcript")[:60]
    return Response(
        content=(data.get("transcript") or "").encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.txt"'},
    )


@app.get("/api/export/json/{session_id}")
def export_json(session_id: str):
    session = get_session(session_id)
    data = build_public_results(session)
    filename = re.sub(r"[^\w\-]+", "_", data.get("title") or "meeting")[:60]
    body = json.dumps(data, indent=2, ensure_ascii=False)
    return Response(
        content=body.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
    )


@app.get("/api/export/chat-pdf/{session_id}")
def export_chat_pdf(session_id: str):
    session = get_session(session_id)
    data = build_public_results(session)
    with session.lock:
        history = list(session.chat_history)
    payload = build_chat_pdf(data, history)
    filename = re.sub(r"[^\w\-]+", "_", data.get("title") or "meeting")[:60]
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}_chat.pdf"'},
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
