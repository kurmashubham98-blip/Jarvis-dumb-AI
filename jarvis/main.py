"""
╔══════════════════════════════════════════════════════════════╗
║                    J.A.R.V.I.S  v2.0                        ║
║        Just A Rather Very Intelligent System                 ║
║                                                              ║
║  Main Entry Point                                            ║
║  Run: python -m jarvis.main                                  ║
║  Or:  python main.py                                         ║
╚══════════════════════════════════════════════════════════════╝

Modes:
  1. Interactive CLI  — text input via terminal (default)
  2. Voice Mode       — full voice pipeline with wake word
  3. Daemon Mode      — runs in background, HUD only on trigger
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.config import JarvisConfig, PROJECT_ROOT, LOGS_DIR
from jarvis.core.brain import JarvisBrain
from jarvis.voice.stt_engine import STTEngine
from jarvis.voice.tts_engine import TTSEngine

from jarvis.agents.orchestrator import Orchestrator
from jarvis.agents.automation_agent import AutomationAgent
from jarvis.agents.research_agent import ResearchAgent
from jarvis.agents.coding_agent import CodingAgent
from jarvis.browser.browser_agent import BrowserAgent
from jarvis.system.commander import PowerShellCommander
from jarvis.system.os_control import OSController
from jarvis.system.workflows import WorkflowManager


# ── Logging Setup ──────────────────────────────────────────────────
def setup_logging():
    """Configure logging to both console and file."""
    log_file = LOGS_DIR / f"jarvis_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(name)-25s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


# ── ASCII Banner ───────────────────────────────────────────────────
BANNER = """
\033[36m
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝ 
\033[0m
\033[90m        Just A Rather Very Intelligent System
                      v2.0 · STARK\033[0m
"""


# ── Interactive CLI Mode ───────────────────────────────────────────
async def run_cli(brain: JarvisBrain, tts: TTSEngine):
    """
    Interactive text mode — type commands in the terminal.
    Perfect for development and testing.
    """
    print(BANNER)
    print(f"\033[36m{brain.get_greeting()}\033[0m")
    print(f"\033[90m{'─' * 55}")
    print("  Type your message and press Enter.")
    print("  Commands: /voice  /status  /clear  /quit")
    print(f"{'─' * 55}\033[0m\n")

    speak_responses = False

    while True:
        try:
            user_input = await asyncio.to_thread(
                input, "\033[97m  You → \033[0m"
            )

            if not user_input.strip():
                continue

            # Handle special commands
            cmd = user_input.strip().lower()

            if cmd in ("/quit", "/exit", "/q", "exit", "quit"):
                print("\n\033[36m  Jarvis: Shutting down. Until next time, Sir.\033[0m\n")
                if speak_responses:
                    await tts.speak("Shutting down. Until next time.")
                break

            elif cmd in ("/tts", "/mute"):
                speak_responses = not speak_responses
                state = "ON" if speak_responses else "OFF"
                print(f"\033[90m  [Voice output: {state}]\033[0m")
                continue

            elif cmd in ("/mic", "/voice"):
                print(f"\033[90m  [Microphone Active - Speak Now...]\033[0m")
                try:
                    import speech_recognition as sr
                    recognizer = sr.Recognizer()
                    
                    # Auto-detect real microphone (skip virtual/droidcam)
                    mics = sr.Microphone.list_microphone_names()
                    device_index = None
                    for i, name in enumerate(mics):
                        if "DroidCam" not in name and "Virtual" not in name:
                            if "Headset" in name or "Headphones" in name or "Array" in name:
                                device_index = i
                                break
                    if device_index is None:
                        device_index = 0 # fallback to default

                    print(f"\033[90m  [Calibrating Microphone: {mics[device_index]}...]\033[0m", end="\r")
                    with sr.Microphone(device_index=device_index) as source:
                        recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        print(f"\r\033[K\033[92m  [Microphone Active - Speak Now...]\033[0m")
                        audio_data = recognizer.listen(source, timeout=10, phrase_time_limit=15)
                    print(f"\033[90m  [Processing audio...]\033[0m")
                    user_input = recognizer.recognize_google(audio_data)
                    print(f"\033[36m  You (Mic) → \033[0m{user_input}")
                except ImportError:
                    print(f"\033[31m  Error: SpeechRecognition not installed. Run: pip install SpeechRecognition PyAudio\033[0m")
                    continue
                except Exception as e:
                    print(f"\033[31m  Microphone error: {e}\033[0m")
                    continue

            elif cmd == "/status":
                status = brain.get_status()
                print(f"\033[90m  ── Brain Status ──")
                print(f"  Personality: {status['personality']}")
                print(f"  Context: {status['context']['messages']} messages, ~{status['context']['estimated_tokens']} tokens")
                print(f"  Session: {status['context']['session_minutes']} min")
                print(f"  Last response: {status['last_response_time']}s")
                print(f"  LLM providers:")
                for name, info in status['llm_status'].items():
                    avail = "✓" if info['available'] else "✗"
                    print(f"    {avail} {name}: {info['remaining_today']} requests remaining today")
                print(f"  ────────────────\033[0m")
                continue

            elif cmd == "/clear":
                brain.new_session()
                print(f"\033[90m  [Conversation cleared]\033[0m")
                continue

            # Normal conversation
            print(f"\033[90m  Thinking...\033[0m", end="\r")

            response = await brain.think(user_input)

            # Clear the "Thinking..." line
            print(f"\r\033[K", end="")
            print(f"\033[36m  Jarvis → \033[0m{response}\n")

            if speak_responses:
                await tts.speak(response)

        except KeyboardInterrupt:
            print("\n\n\033[36m  Jarvis: Caught that. Shutting down gracefully.\033[0m\n")
            break
        except EOFError:
            break
        except Exception as e:
            print(f"\033[31m  Error: {e}\033[0m")
            logging.getLogger("jarvis.main").error(f"CLI error: {e}", exc_info=True)


# ── Voice Mode ─────────────────────────────────────────────────────
async def run_voice(brain: JarvisBrain, stt: STTEngine, tts: TTSEngine):
    """Full voice mode with mic listening."""
    from jarvis.voice.audio_manager import AudioManager

    print(BANNER)
    print(f"\033[36m{brain.get_greeting()}\033[0m")
    await tts.speak(brain.get_greeting())

    audio = AudioManager(
        stt_engine=stt,
        tts_engine=tts,
        brain=brain,
    )

    # Register callbacks for CLI display
    audio.on_transcription(lambda text: print(f"\033[97m  You → \033[0m{text}"))
    audio.on_response(lambda resp: print(f"\033[36m  Jarvis → \033[0m{resp}"))

    print(f"\033[90m  Listening... (speak to interact, Ctrl+C to quit)\033[0m\n")

    try:
        await audio.start_listening()
    except KeyboardInterrupt:
        audio.stop_listening()
        print("\n\033[36m  Jarvis: Voice mode off. Goodbye.\033[0m")


# ── Main ───────────────────────────────────────────────────────────
async def main():
    setup_logging()
    logger = logging.getLogger("jarvis.main")

    # Load config
    try:
        config = JarvisConfig.load()
        logger.info("Configuration loaded")
    except ValueError as e:
        print(f"\n\033[31m  ✗ {e}\033[0m")
        print(f"\033[90m  Create a .env file at: {PROJECT_ROOT / '.env'}")
        print(f"  With your API keys:")
        print(f"    GEMINI_API_KEY=your_key_here")
        print(f"    GROQ_API_KEY=your_key_here\033[0m\n")
        return

    # Initialize core systems
    brain = JarvisBrain(config)
    
    # Initialize agents
    commander = PowerShellCommander()
    oscon = OSController(commander)
    workflows = WorkflowManager(commander, oscon, None)
    
    orchestrator = Orchestrator(brain)
    orchestrator.register_agent(CodingAgent(brain))
    orchestrator.register_agent(ResearchAgent(brain))
    
    # Setup Automation and Browser agents
    browser_agent = BrowserAgent(brain)
    workflows.browser = browser_agent  
    
    # We will register automation agent
    automation_agent = AutomationAgent(brain, oscon, commander, workflows)
    orchestrator.register_agent(automation_agent)
    
    # Register browser agent adapter directly since it lacks BaseAgent inheritance currently
    # We duck-type it for the orchestrator
    class BrowserAdapter:
        name = "Browser"
        async def process(self, query, ctx=None):
            return await browser_agent.execute(query)
    
    orchestrator.register_agent(BrowserAdapter())
    
    # Attach orchestrator to brain
    brain.orchestrator = orchestrator

    tts = TTSEngine(
        voice=config.voice.tts_voice,
        rate=config.voice.tts_rate,
    )

    stt = None
    if config.llm.groq_api_key:
        stt = STTEngine(
            groq_api_key=config.llm.groq_api_key,
            model=config.llm.groq_whisper_model,
        )

    # Parse command line mode
    mode = "cli"
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower().strip("-")

    if mode == "voice":
        if stt:
            await run_voice(brain, stt, tts)
        else:
            print("\033[31m  Voice mode requires GROQ_API_KEY for Whisper STT.\033[0m")
            await run_cli(brain, tts)
    else:
        await run_cli(brain, tts)


if __name__ == "__main__":
    asyncio.run(main())
