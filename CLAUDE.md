# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bot Voyage** (nearby-fact-bot) is a Telegram bot that provides location-based facts using **Anthropic Claude** (Opus 4.6 / Sonnet 4.5 / Haiku 4.5) with Brave Search web verification. It supports both static location queries and real-time live location tracking with multi-language support.

**Version**: 2.0.0
**Python**: 3.12 (minimum 3.11)
**Main Dependencies**: python-telegram-bot 21.7, anthropic 0.50+, httpx 0.27+, aiohttp 3.10.11

## Development Commands

### Essential Commands
- **Run tests**: `python -m pytest tests/ -v`
- **Run specific test**: `python -m pytest tests/test_<module>.py -v`
- **Lint code**: `ruff check src/ tests/`
- **Format code**: `black src/ tests/`
- **Run bot locally**: `python -m src.main` (requires .env with TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, and BRAVE_API_KEY)

### Development Setup
```bash
# Install dependencies
pip install -e ".[dev]"

# Local development (polling mode)
unset WEBHOOK_URL
python -m src.main

# Production uses webhook mode when WEBHOOK_URL is set
```

## Architecture Overview

### Core Components

The architecture supports:
- Static location queries with immediate response
- Live location tracking with configurable intervals (5/10/30/60 minutes)
- Multi-language support (Russian, English, French, Portuguese-Brazil, Ukrainian)
- Multiple database backends (SQLite, PostgreSQL, Firestore)
- Telegram Stars payment system for premium features
- Configurable AI reasoning levels (none/low/medium/high)
- Three Claude models: Opus 4.6 (adaptive thinking), Sonnet 4.5, Haiku 4.5

### Project Structure

```
src/
  __init__.py
  main.py                              # Entry point, bot configuration (615 lines)
  handlers/
    __init__.py
    location.py                        # Location processing, fact delivery (1049 lines)
    donations.py                       # Telegram Stars payments (643 lines)
    language_selection.py              # Language + reasoning/model selection (419 lines)
  services/
    __init__.py
    claude_client.py                   # Core AI engine - Claude API (1758 lines)
    live_location_tracker.py           # Real-time session management (1272 lines)
    web_search.py                      # Brave Search + Yandex fallback (250 lines)
    async_donors_wrapper.py            # Database abstraction layer (233 lines)
    donors_db.py                       # SQLite backend (806 lines)
    postgres_db.py                     # PostgreSQL backend (398 lines)
    firebase_db.py                     # Firestore backend (264 lines)
    firebase_stats.py                  # Firebase analytics (128 lines)
    firebase_client.py                 # Firestore client init (48 lines)
    image_search.py                    # Wikipedia image retrieval (467 lines)
    yandex_image_search.py             # Yandex image search (739 lines)
    yandex_web_search.py               # Yandex web search fallback (227 lines)
    openai_client.py                   # Legacy OpenAI client (2766 lines, unused)
    env_db.py                          # Environment-based DB config (148 lines)
    postgres_wrapper.py                # PostgreSQL wrapper utilities (162 lines)
  utils/
    __init__.py
    formatting_utils.py                # Text processing, dedup logic (333 lines)
    migrate_to_postgres.py             # SQLite -> PostgreSQL migration (147 lines)
tests/
  __init__.py
  test_claude_client.py                # AI client tests (496 lines)
  test_location_handler.py             # Location handler tests (402 lines)
  test_live_location_tracker.py        # Session management tests (306 lines)
  test_live_location_expiry.py         # Session expiry tests (165 lines)
  test_live_location_silence.py        # Silence threshold tests (144 lines)
  test_main.py                         # Command handler tests (122 lines)
  test_fact_accuracy_prompts.py        # Prompt quality tests (161 lines)
docs/                                  # Documentation, images, videos
.github/workflows/ci.yml              # CI/CD pipeline
```

**Total**: ~12,800 lines source code, ~1,800 lines tests

### Key Modules

