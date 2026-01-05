#!/usr/bin/env python3
"""
Helper script to migrate credentials from the original agroverse_shop location.

This script helps copy credentials from the original location to the new video_editor
directory structure.
"""

import os
import shutil
from pathlib import Path

# Path to original credentials
ORIGINAL_SCRIPT_DIR = Path('/Users/garyjob/Applications/agroverse_shop/scripts')
ORIGINAL_CREDENTIALS = ORIGINAL_SCRIPT_DIR / 'youtube_credentials.json'
ORIGINAL_TOKEN = ORIGINAL_SCRIPT_DIR / 'youtube_token.json'

# New location
NEW_CREDENTIALS_DIR = Path(__file__).parent / 'credentials'
NEW_CREDENTIALS_DIR.mkdir(exist_ok=True)

# Default account (admin@truesight.me based on user's note)
DEFAULT_ACCOUNT = 'admin@truesight.me'


def migrate_credentials(account_email=DEFAULT_ACCOUNT):
    """
    Migrate credentials from original location to new structure.
    
    Args:
        account_email: Email address for the account
    """
    new_credentials = NEW_CREDENTIALS_DIR / f'{account_email}_credentials.json'
    new_token = NEW_CREDENTIALS_DIR / f'{account_email}_token.json'
    
    # Copy credentials file
    if ORIGINAL_CREDENTIALS.exists():
        shutil.copy2(ORIGINAL_CREDENTIALS, new_credentials)
        print(f"✅ Copied credentials to {new_credentials}")
    else:
        print(f"⚠️  Credentials file not found at {ORIGINAL_CREDENTIALS}")
        print(f"   Please manually add credentials as {new_credentials}")
        return False
    
    # Copy token file if it exists (optional - will regenerate if needed)
    if ORIGINAL_TOKEN.exists():
        shutil.copy2(ORIGINAL_TOKEN, new_token)
        print(f"✅ Copied token to {new_token}")
    else:
        print(f"ℹ️  Token file not found (will be generated on first use)")
    
    print(f"\n✅ Credentials migrated successfully for {account_email}")
    return True


if __name__ == '__main__':
    import sys
    
    account = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ACCOUNT
    print(f"Migrating credentials for: {account}")
    print()
    
    migrate_credentials(account)


