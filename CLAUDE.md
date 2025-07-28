# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Essential Commands
- **Run tests**: `python -m pytest tests/ -v`
- **Run specific test**: `python -m pytest tests/test_<module>.py -v`
- **Lint code**: `ruff check src/ tests/`
- **Format code**: `black src/ tests/`
- **Run bot locally**: `python -m src.main` (requires .env with TELEGRAM_BOT_TOKEN and OPENAI_API_KEY)

### Development Setup
```bash
# Local development (polling mode)
unset WEBHOOK_URL
python -m src.main

# Production uses webhook mode when WEBHOOK_URL is set
```

## Architecture Overview

### Core Components

**NearbyFactBot** is a Telegram bot that provides location-based facts using OpenAI o4-mini model. The architecture supports both static location queries and live location tracking.

### Key Modules

#### `src/main.py`
- Entry point and bot configuration
- Command handlers for `/start` and info commands
- Webhook vs polling mode switching based on `WEBHOOK_URL` environment variable
- Simplified keyboard interface with location sharing button

#### `src/handlers/location.py`
- **Static locations**: Immediate fact generation and response
- **Live locations**: Interval selection flow → background fact delivery
- Location parsing and response formatting
- Integration with OpenAI and live tracking services
- Media group implementation for Wikipedia images

#### `src/services/live_location_tracker.py`
- **Session management**: `LiveLocationData` dataclass with fact counter
- **Background tasks**: Asyncio-based fact delivery at configurable intervals (5, 10, 30, 60 minutes)
- **Coordinate updates**: Real-time location tracking via edited messages
- **Fact numbering**: Sequential numbering ("Факт #1", "Факт #2") replacing "Начальный факт"
- **Session cleanup**: Automatic termination when live sharing stops

#### `src/services/openai_client.py`
- **Dual model system**: o4-mini for detailed facts (live), GPT-4.1 for quick responses (static)
- **Enhanced coordinate accuracy**: Multi-tier coordinate lookup system:
  1. Direct parsing from model response
  2. WebSearch with GPT-4.1 for precise coordinates
  3. Nominatim geocoding service as fallback
- **Static location history**: `StaticLocationHistory` class with coordinate-based caching (3 decimal places ~111m)
- **Wikipedia integration**: Legacy API for image search with fallback strategies
- Step-by-step reasoning prompts optimized for thorough location analysis
- Russian-language prompts with structured thinking process
- Structured response parsing (Location + Coordinates + Fact format)
- Atlas Obscura-inspired fact quality standards
- Error handling and logging

### Data Flow

1. **Static Location**: User shares location → immediate o4-mini analysis → fact response → venue/location for navigation
2. **Live Location**: User shares live location → interval selection → initial fact → background loop with numbered facts every N minutes → each fact includes venue/location → session cleanup on stop

### Live Location System

- **Fact Numbering**: Each session maintains `fact_count` starting from 1
- **Session Tracking**: Thread-safe dictionary of active sessions with asyncio locks
- **Background Processing**: Independent asyncio tasks per user session
- **Coordinate Updates**: Real-time position updates via Telegram's edited_message events
- **Graceful Shutdown**: Automatic cleanup when live location sharing expires or stops

### Static Location History System

- **Coordinate-based caching**: Uses rounded coordinates (3 decimal places) as cache key
- **In-memory storage**: `StaticLocationHistory` class with TTL (24 hours default)
- **Anti-repetition**: Sends previous facts to AI with instruction to find different places
- **Automatic cleanup**: Removes expired entries and limits cache size (1000 entries max)

### Tech Stack
- **Python 3.12** with python-telegram-bot 21.7
- **OpenAI dual models**: o4-mini for detailed facts + GPT-4.1 with WebSearch for coordinates
- **Navigation**: Telegram venue/location sharing with automatic route building
- **Geocoding**: Nominatim OSM service as coordinate fallback
- **Wikipedia**: Legacy API (`w/api.php`) for image search
- **AsyncIO** for concurrent live location processing
- **aiohttp** for external API calls
- **Railway** deployment with GitHub Actions CI/CD
- **pytest** with AsyncMock for testing
- **ruff + black** for linting and formatting

### Testing Structure
- Comprehensive test coverage with 13 tests
- Mock-based testing for external API calls (Telegram, OpenAI)
- Session management and background task testing
- Location parsing and response formatting tests

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Required for bot operation
- `OPENAI_API_KEY`: Required for fact generation
- `WEBHOOK_URL`: Optional, switches to webhook mode for production
- `PORT`: Optional, defaults to 8000 for webhook mode