#### `src/main.py` (615 lines)
**Entry point and bot configuration**
- Command handlers: `/start`, `/donate`, `/live`, `/stats`, `/dbtest`, `/reason`, `/debuguser`, `/reset`
- Webhook vs polling mode switching based on `WEBHOOK_URL` environment variable
- Localized welcome messages (Russian, English, French) with keyboard interfaces
- PostgreSQL auto-migration on startup (if `DATABASE_URL` set)
- Health check server on port+1 (`/`, `/health`, `/healthz`) for Railway/Koyeb
- Language selection flow for new users
- Live session reset on `/start` (safety measure)
- Optional language reset on deploy (`RESET_LANG_ON_DEPLOY`)

#### `src/handlers/location.py` (1049 lines)
**Core location processing and fact delivery**
- **Static locations**: Immediate fact generation with Claude
- **Live locations**: Interval selection flow (5/10/30/60 min) -> background fact delivery with numbering
- Response parsing: `<answer>` tag format with Location/Coordinates/Search/Interesting fact
- Legacy format fallback: "Location:" / "Interesting fact:" prefixes
- Source extraction (max 4 sources per fact)
- Media group sending with smart truncation (1024 char Telegram limit)
- Multi-fallback image strategy: media group -> 2 images -> text only -> individual images
- Venue/location sharing for navigation integration
- Localized messages for Russian, English, French
- `[[NO_POI_FOUND]]` handling with user-friendly error messages

#### `src/handlers/donations.py` (643 lines)
**Telegram Stars payment integration**
- `/donate` command with preset amounts: 100, 250, 500 (main), 50, 150, 1000, 2000 (extended)
- Pre-checkout validation with idempotency checks (payload, user_id, amount)
- Payment success handling with premium status update
- Premium duration: 1 star = 25 years (effectively permanent, stackable)
- `/stats` command: user facts, global facts, total users
- `/dbtest` command: database diagnostics
- Multi-language payment UI (Russian, English, French)
- XTR currency (Telegram Stars), empty provider_token

#### `src/handlers/language_selection.py` (419 lines)
**Multi-language support and premium settings**
- Language selection keyboard: Russian, English, French, Portuguese-Brazil, Ukrainian
- Custom language input (accepts codes like "es", "de" or names)
- `/reset` command for language reset
- Hidden `/reason` command for premium users:
  - Model selection: Claude Opus 4.6, Sonnet 4.5, Haiku 4.5
  - Reasoning levels: none/low/medium/high
  - Opus 4.6 uses adaptive thinking with effort parameter; older models use budget_tokens
  - Checkmarks for current selections
- User preference persistence in database

#### `src/services/claude_client.py` (1758 lines - Core AI Engine)
**AI fact generation with verification**
- **Models**:
  - `MODEL_OPUS = "claude-opus-4-6"` (best quality, adaptive thinking)
  - `MODEL_SONNET = "claude-sonnet-4-5-20250929"` (default model)
  - `MODEL_HAIKU = "claude-haiku-4-5-20251001"` (fastest)
- **StaticLocationHistory** class: in-memory cache for anti-repetition
  - Coordinate-based keying (search keywords)
  - 24-hour TTL, max 1000 entries, auto-cleanup
  - Returns last 5 facts per location for context
- **System prompts**: Separate Russian and English prompt systems
  - Atlas Obscura style: hidden, forgotten, counterintuitive details
  - Strict fact verification against web search results
  - Source URL validation (only from search results, no invented URLs)
  - Distance rules: <400m preferred, <800m good, <1200m max
- **Web search integration**: Brave Search API via `WebSearchService`
  - Results formatted into prompts for verification
  - Fallback mode when search unavailable
- **Thinking/reasoning config**: Model-dependent thinking modes
  - **Opus 4.6**: Adaptive thinking (`thinking: {type: "adaptive"}`) with effort parameter via `output_config: {effort: "low"|"medium"|"high"}`
  - **Sonnet/Haiku 4.5**: Manual thinking (`thinking: {type: "enabled", budget_tokens: N}`) with defaults: low=1024, medium=2048, high=4096
  - Environment variable overrides for budget_tokens: `CLAUDE_THINKING_BUDGET_TOKENS_{LEVEL}`
  - Auto-fallback on thinking errors (strips thinking config and output_config)
