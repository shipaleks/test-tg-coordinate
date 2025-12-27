# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bot Voyage** (nearby-fact-bot) is a sophisticated Telegram bot that provides location-based facts using OpenAI's GPT-5.1 model with web search verification. It supports both static location queries and real-time live location tracking with multi-language support (5 languages).

**Version**: 1.3.2
**Python**: 3.12
**Main Dependencies**: python-telegram-bot 21.7, openai 1.99.2

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

**Bot Voyage** provides location-based facts using OpenAI's GPT-5.1 model (with GPT-5.1-mini fallback). The architecture supports:
- Static location queries with immediate response
- Live location tracking with configurable intervals (5/10/30/60 minutes)
- Multi-language support (Russian, English, French, Portuguese-Brazil, Ukrainian)
- Multiple database backends (SQLite, PostgreSQL, Firestore)
- Telegram Stars payment system for premium features

### Key Modules

#### `src/main.py` (570 lines)
**Entry point and bot configuration**
- Command handlers: `/start`, `/donate`, `/live`, `/stats`, `/reason`, `/debuguser`, `/reset`
- Webhook vs polling mode switching based on `WEBHOOK_URL` environment variable
- Localized welcome messages and keyboard interfaces
- PostgreSQL auto-migration on startup (if `DATABASE_URL` set)
- Health check endpoints (`/`, `/health`, `/healthz`) for Railway/Koyeb
- Language selection flow for new users

#### `src/handlers/location.py` (650+ lines)
**Core location processing and fact delivery**
- **Static locations**: Immediate fact generation with GPT-5.1
- **Live locations**: Interval selection flow → background fact delivery with numbering
- Duplicate prevention across sessions
- Media group implementation for Wikipedia images (up to 4 images)
- Localized response formatting for all 5 languages
- Venue/location sharing for navigation integration
- Error handling for missing POIs

#### `src/handlers/donations.py`
**Telegram Stars payment integration**
- `/donate` command with preset amounts (10⭐, 50⭐, 100⭐)
- Pre-checkout validation and payment success handling
- Premium user status tracking (25-year duration per star)
- Multi-language payment UI
- Donor statistics commands (`/stats`, `/dbtest`)

#### `src/handlers/language_selection.py`
**Multi-language support system**
- Language selection keyboard (Russian, English, French, Portuguese-Brazil, Ukrainian)
- Custom language input handling
- `/reset` command for language reset
- Hidden `/reason` command for debugging (reasoning levels + model selection)
- User preference persistence across sessions

#### `src/services/live_location_tracker.py` (949 lines)
**Real-time location session management**
- **Session management**: `LiveLocationData` dataclass with fact counter, coordinates, last_update
- **Background tasks**: Asyncio-based fact delivery at configurable intervals (5, 10, 30, 60 minutes)
- **Coordinate updates**: Real-time location tracking via edited messages
- **Fact numbering**: Sequential numbering ("Факт #1", "Факт #2")
- **Silence threshold**: Prevents spam during fast movements
- **Duplicate detection**: Prevents repeating places within same session
- **Session cleanup**: Automatic termination when live sharing stops/expires
- Thread-safe session storage with asyncio locks

#### `src/services/openai_client.py` (2304 lines - Core AI Engine)
**Comprehensive AI fact generation with verification**
- **Model system**: GPT-5.1 for all facts (static + live) with GPT-5.1-mini fallback
- **Web search verification**: At least 2 searches per fact for accuracy
- **Multi-tier coordinate lookup**:
  1. Direct parsing from model response
  2. WebSearch with GPT-5.1 for precise coordinates
  3. Nominatim geocoding service (OSM) as fallback
- **StaticLocationHistory class**: Coordinate-based caching (3 decimal places ~111m precision)
  - In-memory cache with 24-hour TTL
  - Max 1000 entries with automatic cleanup
  - Anti-repetition: sends previous facts to AI
