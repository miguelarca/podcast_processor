# ADN Divergente - Podcast Processor 🎙️⚡

An automated, local-first post-production AI tool designed for the **[ADN Divergente](https://www.youtube.com/@ADNDivergente)** podcast. 

This tool automates the process of transforming raw Riverside recordings into published content:
- 📝 **Accurate Spanish Transcription** with word-level timestamps (Local Faster-Whisper or Cloud Whisper).
- 🏷️ **Metadata Generation**: 10 title variations, YouTube Chapters, SEO descriptions, and social posts.
- ✂️ **Magic Clips (Lex Fridman Style)**: Automatically detects and cuts engaging standalone 16:9 discussion segments (3–10 min).
- 📱 **Shorts / Reels / TikTok Generator**: 9:16 vertical video re-framing with animated karaoke-style dynamic subtitles.
- 🎨 **Thumbnail Ideator & Keyframe Extractor**: Finds the best facial expressions and visual themes.
- 🤖 **Antigravity AI Agent Skill**: Control and collaborate with the pipeline directly inside your agent chat.

---

## 🛠️ Requirements

- macOS (Apple Silicon optimized)
- Python 3.10+
- `ffmpeg` installed (`brew install ffmpeg`)

---

## 🚀 Quickstart with `uv` (Recommended)

```bash
# 1. Clone & enter project
git clone git@github.com:miguelarca/podcast_processor.git
cd podcast_processor

# 2. Sync dependencies (instant with uv)
uv sync

# 3. Configure environment
cp .env.example .env
# (Add your GEMINI_API_KEY to .env)

# 4. Check system health
uv run adn doctor

# 5. Process an episode end-to-end
uv run adn process episode.mp4
```

---

## ⚡ CLI Commands

| Command | Description |
| :--- | :--- |
| `uv run adn process <file>` | Full pipeline: Transcribe -> Analyze -> 16:9 Clips -> 9:16 Shorts |
| `uv run adn transcribe <file>` | Generates Spanish transcript (`.json`, `.txt`, `.srt`) |
| `uv run adn analyze <transcript.json>` | Generates 10 YouTube titles, chapters, show notes & clip ideas |
| `uv run adn cut <video> <analysis.json>` | Slices standalone 16:9 mini-episodes (Lex style) |
| `uv run adn thumbnail <analysis.json>` | 🎨 Generates concepts + renders local 16:9 thumbnails via FLUX.1 |
| `uv run adn flux-render "<prompt>"` | ⚡ Generates any custom 16:9 image locally on Apple Silicon Metal GPU |
| `uv run adn composite-thumbnail <img.png>` | 🖼️ Composites branding + auto-fitted 3D text onto any background |
| `uv run adn upload <video> <analysis.json>` | 🚀 Uploads full video with title, chapters, description, CC to YouTube |
| `uv run adn upload-shorts <analysis.json>` | 📱 Batch uploads all vertical shorts to YouTube Shorts |
| `uv run adn upload-clips <analysis.json>` | ✂️ Batch uploads all standalone 16:9 mini-episodes to YouTube |
| `uv run adn update-metadata <id> -t "..."` | ✏️ Updates title/description of existing YouTube videos via API |
| `uv run adn auth` | Authenticates with YouTube Data API via browser OAuth |
| `uv run adn doctor` | Checks FFmpeg, AI keys, FLUX.1 engine, and YouTube OAuth |

---

## 📺 YouTube Auto-Upload Setup (Optional)

To enable 1-click uploads directly from the CLI:
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Enable the **YouTube Data API v3**.
3. Create an **OAuth 2.0 Client ID** (Application type: *Desktop App*).
4. Download the JSON and place it in the project root as `client_secrets.json`.
5. Run `uv run adn auth` to log in once in your browser. (Credentials are saved to `token.json`, which is git-ignored).

