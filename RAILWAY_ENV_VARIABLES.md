# Railway Environment Variables Configuration Guide

This document lists all environment variables that need to be configured in Railway for the Django application to work properly.

## 🔐 Required Environment Variables

### Database (PostgreSQL)
Railway automatically provides these when you add a PostgreSQL service, but you can also set them manually:

- **`PGDATABASE`** - Database name (usually `railway`)
- **`PGUSER`** - Database user (usually `postgres`)
- **`PGPASSWORD`** - Database password
- **`PGHOST`** - Database host (e.g., `switchback.proxy.rlwy.net`)
- **`PGPORT`** - Database port (e.g., `17976`)

### OpenAI API Keys (Required for AI Features)

- **`OPEN_AI_API_KEY`** or **`OPENAI_API_KEY`** - Your OpenAI API key
  - Get from: https://platform.openai.com/api-keys
  - Format: `sk-proj-...` or `sk-...`
  - Used for:
    - Financial statement template suggestions
    - Chat functionality
    - AI-powered features

### Optional AI Configuration

- **`ANTHROPIC_API_KEY`** - Anthropic API key (optional alternative to OpenAI)
  - Get from: https://console.anthropic.com/
  - Format: `sk-ant-...`
  
- **`TEMPLATE_AI_PROVIDER`** - Default AI provider (optional)
  - Values: `openai` or `anthropic`
  - Default: `openai`

- **`TEMPLATE_AI_MODEL`** - Default AI model (optional)
  - OpenAI options: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`
  - Anthropic options: `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`
  - Default: Provider default

### Redis (Optional - for Celery async tasks)

- **`REDIS_URL`** - Redis connection URL (optional)
  - Format: `redis://user:password@host:port` or `redis://localhost:6379/0`
  - If not set, Celery tasks run synchronously (no worker needed)
  - If set, enables async task processing

### Email Configuration (Optional)

- **`EMAIL_HOST_USER`** - Email address for sending emails
- **`EMAIL_HOST_PASSWORD`** - Email password or app password
- **`PASSWORD_RESET_EMAIL_COOLDOWN`** - Cooldown period in minutes (default: 5)

### Embedding Service (Optional - for AI embeddings)

- **`EMBED_BASE_URL`** - Embedding service URL
  - Default: `https://embedding-service.up.railway.app`
- **`EMBED_INTERNAL_HOST`** - Internal service host (for Railway internal networking)
- **`EMBED_PORT`** - Embedding service port (default: `11434`)
- **`EMBED_PATH`** - API path (default: `/api/embeddings`)
- **`EMBED_MODEL`** - Model name (default: `nomic-embed-text`)
- **`EMBED_DIM`** - Embedding dimensions (default: `768`)
- **`EMBED_API_KEY`** - Optional API key for embedding service

### LLM Service (Optional - for local LLM)

- **`LLM_BASE_URL`** - LLM service URL
  - Default: `https://chat-service-production-d54a.up.railway.app`
- **`LLM_GENERATE_PATH`** - API path (default: `/api/generate`)
- **`LLM_MODEL`** - Model name (default: `llama3.2:1b-instruct-q4_K_M`)
- **`LLM_TIMEOUT`** - Request timeout in seconds (default: `30`)

### Celery Configuration (Optional)

- **`CELERY_TASK_TIME_LIMIT`** - Task time limit in minutes (default: `10`)

### Environment Mode

- **`ENVIRONMENT_MODE`** - Environment mode (optional)
  - Values: `production`, `local`, `homolog`, `homologation`
  - Default: `production`
  - Affects database selection and local settings loading

## 📋 Quick Setup Checklist for Railway

### Minimum Required Variables:
1. ✅ Database variables (auto-provided by Railway PostgreSQL service)
2. ✅ `OPEN_AI_API_KEY` - For AI features

### Recommended Variables:
3. ✅ `REDIS_URL` - If you want async Celery tasks
4. ✅ `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` - If you need email functionality

### Optional Variables:
5. ⚪ `ANTHROPIC_API_KEY` - If using Anthropic instead of OpenAI
6. ⚪ `TEMPLATE_AI_PROVIDER` - To specify default AI provider
7. ⚪ `TEMPLATE_AI_MODEL` - To specify default AI model
8. ⚪ Embedding service variables - If using custom embedding service
9. ⚪ LLM service variables - If using custom LLM service

## 🔒 Security Notes

1. **Never commit API keys to git** - Always use environment variables
2. **Use Railway's secret management** - Set variables in Railway dashboard, not in code
3. **Rotate keys regularly** - Especially if exposed or compromised
4. **Use different keys for different environments** - Separate dev/staging/production keys

## 🚀 Setting Variables in Railway

1. Go to your Railway project dashboard
2. Select your service
3. Go to the "Variables" tab
4. Click "New Variable"
5. Add each variable name and value
6. Click "Add" to save

## 📝 Example Railway Variables Configuration

```
# Database (auto-provided by Railway)
PGDATABASE=railway
PGUSER=postgres
PGPASSWORD=your_password_here
PGHOST=switchback.proxy.rlwy.net
PGPORT=17976

# OpenAI (Required)
OPEN_AI_API_KEY=sk-proj-your-key-here

# Redis (Optional - for async tasks)
REDIS_URL=redis://default:password@redis.railway.internal:6379/0

# Email (Optional)
EMAIL_HOST_USER=noreply@yourdomain.com
EMAIL_HOST_PASSWORD=your_email_password

# AI Configuration (Optional)
TEMPLATE_AI_PROVIDER=openai
TEMPLATE_AI_MODEL=gpt-4o
```

## 🔍 How the App Loads Variables

The application checks for environment variables in this order:

1. **Environment variables** (Railway) - Highest priority
2. **Django settings** (from `settings.py`)
3. **Local credentials file** (`local_credentials.ini`) - Only in local development

For OpenAI specifically, the app checks:
- `OPEN_AI_API_KEY` (preferred)
- `OPENAI_API_KEY` (fallback)
- Settings: `settings.OPEN_AI_API_KEY`
- Settings: `settings.OPENAI_API_KEY`

## ⚠️ Troubleshooting

### "OpenAI API key not found" error:
- Check that `OPEN_AI_API_KEY` is set in Railway variables
- Verify the key is valid and has proper permissions
- Check logs for which variable names were checked

### Database connection errors:
- Verify Railway PostgreSQL service is running
- Check that database variables are set correctly
- Ensure database is accessible from your service

### Celery tasks not running:
- Check if `REDIS_URL` is set (required for async tasks)
- If not set, tasks run synchronously (no worker needed)
- Verify Redis service is running if using async mode