- **Wikipedia integration**: Legacy API (`w/api.php`) for image search
- **Reasoning levels**: none/low/medium/high (configurable per user)
- **Multi-language prompts**: Supports all 5 languages
- Atlas Obscura-inspired fact quality (novel, verified, interesting)
- Structured response format: Location + Coordinates + Fact
- Distance preferences: <400m ideal, <800m good, <1200m max

#### `src/services/async_donors_wrapper.py` (216 lines)
**Database abstraction layer - unified interface for 3 backends**
- Auto-detects and switches between: Firestore → PostgreSQL → SQLite
- Async-first design for all database operations
- Methods: `add_donation()`, `is_premium_user()`, `get_donor_info()`
- User preferences: `get/set_user_language()`, `get/set_user_reasoning()`, `get/set_user_model()`
- Auto-upgrade: donors from reasoning='none' → 'low'
- Legacy model mapping: gpt-5 → gpt-5.1

#### `src/services/donors_db.py` (658 lines)
**SQLite database for local/Railway deployment**
- Tables: donors, donations, user_preferences
- Railway volume auto-detection (`/data` mount path)
- Fallback chain: Railway volume → /tmp → local directory
- Payment ID deduplication
- Premium status calculation (expires > current_time)
- Thread-safe operations

#### `src/services/postgres_db.py` (351 lines)
**PostgreSQL production database**
- Connection pool: asyncpg (min_size=1, max_size=10)
- Same schema as SQLite with indexes
- Automatic migration on initialization
- Full async support

#### `src/services/firebase_db.py` (258 lines)
**Firestore document storage (GCP-native)**
- Collections: `users/{user_id}`, `donations/{payment_id}`
- Batch operations for atomic updates
- Premium status tracking
- User preferences storage

#### `src/services/firebase_stats.py` (110 lines)
**Firebase analytics integration**
- `increment_fact_counters()` - Track fact generation
- `record_movement()` - Track user movement
- `get_stats_for_user()` - User-specific analytics
- `get_global_stats()` - Global metrics

#### `src/services/image_search.py` (395 lines)
**Wikipedia image retrieval**
- Legacy API integration (`w/api.php`)
- Multi-fallback strategy
- Relevance scoring
- Thumbnail/full-size support

#### `src/services/yandex_image_search.py` (675 lines)
**Alternative image search implementation**
- Yandex image search API
- Fallback when Wikipedia fails
- Supports Russian queries

#### `src/utils/formatting_utils.py`
**Text processing utilities**
- `extract_sources_from_answer()` - Parse Sources/Источники sections
- `strip_sources_section()` - Remove trailing sources
- `sanitize_url()` - Telegram Markdown-safe URLs
- `escape_html()` - HTML entity escaping
- `is_duplicate_place()` - Location deduplication logic

### Data Flow

1. **Static Location**: User shares location → language check → GPT-5.1 analysis with web search → fact response with images → venue/location for navigation
2. **Live Location**: User shares live location → interval selection (5/10/30/60 min) → initial fact → background loop with numbered facts → duplicate prevention → venue/location → session cleanup on stop/expire
3. **Donations**: `/donate` command → amount selection → Telegram Stars payment → pre-checkout validation → payment success → premium status (25 years per star)
4. **Language Selection**: New user → `/start` → language keyboard → preference saved → localized experience
5. **Reasoning/Model**: Premium user → `/reason` → level selection (none/low/medium/high) + model (GPT-5.1/5.1-mini) → preferences saved

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

### Telegram Stars Donation System

- **Payment Processing**: Full Telegram Stars integration with pre-checkout validation
- **Premium Benefits**: Advanced reasoning levels + model selection for enhanced analysis
- **Duration**: 1 star = 25 years premium (effectively permanent, stackable)
- **Database**: Multi-backend support (SQLite/PostgreSQL/Firestore)
- **Commands**: `/donate` with 10⭐, 50⭐, 100⭐ preset options + custom amounts
- **Security**: Payment ID deduplication and user validation
- **Multi-language**: Payment UI localized in all 5 languages

