# Setup Instructions

## Step 1: Create Virtual Environment

```bash
cd /Users/garyjob/Applications/video_editor
python3 -m venv venv
```

## Step 2: Activate Virtual Environment

```bash
source venv/bin/activate
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Set Up Credentials

### Option A: Migrate Existing Credentials (admin@truesight.me)

If you want to use the existing credentials from `agroverse_shop`:

```bash
# Make sure venv is activated
source venv/bin/activate

# Run migration script
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

## Step 5: Run the Web UI

### Option 1: Using the run script
```bash
chmod +x run.sh
./run.sh
```

### Option 2: Manual activation
```bash
source venv/bin/activate
python app.py
```

Then open http://localhost:8080 in your browser (default port).

### Using a Custom Port

To use a different port, set the PORT environment variable:

```bash
# Using run.sh
PORT=3000 ./run.sh

# Or manually
source venv/bin/activate
PORT=3000 python app.py
```

## Running CLI Commands

Always activate the virtual environment first:

```bash
source venv/bin/activate

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

## Quick Reference

- **Activate venv**: `source venv/bin/activate`
- **Deactivate venv**: `deactivate`
- **Run web UI**: `python app.py` (with venv activated) or `./run.sh`
- **Credentials location**: `credentials/{email}_credentials.json`

