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

## 🚀 Quickstart (Coming soon)

```bash
# Clone the repository
git clone https://github.com/<your-username>/podcast-processor.git
cd podcast-processor

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Process an episode
adn-cli process episode.mp4
```