### Tech Stack

**Core Framework & Language**
- **Python 3.12** with async/await throughout
- **python-telegram-bot 21.7** - Bot framework with webhook support
- **AsyncIO** - Concurrent live location processing

**AI & Search**
- **OpenAI API (1.99.2)** - GPT-5.1 for all facts, GPT-5.1-mini fallback
- **Web Search Integration** - At least 2 searches per fact for verification
- **Reasoning Levels** - none/low/medium/high (user-configurable)

**Database Backends** (Auto-switchable)
- **SQLite** - Local/Railway deployment with volume persistence
- **PostgreSQL (asyncpg)** - Production with connection pooling
- **Firestore (firebase-admin)** - GCP-native with analytics

**External APIs**
- **Telegram Stars** - Payment system for premium features
- **Nominatim (OSM)** - Geocoding service as coordinate fallback
- **Wikipedia Legacy API** - Image search (`w/api.php`)
- **Yandex Images** - Alternative image source
- **aiohttp 3.10.11** - Async HTTP client

**Development & Deployment**
- **Railway/Koyeb** - Production deployment with auto-scaling
- **Docker** - Containerized deployment
- **GitHub Actions** - CI/CD pipeline (lint → format → test → deploy)
- **pytest + pytest-anyio** - Async testing with mocks
- **ruff + black** - Linting and code formatting

**Utilities**
- **asyncio-throttle** - Rate limiting for concurrent requests
- **python-dotenv** - Environment variable management
- **sqlalchemy 2.0.36** - ORM with async support

### Testing Structure

**Test Files** (7 files, 1719+ lines total)
- `test_openai_client.py` (502 lines) - Fact generation, coordinate extraction, image search, caching
- `test_location_handler.py` (393 lines) - Static/live location flows, media groups, formatting
- `test_live_location_tracker.py` (308 lines) - Session management, fact delivery, cleanup
- `test_live_location_expiry.py` (156 lines) - Session timeout, expiry handling
- `test_live_location_silence.py` (137 lines) - Silence threshold, spam prevention
- `test_main.py` (117 lines) - Command handlers, welcome messages
- `test_fact_accuracy_prompts.py` (105 lines) - Prompt quality and accuracy

**Testing Approach**
- AsyncIO testing with pytest-anyio
- Mock external APIs (Telegram, OpenAI, Firebase)
- Session management verification
- Error handling scenarios
- Duplicate prevention logic

### Environment Variables

**Required**
- `TELEGRAM_BOT_TOKEN` - Bot token from @BotFather
- `OPENAI_API_KEY` - OpenAI API key for GPT-5.1

**Optional - Deployment**
- `WEBHOOK_URL` - Public URL for production (triggers webhook mode)
- `PORT` - Server port for webhook mode (default: 8000)

**Optional - Database**
- `DATABASE_URL` - PostgreSQL connection string (format: `postgresql://user:pass@host:port/db`)
- `USE_FIRESTORE_DB` - Set to "true" to use Firestore backend
- `RAILWAY_VOLUME_MOUNT_PATH` - Custom volume path (auto-detected as `/data` on Railway)

**Optional - Features**
- `RESET_LANG_ON_DEPLOY` - Reset all user languages on deploy (for testing)
- `HOWTO_STEP1_FILE_ID` - Cached Telegram file ID for step 1 image
- `HOWTO_STEP2_FILE_ID` - Cached Telegram file ID for step 2 image
- `HOWTO_STEP3_FILE_ID` - Cached Telegram file ID for step 3 image

### Railway Deployment Setup

#### SQLite Persistence Configuration
1. **Create Volume in Railway Dashboard:**
   - Go to your project → Volumes
   - Create new volume with mount path: `/data`
   - Name: `donors-db` (or any descriptive name)

2. **Volume Auto-Detection:**
   - Code automatically detects `/data` volume availability
   - Falls back to local storage for development
   - Database file: `/data/donors.db` (production) or `donors.db` (local)

