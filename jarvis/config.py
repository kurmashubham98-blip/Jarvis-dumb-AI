"""
Jarvis v2.0 — Global Configuration System
==========================================
Manages all settings, API keys, paths, and user preferences.
API keys are loaded from environment variables or .env file — NEVER hardcoded.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_FILE = DATA_DIR / "config.yaml"
PERMISSIONS_FILE = DATA_DIR / "permissions.yaml"
WORKFLOWS_DIR = DATA_DIR / "workflows"
KEYS_DIR = DATA_DIR / "keys"
MEMORY_DIR = Path("D:/JarvisMemory")  # MemPalace data lives here
LOGS_DIR = DATA_DIR / "logs"

# Ensure directories exist
for d in [DATA_DIR, WORKFLOWS_DIR, KEYS_DIR, MEMORY_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Load Environment ───────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class LLMConfig:
    """LLM provider configuration — cloud-only cascade."""
    # Primary: Gemini 2.5 Flash
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_rpm_limit: int = 15  # Free tier ~15 RPM
    gemini_daily_limit: int = 1500

    # Fallback: Groq (Llama 3.3 70B)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_rpm_limit: int = 30
    groq_daily_limit: int = 1000

    # Groq Whisper (cloud STT)
    groq_whisper_model: str = "whisper-large-v3"

    # Generation settings
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.95


@dataclass
class VoiceConfig:
    """Voice system configuration."""
    # TTS
    tts_voice: str = "en-GB-RyanNeural"  # Microsoft Edge neural voice
    tts_rate: str = "+10%"  # Slightly faster for Jarvis feel
    tts_volume: str = "+0%"
    tts_pitch: str = "+0Hz"

    # Wake word
    wake_word: str = "hey jarvis"
    wake_word_sensitivity: float = 0.6

    # Audio
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1280  # ~80ms at 16kHz

    # STT
    stt_provider: str = "groq_whisper"  # Cloud-based Whisper via Groq
    stt_language: str = "en"


@dataclass
class SecurityConfig:
    """Security and privacy configuration."""
    # Auth
    voice_passphrase: str = ""  # Set during setup
    pin_code: str = ""  # Set during setup
    auth_timeout_minutes: int = 30  # Re-auth after idle

    # Privacy
    sanitize_before_cloud: bool = True
    blocked_paths: list = field(default_factory=lambda: [
        "C:\\Users\\*\\AppData",
        "C:\\Windows\\System32",
        "C:\\Program Files",
        "*\\.ssh",
        "*\\.gnupg",
        "*\\passwords*",
        "*\\credentials*",
    ])

    # Sensitive patterns to redact
    redact_patterns: list = field(default_factory=lambda: [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # Emails
        r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",                      # Phone numbers
        r"(?:password|passwd|pwd)\s*[:=]\s*\S+",                 # Passwords
        r"(?:api[_-]?key|token|secret)\s*[:=]\s*\S+",           # API keys
        r"[A-Za-z]:\\Users\\[^\\]+",                              # User paths
    ])


@dataclass
class MonitorConfig:
    """System monitoring configuration."""
    poll_interval_seconds: int = 5
    cpu_alert_threshold: float = 90.0
    ram_alert_threshold: float = 85.0
    battery_low_threshold: int = 20
    battery_critical_threshold: int = 10
    disk_alert_threshold: float = 90.0


@dataclass
class UIConfig:
    """HUD interface configuration."""
    width: int = 480
    height: int = 720
    transparent: bool = True
    frameless: bool = True
    on_top: bool = True
    theme: str = "ironman"  # ironman, stealth, minimal


@dataclass
class TriggerRule:
    """A condition-based automation trigger."""
    name: str
    condition: str  # Python expression to evaluate
    action: str  # Action to perform
    cooldown_seconds: int = 300  # Don't re-trigger for 5 min
    enabled: bool = True
    message: str = ""  # Optional Jarvis quip


@dataclass
class JarvisConfig:
    """Master configuration for Jarvis v2.0."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # Personality
    personality_name: str = "Jarvis"
    personality_style: str = "witty"  # witty, serious, casual
    user_name: str = "Sir"

    # Triggers — loaded from YAML, with Iron Man defaults
    triggers: list = field(default_factory=list)

    def load_api_keys(self):
        """Load API keys from environment variables."""
        self.llm.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.llm.groq_api_key = os.getenv("GROQ_API_KEY", "")

        if not self.llm.gemini_api_key and not self.llm.groq_api_key:
            raise ValueError(
                "No API keys found! Set GEMINI_API_KEY and/or GROQ_API_KEY "
                "in your .env file or environment variables."
            )

    def save(self):
        """Save config to YAML (excluding API keys — those stay in .env)."""
        config_dict = {
            "personality": {
                "name": self.personality_name,
                "style": self.personality_style,
                "user_name": self.user_name,
            },
            "voice": {
                "tts_voice": self.voice.tts_voice,
                "tts_rate": self.voice.tts_rate,
                "wake_word": self.voice.wake_word,
                "wake_word_sensitivity": self.voice.wake_word_sensitivity,
                "stt_provider": self.voice.stt_provider,
            },
            "security": {
                "auth_timeout_minutes": self.security.auth_timeout_minutes,
                "sanitize_before_cloud": self.security.sanitize_before_cloud,
            },
            "monitor": {
                "poll_interval_seconds": self.monitor.poll_interval_seconds,
                "cpu_alert_threshold": self.monitor.cpu_alert_threshold,
                "ram_alert_threshold": self.monitor.ram_alert_threshold,
                "battery_low_threshold": self.monitor.battery_low_threshold,
            },
            "ui": {
                "width": self.ui.width,
                "height": self.ui.height,
                "theme": self.ui.theme,
            },
        }
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False)

    @classmethod
    def load(cls) -> "JarvisConfig":
        """Load config from YAML + environment."""
        config = cls()
        config.load_api_keys()

        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                data = yaml.safe_load(f) or {}

            if "personality" in data:
                config.personality_name = data["personality"].get("name", config.personality_name)
                config.personality_style = data["personality"].get("style", config.personality_style)
                config.user_name = data["personality"].get("user_name", config.user_name)

            if "voice" in data:
                config.voice.tts_voice = data["voice"].get("tts_voice", config.voice.tts_voice)
                config.voice.tts_rate = data["voice"].get("tts_rate", config.voice.tts_rate)
                config.voice.wake_word = data["voice"].get("wake_word", config.voice.wake_word)

            if "ui" in data:
                config.ui.width = data["ui"].get("width", config.ui.width)
                config.ui.height = data["ui"].get("height", config.ui.height)
                config.ui.theme = data["ui"].get("theme", config.ui.theme)

        # Load default triggers
        config.triggers = cls._default_triggers()

        return config

    @staticmethod
    def _default_triggers() -> list:
        """Iron Man-worthy default triggers."""
        return [
            TriggerRule(
                name="battery_low",
                condition="battery_percent < 20",
                action="enable_power_saver",
                message="Sir, power reserves are depleting. Switching to conservation mode.",
            ),
            TriggerRule(
                name="battery_critical",
                condition="battery_percent < 10",
                action="critical_power_alert",
                cooldown_seconds=120,
                message="Sir, we're running on fumes. I'd recommend plugging in immediately.",
            ),
            TriggerRule(
                name="cpu_overload",
                condition="cpu_percent > 90",
                action="suggest_cpu_fix",
                cooldown_seconds=300,
                message="CPU load is critical at {cpu_percent}%. Shall I identify the culprit?",
            ),
            TriggerRule(
                name="ram_pressure",
                condition="ram_percent > 85",
                action="suggest_ram_fix",
                message="Memory usage at {ram_percent}%. Chrome has {chrome_tabs} tabs open. Want me to handle it?",
            ),
            TriggerRule(
                name="morning_briefing",
                condition="time_hour == 9 and time_minute == 0",
                action="morning_briefing",
                cooldown_seconds=3600,
                message="Good morning, {user_name}. Here's your daily briefing.",
            ),
            TriggerRule(
                name="midnight_owl",
                condition="time_hour == 0 and time_minute == 0",
                action="midnight_warning",
                cooldown_seconds=3600,
                message="Sir, it's past midnight. Even geniuses need sleep. Shall I enable night mode?",
            ),
            TriggerRule(
                name="long_session",
                condition="active_session_minutes > 180",
                action="break_reminder",
                cooldown_seconds=1800,
                message="You've been at it for {active_session_minutes} minutes straight. Even Stark took breaks between suits.",
            ),
            TriggerRule(
                name="idle_detected",
                condition="idle_minutes > 30",
                action="idle_response",
                cooldown_seconds=1800,
                message="No activity for {idle_minutes} minutes. I'll dim the displays and stand by, Sir.",
            ),
            TriggerRule(
                name="wifi_disconnect",
                condition="wifi_connected == False",
                action="wifi_reconnect",
                cooldown_seconds=60,
                message="Network connection lost. Attempting to re-establish communications.",
            ),
            TriggerRule(
                name="usb_device_connected",
                condition="new_usb_detected == True",
                action="usb_security_scan",
                cooldown_seconds=10,
                message="New device detected. Running security scan before I trust it.",
            ),
            TriggerRule(
                name="gaming_mode",
                condition="gpu_usage > 80 and gaming_process_detected == True",
                action="enable_gaming_mode",
                cooldown_seconds=600,
                message="Game detected. Optimizing system performance. Go win, {user_name}.",
            ),
            TriggerRule(
                name="coding_detected",
                condition="coding_app_active == True and active_session_minutes > 5",
                action="coding_mode",
                cooldown_seconds=3600,
                message="Coding session detected. I'll monitor for errors and keep things quiet.",
            ),
            TriggerRule(
                name="disk_space_low",
                condition="disk_percent > 90",
                action="disk_cleanup_suggest",
                cooldown_seconds=3600,
                message="Storage running low at {disk_percent}%. Shall I find what's eating space?",
            ),
            TriggerRule(
                name="high_download",
                condition="download_speed_mbps > 50 and download_active == True",
                action="download_monitor",
                cooldown_seconds=300,
                message="Large download in progress. I'll notify you when it completes.",
            ),
            TriggerRule(
                name="system_boot",
                condition="just_booted == True",
                action="boot_greeting",
                cooldown_seconds=300,
                message="Systems online. All reactors nominal. Welcome back, {user_name}.",
            ),
            TriggerRule(
                name="temperature_warning",
                condition="cpu_temp > 85",
                action="thermal_warning",
                cooldown_seconds=300,
                message="Thermal readings are elevated — {cpu_temp}°C. Recommending a cooldown, Sir.",
            ),
        ]