- **Multi-tier coordinate lookup**:
  1. Direct parsing from `<answer>` response
  2. Nominatim geocoding (OSM) with smart fallbacks
- **Image pipeline**: Wikipedia/Wikimedia Commons with QID/P18 caching
  - Wikimedia entity lookup and file info extraction
  - Multiple search strategies with parallel async tasks
- **Response format** (structured):
  ```
  <answer>
  Location: [exact address/building]
  Coordinates: [LAT, LON - 6 decimal places]
  Search: [Nominatim query for geocoding]
  Interesting fact: [Atlas Obscura style fact]
  Sources:
  - [title] -- [URL from search results]
  </answer>
  ```
- Concurrency control: asyncio.Semaphore(3) for API requests

#### `src/services/live_location_tracker.py` (1272 lines)
**Real-time location session management**
- **LiveLocationData** dataclass:
  - `user_id`, `chat_id`, `latitude`, `longitude`, `last_update`
  - `live_period` (seconds), `fact_interval_minutes`
  - `session_start`, `fact_count` (sequential numbering)
  - `mentioned_places` (list for duplicate detection)
  - `task` (asyncio.Task for background loop)
- **LiveLocationTracker** (singleton):
  - `start_live_location()` - Create session, start background task
  - `stop_live_location()` - Cleanup session, cancel task
  - `update_live_location()` - Update coordinates from edited messages
  - `is_user_tracking()`, `get_active_sessions_count()`
- **Background fact loop**: `_fact_sending_loop()`
  - Periodic delivery at user-selected intervals
  - Silence threshold: 5 minutes minimum between facts
  - Session expiry detection (now - session_start > live_period)
  - Duplicate detection against `session.mentioned_places` (max 2 retries)
  - Fact numbering: "Fact #1", "Fact #2", etc.
- Image sending with media groups and fallbacks
- Thread-safe session storage with asyncio locks

#### `src/services/web_search.py` (250 lines)
**Brave Search API integration with Yandex fallback**
- `WebSearchService` class
- Brave Search API: 2000 queries/month free tier
- Methods: `search()`, `search_for_coordinates()`, `search_for_facts()`, `format_results_for_prompt()`
- Language-aware search queries with country filtering
- Yandex Web Search as automatic fallback on HTTP 429 (rate limit)
- Returns structured results: title, url, description, age

#### `src/services/async_donors_wrapper.py` (233 lines)
**Database abstraction layer - unified async interface for 3 backends**
- Auto-detects backend: Firestore (`USE_FIRESTORE_DB`) -> PostgreSQL (`DATABASE_URL`) -> SQLite (default)
- Async wrapper around sync SQLite operations
- Methods: `add_donation()`, `is_premium_user()`, `get_donor_info()`, `get_donation_history()`, `get_stats()`
- User preferences: `get/set_user_language()`, `get/set_user_reasoning()`, `get/set_user_model()`
- `has_language_set()`, `reset_user_language()`
- Auto-upgrade: donors from reasoning='none' -> 'low' (hidden bonus)
- Legacy model mapping: `gpt-5` -> `claude-opus-4-6`, `claude-opus-4-5-20251101` -> `claude-opus-4-6`
- Singleton pattern via `get_async_donors_db()`

