# Bot Voyage 🗺️

**Bot Voyage** is a Telegram bot that acts as your personal AI tour guide. Send your location (static or live) and get surprising, verified facts about nearby places.

## ✨ Key Features

### 📍 Instant Facts
- Send your **static location** via attachment.
- Receive an interesting fact about a nearby landmark in seconds (10-15s).
- Uses **OpenAI GPT-5.1** with web search to ensure accuracy.

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
- Powered by **GPT-5.1** (Reasoning models).
- **Reasoning Levels**: Adjusts AI depth (minimal/low/medium/high) based on user tier or settings.
- **Web Search**: Mandatory verification step to reduce hallucinations.

## 🛠️ Tech Stack

- **Language**: Python 3.12
- **Framework**: `python-telegram-bot` (AsyncIO)
- **AI Engine**: OpenAI GPT-5.1 & GPT-5.1-mini
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
- OpenAI API Key (with access to GPT-5 models)
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
   pip install -r requirements.txt
   ```

4. **Configure environment**
   Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   ```
   Required variables:
   - `TELEGRAM_BOT_TOKEN`: Your bot token.
   - `OPENAI_API_KEY`: Your OpenAI key.

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
   - `OPENAI_API_KEY`
   - `WEBHOOK_URL`: Your public URL (e.g., `https://your-app.koyeb.app`)
   - `PORT`: (Default: 8000)

2. **Healthcheck**:
   The bot exposes a health check endpoint at `/` and `/health` to prevent platform timeouts.

3. **Push to deploy**:
   Connect your GitHub repository to Railway or Koyeb for automatic deployments.

## 📂 Project Structure

```
├── docs/               # Documentation & guides
├── infra/              # Infrastructure configs
├── src/
│   ├── handlers/       # Telegram command & message handlers
│   ├── services/       # External services (OpenAI, Firebase, DB)
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

## 📄 License

[MIT](LICENSE)
