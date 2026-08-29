---
name: adn-podcast-processor
description: >-
  Automates the post-production workflow for ADN Divergente podcast episodes.
  Use when processing raw Riverside audio/video recordings, generating Spanish
  transcripts, brainstorming YouTube titles, generating chapters, cutting 16:9
  clips, and rendering 9:16 vertical shorts with dynamic subtitles.
---

# ADN Divergente Podcast Processor Skill

This skill teaches Antigravity how to manage and execute the post-production pipeline for the **ADN Divergente** podcast.

## 🎙️ Podcast Profile
- **Show**: ADN Divergente (https://www.youtube.com/@ADNDivergente)
- **Hosts**: Miguel & Brother
- **Tone**: Candid, intellectual, philosophical, critical, authentic, unscripted.
- **Language**: Spanish (Latin American natural phrasing).

---

## 🛠️ CLI Quick Reference

### Using `uv` (Recommended):
```bash
# 1. Full Pipeline (Transcribe -> Analyze -> 16:9 Clips -> 9:16 Shorts)
uv run adn process /path/to/episode.mp4

# 2. Step-by-Step Execution
uv run adn transcribe /path/to/episode.mp4
uv run adn analyze output/<episode>/<episode>_transcript.json
uv run adn cut /path/to/episode.mp4 output/<episode>/<episode>_analysis.json
uv run adn shorts /path/to/episode.mp4 output/<episode>/<episode>_analysis.json output/<episode>/<episode>_transcript.json

# 3. YouTube Automated Uploads
uv run adn upload /path/to/episode.mp4 output/<episode>/<episode>_analysis.json --privacy unlisted
uv run adn upload-shorts output/<episode>/<episode>_analysis.json --privacy unlisted
uv run adn auth

# 4. Health & Configuration Check
uv run adn doctor
```

### Or using activated `.venv`:
```bash
source .venv/bin/activate
adn process /path/to/episode.mp4
```

---

## 📂 Output Artifacts

When an episode is processed, the files are structured under `output/<episode_name>/`:
- `*_transcript.json`: Full transcript with word/segment timestamps.
- `*_transcript.srt`: Formatted subtitles for YouTube.
- `*_transcript.txt`: Plaintext transcript with periodic timestamps.
- `*_analysis.json`: Structured metadata (titles, chapters, clip picks, social posts).
- `*_youtube_description.txt`: Formatted description ready for upload.
- `clips/*.mp4`: Standalone 16:9 mini-episodes (Lex Fridman style).
- `shorts/*.mp4`: 9:16 vertical videos with burned-in dynamic karaoke subtitles.

---

## 🤖 Agent Workflow Guidelines

When the user asks you to process or assist with an episode:

1. **Verify Environment**:
   Run `adn doctor` to ensure FFmpeg and at least one LLM key (`GEMINI_API_KEY` or `OPENAI_API_KEY`) is active.
2. **Execute Processing**:
   Run `adn process <file>` via `run_command`.
3. **Present Editorial Choices**:
   After processing finishes, present the user with:
   - The top 3 recommended YouTube titles with rationale.
   - The generated YouTube chapters for review.
   - The list of cut clips and shorts generated.
4. **Collaborate & Refine**:
   If the user wants to adjust clip start/end times or tweak titles, modify the `*_analysis.json` and re-run `adn cut` or `adn shorts`.
