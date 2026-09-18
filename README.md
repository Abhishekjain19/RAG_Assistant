# RAG Assistant (MeetingAI)

A local meeting-intelligence app. Upload audio/video or paste a YouTube URL; the pipeline transcribes speech, analyses the meeting with Gemini, and lets you chat over the transcript with retrieval-augmented generation (RAG).

## What it does

1. **Ingest** — download or accept a recording (`yt-dlp` + `pydub`).
2. **Transcribe** — local OpenAI Whisper (English) or Sarvam speech-to-text (Hinglish).
3. **Analyse** — Gemini produces a title, summary, action items, and key decisions.
4. **Index** — embed the transcript into a Chroma vector store.
5. **Chat** — ask questions grounded in the meeting text.
6. **Export** — download transcript, JSON, or a PDF of the chat.

The web UI lives in `static/` and is served by FastAPI in `main.py`.

## Requirements

### System

- **Python 3.10+** (3.13 works; see notes in `Requirements.txt`)
- **ffmpeg** — required by Whisper, yt-dlp, and pydub

Install ffmpeg:

- Windows: `winget install Gyan.FFmpeg` (or `choco install ffmpeg`)
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`

Confirm with `ffmpeg -version`. Restart the terminal after installing so `PATH` updates.

### Accounts / API keys

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | Summaries, analysis, and RAG answers |
| `SARVAM_API_KEY` | Only for Hinglish | Cloud STT-translate instead of Whisper |
| `WHISPER_MODEL` | No | Whisper size (`tiny`, `base`, `small`, …). Default: `small` |

Get a Gemini key from [Google AI Studio](https://aistudio.google.com/apikey).

First Whisper run downloads the chosen model (hundreds of MB for `small` and larger). A CPU is enough; a CUDA GPU is optional (install a CUDA `torch` build first if you use one).

### Python packages

Listed in `Requirements.txt`. Notable stacks: FastAPI, Uvicorn, openai-whisper, PyTorch, LangChain + Google GenAI, Chroma, sentence-transformers, yt-dlp.

## Initial setup

1. Clone the repo:

   ```bash
   git clone https://github.com/Abhishekjain19/RAG_Assistant.git
   cd RAG_Assistant
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows (PowerShell):

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   macOS / Linux:

   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r Requirements.txt
   ```

   On Windows, if you see Unicode print errors, set `PYTHONUTF8=1` in the environment.

4. Copy the env template and fill in keys (never commit `.env`):

   ```bash
   copy .env.example .env
   ```

   On macOS/Linux: `cp .env.example .env`

5. Run the web app from the project root:

   ```bash
   python main.py
   ```

   Or: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

6. Open [http://127.0.0.1:8000](http://127.0.0.1:8000), upload a file or paste a YouTube URL, then chat and export when the pipeline finishes.

### Optional CLI smoke test

`test.py` runs the pipeline on a sample YouTube URL without the UI:

```bash
python test.py
```

Edit `source` and `language` (`english` or `hinglish`) at the top of that file first.

## Project layout

```
main.py              FastAPI app, sessions, WebSockets, exports
core/                Transcription, analysis, RAG, vector store, LLM
utils/               Audio download / chunking
static/              MeetingAI frontend (HTML, CSS, JS)
Requirements.txt     Python dependencies
.env.example         Environment variable template
```

Audio downloads land in `downloades/`; Chroma data in `vector_db/`. Both are gitignored.

## Notes

- Sessions expire after about two hours in memory.
- Keep API keys in `.env` only. Rotate any key that was ever committed or shared.
- `streamlit` is listed in `Requirements.txt` but the current UI is FastAPI + static files.
