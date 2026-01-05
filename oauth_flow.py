#!/usr/bin/env python3
"""
OAuth flow handler for YouTube authentication.

This module handles the OAuth2 flow to authenticate YouTube accounts
and store tokens locally.
"""

import os
import json
import requests
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# OAuth 2.0 scopes required for uploading videos
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Base directory for credentials
BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / 'credentials'

# Shared OAuth client credentials (we'll use the first available credentials file)
# or a default one if available
DEFAULT_OAUTH_CLIENT = CREDENTIALS_DIR / 'oauth_client.json'


def get_oauth_client_path():
    """
    Get the path to OAuth client credentials.
    Uses the first available account's credentials as the OAuth client,
    or a default oauth_client.json file.
    """
    # Check for default OAuth client file
    if DEFAULT_OAUTH_CLIENT.exists():
        return DEFAULT_OAUTH_CLIENT
    
    # Use the first available account's credentials as OAuth client
    for file in CREDENTIALS_DIR.glob('*_credentials.json'):
        return file
    
    return None


def authenticate_account(account_email, oauth_client_path=None, port=8080):
    """
    Authenticate a YouTube account using OAuth2 flow.
    
    Args:
        account_email: Email address for the account to authenticate
        oauth_client_path: Path to OAuth client credentials (optional, will auto-detect)
        port: Port for OAuth callback (default: 8080)
    
    Returns:
        dict: Result with status and account info
    """
    if oauth_client_path is None:
        oauth_client_path = get_oauth_client_path()
        if oauth_client_path is None:
            raise FileNotFoundError(
                "No OAuth client credentials found. "
                "Please add at least one credentials file first, or create oauth_client.json"
            )
    
    oauth_client_path = Path(oauth_client_path)
    if not oauth_client_path.exists():
        raise FileNotFoundError(f"OAuth client file not found: {oauth_client_path}")
    
    # Paths for this account's token
    token_file = CREDENTIALS_DIR / f'{account_email}_token.json'
    
    # Run OAuth flow
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(oauth_client_path),
            SCOPES
        )
        
        # Run the flow - this will open browser for authentication
        creds = flow.run_local_server(port=port, open_browser=True)
        
        # Get user email from OAuth token/userinfo
        authenticated_email = None
        channel_info = {}
        
        try:
            # Try to get email from Google userinfo API
            userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
            headers = {'Authorization': f'Bearer {creds.token}'}
            userinfo_response = requests.get(userinfo_url, headers=headers)
            
            if userinfo_response.status_code == 200:
                userinfo = userinfo_response.json()
                authenticated_email = userinfo.get('email')
        except Exception:
            pass
        
        # Also get channel info for display
        try:
            youtube = build(API_SERVICE_NAME, API_VERSION, credentials=creds)
            request = youtube.channels().list(part='snippet', mine=True)
            response = request.execute()
            
            if 'items' in response and len(response['items']) > 0:
                channel_info = response['items'][0]['snippet']
        except HttpError:
            pass
        
        # Use provided account_email as fallback if we couldn't extract email
        if not authenticated_email:
            authenticated_email = account_email or 'unknown@example.com'
        
        # Save the token using the authenticated email
        token_file = CREDENTIALS_DIR / f'{authenticated_email}_token.json'
        token_file.parent.mkdir(exist_ok=True)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
        
        # Copy OAuth client to account-specific credentials if it doesn't exist
        account_credentials = CREDENTIALS_DIR / f'{authenticated_email}_credentials.json'
        if not account_credentials.exists():
            import shutil
            shutil.copy2(oauth_client_path, account_credentials)
        
        return {
            'status': 'success',
            'account_email': authenticated_email,  # Use extracted email
            'token_file': str(token_file),
            'channel_info': channel_info,
            'authenticated_email': authenticated_email
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'account_email': account_email
        }


def check_authentication_status(account_email):
    """
    Check if an account is already authenticated.
    
    Args:
        account_email: Email address for the account
    
    Returns:
        dict: Status information
    """
    token_file = CREDENTIALS_DIR / f'{account_email}_token.json'
    
    if not token_file.exists():
        return {
            'authenticated': False,
            'message': 'Not authenticated'
        }
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        
        if creds and creds.valid:
            return {
                'authenticated': True,
                'message': 'Authenticated and valid'
            }
        elif creds and creds.expired and creds.refresh_token:
            return {
                'authenticated': True,
                'expired': True,
                'message': 'Authenticated but expired (can be refreshed)'
            }
        else:
            return {
                'authenticated': False,
                'message': 'Token exists but invalid'
            }
    except Exception as e:
        return {
            'authenticated': False,
            'error': str(e),
            'message': 'Error checking authentication'
        }


