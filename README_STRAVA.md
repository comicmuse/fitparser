# Strava Webhook Integration

Automatically download FIT files from Strava when new running activities are uploaded.

## Overview

This integration consists of:
- **OAuth Tool** (`strava_oauth.py`) - Interactive script for OAuth2 authorization
- **Webhook Receiver** (`strava_webhook.py`) - Flask server that receives activity events from Strava
- **Strava Client** (`strava_downloader.py`) - Handles OAuth2 authentication and FIT file downloads
- **Automatic Downloads** - Only downloads "Run" and "VirtualRun" activities with original FIT files

Downloaded files are organized as: `downloads/{yyyy}/{mm}/{activity_id}.fit`

## Prerequisites

1. Python 3.7 or later
2. A Strava account
3. A publicly accessible server or ngrok for webhook URL (for development)

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a Strava API Application

1. Go to https://www.strava.com/settings/api
2. Click "Create An App" (or use an existing app)
3. Fill in the required fields:
   - **Application Name**: Choose a name (e.g., "FIT File Downloader")
   - **Category**: Choose appropriate category
   - **Club**: Leave blank (optional)
   - **Website**: Your website or `http://localhost`
   - **Authorization Callback Domain**: `localhost` (for local development)
4. Click "Create"
5. Note your **Client ID** and **Client Secret**

### 3. Configure Environment Variables

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and fill in your Strava application credentials:
```bash
STRAVA_CLIENT_ID=your_client_id_here
STRAVA_CLIENT_SECRET=your_client_secret_here
STRAVA_VERIFY_TOKEN=$(openssl rand -hex 16)  # Generate a random token
```

3. Configure other settings (optional):
```bash
DOWNLOAD_BASE_DIR=./downloads
STATE_FILE=./downloaded_activities.json
WEBHOOK_PORT=5000
```

### 4. Authorize the Application (Get OAuth Tokens)

You need to authorize the application to access your Strava data.

#### Option A: Automated OAuth Flow (Recommended)

The easiest way is to use the automated OAuth script that handles everything for you:

```bash
python strava_oauth.py
```

This will:
1. Open your browser to Strava's authorization page
2. Start a local server to receive the callback
3. Exchange the authorization code for tokens
4. Save the tokens to your `.env` file automatically

**Note**: Make sure your Strava application settings include `localhost` in the "Authorization Callback Domain" field (not the full URL, just `localhost`).

If you need to use a different port than 8000, set it in your `.env` file:
```bash
OAUTH_REDIRECT_URI=http://localhost:8000
OAUTH_PORT=8000
```

#### Option B: Manual Authorization Code Flow

If you prefer to do it manually or the automated flow doesn't work:

1. Open this URL in your browser (replace YOUR_CLIENT_ID):
```
https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read
```

2. Click "Authorize"

3. You'll be redirected to `http://localhost/?code=XXXXX`
   - Copy the `code` parameter from the URL

4. Exchange the code for tokens using Python:
```python
from strava_downloader import StravaClient, save_tokens_to_env
import os
from dotenv import load_dotenv

load_dotenv()

client = StravaClient(
    client_id=os.getenv('STRAVA_CLIENT_ID'),
    client_secret=os.getenv('STRAVA_CLIENT_SECRET')
)

# Exchange code for tokens
token_data = client.get_access_token_from_code('YOUR_CODE_HERE')

# Save tokens to .env file
save_tokens_to_env(
    token_data['access_token'],
    token_data['refresh_token']
)

print("Tokens saved to .env file!")
```

#### Option C: Using Existing Tokens

If you already have access and refresh tokens, add them directly to `.env`:
```bash
STRAVA_ACCESS_TOKEN=your_access_token
STRAVA_REFRESH_TOKEN=your_refresh_token
```

### 5. Test the Downloader (Optional)

Test downloading a specific activity:
```bash
python strava_downloader.py ACTIVITY_ID
```

