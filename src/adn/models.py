"""Pydantic data models for transcripts and AI-generated analysis."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# --- Transcript Models ---

class TranscriptWord(BaseModel):
    word: str
    start: float
    end: float
    probability: Optional[float] = None


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: Optional[List[TranscriptWord]] = None


class Transcript(BaseModel):
    language: str = "es"
    duration: float
    full_text: str
    segments: List[TranscriptSegment]


# --- AI Analysis Models ---

class TitleOption(BaseModel):
    title: str = Field(..., description="Compelling YouTube title (max 70 chars).")
    style: Literal["curiosity", "debate", "question", "story", "contrarian"] = Field(
        ..., description="The psychological hook style."
    )
    rationale: str = Field(..., description="Why this title works for ADN Divergente audience.")


class YouTubeChapter(BaseModel):
    timestamp: str = Field(..., description="Formatted timestamp (e.g. '00:00', '14:23').")
    seconds: float = Field(..., description="Start time in seconds.")
    title: str = Field(..., description="Short, intriguing chapter title (in Spanish).")


class ClipCandidate(BaseModel):
    id: str = Field(..., description="Identifier (e.g. 'clip_01').")
    title: str = Field(..., description="Catchy title for the mini-episode / standalone clip.")
    start_seconds: float = Field(..., description="Start timestamp in seconds.")
    end_seconds: float = Field(..., description="End timestamp in seconds.")
    duration_formatted: str = Field(..., description="Duration string (e.g. '05:32').")
    hook: str = Field(..., description="The opening hook of this clip.")
    summary: str = Field(..., description="Summary of the debate or topic in this clip.")
    reason: str = Field(..., description="Why this works as a standalone Lex Fridman style clip.")


class ShortCandidate(BaseModel):
    id: str = Field(..., description="Identifier (e.g. 'short_01').")
    title: str = Field(..., description="Punchy title for TikTok/Reels/Shorts.")
    start_seconds: float = Field(..., description="Start timestamp in seconds (between 30s-75s total duration).")
    end_seconds: float = Field(..., description="End timestamp in seconds.")
    duration_seconds: float = Field(..., description="Duration in seconds.")
    hook_quote: str = Field(..., description="The opening or most explosive sentence.")
    topic: str = Field(..., description="Key idea or reaction.")


class SocialContent(BaseModel):
    x_thread: List[str] = Field(..., description="3-5 tweet thread highlighting key insights.")
    linkedin_post: str = Field(..., description="Professional, thought-provoking post for LinkedIn.")
    instagram_caption: str = Field(..., description="Engaging Instagram caption with emojis and relevant hashtags.")


class EpisodeAnalysis(BaseModel):
    episode_summary: str = Field(..., description="Executive summary of the episode (in Spanish).")
    core_themes: List[str] = Field(..., description="List of primary topics and cultural/social themes discussed.")
    title_options: List[TitleOption] = Field(..., description="10 high-CTR YouTube title options in Spanish.")
    youtube_chapters: List[YouTubeChapter] = Field(..., description="Chronological YouTube chapters.")
    youtube_description: str = Field(..., description="Complete ready-to-paste YouTube description with timestamps and links.")
    clips: List[ClipCandidate] = Field(..., description="3 to 6 standalone mini-episode clips (3-10 minutes each).")
    shorts: List[ShortCandidate] = Field(..., description="4 to 8 punchy vertical short candidates (30-75 seconds each).")
    social_content: SocialContent = Field(..., description="Social media copy.")