#### Volume Benefits
- **Persistent Storage**: Donor data survives deployments and restarts
- **Zero Configuration**: Auto-detection handles production vs development
- **Scalable**: SQLite with proper indexing handles concurrent access

## Database Schema

### SQLite / PostgreSQL Tables

```sql
-- Donors (premium users)
CREATE TABLE donors (
  user_id BIGINT PRIMARY KEY,
  telegram_username TEXT,
  first_name TEXT,
  total_stars INTEGER DEFAULT 0,
  first_donation_date BIGINT,  -- Unix timestamp
  last_donation_date BIGINT,   -- Unix timestamp
  premium_expires BIGINT,      -- Unix timestamp
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Donations (payment records)
CREATE TABLE donations (
  id SERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES donors(user_id),
  payment_id TEXT UNIQUE,      -- Telegram payment ID (deduplication)
  stars_amount INTEGER,
  payment_date BIGINT,         -- Unix timestamp
  invoice_payload TEXT
);

-- User Preferences
CREATE TABLE user_preferences (
  user_id BIGINT PRIMARY KEY,
  language TEXT DEFAULT 'ru',         -- en, ru, fr, pt, uk
  reasoning TEXT DEFAULT 'none',      -- none, low, medium, high
  model TEXT DEFAULT 'gpt-5.1',       -- gpt-5.1, gpt-5.1-mini
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Firestore Collections

**users/{user_id}** - User profiles
```json
{
  "telegram_username": "string",
  "first_name": "string",
  "total_stars": 0,
  "first_donation_date": "timestamp",
  "last_donation_date": "timestamp",
  "premium_expires": "timestamp",
  "language": "ru",
  "reasoning": "none",
  "model": "gpt-5.1"
}
```

**donations/{payment_id}** - Payment records
```json
{
  "user_id": 123456789,
  "stars_amount": 10,
  "payment_date": "timestamp",
  "invoice_payload": "string"
}
```

**metrics/counters** - Global statistics
```json
{
  "total_facts": 0,
  "total_movements": 0
}
```

### In-Memory Cache (OpenAI Client)

**StaticLocationHistory** - Location-to-facts mapping
- **Key**: Coordinates rounded to 3 decimal places (~111m precision)
- **Value**: List of previously generated facts for that location
- **TTL**: 24 hours
- **Max entries**: 1000 (automatic cleanup of oldest)
- **Purpose**: Prevent repetition within 24-hour window

## CI/CD Pipeline

### GitHub Actions Workflow (`.github/workflows/ci.yml`)

**Triggers**
- Push to `main` or `develop` branches
- Pull requests targeting `main`

**Jobs**

1. **Test Job** (Matrix: Python 3.11, 3.12)
   ```yaml
   steps:
     - Checkout code
     - Setup Python
     - Install dependencies: pip install -e ".[dev]"
     - Lint: ruff check src/ tests/
     - Format check: black --check src/ tests/
     - Test: pytest tests/ -v (with OPENAI_API_KEY=test-key)
   ```

2. **Deploy Job** (Conditional: main branch + push only)
   ```yaml
   depends_on: test
   steps:
     - Install Railway CLI
     - Deploy: railway deploy --service nearby-fact-bot
     - Requires: RAILWAY_TOKEN secret
   ```

**Pipeline Flow**: Code → Lint → Format → Test → Deploy (main only)

## Deployment Architectures

### Local Development
```bash
# Setup
unset WEBHOOK_URL
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and OPENAI_API_KEY

# Run
python -m src.main
```
- **Mode**: Polling (no webhook)
- **Database**: SQLite (donors.db)
- **Port**: Not required

### Railway Deployment
```bash
# One-time setup
railway login
railway link
railway volume create --mount /data

