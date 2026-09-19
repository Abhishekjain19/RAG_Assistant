import yt_dlp
from pydub import AudioSegment
import static_ffmpeg
import os

static_ffmpeg.add_paths()

DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def clear_download_dir(directory: str = DOWNLOAD_DIR, preserve_file: str = None):
    """Remove all files and subdirectories within the downloads folder, optionally preserving a specified file."""
    import shutil
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        return

    preserve_norm = os.path.abspath(preserve_file) if preserve_file else None

    for root, dirs, files in os.walk(directory, topdown=False):
        for f in files:
            file_path = os.path.abspath(os.path.join(root, f))
            if preserve_norm and file_path == preserve_norm:
                continue
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
        for d in dirs:
            dir_path = os.path.abspath(os.path.join(root, d))
            # Don't delete directory if it contains the preserved file
            if preserve_norm and (preserve_norm.startswith(dir_path + os.sep) or preserve_norm == dir_path):
                continue
            try:
                os.rmdir(dir_path)
            except Exception:
                pass
    # Ensure nested uploads folder exists
    uploads_path = os.path.join(directory, "uploads")
    os.makedirs(uploads_path, exist_ok=True)



def download_youtube_audio(url :str) ->str:
    output_path = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "js_runtimes": {"nodejs": {}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    return filename



def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to WAV format using pydub."""
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000) #16khz
    audio.export(output_path, format="wav")
    return output_path



def chunk_audio(wav_path : str , chunk_minutes : int = 10) -> list:
    audio = AudioSegment.from_wav(wav_path)
    if len(audio) == 0:
        raise ValueError("The audio file is empty (0 seconds).")
    chunk_ms = chunk_minutes * 60 * 1000 

    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start : start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")

        chunks.append(chunk_path)
    
    return chunks

def process_input(source: str) -> list:
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected YouTube URL. Downloading audio...")
        downloaded_file = download_youtube_audio(source)
        wav_path = convert_to_wav(downloaded_file)
    else:
        if not os.path.exists(source):
            raise FileNotFoundError(f"Audio file not found: {source}")
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return chunks