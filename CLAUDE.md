# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Podcastfy is an open-source Python package (v0.4.1) that transforms multi-modal content (websites, PDFs, images, YouTube videos, text) into engaging, multi-lingual audio conversations using Generative AI. It's an open-source, programmatic alternative to Google's NotebookLM podcast feature.

**Key capabilities:**
- Multi-modal input: websites, YouTube, PDFs, images, raw text, topics
- 100+ LLM models via LiteLLM + Google Gemini + local LLMs
- Multiple TTS providers: OpenAI, ElevenLabs, Google (Gemini multi-speaker), Edge TTS
- Short-form (2-5 min) and long-form (30+ min) podcast generation
- Multi-language support
- CLI, Python API, and FastAPI REST endpoints

## Architecture

The codebase follows a **modular, multi-stage pipeline architecture**:

```
Input Sources → Content Extraction → LLM Generation → TTS Conversion → Audio Output
```

### Core Modules

**`podcastfy/client.py`** - Main orchestrator
- CLI entry point (Typer-based)
- Python API: `generate_podcast()` function
- Coordinates the entire pipeline

**`podcastfy/content_parser/`** - Multi-source content extraction
- `content_extractor.py` - Router for all content types
- `website_extractor.py` - BeautifulSoup-based web scraping
- `youtube_transcriber.py` - YouTube transcript API
- `pdf_extractor.py` - PyMuPDF-based PDF extraction

**`podcastfy/content_generator.py`** - LLM-based transcript generation
- Supports 100+ models via LiteLLM abstraction
- Google Gemini as special case (native API)
- Local LLM support (Llamafile)
- `LongFormContentGenerator` - "Content Chunking with Contextual Linking" for 30+ min podcasts

**`podcastfy/text_to_speech.py`** - TTS orchestration
- PyDub for audio merging
- SSML cleanup
- Ending message insertion

**`podcastfy/tts/`** - TTS provider abstraction
- `base.py` - Abstract `TTSProvider` base class
- `factory.py` - Factory pattern for provider creation
- `providers/` - OpenAI, ElevenLabs, Gemini (single/multi-speaker), Edge TTS

**`podcastfy/utils/`** - Configuration management
- `config.py` - YAML + environment variable loading
- `config_conversation.py` - Conversation style configuration
- `logger.py` - Logging setup

**`podcastfy/api/fast_app.py`** - FastAPI REST endpoints
- `POST /generate` - Generate podcast endpoint

### Key Design Patterns

1. **Factory Pattern** - TTS provider creation (`TTSProviderFactory`)
2. **Strategy Pattern** - Multiple LLM backends (Gemini, LiteLLM, local)
3. **Abstract Base Class** - TTS interface (`TTSProvider`)
4. **Configuration Hierarchy** - `.env` → env vars → YAML → runtime params

## Development Commands

### Environment Setup
```bash
# Using Poetry (preferred)
poetry install

# Using uv (alternative)
uv pip install -r requirements.txt

# Install ffmpeg (required for audio processing)
pip install ffmpeg  # or use system package manager
```

### Testing
```bash
# Run all tests in parallel
poetry run pytest -n auto

# Run all tests with pytest directly
pytest -n auto

# Run specific test file
poetry run pytest tests/test_client.py

# Run single test
poetry run pytest tests/test_client.py::test_function_name
```

### Code Quality
```bash
# Run linter and type checker
make lint

# Format code with black
black podcastfy/*.py tests/*.py

# Type check with mypy
mypy podcastfy/*.py
```

### Documentation
```bash
# Regenerate Sphinx API documentation
make doc-gen

# This runs:
# 1. sphinx-apidoc -f -o ./docs/source ./podcastfy
# 2. cd ./docs && make clean && make html
```

### Running the Application