#### `src/services/donors_db.py` (806 lines)
**SQLite database for local/Railway deployment**
- Tables: donors, donations, user_preferences
- Railway detection: checks `RAILWAY_ENVIRONMENT`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`, etc.
- Path selection: Railway volume (`/data`) -> custom `VOLUME_PATH` -> `/tmp` -> local directory
- Default language: `'en'`, default model: `'claude-sonnet-4-5-20250929'`, default reasoning: `'low'`
- Payment ID deduplication (UNIQUE constraint)
- Premium status: `premium_expires > current_time` (25 years per star)
- Thread-safe with `threading.Lock`
- Full CRUD for donors, donations, and user preferences

#### `src/services/postgres_db.py` (398 lines)
**PostgreSQL production database**
- Connection pool: asyncpg (min_size=1, max_size=10)
- Same schema as SQLite with indexes on user_id, payment_id
- Auto-migration on initialization
- Full async support for all operations

#### `src/services/firebase_db.py` (264 lines)
**Firestore document storage (GCP-native)**
- Collections: `users/{user_id}`, `donations/{payment_id}`
- Batch operations for atomic donation + user updates
- Premium status tracking
- User preferences storage (language, reasoning, model)
- `_reset_all_languages()` for bulk operations

#### `src/services/firebase_stats.py` (128 lines)
**Firebase analytics integration**
- `ensure_user(user_id, username, first_name)` - Create/update user document
- `increment_fact_counters(user_id, count)` - Track fact generation
- `record_movement(user_id, lat, lon)` - Track user movement
- `get_stats_for_user(user_id)` - User-specific analytics
- `get_global_stats()` - Global metrics (total_facts, total_movements)

#### `src/services/image_search.py` (467 lines)
**Wikipedia image retrieval**
- `ImageSearchEngine` class
- Multiple search strategies: entity extraction, source URL images, place name search, geo-search
- Image ranking by relevance
- Deduplication of results
- Async parallel search tasks
- Thumbnail and full-size support

#### `src/services/yandex_image_search.py` (739 lines)
**Alternative image search implementation**
- Yandex image search API
- Fallback when Wikipedia returns no results
- Russian language query support

#### `src/services/yandex_web_search.py` (227 lines)
**Yandex web search fallback**
- Used when Brave Search hits rate limits (HTTP 429)
- Same result format as Brave Search for compatibility

#### `src/utils/formatting_utils.py` (333 lines)
**Text processing utilities**
- `extract_sources_from_answer(answer_content)` - Parse Sources/Источники sections into [(title, url)]
- `strip_sources_section(text)` - Remove trailing sources block
- `sanitize_url(url)` - Telegram Markdown-safe URL escaping
- `escape_html(text)` - HTML entity escaping
- `label_to_html(label)` - Convert Markdown bold to HTML
- `extract_bare_links(text)` - Find domain URLs in text
- `remove_bare_links_from_text(text)` - Remove (example.com) patterns
- `normalize_place_name(place)` - Normalize for duplicate detection (removes prefixes, articles, punctuation)
- `extract_place_names_from_history(history_text)` - Parse places from session history
- `is_duplicate_place(new_place, mentioned_places)` - Fuzzy duplicate check with cross-language equivalents

#### `src/utils/migrate_to_postgres.py` (147 lines)
**SQLite to PostgreSQL migration**
- Auto-runs on startup when `DATABASE_URL` is set
- Migrates donors, donations, and user_preferences tables

### Data Flow

1. **Static Location**: User shares location -> language check -> Claude analysis with Brave Search verification -> fact response with Wikipedia images -> venue/location for navigation
2. **Live Location**: User shares live location -> interval selection (5/10/30/60 min) -> initial fact -> background loop with numbered facts -> duplicate prevention -> venue/location -> session cleanup on stop/expire
3. **Donations**: `/donate` command -> amount selection -> Telegram Stars invoice (XTR) -> pre-checkout validation -> payment success -> premium status (25 years per star)
4. **Language Selection**: New user -> `/start` -> language keyboard -> preference saved -> localized experience
5. **Reasoning/Model**: Premium user -> `/reason` -> level selection (none/low/medium/high) + model (Opus/Sonnet/Haiku) -> preferences saved

### Live Location System

- **Fact Numbering**: Each session maintains `fact_count` starting from 1
- **Session Tracking**: Thread-safe dictionary of active sessions with asyncio locks
- **Background Processing**: Independent asyncio tasks per user session
- **Coordinate Updates**: Real-time position updates via Telegram's edited_message events
- **Silence Threshold**: 5-minute minimum between facts (prevents spam during fast movement)
- **Duplicate Detection**: Tracks mentioned places per session, retries up to 2 times on duplicates
- **Graceful Shutdown**: Automatic cleanup when live location sharing expires or stops

### Static Location History System

- **Search keyword-based caching**: Uses search keywords as cache key
- **In-memory storage**: `StaticLocationHistory` class in `claude_client.py`
- **TTL**: 24 hours, max 1000 entries
- **Anti-repetition**: Sends last 5 previous facts to AI with instruction to find different places
- **Automatic cleanup**: Removes expired entries and enforces size limit

### Telegram Stars Donation System

- **Payment Processing**: Full Telegram Stars integration (XTR currency)
- **Premium Benefits**: Advanced reasoning levels + model selection
- **Duration**: 1 star = 25 years premium (effectively permanent, stackable)
- **Database**: Multi-backend support (SQLite/PostgreSQL/Firestore)
- **Commands**: `/donate` with 100, 250, 500 preset options + 50, 150, 1000, 2000 extended options
- **Security**: Payment ID deduplication, pre-checkout validation, user validation
- **Multi-language**: Payment UI localized (Russian, English, French)

### Tech Stack

**Core Framework & Language**
- **Python 3.12** (minimum 3.11) with async/await throughout
- **python-telegram-bot 21.7** - Bot framework with webhook support
- **AsyncIO** - Concurrent live location processing

**AI & Search**
- **Anthropic Claude API** (anthropic 0.50+) - Claude Opus 4.6 (adaptive thinking), Sonnet 4.5, Haiku 4.5
- **Brave Search API** - Web search for fact verification (2000 queries/month free)
- **Extended thinking** - Configurable reasoning budgets (1024-4096 tokens)

**Database Backends** (Auto-switchable)
- **SQLite** - Local/Railway deployment with volume persistence
- **PostgreSQL (asyncpg 0.29)** - Production with connection pooling
- **Firestore (firebase-admin 6.5)** - GCP-native with analytics

**External APIs**
- **Telegram Stars** - Payment system for premium features (XTR currency)
- **Nominatim (OSM)** - Geocoding service as coordinate fallback
- **Wikipedia/Wikimedia Commons** - Image search (Legacy API `w/api.php`, Wikidata QID/P18)
- **Yandex Images** - Alternative image source
- **Yandex Web Search** - Fallback when Brave rate-limited

**HTTP Clients**
- **httpx 0.27+** - Primary async HTTP client (Brave Search, Nominatim)
- **aiohttp 3.10.11** - Additional async HTTP client

**Development & Deployment**
- **Railway/Koyeb** - Production deployment with auto-scaling
- **Docker** - Containerized deployment (python:3.12-slim)
- **GitHub Actions** - CI/CD pipeline (lint -> format -> test -> deploy)
- **pytest + pytest-anyio** - Async testing with mocks
- **ruff + black** - Linting (88 char lines) and code formatting

**Utilities**
- **asyncio-throttle 1.0.2** - Rate limiting for concurrent requests
- **python-dotenv 1.0.1** - Environment variable management
- **sqlalchemy 2.0.36** - ORM with async support

### Testing Structure

**Test Files** (7 files, ~1,800 lines total)
- `test_claude_client.py` (496 lines) - Claude fact generation, coordinate extraction, image search, caching, model selection
- `test_location_handler.py` (402 lines) - Static/live location flows, media groups, response parsing
- `test_live_location_tracker.py` (306 lines) - Session management, fact delivery, cleanup
- `test_live_location_expiry.py` (165 lines) - Session timeout, expiry handling
- `test_live_location_silence.py` (144 lines) - Silence threshold, spam prevention
- `test_main.py` (122 lines) - Command handlers, welcome messages
- `test_fact_accuracy_prompts.py` (161 lines) - Prompt quality, fact verification requirements

**Testing Approach**
- AsyncIO testing with pytest-anyio
- Mock external APIs (Telegram, Anthropic, Firebase, Brave Search)
- Session management verification
- Error handling scenarios
- Duplicate prevention logic
- Run with: `OPENAI_API_KEY=test-key pytest tests/ -v` (legacy env var used in CI)

### Environment Variables

**Required**
- `TELEGRAM_BOT_TOKEN` - Bot token from @BotFather
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude
- `BRAVE_API_KEY` - Brave Search API key (get at https://brave.com/search/api/)

**Optional - Deployment**
- `WEBHOOK_URL` - Public URL for production (triggers webhook mode)
- `PORT` - Server port for webhook mode (default: 8000)

**Optional - Database**
- `DATABASE_URL` - PostgreSQL connection string (format: `postgresql://user:pass@host:port/db`)
- `USE_FIRESTORE_DB` - Set to "true" to use Firestore backend
- `RAILWAY_VOLUME_MOUNT_PATH` - Custom volume path (auto-detected as `/data` on Railway)