Replace `ACTIVITY_ID` with a real Strava activity ID from your account.

### 6. Start the Webhook Server

```bash
python strava_webhook.py
```

The server will start on port 5000 (or your configured port).

You should see:
```
============================================================
Strava Webhook Receiver
============================================================
Download directory: ./downloads
State file: ./downloaded_activities.json
Starting webhook server on port 5000
Press Ctrl+C to stop
============================================================
```

### 7. Make Webhook Accessible (Development)

For local development, use ngrok to expose your webhook:

```bash
# Install ngrok from https://ngrok.com/
ngrok http 5000
```

Note the HTTPS URL provided (e.g., `https://abc123.ngrok.io`)

### 8. Create Webhook Subscription

Subscribe to Strava webhook events:

```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=YOUR_CLIENT_ID \
  -F client_secret=YOUR_CLIENT_SECRET \
  -F callback_url=https://YOUR_NGROK_URL/webhook \
  -F verify_token=YOUR_VERIFY_TOKEN
```

Replace:
- `YOUR_CLIENT_ID` with your Strava client ID
- `YOUR_CLIENT_SECRET` with your Strava client secret
- `YOUR_NGROK_URL` with your ngrok URL
- `YOUR_VERIFY_TOKEN` with the verify token from your `.env` file

If successful, you'll receive a response like:
```json
{
  "id": 123456,
  "callback_url": "https://abc123.ngrok.io/webhook",
  "created_at": "2026-02-08T12:00:00Z",
  "updated_at": "2026-02-08T12:00:00Z"
}
```

### 9. List Existing Subscriptions (Optional)

Check your active webhook subscriptions:

```bash
curl -G https://www.strava.com/api/v3/push_subscriptions \
  -d client_id=YOUR_CLIENT_ID \
  -d client_secret=YOUR_CLIENT_SECRET
```

### 10. Delete a Subscription (Optional)

Remove a webhook subscription:

```bash
curl -X DELETE https://www.strava.com/api/v3/push_subscriptions/SUBSCRIPTION_ID \
  -F client_id=YOUR_CLIENT_ID \
  -F client_secret=YOUR_CLIENT_SECRET
```

## How It Works

1. **Activity Upload**: You upload a new running activity to Strava (via watch, app, or manual)

2. **Webhook Event**: Strava sends a POST request to your webhook URL with event details:
```json
{
  "aspect_type": "create",
  "event_time": 1234567890,
  "object_id": 12345,
  "object_type": "activity",
  "owner_id": 67890,
  "subscription_id": 111213
}
```

3. **Event Processing**: The webhook receiver:
   - Validates it's a "create" event for an "activity"
   - Starts an async download thread
   - Responds immediately (to avoid timeout)

4. **Download Process**:
   - Fetches activity details from Strava API
   - Checks if activity type is "Run" or "VirtualRun"
   - Checks if already downloaded (state tracking)
   - Downloads the original FIT file
   - Saves to `downloads/{yyyy}/{mm}/{activity_id}.fit`
   - Updates state file to prevent re-downloads

5. **Token Refresh**: If access token expires, it's automatically refreshed using the refresh token

## File Organization

Downloaded FIT files are organized by year and month:
```
downloads/
├── 2026/
│   ├── 01/
│   │   ├── 12345.fit
│   │   └── 12346.fit
│   └── 02/
│       └── 12347.fit
└── 2027/
    └── 01/
        └── 12348.fit
```

## State Tracking

The `downloaded_activities.json` file tracks which activities have been downloaded:

```json
{
  "downloaded_activities": [
    {
      "activity_id": 12345,
      "download_time": "2026-02-08T12:00:00Z",
      "file_path": "downloads/2026/02/12345.fit"
    }
  ]
}
```

This prevents duplicate downloads when:
- Webhook events are duplicated
- You restart the server
- Activities are updated (triggers webhook but file already exists)

## Endpoints