# Environment variables (set in Railway dashboard)
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
WEBHOOK_URL=https://your-app.railway.app
PORT=8000
```
- **Mode**: Webhook
- **Database**: SQLite with volume persistence (`/data/donors.db`)
- **Auto-deploy**: GitHub push to main → CI → Railway deploy

### PostgreSQL Production
```bash
# Additional environment variable
DATABASE_URL=postgresql://user:pass@host:port/db
```
- **Mode**: Webhook
- **Database**: PostgreSQL with connection pooling
- **Migration**: Auto-runs on startup
- **Scaling**: Supports multiple instances

### Firestore/GCP Deployment
```bash
# Additional environment variables
USE_FIRESTORE_DB=true
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```
- **Mode**: Webhook
- **Database**: Firestore with Firebase Analytics
- **Scaling**: Serverless auto-scaling
- **Platform**: Cloud Run, GCP App Engine, or any Docker host

## Multi-Language Support

### Supported Languages
1. **Russian (ru)** - Default, primary language
2. **English (en)** - Full translation
3. **French (fr)** - Full translation
4. **Portuguese-Brazil (pt)** - Full translation
5. **Ukrainian (uk)** - Full translation

### Localization System

**Message Dictionaries** (in handlers)
```python
MESSAGES = {
    'welcome': {
        'ru': "Привет! 👋",
        'en': "Hello! 👋",
        'fr': "Bonjour! 👋",
        ...
    }
}
```

**Helper Functions**
- `get_message(key, lang)` - Retrieve localized message
- Language detection from user preferences
- Fallback to Russian if language not set

**User Preferences**
- Set via language selection keyboard on `/start`
- Persisted in database (user_preferences table)
- Can be reset with `/reset` command

## Code Patterns & Best Practices

### Architectural Patterns

**1. Async-First Design**
- All I/O operations use async/await
- AsyncOpenAI for AI calls
- Asyncio task management for background jobs
- Async database operations across all backends

**2. Database Abstraction**
```python
# AsyncDonorsWrapper provides unified interface
db = await get_db()  # Auto-detects backend
await db.add_donation(...)
await db.is_premium_user(...)
```
- Easy switching between SQLite/PostgreSQL/Firestore
- No tight coupling to specific backend
- Graceful fallbacks

**3. Session Management**
```python
# Thread-safe live location sessions
live_sessions[user_id] = LiveLocationData(
    user_id=user_id,
    fact_count=1,
    coordinates=(lat, lon),
    ...
)
```
- Thread-safe session storage
- Automatic cleanup on session end
- Duplicate detection within sessions

**4. Error Handling Strategy**
- Graceful degradation (fallbacks for missing data)
- User-friendly error messages in all languages
- Comprehensive logging with context
- Never expose internal errors to users

**5. Caching & Anti-Repetition**
```python
# StaticLocationHistory prevents repetition
history = StaticLocationHistory(ttl_hours=24, max_entries=1000)
previous_facts = history.get_facts(lat, lon)
# Send previous_facts to AI with "find different place" instruction
```

### Code Organization

**Module Responsibilities**
- `handlers/` - Telegram message handling, user interaction
- `services/` - Business logic, external API integration
- `utils/` - Shared utilities, formatting helpers

**Naming Conventions**
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case()`
- Constants: `UPPER_SNAKE_CASE`

**Import Order**
1. Standard library
2. Third-party packages
3. Local modules

### Testing Guidelines

**Mock External APIs**
```python
@pytest.mark.anyio
async def test_generate_fact(mock_openai):
    mock_openai.return_value = "Interesting fact"
    result = await generate_location_fact(...)
    assert "Interesting fact" in result
```

**Test Session Management**
```python
async def test_live_location_cleanup():
    # Test automatic cleanup on session end
    await start_live_location(...)
    await stop_live_location(...)
    assert user_id not in live_sessions
```

## Key Features & Implementation Details

### Duplicate Prevention

**Live Sessions**
```python
# Track places mentioned in current session
session.mentioned_places = ["Eiffel Tower", "Louvre"]
# Skip if new fact mentions same place
if is_duplicate_place(new_fact, session.mentioned_places):
    continue  # Generate different fact
```