**Optional - Features**
- `RESET_LANG_ON_DEPLOY` - Reset all user languages on deploy (for testing)
- `HOWTO_STEP1_FILE_ID` - Cached Telegram file ID for onboarding step 1 image
- `HOWTO_STEP2_FILE_ID` - Cached Telegram file ID for onboarding step 2 image
- `HOWTO_STEP3_FILE_ID` - Cached Telegram file ID for onboarding step 3 image

**Optional - AI Configuration**
- `CLAUDE_THINKING_BUDGET_TOKENS_LOW` - Custom token budget for low reasoning (default: 1024)
- `CLAUDE_THINKING_BUDGET_TOKENS_MEDIUM` - Custom token budget for medium (default: 2048)
- `CLAUDE_THINKING_BUDGET_TOKENS_HIGH` - Custom token budget for high (default: 4096)
- `ANTHROPIC_THINKING_BUDGET_TOKENS_{LEVEL}` - Alternative env var prefix

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
  payment_id TEXT UNIQUE,      -- Telegram payment ID (deduplication key)
  stars_amount INTEGER,
  payment_date BIGINT,         -- Unix timestamp
  invoice_payload TEXT
);

-- User Preferences
CREATE TABLE user_preferences (
  user_id BIGINT PRIMARY KEY,
  language TEXT DEFAULT 'en',
  reasoning TEXT DEFAULT 'low',
  model TEXT DEFAULT 'claude-sonnet-4-5-20250929',
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
  "language": "en",
  "reasoning": "low",
  "model": "claude-sonnet-4-5-20250929"
}
```

**donations/{payment_id}** - Payment records
```json
{
  "user_id": 123456789,
  "stars_amount": 100,
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

### In-Memory Cache (Claude Client)

**StaticLocationHistory** - Search keywords to facts mapping
- **Key**: Search keywords identifying the location area
- **Value**: List of previously generated facts (last 5 returned, max 10 stored per key)
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
     - Test: OPENAI_API_KEY=test-key pytest tests/ -v
   ```

2. **Deploy Job** (Conditional: main branch + push only)
   ```yaml
   depends_on: test
   steps:
     - Install Railway CLI
     - Deploy: railway deploy --service nearby-fact-bot
     - Requires: RAILWAY_TOKEN secret
   ```

**Pipeline Flow**: Code -> Lint -> Format -> Test -> Deploy (main only)

Note: The CI uses `OPENAI_API_KEY=test-key` as a legacy env var. The actual codebase uses `ANTHROPIC_API_KEY` for the Claude API.

## Deployment Architectures

### Local Development
```bash
# Setup
pip install -e ".[dev]"
unset WEBHOOK_URL
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, and BRAVE_API_KEY

# Run
python -m src.main
```
- **Mode**: Polling (no webhook)
- **Database**: SQLite (donors.db in current directory)
- **Port**: Not required

### Railway Deployment
```bash
# One-time setup
railway login
railway link
railway volume create --mount /data

# Environment variables (set in Railway dashboard)
TELEGRAM_BOT_TOKEN=...
ANTHROPIC_API_KEY=...
BRAVE_API_KEY=...
WEBHOOK_URL=https://your-app.railway.app
PORT=8000
```
- **Mode**: Webhook
- **Database**: SQLite with volume persistence (`/data/donors.db`)
- **Health check**: Separate HTTP server on port+1
- **Auto-deploy**: GitHub push to main -> CI -> Railway deploy

### PostgreSQL Production
```bash
# Additional environment variable
DATABASE_URL=postgresql://user:pass@host:port/db
```
- **Mode**: Webhook
- **Database**: PostgreSQL with connection pooling (asyncpg)
- **Migration**: Auto-runs on startup via `migrate_to_postgres.py`
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
1. **Russian (ru)** - Full translation with dedicated Atlas Obscura style prompts
2. **English (en)** - Default language, full translation
3. **French (fr)** - Full translation
4. **Portuguese-Brazil (pt)** - Supported via language selection
5. **Ukrainian (uk)** - Supported via language selection

### Localization Coverage
- **Welcome messages in main.py**: Russian, English, French (3 languages)
- **Location handler messages**: Russian, English, French (3 languages)
- **Donation messages**: Russian, English, French (3 languages)
- **Language selection UI**: All 5 languages + custom input
- **AI prompts**: Separate Russian prompt system; unified English prompt for all other languages with `LANGUAGE: Write in {user_language}` instruction

### Localization System

**Message Dictionaries** (in handlers)
```python
LOCALIZED_MESSAGES = {
    "ru": {"welcome": "...", "buttons": {...}, "info_text": "..."},
    "en": {"welcome": "...", "buttons": {...}, "info_text": "..."},
    "fr": {"welcome": "...", "buttons": {...}, "info_text": "..."},
}
```

**Helper Functions**
- `get_localized_message(user_id, key, **kwargs)` - Retrieve localized text for user
- Language detection from database preferences
- Fallback to English if language not set

**User Preferences**
- Set via language selection keyboard on `/start`
- Persisted in database (user_preferences table)
- Can be reset with `/reset` command

## Code Patterns & Best Practices

### Architectural Patterns

**1. Async-First Design**
- All I/O operations use async/await
- `AsyncAnthropic` client for Claude API calls
- Asyncio task management for background live location loops
- Async database operations across all backends (async wrapper for sync SQLite)

**2. Database Abstraction**
```python
# AsyncDonorsWrapper provides unified interface
db = await get_async_donors_db()  # Auto-detects backend
await db.add_donation(...)
await db.is_premium_user(...)
```
- Easy switching between SQLite/PostgreSQL/Firestore via env vars
- No tight coupling to specific backend
- Graceful fallbacks

**3. Session Management**
```python
# Thread-safe live location sessions
tracker = get_live_location_tracker()  # Singleton
await tracker.start_live_location(user_id, chat_id, lat, lon, ...)
# Background task runs independently
await tracker.stop_live_location(user_id)  # Cleanup
```
- Asyncio locks for thread safety
- Automatic cleanup on session end/expiry
- Duplicate detection within sessions

**4. Error Handling Strategy**
- Graceful degradation (fallbacks for missing data, images, search results)
- User-friendly error messages in user's language
- Comprehensive logging with context
- Never expose internal errors to users
- `[[NO_POI_FOUND]]` sentinel for AI when no suitable place found

**5. Caching & Anti-Repetition**
```python
# StaticLocationHistory in claude_client.py
history = StaticLocationHistory(ttl_hours=24, max_entries=1000)
previous_facts = history.get_previous_facts(search_keywords)
# Previous facts sent to AI: "find a DIFFERENT place"
```

**6. Fallback Chains**
- Search: Brave Search -> Yandex Web Search -> knowledge-only mode
- Images: Wikipedia -> Yandex Images -> text-only
- Database: Firestore -> PostgreSQL -> SQLite
- Coordinates: Direct parse -> Nominatim geocoding
- Media: Media group -> 2 images -> text + individual images

### Code Organization

**Module Responsibilities**
- `handlers/` - Telegram message handling, user interaction, response formatting
- `services/` - Business logic, external API integration, database operations
- `utils/` - Shared utilities, text formatting, duplicate detection

**Naming Conventions**
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case()`
- Constants: `UPPER_SNAKE_CASE`

**Import Order**
1. Standard library
2. Third-party packages
3. Local modules (relative imports in services)

### Testing Guidelines

**Mock External APIs**
```python
@pytest.mark.anyio
async def test_generate_fact(mock_claude):
    mock_claude.return_value = "<answer>Location: Test\n..."
    result = await client.get_nearby_fact(55.75, 37.62)
    assert "Test" in result
```

**Test Session Management**
```python
async def test_live_location_cleanup():
    tracker = get_live_location_tracker()
    await tracker.start_live_location(...)
    await tracker.stop_live_location(user_id)
    assert not tracker.is_user_tracking(user_id)
```

## Command Reference

### User Commands
- `/start` - Welcome message + language selection (new users), session reset (existing)
- `/donate` - Telegram Stars donation with preset amounts
- `/live` - How-to guide for live location (3 steps with images)
- `/reset` - Reset language preference (re-shows language selection)

### Premium User Commands
- `/reason` - Set reasoning level (none/low/medium/high) + model selection (Opus/Sonnet/Haiku)
- `/stats` - View donation statistics and premium status

### Admin/Debug Commands
- `/debuguser` - Show user info (ID, language, Firestore document data)
- `/dbtest` - Database diagnostics and connection info

## Key Implementation Details

### Response Parsing

The location handler parses Claude's response in two formats:

**New format** (preferred):
```
<answer>
Location: Maison de Victor Hugo
Coordinates: 48.855400, 2.365200
Search: Maison Victor Hugo, Place des Vosges, Paris
Interesting fact: Behind the elegant facade...
Sources:
- Wikipedia -- https://...
</answer>
```

**Legacy format** (fallback):
```
Location: [name]
Interesting fact: [text]
```

### Duplicate Prevention

**Live Sessions**: Tracks `mentioned_places` list per session. Uses `is_duplicate_place()` with normalization and fuzzy matching. On duplicate, retries up to 2 times before skipping.

**Static Locations**: `StaticLocationHistory` caches previous facts by search keywords. Previous facts sent to AI prompt so it picks different places.

### Thinking Configuration

Extended thinking is controlled per-user via reasoning levels. The implementation differs by model:

**Opus 4.6** (adaptive thinking):
- `none` -> thinking disabled
- `low` -> `thinking: {type: "adaptive"}` + `output_config: {effort: "low"}`
- `medium` -> `thinking: {type: "adaptive"}` + `output_config: {effort: "medium"}`
- `high` -> `thinking: {type: "adaptive"}` + `output_config: {effort: "high"}`

**Sonnet 4.5 / Haiku 4.5** (manual budget_tokens):
- `none` -> thinking disabled
- `low` -> 1024 token budget (default for all users)
- `medium` -> 2048 token budget
- `high` -> 4096 token budget

Minimum enforced for budget_tokens: 1024. Auto-fallback to disabled on API errors.

## Troubleshooting

### Common Issues

**Bot not responding**
- Check `TELEGRAM_BOT_TOKEN` is set correctly
- Verify network connectivity
- Check logs for errors

**Database errors**
- SQLite: Check file permissions and volume mount path
- PostgreSQL: Verify `DATABASE_URL` format and connectivity
- Firestore: Check service account credentials and `USE_FIRESTORE_DB=true`

**Live location not working**
- User must share live location (not static) via Telegram's location sharing
- Verify interval selection was completed
- Check logs for session creation

**Facts not generating**
- Verify `ANTHROPIC_API_KEY` is valid and has quota
- Verify `BRAVE_API_KEY` for web search (bot works without it but with lower quality)
- Review logs for API errors or `[[NO_POI_FOUND]]` responses

**Images not appearing**
- Wikipedia API may be rate-limited
- Check image URLs are valid and accessible
- Media group caption must be <= 1024 chars (auto-truncated)
- Fallback chain: media group -> 2 images -> text-only -> individual images

**Legacy files**
- `src/services/openai_client.py` (2766 lines) is a legacy OpenAI-based client, not actively used
- `requirements.txt` still lists `openai==1.99.2` as a dependency
- `.env.example` references `OPENAI_API_KEY` (legacy)
- The actual AI integration uses `anthropic` package via `claude_client.py`