### `GET /webhook`
Webhook verification endpoint for Strava subscription setup.

### `POST /webhook`
Receives activity events from Strava.

### `GET /health`
Health check endpoint. Returns:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-08T12:00:00",
  "client_initialized": true
}
```

### `GET /`
Info page with available endpoints.

## Troubleshooting

### Webhook Verification Fails

**Problem**: Strava can't verify your webhook during subscription creation.

**Solutions**:
- Ensure webhook server is running
- Ensure URL is publicly accessible (check ngrok)
- Verify `STRAVA_VERIFY_TOKEN` matches in `.env` and curl command
- Check server logs for verification attempts

### Activities Not Downloading

**Problem**: Webhook events received but files not downloaded.

**Solutions**:
1. Check if tokens are set:
   - `STRAVA_ACCESS_TOKEN` and `STRAVA_REFRESH_TOKEN` in `.env`
2. Check activity type:
   - Only "Run" and "VirtualRun" activities are downloaded
3. Check if already downloaded:
   - Look in `downloaded_activities.json`
4. Check for FIT file availability:
   - Some activities may not have original FIT files (e.g., manual entries)
5. Check server logs for errors:
   - Look for authentication, API, or network errors

### Token Expired

**Problem**: `401 Unauthorized` errors in logs.

**Solutions**:
- The client automatically refreshes tokens
- If refresh fails, re-authorize the application (see Step 4)
- Ensure `STRAVA_REFRESH_TOKEN` is set in `.env`

### Duplicate Downloads

**Problem**: Same activity downloaded multiple times.

**Solutions**:
- Check `downloaded_activities.json` is being saved properly
- Ensure file permissions allow writing to state file
- Check for concurrent processes using the same state file

### ngrok Connection Issues

**Problem**: ngrok URL not working or timing out.

**Solutions**:
- Restart ngrok
- Use a different ngrok region: `ngrok http 5000 --region us`
- Upgrade to ngrok paid plan for more stable connections
- For production, deploy to a proper server with static URL

## Production Deployment

For production use:

1. **Use a proper server** with a static domain/IP
   - Deploy to AWS, Google Cloud, Azure, Heroku, etc.
   - Use a reverse proxy (nginx, Apache)

2. **Use HTTPS** (required by Strava)
   - Get SSL certificate (Let's Encrypt, etc.)

3. **Use a process manager**
   - systemd, supervisor, PM2
   - Auto-restart on crashes

4. **Set up logging**
   - Rotate logs to prevent disk fill
   - Monitor for errors

5. **Secure your tokens**
   - Use environment variables, not `.env` file
   - Restrict file permissions
   - Use secrets management (AWS Secrets Manager, etc.)

6. **Monitor the service**
   - Set up health check monitoring
   - Alert on failures
   - Track download success rate

## Example systemd Service (Linux)

Create `/etc/systemd/system/strava-webhook.service`:

```ini
[Unit]
Description=Strava Webhook Receiver
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/fitparser
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python strava_webhook.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable strava-webhook
sudo systemctl start strava-webhook
sudo systemctl status strava-webhook
```

## Security Notes

- **Never commit `.env` file** to version control (it contains secrets)
- **Restrict webhook access** using firewall rules if possible
- **Validate webhook signatures** (Strava doesn't provide signatures, but validate verify_token)
- **Rate limit** webhook endpoint if needed
- **Monitor for abuse** - check logs for unusual activity
- **Rotate tokens periodically** for security

## API Rate Limits

Strava API has rate limits:
- **200 requests per 15 minutes** per application
- **2,000 requests per day** per application

The webhook approach is efficient:
- 1 request to verify activity details
- 1 request to download FIT file
- = 2 requests per activity

## Need Help?

- **Strava API Documentation**: https://developers.strava.com/
- **Strava API Support**: https://developers.strava.com/community/
- **FIT File Format**: https://developer.garmin.com/fit/

## License

See main repository license.
