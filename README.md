# Jarvis-dumb-AI

> **J A.R.V.I.S.** - Complete AI Assistant v2.0

A fully free, Iron Man-inspired AI assistant with 14 core subsystems. Voice-activated, multi-AI-provider, and application-focused.

---

## Features

|-|-|
|---|---|
 | 📅 **Voice I/O** | Speech to text (Groq) + Neural TTS (Edge), wake word "Hey Jarvis" |
 | 💥 **Multi-LL Provider** | Gemini 2.5 Flash (hierarchy) → Groq -> Ollama (offline) |
 | 💧 **Memory System** | MemPalace + ChromaDB for long-term vervatim recall |
 | 💧 **Browser Automation** | Playwright-based, DOM-level control |
 | 💹 **Vision & OCR**| Screen capture, text extraction, image processing |
 | 🌎 **GUI HUD (Overlay)** | PywebView transparent overlay |
 | 📸 **Coding Agent** |  Code generation and system control |
 | 💣 **Research Agent**|  Web search (Cookie) + HTML parsing |
 | 💩 **Security Layer** | AES/Fernet encryption |
 | 💻 **Task Automation** | APScheduler-based scheduling |
 | 💪 **System Monitoring** | psutil-based system health tracking |

## Getting Started

```bash
git clone https://github.com/kurmashubham98-blip/Jarvis-dumb-AI.git
cd Jarvis-dumb-AI
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then run the bat file to launch:

```bash
Run_Jarvis.bat
```

## Requirements

- Python 3.9+
+ Microsoft Edge TTUS voices (windows)
- (Optional) OLLAMA for offline LLM requires NEVIDIA GPU

## License

MIT
