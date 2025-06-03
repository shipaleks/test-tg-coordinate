# NearbyFactBot 🗺️

[![CI/CD](https://github.com/shipaleks/test-tg-coordinate/actions/workflows/ci.yml/badge.svg)](https://github.com/shipaleks/test-tg-coordinate/actions/workflows/ci.yml)

Telegram bot that provides interesting facts about places near your location using GPT-4.1.

## Features

- 📍 Send a location and get an interesting fact within 3 seconds
- 🔴 **Live location support (v1.1)** - automatic facts every 10 minutes while sharing location
- 🤖 Powered by OpenAI GPT-4.1
- 🎓 Professional tour guide with deep knowledge of locations worldwide
- 🇷🇺 Responds in Russian with culturally relevant and historically accurate facts
- 🎯 Focuses on specific toponyms within 300 meters of your location

## How to Use

### Static Location
1. Open chat with the bot
2. Click the attachment button 📎
3. Select "Location" 📍
4. Send your location
5. Get an instant interesting fact!

### Live Location (v1.1)
1. Click attachment button 📎 → "Location" 📍
2. **Select "Share Live Location"** and choose duration
3. Get an immediate fact, then automatic facts every 10 minutes
4. Stop sharing location to end the session

## Quick Start

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your API keys
3. Install dependencies: `pip install -e .`
4. Run locally: `python -m src.main`

## Environment Variables

- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from @BotFather
- `OPENAI_API_KEY` - Your OpenAI API key
- `PORT` - Port for webhook (default: 8000)
- `WEBHOOK_URL` - Webhook URL for production deployment

## Development

- Code formatting: `black src/ tests/`
- Linting: `ruff check src/ tests/`
- Tests: `pytest`

## Deployment

The bot is deployed on Railway. The deployment is automated via GitHub Actions on pushes to the main branch.

### Railway Setup

1. Create a new Railway project
2. Connect your GitHub repository
3. Set environment variables in Railway dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `WEBHOOK_URL` (Railway will provide the domain)
4. Deploy using `railway deploy`

## Architecture

- **Static Location**: Immediate fact response
- **Live Location**: Background tracking with facts every 10 minutes
- **Async Processing**: Non-blocking fact generation and delivery
- **Error Handling**: Graceful fallbacks for API failures

## Version History

- **v1.0**: Static location facts with GPT-4.1
- **v1.1**: Live location support with automatic fact delivery

## Milestones

- [x] MVP with static location facts
- [x] **Live location support (v1.1)** 🎉
- [ ] Internationalization (v1.2) 