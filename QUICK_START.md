# Quick Start Guide

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Set Up Credentials

### Option A: Migrate Existing Credentials (admin@truesight.me)

If you want to use the existing credentials from `agroverse_shop`:

```bash
python migrate_credentials.py admin@truesight.me
```

### Option B: Add New Credentials Manually

1. Get OAuth2 credentials from [Google Cloud Console](https://console.cloud.google.com/)
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop app)
4. Save as `credentials/{email}_credentials.json`

For example:
- `credentials/admin@truesight.me_credentials.json`
- `credentials/garyjob@gmail.com_credentials.json`

## Step 3: Run the Web UI

```bash
python app.py
```

Open http://localhost:8080 in your browser (default port, configurable via PORT environment variable).

## Step 4: Use the CLI (Optional)

```bash
# List available accounts
python upload_cli.py --list-accounts

# Upload a video
python upload_cli.py video.mp4 \
  --account admin@truesight.me \
  --title "My Video Title" \
  --description "Video description" \
  --privacy public \
  --tags tag1 tag2 tag3
```

## First-Time Authentication

The first time you use an account, you'll be prompted to:
1. Open a browser window for authentication
2. Sign in to the Google account
3. Grant permissions for YouTube upload
4. The token will be saved for future use

## Adding Multiple Accounts

To support multiple YouTube accounts (like admin@truesight.me and garyjob@gmail.com):

1. For each account, get OAuth2 credentials from Google Cloud Console
2. Save each as `credentials/{email}_credentials.json`
3. Both accounts will appear in the web UI dropdown

