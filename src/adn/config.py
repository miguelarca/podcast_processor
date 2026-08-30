"""Configuration management for ADN Podcast Processor."""

import os
import shutil
from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys & Tokens
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    HF_TOKEN: Optional[str] = None

    # Processing Defaults
    DEFAULT_LLM_PROVIDER: Literal["gemini", "openai"] = "gemini"
    GEMINI_MODEL: str = "gemini-3.6-flash"
    OPENAI_MODEL: str = "gpt-4o"
    DEFAULT_TRANSCRIPTION_BACKEND: Literal["faster-whisper", "groq", "openai"] = "faster-whisper"
    WHISPER_MODEL_SIZE: str = "medium"  # "base", "small", "medium", "large-v3"
    WHISPER_DEVICE: str = "auto"  # "auto", "cpu", "cuda"
    WHISPER_COMPUTE_TYPE: str = "int8"  # "int8", "float16", "default"

    # Default Output Directory
    DEFAULT_OUTPUT_DIR: Path = Path("output")

    @property
    def ffmpeg_path(self) -> Optional[str]:
        """Detect ffmpeg binary location."""
        # Common locations on macOS
        candidates = [
            shutil.which("ffmpeg"),
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
        ]
        for path in candidates:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                return path
        return None

    @property
    def ffprobe_path(self) -> Optional[str]:
        """Detect ffprobe binary location."""
        candidates = [
            shutil.which("ffprobe"),
            "/opt/homebrew/bin/ffprobe",
            "/usr/local/bin/ffprobe",
        ]
        for path in candidates:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                return path
        return None


settings = Settings()
