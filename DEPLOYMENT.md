# Deployment Guide

## GitHub Repository
✅ **Completed**: Code pushed to https://github.com/shipaleks/test-tg-coordinate.git

## Local Testing
✅ **Completed**: Bot starts successfully and loads environment variables from `.env` file

## Next Steps for Production Deployment

### 1. Railway Deployment

1. **Create Railway Project**
   ```bash
   # Install Railway CLI if not installed
   npm install -g @railway/cli
   
   # Login to Railway
   railway login
   
   # Create new project
   railway new
   ```

2. **Connect GitHub Repository**
   - Go to Railway dashboard
   - Click "New Project" → "Deploy from GitHub repo"
   - Select `shipaleks/test-tg-coordinate`

3. **Set Environment Variables**
   In Railway dashboard, go to Variables tab and add:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   OPENAI_API_KEY=your_openai_api_key
   WEBHOOK_URL=https://your-app-name.up.railway.app/webhook
   PORT=8000
   ```

4. **Deploy**
   - Railway will automatically deploy on git push to main branch
   - Check logs in Railway dashboard

### 2. Telegram Bot Setup

1. **Create Bot with @BotFather**
   - Send `/newbot` to @BotFather
   - Choose bot name and username
   - Copy the token to `TELEGRAM_BOT_TOKEN`

2. **Set Webhook** (Railway will do this automatically)
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-app.up.railway.app/webhook
   ```

### 3. Testing

1. **Send `/start` to your bot**
2. **Send location** using 📎 → Location
3. **Verify bot responds** with interesting facts

### 4. Monitoring

- Check Railway logs for errors
- Monitor response times (should be ≤ 3 seconds)
- Verify webhook endpoint health

## Current Status

✅ MVP Implementation Complete:
- ✅ Location message handling
- ✅ OpenAI integration for facts generation
- ✅ Error handling and user feedback
- ✅ Comprehensive testing
- ✅ CI/CD pipeline configured
- ✅ Docker support
- ✅ Environment variables management

🚀 **Ready for Production Deployment** 