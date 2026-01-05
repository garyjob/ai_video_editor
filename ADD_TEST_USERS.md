# How to Add Test Users for YouTube Authentication

## Direct URL to OAuth Consent Screen:

**https://console.cloud.google.com/apis/credentials/consent?project=agroverse-youtube-uploaded**

## Step-by-Step Instructions:

1. **Click the link above** or manually navigate:
   - Go to https://console.cloud.google.com/
   - Make sure the project "agroverse-youtube-uploaded" is selected (check the project dropdown at the top)
   - Go to: **APIs & Services** → **OAuth consent screen**

2. **Find the "Test users" section**
   - Scroll down on the OAuth consent screen page
   - Look for a section labeled "Test users" (usually near the bottom of the page)
   - You should see a list of current test users and an "+ ADD USERS" button

3. **Add test users**
   - Click the "+ ADD USERS" button
   - Enter email addresses one at a time, or paste multiple emails
   - Add these emails:
     - `garyjob@gmail.com`
     - `admin@truesight.me` (if not already added)
   - Click "ADD" to save

4. **Wait a few minutes** for changes to propagate

5. **Try authenticating again**:
   ```bash
   source venv/bin/activate
   python authenticate_account.py garyjob@gmail.com
   ```

## Alternative Navigation (if the link doesn't work):

1. Go to https://console.cloud.google.com/
2. Select project: `agroverse-youtube-uploaded` (dropdown at the top)
3. In the left sidebar, click: **APIs & Services**
4. Click: **OAuth consent screen**
5. Scroll down to find: **Test users** section
6. Click: **+ ADD USERS**
7. Add `garyjob@gmail.com` and click **ADD**

## Note:

If you don't see a "Test users" section, make sure:
- The app is in "Testing" publishing status (not "In production")
- You're viewing the OAuth consent screen, not just the Overview
- You have the correct permissions on the project


