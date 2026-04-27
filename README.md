# Video Transcriber

Paste any YouTube, TikTok, Instagram, Twitter/X, or Facebook video URL and get a text transcript. Completely free — runs locally on your machine.

## How it works

- **YouTube**: grabs existing captions instantly (no AI needed)
- **Everything else**: downloads audio with yt-dlp, transcribes with OpenAI Whisper running locally on your computer

No API keys. No subscriptions. No cost per video.

---

## Setup (one-time)

### 1. Install FFmpeg

**Mac:**
```bash
brew install ffmpeg
```
**Windows:** download from https://ffmpeg.org or run `winget install ffmpeg`

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the app
```bash
python app.py
```

The first time you run a non-YouTube video, Whisper will download the model (~140 MB for `base`). After that it's cached.

---

## Bundle as a clickable desktop app (optional)

### Install PyInstaller
```bash
pip install pyinstaller
```

### Mac
```bash
pyinstaller --onefile --windowed app.py
```
Your `.app` file will appear in the `dist/` folder.

### Windows
```bash
pyinstaller --onefile --noconsole app.py
```
Your `.exe` will appear in the `dist/` folder.

---

## Whisper model sizes

| Model  | Speed  | Accuracy | RAM needed |
|--------|--------|----------|------------|
| tiny   | Fastest | Lower   | ~1 GB      |
| base   | Fast   | Good     | ~1 GB      |
| small  | Medium | Better   | ~2 GB      |
| medium | Slow   | Best     | ~5 GB      |

`base` is the default and works well for most videos.
