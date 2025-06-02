# NearbyFactBot 🗺️

[![CI/CD](https://github.com/shipaleks/test-tg-coordinate/actions/workflows/ci.yml/badge.svg)](https://github.com/shipaleks/test-tg-coordinate/actions/workflows/ci.yml)

Telegram bot that provides interesting facts about places near your location using GPT-4.1.

## Features

- 📍 Send a location and get an interesting fact within 3 seconds
- 🔴 Live location support (v1.1) - automatic facts every 10 minutes
- 🤖 Powered by OpenAI GPT-4.1
- 🎓 Professional tour guide with deep knowledge of locations worldwide
- 🇷🇺 Responds in Russian with culturally relevant and historically accurate facts
- 🎯 Focuses on specific toponyms within 300 meters of your location

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

## Milestones

- [x] MVP with static location facts
- [ ] Live location support (v1.1)
- [ ] Internationalization (v1.2) 