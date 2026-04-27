import os
import re
import threading
import webbrowser
import warnings
warnings.filterwarnings("ignore")

# make static-ffmpeg available if system ffmpeg is missing
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ── platform detection ────────────────────────────────────────────────────────

def detect_platform(url):
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:   return "tiktok"
    if "instagram.com" in u: return "instagram"
    if "twitter.com" in u or "x.com" in u: return "twitter/x"
    if "facebook.com" in u or "fb.watch" in u: return "facebook"
    return "video"

# ── transcription ─────────────────────────────────────────────────────────────

def transcribe_youtube(url):
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
        raise ValueError("Could not extract YouTube video ID from URL.")

    tlist = YouTubeTranscriptApi.list_transcripts(video_id)
    try:
        t = tlist.find_manually_created_transcript(["en", "en-US", "en-GB"])
    except Exception:
        try:
            t = tlist.find_generated_transcript(["en", "en-US", "en-GB"])
        except Exception:
            t = next(iter(tlist))
    return " ".join(e["text"] for e in t.fetch())


def transcribe_with_whisper(url, model_size):
    import tempfile, yt_dlp, whisper
    platform = detect_platform(url)

    with tempfile.TemporaryDirectory() as tmpdir:
        base_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "192"}],
            "quiet": True, "no_warnings": True,
            # Chrome cookies fix 403s on YouTube and help with other platforms
            "cookiesfrombrowser": ("chrome",),
        }

        if platform == "tiktok":
            base_opts.update({
                "extractor_args": {
                    "tiktok": {
                        "api_hostname": ["api22-normal-c-useast2a.tiktokv.com"],
                    }
                },
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
                    ),
                    "Referer": "https://www.tiktok.com/",
                },
            })

        with yt_dlp.YoutubeDL(base_opts) as ydl:
            ydl.download([url])

        audio_path = next(
            (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".mp3")),
            None
        )
        if not audio_path:
            raise FileNotFoundError("Audio download failed.")

        model = whisper.load_model(model_size)
        result = model.transcribe(audio_path)
    return result["text"]


def format_transcript(text):
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

