# Bot Voyage 🗺️

**Bot Voyage** is a Telegram bot that acts as your personal AI tour guide. Send your location (static or live) and get surprising, verified facts about nearby places.

## ✨ Key Features

### 📍 Instant Facts
- Send your **static location** via attachment.
- Receive an interesting fact about a nearby landmark in seconds (10-15s).
- Uses **Anthropic Claude** with Brave Search web verification to ensure accuracy.

### 🔴 Live Location (Tour Mode)
- Share your **Live Location** for a hands-free tour experience.
- Select an update interval (e.g., every 5, 10, 30, or 60 minutes).
- The bot automatically sends new facts as you walk.
- **Numbered Facts**: Keep track of your journey (Fact #1, #2...).
- **Smart Duplicate Prevention**: Ensures you don't hear about the same place twice, even if you circle back.

### 🌐 Multilingual Support
- Automatically detects and supports:
  - 🇬🇧 English
  - 🇷🇺 Russian
  - 🇫🇷 French
- Change language anytime via the main menu.

### 🧠 Advanced AI Logic
- Powered by the **Claude 5 family**: Sonnet 5 (default), Opus 5 and Haiku 4.5 (premium options).
- **Reasoning Levels**: Adjusts AI depth (none/low/medium/high). Claude 5 models use adaptive thinking with an effort parameter; Haiku 4.5 uses thinking token budgets.
- **Web Search**: Mandatory verification step to reduce hallucinations (Brave Search with Yandex fallback).

## 🛠️ Tech Stack

- **Language**: Python 3.12
- **Framework**: `python-telegram-bot` (AsyncIO)
- **AI Engine**: Anthropic Claude — Opus 5 / Sonnet 5 / Haiku 4.5
- **Database**:
  - **Firestore**: User profiles & settings (production)
  - **PostgreSQL**: Donation tracking & analytics
  - **SQLite**: Local development fallback
- **Infrastructure**: Docker, Railway / Koyeb
- **CI/CD**: GitHub Actions

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Anthropic API Key (https://console.anthropic.com/)
- Brave Search API Key (https://brave.com/search/api/)
- Firebase Credentials (optional, for production)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/bot-voyage.git
   cd bot-voyage
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Configure environment**
   Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   ```
   Required variables:
   - `TELEGRAM_BOT_TOKEN`: Your bot token.
   - `ANTHROPIC_API_KEY`: Your Anthropic key.
   - `BRAVE_API_KEY`: Your Brave Search key.

5. **Run the bot**
   ```bash
   # Run in polling mode (easiest for local dev)
   python -m src.main
   ```

## 📦 Deployment

### Railway / Koyeb

The project is Dockerized and ready for cloud deployment.

1. **Environment Variables**: Set the following in your project settings:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `BRAVE_API_KEY`
   - `WEBHOOK_URL`: Your public URL (e.g., `https://your-app.railway.app`)
   - `PORT`: (Default: 8000)

2. **Healthcheck**:
   The bot exposes a health check endpoint at `/` and `/health` to prevent platform timeouts.

3. **Push to deploy**:
   Connect your GitHub repository to Railway or Koyeb for automatic deployments.

## 📂 Project Structure

```
├── docs/               # Documentation & guides
├── src/
│   ├── handlers/       # Telegram command & message handlers
│   ├── services/       # External services (Claude, search, Firebase, DB)
│   ├── utils/          # Helper functions
│   └── main.py         # Entry point
├── tests/              # Pytest suite
├── .env.example        # Template for environment variables
├── Dockerfile          # Production Docker image
└── requirements.txt    # Python dependencies
```

## 🤝 Contributing

Contributions are welcome! Please verify your changes with existing tests:

```bash
python -m pytest tests/ -v
```