**CLI:**
```bash
# Generate from URLs
python -m podcastfy.client --url <url1> --url <url2>

# Generate from YouTube
python -m podcastfy.client --url https://youtube.com/watch?v=...

# Generate from PDF
python -m podcastfy.client --file path/to/urls.txt

# Use specific TTS provider
python -m podcastfy.client --url <url> --tts-model elevenlabs

# Transcript only (no audio)
python -m podcastfy.client --url <url> --transcript-only

# Long-form generation (30+ min)
python -m podcastfy.client --url <url> --longform

# Custom conversation config
python -m podcastfy.client --url <url> --conversation-config custom_config.yaml

# Use local LLM
python -m podcastfy.client --url <url> --local

# Generate from topic (uses web search)
python -m podcastfy.client --topic "AI safety in 2024"

# Generate from images
python -m podcastfy.client --image path/to/image1.jpg --image path/to/image2.jpg
```

**Python API:**
```python
from podcastfy.client import generate_podcast

# Basic usage
audio_file = generate_podcast(urls=["https://example.com"])

# With custom config
audio_file = generate_podcast(
    urls=["url1", "url2"],
    tts_model="elevenlabs",
    longform=True,
    conversation_config={"style": "casual"}
)
```

**FastAPI:**
```bash
# Build and run API container
docker build -f Dockerfile_api -t podcastfy-api .
docker run -p 8000:8000 podcastfy-api

# Or use docker-compose
docker-compose up
```

## Configuration

### API Keys (Required)

Set these environment variables in `.env` or your shell:

```bash
GEMINI_API_KEY=<your-key>      # For Google Gemini (recommended)
OPENAI_API_KEY=<your-key>      # For OpenAI TTS/LLM
ELEVENLABS_API_KEY=<your-key>  # For ElevenLabs TTS
GOOGLE_CLOUD_CREDENTIALS=<path> # For Google Cloud TTS
```

### Configuration Files

**`podcastfy/config.yaml`** - Content extraction settings
- Website scraping patterns
- YouTube extraction rules
- PDF processing options

**`podcastfy/conversation_config.yaml`** - Conversation generation
- Podcast style and structure
- Speaker roles and personalities
- TTS provider settings
- Output directory paths

**Custom configs** can be passed via:
- `--conversation-config` CLI flag
- `conversation_config` parameter in Python API
- Runtime dictionary overrides

## Dependency Management

**Primary tool:** Poetry (pyproject.toml)

**Adding dependencies:**
```bash
poetry add <package>
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

**Removing dependencies:**
```bash
poetry remove <package>
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

**Alternative:** Contributors can use `uv` and update requirements.txt

## Pre-Pull Request Checklist

1. **Dependencies**: If added/removed packages:
   - `poetry add/remove <package>`
   - `poetry export -f requirements.txt --output requirements.txt --without-hashes`

2. **Testing**:
   - Add tests in `tests/*.py` for user-facing changes
   - Run locally: `poetry run pytest`
   - CI runs tests automatically - verify they pass

3. **Code quality**:
   - Format with black: `black podcastfy/*.py tests/*.py`
   - Type check: `mypy podcastfy/*.py`
   - Run linter: `make lint`