# ── routes ────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Transcriber</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#f5f5f7;min-height:100vh;display:flex;justify-content:center;
       padding:40px 16px}
  .card{background:#fff;border-radius:16px;padding:36px;width:100%;max-width:700px;
        box-shadow:0 2px 20px rgba(0,0,0,.08);align-self:flex-start}
  h1{font-size:1.6rem;font-weight:700;margin-bottom:4px}
  .sub{color:#666;font-size:.9rem;margin-bottom:28px}
  label{display:block;font-weight:600;font-size:.85rem;margin-bottom:6px;color:#333}
  input[type=text]{width:100%;padding:10px 14px;border:1.5px solid #ddd;border-radius:8px;
                   font-size:1rem;outline:none;transition:border .2s}
  input[type=text]:focus{border-color:#2563eb}
  select{padding:8px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:.9rem;
         background:#fff;outline:none;cursor:pointer}
  .row{display:flex;gap:16px;align-items:flex-end;margin:16px 0 20px}
  .row>div{flex:1}
  button.primary{background:#2563eb;color:#fff;border:none;padding:11px 28px;
                 border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;
                 transition:background .2s;width:100%}
  button.primary:hover{background:#1d4ed8}
  button.primary:disabled{background:#93c5fd;cursor:not-allowed}
  #status{margin:16px 0 4px;font-size:.9rem;color:#555;min-height:20px}
  #status.error{color:#dc2626}
  #status.ok{color:#16a34a}
  textarea{width:100%;min-height:320px;border:1.5px solid #ddd;border-radius:8px;
           padding:14px;font-size:.95rem;line-height:1.6;resize:vertical;
           font-family:inherit;outline:none;margin-top:8px}
  .actions{display:flex;gap:10px;margin-top:12px}
  .actions button{flex:1;padding:9px;border:1.5px solid #ddd;border-radius:8px;
                  background:#fff;font-size:.9rem;cursor:pointer;font-weight:500;
                  transition:background .15s}
  .actions button:hover{background:#f3f4f6}
  .meta{font-size:.8rem;color:#999;margin-top:8px;text-align:right}
  .hint{font-size:.8rem;color:#999;margin-top:4px}
</style>
</head>
<body>
<div class="card">
  <h1>🎬 Video Transcriber</h1>
  <p class="sub">YouTube · TikTok · Instagram · Twitter/X · Facebook</p>

  <label for="url">Video URL</label>
  <input type="text" id="url" placeholder="https://www.youtube.com/watch?v=...">

  <div class="row">
    <div>
      <label for="model">Whisper model <span style="font-weight:400;color:#999">(non-YouTube only)</span></label>
      <select id="model">
        <option value="tiny">tiny — fastest</option>
        <option value="base" selected>base — balanced ✓</option>
        <option value="small">small — more accurate</option>
        <option value="medium">medium — most accurate</option>
      </select>
    </div>
    <div>
      <button class="primary" id="btn" onclick="transcribe()">Transcribe</button>
    </div>
  </div>

  <p id="status"></p>

  <label>Transcript</label>
  <textarea id="output" placeholder="Your transcript will appear here…" readonly></textarea>
  <p class="meta" id="meta"></p>

  <div class="actions">
    <button onclick="copyText()">📋 Copy</button>
    <button onclick="downloadText()">💾 Save as .txt</button>
    <button onclick="clearAll()">✕ Clear</button>
  </div>
</div>

<script>
async function transcribe() {
  const url = document.getElementById('url').value.trim();
  if (!url) { setStatus('Please paste a video URL first.', 'error'); return; }

  const btn = document.getElementById('btn');
  btn.disabled = true;
  document.getElementById('output').value = '';
  document.getElementById('meta').textContent = '';
  setStatus('Starting…', '');

  try {
    const res = await fetch('/transcribe', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url, model: document.getElementById('model').value})
    });
    const data = await res.json();
    if (data.error) {
      setStatus('Error: ' + data.error, 'error');
    } else {
      document.getElementById('output').value = data.transcript;
      const words = data.transcript.split(/\s+/).length;
      document.getElementById('meta').textContent =
        words.toLocaleString() + ' words · ' + data.transcript.length.toLocaleString() + ' characters';
      setStatus('Done! ✓', 'ok');
    }
  } catch(e) {
    setStatus('Request failed: ' + e.message, 'error');
  }
  btn.disabled = false;
}

function setStatus(msg, cls) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = cls;
}

function copyText() {
  const t = document.getElementById('output').value;
  if (!t) return;
  navigator.clipboard.writeText(t);
  setStatus('Copied to clipboard!', 'ok');
}

function downloadText() {
  const t = document.getElementById('output').value;
  if (!t) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([t], {type:'text/plain'}));
  a.download = 'transcript.txt';
  a.click();
}

function clearAll() {
  document.getElementById('url').value = '';
  document.getElementById('output').value = '';
  document.getElementById('meta').textContent = '';
  setStatus('', '');
}

// allow Enter key to trigger transcription
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.activeElement.id === 'url') transcribe();
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return HTML


@app.route("/transcribe", methods=["POST"])
def transcribe():
    data = request.get_json()
    url = (data.get("url") or "").strip()
    model_size = data.get("model", "base")

    if not url:
        return jsonify({"error": "No URL provided."})

    try:
        platform = detect_platform(url)
        if platform == "youtube":
            try:
                raw = transcribe_youtube(url)
            except Exception:
                raw = transcribe_with_whisper(url, model_size)
        else:
            raw = transcribe_with_whisper(url, model_size)

        transcript = format_transcript(raw)
        return jsonify({"transcript": transcript})

    except Exception as e:
        # strip ANSI colour codes from yt-dlp error messages
        clean = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
        return jsonify({"error": clean})


# ── launch ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5123
    url = f"http://localhost:{port}"
    # open browser after a short delay so Flask has time to start
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  Video Transcriber running at {url}")
    print("  Press Ctrl+C to stop.\n")
    app.run(port=port, debug=False)