def start_oauth_flow(account_email, oauth_client_path=None, redirect_uri=None):
    """
    Start OAuth flow by generating authorization URL (for web-based flow).
    
    Args:
        account_email: Email address for the account to authenticate
        oauth_client_path: Path to OAuth client credentials (optional, will auto-detect)
        redirect_uri: Redirect URI for OAuth callback (e.g., http://localhost:8080/oauth/callback)
    
    Returns:
        dict: Authorization URL and state
    """
    if oauth_client_path is None:
        oauth_client_path = get_oauth_client_path()
        if oauth_client_path is None:
            raise FileNotFoundError(
                "No OAuth client credentials found. "
                "Please add at least one credentials file first, or create oauth_client.json"
            )
    
    oauth_client_path = Path(oauth_client_path)
    if not oauth_client_path.exists():
        raise FileNotFoundError(f"OAuth client file not found: {oauth_client_path}")
    
    if redirect_uri is None:
        raise ValueError("redirect_uri is required for web-based OAuth flow")
    
    # Create OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(
        str(oauth_client_path),
        SCOPES
    )
    
    # Set redirect URI
    flow.redirect_uri = redirect_uri
    
    # Generate authorization URL
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force consent screen to get refresh token
    )
    
    return {
        'authorization_url': authorization_url,
        'state': state,
        'account_email': account_email
    }


def complete_oauth_flow(account_email, authorization_code, oauth_client_path=None, redirect_uri=None, state=None):
    """
    Complete OAuth flow by exchanging authorization code for tokens.
    
    Args:
        account_email: Email address for the account
        authorization_code: Authorization code from OAuth callback
        oauth_client_path: Path to OAuth client credentials (optional, will auto-detect)
        redirect_uri: Redirect URI used in authorization (must match)
        state: State parameter from authorization (for verification)
    
    Returns:
        dict: Result with status and account info
    """
    if oauth_client_path is None:
        oauth_client_path = get_oauth_client_path()
        if oauth_client_path is None:
            raise FileNotFoundError(
                "No OAuth client credentials found. "
                "Please add at least one credentials file first, or create oauth_client.json"
            )
    
    oauth_client_path = Path(oauth_client_path)
    if not oauth_client_path.exists():
        raise FileNotFoundError(f"OAuth client file not found: {oauth_client_path}")
    
    if redirect_uri is None:
        raise ValueError("redirect_uri is required for web-based OAuth flow")
    
    # Paths for this account's token
    token_file = CREDENTIALS_DIR / f'{account_email}_token.json'
    
    try:
        # Create OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(oauth_client_path),
            SCOPES
        )
        flow.redirect_uri = redirect_uri
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=authorization_code)
        creds = flow.credentials
        
        # Get user email from OAuth token/userinfo
        authenticated_email = None
        channel_info = {}
        
        try:
            # Try to get email from Google userinfo API
            userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
            headers = {'Authorization': f'Bearer {creds.token}'}
            userinfo_response = requests.get(userinfo_url, headers=headers)
            
            if userinfo_response.status_code == 200:
                userinfo = userinfo_response.json()
                authenticated_email = userinfo.get('email')
        except Exception:
            pass
        
        # Also get channel info for display
        try:
            youtube = build(API_SERVICE_NAME, API_VERSION, credentials=creds)
            request = youtube.channels().list(part='snippet', mine=True)
            response = request.execute()
            
            if 'items' in response and len(response['items']) > 0:
                channel_info = response['items'][0]['snippet']
        except HttpError:
            pass
        
        # Use provided account_email as fallback if we couldn't extract email
        if not authenticated_email:
            authenticated_email = account_email or 'unknown@example.com'
        
        # Save the token using the authenticated email
        token_file = CREDENTIALS_DIR / f'{authenticated_email}_token.json'
        token_file.parent.mkdir(exist_ok=True)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
        
        # Copy OAuth client to account-specific credentials if it doesn't exist
        account_credentials = CREDENTIALS_DIR / f'{authenticated_email}_credentials.json'
        if not account_credentials.exists():
            import shutil
            shutil.copy2(oauth_client_path, account_credentials)
        
        return {
            'status': 'success',
            'account_email': authenticated_email,  # Use extracted email
            'token_file': str(token_file),
            'channel_info': channel_info,
            'authenticated_email': authenticated_email
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'account_email': account_email
        }

