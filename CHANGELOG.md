# Changelog

## [v1.3.3] - 2025-11-28

### 🐛 Fixed
- **Duplicate Place Prevention**: Fixed issue where live location facts could repeat the same place with different names
- **Place Name Normalization**: Added intelligent comparison that handles translations and variations (e.g., "Tour Eiffel" = "Eiffel Tower")
- **Retry Mechanism**: When AI returns a duplicate place, system now retries up to 2 times with stronger instructions
- **Enhanced Prompts**: Added explicit "forbidden places" list to AI prompts for better duplicate avoidance

### ✨ Added
- `normalize_place_name()` - Normalizes place names for comparison across languages
- `is_duplicate_place()` - Checks if a place is duplicate of previous places
- `extract_place_names_from_history()` - Extracts place names from fact history

### 📝 Documentation
- Added `docs/DUPLICATE_FIX_V1.3.3.md` - Detailed fix documentation

---

## [v1.3.1] - 2025-11-15

### ✨ Added
- **GPT-5.1 Support**: Upgraded to latest OpenAI models (gpt-5.1 and gpt-5.1-mini)
- **Healthcheck Endpoint**: Added `/health`, `/healthz`, `/` endpoints for Koyeb/Railway
- **Pinned Dependencies**: Fixed all dependency versions for stability

### 🔧 Changed
- `gpt-5` → `gpt-5.1` (improved accuracy and quality)
- `gpt-5-mini` → `gpt-5.1-mini` (default model for all users)
- Updated model selection UI (`/reason` command)
- Updated donation messages to mention GPT-5.1
- Pinned all dependencies in `requirements.txt` (no more `>=`)

### 🐛 Fixed
- **Koyeb Instance Stopping**: Added healthcheck to prevent platform from stopping instances
- **Dependency Drift**: Fixed versions to prevent unexpected updates

### 📝 Documentation
- Added `docs/KOYEB_FIX.md` - Koyeb healthcheck setup guide
- Added `docs/ПОЧЕМУ_СЛОМАЛОСЬ.md` - Root cause analysis
- Added `docs/GPT-5.1_MIGRATION.md` - Migration guide
- Updated `README.md` with v1.3.1 changes

### 🗃️ Database
- Updated default model in SQLite: `gpt-5.1-mini`
- Updated default model in PostgreSQL: `gpt-5.1-mini`
- Updated default model in Firestore: `gpt-5.1-mini`
- No migration needed (backward compatible)

### ⚙️ Technical Details
- All OpenAI API calls now use `gpt-5.1` and `gpt-5.1-mini`
- Same parameters: reasoning (minimal/low/medium/high)
- Same web_search tool integration
- Same pricing and performance
- Better accuracy and fewer hallucinations

---

## [v1.3] - 2025-09-09

### ✨ Added
- **GPT-5 Responses API**: Mandatory web_search for all facts
- **Online Verification**: Coordinates and facts verified before sending
- **Improved Image Search**: Better Wikimedia extraction

### 🔧 Changed
- Switched from GPT-4 to GPT-5 with reasoning
- Enhanced prompt engineering for fact quality
- Better source attribution

---

## [v1.2.2] - 2025-08-XX

### ✨ Added
- **Numbered Facts**: Live location facts show "🔴 Fact #1", "#2", etc.
- **Fact Counter**: Track progress during walks

### 🐛 Fixed
- Removed unnatural "Initial Fact" label

---

## [v1.2.1] - 2025-08-XX

### 🔧 Changed
- **Simplified Interface**: Removed redundant buttons
- **Improved Instructions**: Better live location onboarding
- **Shorter Messages**: Less noise, better UX

---

## [v1.2] - 2025-07-XX

### ✨ Added
- **Location Button**: ReplyKeyboardMarkup with request_location
- **Info System**: Built-in help for live location
- **Multi-language Support**: ru, en, fr, pt, uk

---

## [v1.1] - 2025-06-XX

### ✨ Added
- **Live Location**: Automatic facts every N minutes
- **Custom Intervals**: 5, 10, 30, 60 minutes
- **Full Localization**: Including OpenAI prompts
- **Session Management**: Multiple users, background tasks

---

## [v1.0] - 2025-05-XX

### 🎉 Initial Release
- **Static Location**: Send location → get fact
- **OpenAI Integration**: GPT-4 for fact generation
- **Telegram Bot**: python-telegram-bot framework
- **Production Ready**: Railway deployment with webhook
- **Image Support**: Wikipedia images for facts

---

## Legend

- ✨ **Added**: New features
- 🔧 **Changed**: Changes in existing functionality
- 🐛 **Fixed**: Bug fixes
- 🗑️ **Removed**: Removed features
- 📝 **Documentation**: Documentation changes
- 🗃️ **Database**: Database schema changes
- ⚙️ **Technical**: Internal/technical changes