4. **Documentation**:
   - Update README.md, usage/*.md, or *.ipynb as needed
   - Regenerate API docs if docstrings changed: `make doc-gen`

## Code Style Guidelines

- **Follow PEP 8** for Python code
- **Use tabs for indentation** (not spaces)
- **Descriptive variable names** that reflect components
- **Include docstrings** for all functions, classes, and modules
- **Type hints** are encouraged (mypy is used)

## CI/CD Pipeline

**Workflow:** `.github/workflows/python-app.yml`

**Triggers:**
- Push to `main` branch (for .py files, tests, requirements, workflows)
- Pull requests to `main`

**Steps:**
1. Install Python 3.11+, ffmpeg, dependencies
2. Create venv in `/opt/venv`
3. Run flake8 linting
4. Run pytest with `-n auto --dist loadfile`
5. Upload test artifacts

**Required secrets:**
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`

## Important Implementation Details

### Long-form Generation
- Uses "Content Chunking with Contextual Linking" technique
- Breaks input into chunks (default: 8 chunks, min 600 chars each)
- Maintains context between chunks
- Smart speaker alternation to avoid repetition
- Configurable via `max_num_chunks`, `min_chunk_size`

### TTS Providers
- **OpenAI**: tts-1-hd model, 25MB max per request
- **ElevenLabs**: eleven_multilingual_v2, premium quality
- **Gemini Multi-speaker**: en-US-Studio-MultiSpeaker, natural conversations
- **Edge TTS**: Free, no API key, 150+ language variants

### Content Extraction
- **Websites**: BeautifulSoup, 10-second timeout, configurable patterns
- **YouTube**: Transcript API, removes music tags
- **PDF**: PyMuPDF (10x faster than pypdf), Unicode normalization
- **Topics**: Google Gemini with real-time web search (Search Retrieval)

### LLM Configuration
- Temperature: 0.7 (creativity)
- Frequency penalty: 0.75 (avoid repetition)
- Presence penalty: 0.75 (encourage diversity)
- Output format: XML-style `<Person1>...</Person1><Person2>...</Person2>`

## Project Structure

```
podcastfy/
├── client.py                   # Main orchestrator
├── content_generator.py        # LLM-based generation
├── text_to_speech.py          # TTS orchestration
├── config.yaml                 # Extraction config
├── conversation_config.yaml    # Conversation config
├── content_parser/            # Multi-source extraction
│   ├── content_extractor.py
│   ├── website_extractor.py
│   ├── youtube_transcriber.py
│   └── pdf_extractor.py
├── tts/                       # TTS abstraction
│   ├── base.py
│   ├── factory.py
│   └── providers/
│       ├── openai.py
│       ├── elevenlabs.py
│       ├── edge.py
│       ├── gemini.py
│       └── geminimulti.py
├── utils/                     # Config & logging
│   ├── config.py
│   ├── config_conversation.py
│   └── logger.py
└── api/
    └── fast_app.py           # FastAPI endpoints

tests/                         # Test suite (7 modules)
├── test_client.py
├── test_content_parser.py
├── test_genai_podcast.py
├── test_audio.py
├── test_api.py
└── test_generate_podcast.py

docs/                          # Sphinx documentation
└── source/

usage/                         # User guides (11 .md files)
├── cli.md
├── config.md
├── conversation_custom.md
├── api.md
├── local_llm.md
└── ...

data/                          # Runtime data
├── audio/                     # Generated podcasts
├── transcripts/              # Generated transcripts
├── images/                    # Test images
└── urls/                      # Test URL collections
```

## Key Dependencies

**LLM/AI:**
- langchain (0.3.3), langchain-google-genai, langchain-google-vertexai
- litellm (1.52.0) - Multi-LLM abstraction
- google-generativeai (0.8.2)

**TTS:**
- openai (1.51.0), elevenlabs (1.9.0), edge-tts (6.1.12)
- google-cloud-texttospeech (2.21.0)

**Content Processing:**
- beautifulsoup4 (4.12.3), PyMuPDF (1.24.11)
- youtube-transcript-api (0.6.2)
- pydub (0.25.1), ffmpeg (1.4)

**Framework:**
- typer (0.12.5) - CLI
- pyyaml (6.0.2), python-dotenv (1.0.1)

**Testing:**
- pytest (8.3.3), pytest-xdist (3.6.1)

**Docs:**
- sphinx (8.0.2+), sphinx-rtd-theme (3.0.1)
- nbsphinx (0.9.5), pandoc (2.4)

## Common Pitfalls

1. **Missing ffmpeg**: Audio processing requires ffmpeg system package
2. **API key issues**: Ensure `.env` file is in project root
3. **TTS limits**: OpenAI has 25MB limit per request, may need chunking
4. **Tabs vs spaces**: This project uses tabs for indentation
5. **Requirements sync**: Always export requirements.txt after poetry changes
6. **Long content**: Use `--longform` flag for content >10 minutes
7. **Local LLM**: Requires Llamafile setup, see usage/local_llm.md

## Documentation Resources

- **API Docs**: https://podcastfy.readthedocs.io/
- **User Guides**: `/usage/*.md` (11 comprehensive guides)
- **Examples**: `podcastfy.ipynb` (Jupyter notebook)
- **README**: Main project overview
- **GUIDELINES**: Contribution process
- **CHANGELOG**: Version history and features