**Static Locations** (24-hour cache)
```python
# Check history for this coordinate
previous_facts = history.get_facts(lat, lon)
# Include in prompt: "These places already mentioned: ..."
prompt += f"Previous facts: {previous_facts}"
```

### Silence Threshold (Live Locations)

**Purpose**: Prevent spam during fast movements (e.g., in car/train)

**Implementation**
```python
MIN_SILENCE_SECONDS = 300  # 5 minutes
if time_since_last_fact < MIN_SILENCE_SECONDS:
    return  # Skip fact generation
```

**User Experience**: Facts only delivered when user stays in area long enough

### Multi-Tier Coordinate Lookup

**Tier 1: Direct Parsing**
```python
# Extract from AI response
match = re.search(r'(\d+\.\d+),\s*(\d+\.\d+)', response)
```

**Tier 2: Web Search + GPT-5.1**
```python
# Ask GPT-5.1 with web search
"Find exact coordinates for: [place name]"
```

**Tier 3: Nominatim Geocoding**
```python
# Fallback to OSM geocoding API
url = f"https://nominatim.openstreetmap.org/search?q={place_name}&format=json"
```

### Media Groups (Up to 4 Images)

**Implementation**
```python
media_group = [
    InputMediaPhoto(media=img1, caption=fact),
    InputMediaPhoto(media=img2),
    InputMediaPhoto(media=img3),
    InputMediaPhoto(media=img4),
]
await context.bot.send_media_group(chat_id, media_group)
```

**Fallback**: If <4 images, send available ones. If 0 images, send text-only.

## Command Reference

### User Commands
- `/start` - Welcome message + language selection (for new users)
- `/donate` - Telegram Stars donation with preset amounts
- `/live` - How-to guide for live location (3 steps with images)
- `/reset` - Reset language preference

### Premium User Commands
- `/reason` - Set reasoning level (none/low/medium/high) + model selection
- `/stats` - View donation statistics and premium status

### Admin/Debug Commands
- `/debuguser` - Show user info (ID, language, premium status)

## Recent Changes & Patterns

**Latest Improvements** (from commit history)
1. **Silence threshold increase** - Prevent spam during fast movements
2. **Token security** - Secure token handling in CI/CD
3. **Session timeout fixes** - Prevent timeouts during long fact generation
4. **Duplicate prevention** - Avoid repeating places in live sessions
5. **GPT-5.1 standardization** - Unified model across all fact types

**Common Patterns**
- Focus on live location reliability (timeouts, silence, duplicates)
- UX refinements (button text, onboarding clarity)
- Multi-language consistency across all features
- Database backend flexibility

## Development Workflow

### Making Changes

1. **Create feature branch**
   ```bash
   git checkout -b feature/description
   ```

2. **Make changes** following code patterns above

3. **Run tests locally**
   ```bash
   pytest tests/ -v
   ruff check src/ tests/
   black src/ tests/
   ```

4. **Commit & push**
   ```bash
   git add .
   git commit -m "feat: description"
   git push origin feature/description
   ```

5. **Create PR** - CI will run automatically

### Testing Locally

**With real Telegram bot**
```bash
# .env file
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_key

# Run
python -m src.main
```

**With pytest**
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_openai_client.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Troubleshooting

### Common Issues

**Bot not responding**
- Check `TELEGRAM_BOT_TOKEN` is set correctly
- Verify network connectivity
- Check logs for errors

**Database errors**
- SQLite: Check file permissions and volume mount
- PostgreSQL: Verify `DATABASE_URL` format
- Firestore: Check service account credentials

**Live location not working**
- Check user shared live location (not static)
- Verify interval selection completed
- Check logs for session creation

**Facts not generating**
- Verify `OPENAI_API_KEY` is valid
- Check OpenAI API quota/limits
- Review logs for API errors

**Images not appearing**
- Wikipedia API may be rate-limited
- Check image URLs are valid
- Verify Telegram media group limits (max 10)