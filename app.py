import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import os
import warnings
warnings.filterwarnings("ignore")

# make static-ffmpeg available if system ffmpeg is missing
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass


# ── platform detection ────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    url = url.lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "tiktok.com" in url:
        return "tiktok"
    if "instagram.com" in url:
        return "instagram"
    if "twitter.com" in url or "x.com" in url:
        return "twitter/x"
    if "facebook.com" in url or "fb.watch" in url:
        return "facebook"
    return "video"


# ── transcription logic ───────────────────────────────────────────────────────

def transcribe_youtube(url: str) -> str:
    """Uses YouTube's own captions — instant and free."""
    import re
    from youtube_transcript_api import YouTubeTranscriptApi

    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
        r"(?:shorts/)([A-Za-z0-9_-]{11})",
    ]
    video_id = None
    for p in patterns:
        m = re.search(p, url)
        if m:
            video_id = m.group(1)
            break
    if not video_id:
        raise ValueError("Could not extract YouTube video ID from the URL.")

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    try:
        t = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
    except Exception:
        try:
            t = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
        except Exception:
            t = next(iter(transcript_list))

    entries = t.fetch()
    return " ".join(e["text"] for e in entries)


def transcribe_with_whisper(url: str, model_size: str, status_cb) -> str:
    """Downloads audio with yt-dlp and transcribes locally with Whisper."""
    import tempfile
    import yt_dlp
    import whisper

    with tempfile.TemporaryDirectory() as tmpdir:
        status_cb("Downloading audio…")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        audio_path = None
        for f in os.listdir(tmpdir):
            if f.endswith(".mp3"):
                audio_path = os.path.join(tmpdir, f)
                break
        if not audio_path:
            raise FileNotFoundError("Audio download failed — no mp3 found.")

        status_cb(f"Loading Whisper '{model_size}' model…")
        model = whisper.load_model(model_size)

        status_cb("Transcribing… (this can take a minute)")
        result = model.transcribe(audio_path)

    return result["text"]


def format_transcript(text: str) -> str:
    import re
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    paragraphs, chunk = [], []
    for s in sentences:
        chunk.append(s)
        if len(chunk) >= 5:
            paragraphs.append(" ".join(chunk))
            chunk = []
    if chunk:
        paragraphs.append(" ".join(chunk))
    return "\n\n".join(paragraphs)


# ── background worker ─────────────────────────────────────────────────────────

def run_transcription(url, model_size, status_cb, done_cb, error_cb):
    try:
        platform = detect_platform(url)
        status_cb(f"Platform: {platform.upper()} — starting…")

        if platform == "youtube":
            status_cb("Fetching YouTube captions…")
            try:
                raw = transcribe_youtube(url)
                status_cb("YouTube captions found — done!")
            except Exception:
                status_cb("No captions found — falling back to Whisper…")
                raw = transcribe_with_whisper(url, model_size, status_cb)
        else:
            raw = transcribe_with_whisper(url, model_size, status_cb)

        transcript = format_transcript(raw)
        done_cb(transcript)

    except Exception as e:
        error_cb(str(e))


# ── UI ────────────────────────────────────────────────────────────────────────

class TranscriberApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Transcriber")
        self.geometry("680x560")
        self.resizable(True, True)
        self.configure(bg="#f0f0f0", padx=24, pady=20)
        self._build_ui()

    def _build_ui(self):
        # title
        tk.Label(self, text="🎬 Video Transcriber", font=("Arial", 18, "bold"),
                 bg="#f0f0f0").pack(anchor="w", pady=(0, 4))
        tk.Label(self, text="YouTube • TikTok • Instagram • Twitter/X • Facebook",
                 font=("Arial", 10), fg="#666", bg="#f0f0f0").pack(anchor="w", pady=(0, 16))

        # url input
        tk.Label(self, text="Video URL", font=("Arial", 11, "bold"),
                 bg="#f0f0f0").pack(anchor="w")
        url_frame = tk.Frame(self, bg="#f0f0f0")
        url_frame.pack(fill="x", pady=(4, 12))
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(url_frame, textvariable=self.url_var,
                                  font=("Arial", 12), relief="solid", bd=1)
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(url_frame, text="✕", font=("Arial", 10), relief="flat",
                  bg="#f0f0f0", command=lambda: self.url_var.set("")).pack(side="left", padx=(6, 0))

        # model selector
        model_frame = tk.Frame(self, bg="#f0f0f0")
        model_frame.pack(fill="x", pady=(0, 12))
        tk.Label(model_frame, text="Whisper model (for non-YouTube):",
                 font=("Arial", 10), bg="#f0f0f0").pack(side="left")
        self.model_var = tk.StringVar(value="base")
        model_menu = ttk.Combobox(model_frame, textvariable=self.model_var,
                                   values=["tiny", "base", "small", "medium"],
                                   state="readonly", width=10)
        model_menu.pack(side="left", padx=(8, 0))
        tk.Label(model_frame,
                 text="  tiny=fastest  base=balanced  small/medium=most accurate",
                 font=("Arial", 9), fg="#888", bg="#f0f0f0").pack(side="left")

        # transcribe button
        self.btn = tk.Button(self, text="Transcribe", font=("Arial", 13, "bold"),
                             bg="#2563eb", fg="white", relief="flat",
                             activebackground="#1d4ed8", activeforeground="white",
                             padx=24, pady=8, cursor="hand2",
                             command=self._start)
        self.btn.pack(pady=(0, 10))

        # status
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(self, textvariable=self.status_var, font=("Arial", 10, "italic"),
                 fg="#555", bg="#f0f0f0").pack(anchor="w", pady=(0, 8))

        # output
        tk.Label(self, text="Transcript", font=("Arial", 11, "bold"),
                 bg="#f0f0f0").pack(anchor="w")
        self.text_area = scrolledtext.ScrolledText(
            self, wrap=tk.WORD, font=("Arial", 11),
            relief="solid", bd=1, height=14)
        self.text_area.pack(fill="both", expand=True, pady=(4, 10))

        # action buttons
        btn_frame = tk.Frame(self, bg="#f0f0f0")
        btn_frame.pack(fill="x")
        tk.Button(btn_frame, text="📋 Copy", font=("Arial", 10),
                  command=self._copy, relief="solid", bd=1,
                  padx=12, pady=4).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="💾 Save as .txt", font=("Arial", 10),
                  command=self._save, relief="solid", bd=1,
                  padx=12, pady=4).pack(side="left")
        self.word_count_var = tk.StringVar(value="")
        tk.Label(btn_frame, textvariable=self.word_count_var, font=("Arial", 9),
                 fg="#888", bg="#f0f0f0").pack(side="right")

    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please paste a video URL first.")
            return
        self.btn.config(state="disabled")
        self.text_area.delete("1.0", tk.END)
        self.word_count_var.set("")
        t = threading.Thread(
            target=run_transcription,
            args=(url, self.model_var.get(),
                  self._set_status, self._on_done, self._on_error),
            daemon=True,
        )
        t.start()

    def _set_status(self, msg):
        self.after(0, lambda: self.status_var.set(msg))

    def _on_done(self, transcript):
        def _update():
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert(tk.END, transcript)
            words = len(transcript.split())
            self.word_count_var.set(f"{words:,} words · {len(transcript):,} chars")
            self.status_var.set("Done!")
            self.btn.config(state="normal")
        self.after(0, _update)

    def _on_error(self, msg):
        def _update():
            self.status_var.set("Error — see message box.")
            messagebox.showerror("Transcription Error", msg)
            self.btn.config(state="normal")
        self.after(0, _update)

    def _copy(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied to clipboard!")
        else:
            messagebox.showinfo("Nothing to copy", "Run a transcription first.")

    def _save(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showinfo("Nothing to save", "Run a transcription first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="transcript.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.status_var.set(f"Saved to {os.path.basename(path)}")


if __name__ == "__main__":
    app = TranscriberApp()
    app.mainloop()
