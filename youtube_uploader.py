#!/usr/bin/env python3
"""
YouTube uploader module with multi-account support.

This module handles uploading videos to YouTube using the YouTube Data API v3.
It supports multiple YouTube accounts and manages credentials per account.
"""

import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# OAuth 2.0 scopes required for uploading videos
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Base directory for credentials
BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / 'credentials'
CREDENTIALS_DIR.mkdir(exist_ok=True)


class YouTubeUploader:
    """YouTube uploader with multi-account support."""
    
    def __init__(self, account_email):
        """
        Initialize YouTube uploader for a specific account.
        
        Args:
            account_email: Email address identifying the YouTube account
        """
        self.account_email = account_email
        self.credentials_file = CREDENTIALS_DIR / f'{account_email}_credentials.json'
        self.token_file = CREDENTIALS_DIR / f'{account_email}_token.json'
        
    def get_authenticated_service(self):
        """Get authenticated YouTube service for this account."""
        creds = None
        
        # Load existing token if available
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        
        # If no valid credentials, run OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found at {self.credentials_file}. "
                        f"Please add OAuth2 credentials for {self.account_email}."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        return build(API_SERVICE_NAME, API_VERSION, credentials=creds)
    
    def upload_video(self, video_file, title, description='', privacy='public', tags=None, category_id='24'):
        """
        Upload a video to YouTube.
        
        Args:
            video_file: Path to video file
            title: Video title
            description: Video description (default: '')
            privacy: Privacy setting - 'public', 'unlisted', or 'private' (default: 'public')
            tags: List of video tags (default: None)
            category_id: YouTube category ID (default: '24' for People & Blogs)
        
        Returns:
            dict: Upload response with video ID and URL, or None if failed
        """
        video_path = Path(video_file)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_file}")
        
        youtube = self.get_authenticated_service()
        
        # Video metadata
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Create media upload request
        media = MediaFileUpload(
            str(video_path),
            chunksize=-1,
            resumable=True,
            mimetype='video/mp4'
        )
        
        # Insert video
        try:
            insert_request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Execute upload
            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    yield {'status': 'uploading', 'progress': progress}
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            yield {
                'status': 'complete',
                'video_id': video_id,
                'video_url': video_url,
                'response': response
            }
            
        except HttpError as e:
            error_details = json.loads(e.content.decode('utf-8'))
            yield {
                'status': 'error',
                'error': str(e),
                'error_details': error_details
            }


def get_available_accounts():
    """Get list of available YouTube accounts (accounts with credentials files)."""
    accounts = []
    for file in CREDENTIALS_DIR.glob('*_credentials.json'):
        account_email = file.stem.replace('_credentials', '')
        accounts.append(account_email)
    return sorted(accounts)


def add_account(account_email, credentials_json_path):
    """
    Add a new YouTube account by copying credentials file.
    
    Args:
        account_email: Email address for the account
        credentials_json_path: Path to OAuth2 credentials JSON file
    """
    source = Path(credentials_json_path)
    if not source.exists():
        raise FileNotFoundError(f"Credentials file not found: {credentials_json_path}")
    
    dest = CREDENTIALS_DIR / f'{account_email}_credentials.json'
    import shutil
    shutil.copy2(source, dest)
    return dest

