#!/usr/bin/env python3
"""
Standalone script to authenticate a YouTube account via OAuth.

This script opens a browser window for authentication and stores the credentials.

Usage:
    python authenticate_account.py <account_email>

Example:
    python authenticate_account.py garyjob@gmail.com
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from oauth_flow import authenticate_account, get_oauth_client_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python authenticate_account.py <account_email>")
        print("\nExample:")
        print("  python authenticate_account.py garyjob@gmail.com")
        sys.exit(1)
    
    account_email = sys.argv[1].strip()
    
    # Validate email format
    if '@' not in account_email or '.' not in account_email.split('@')[1]:
        print(f"❌ Error: Invalid email format: {account_email}")
        sys.exit(1)
    
    print(f"\n🔐 Authenticating YouTube account: {account_email}")
    print("=" * 60)
    
    # Check if OAuth client exists
    oauth_client_path = get_oauth_client_path()
    if oauth_client_path is None:
        print("\n❌ Error: No OAuth client credentials found.")
        print("\nPlease add at least one OAuth2 credentials file first:")
        print("  1. Get OAuth2 credentials from Google Cloud Console")
        print("  2. Save as: credentials/oauth_client.json")
        print("  OR upload a credentials file through the web UI")
        sys.exit(1)
    
    print(f"📁 Using OAuth client: {oauth_client_path.name}")
    print("\n📱 A browser window will open for authentication...")
    print("   Please sign in with your YouTube account and grant permissions.")
    print()
    
    try:
        # Use a port that's different from the Flask server (8080)
        # Try different ports starting from 8090
        import socket
        
        def find_free_port(start_port=8090):
            for port in range(start_port, start_port + 10):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.bind(('localhost', port))
                    sock.close()
                    return port
                except OSError:
                    continue
            return start_port  # Fallback
        
        oauth_port = find_free_port(8090)
        print(f"🔌 Using OAuth callback port: {oauth_port}")
        result = authenticate_account(account_email, oauth_client_path, port=oauth_port)
        
        if result.get('status') == 'success':
            print("\n" + "=" * 60)
            print("✅ Authentication successful!")
            print(f"   Account: {account_email}")
            print(f"   Token saved to: {result.get('token_file')}")
            
            channel_info = result.get('channel_info', {})
            if channel_info:
                channel_name = channel_info.get('title', 'N/A')
                print(f"   Channel: {channel_name}")
            
            print("\n🎉 You can now use this account to upload videos!")
            print("   The account will appear in the web UI account dropdown.")
            sys.exit(0)
        else:
            print("\n❌ Authentication failed:")
            print(f"   {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n❌ Authentication cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

