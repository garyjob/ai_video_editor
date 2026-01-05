#!/usr/bin/env python3
"""
Command-line interface for YouTube video uploads.

Usage:
    python upload_cli.py <video_file> --account <email> --title "Title" [options]

Example:
    python upload_cli.py video.mp4 --account admin@truesight.me --title "My Video" --description "Description" --privacy public
"""

import argparse
import sys
from pathlib import Path
from youtube_uploader import YouTubeUploader, get_available_accounts


def main():
    parser = argparse.ArgumentParser(
        description='Upload video to YouTube',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload to default account (admin@truesight.me)
  python upload_cli.py video.mp4 --account admin@truesight.me --title "My Video"
  
  # Upload to garyjob@gmail.com account
  python upload_cli.py video.mp4 --account garyjob@gmail.com --title "My Video" --privacy unlisted
  
  # Upload with tags and description
  python upload_cli.py video.mp4 --account admin@truesight.me --title "My Video" \\
      --description "Video description" --tags tag1 tag2 tag3 --privacy public
        """
    )
    
    parser.add_argument('video_file', help='Path to video file')
    parser.add_argument('--account', required=True, help='YouTube account email (e.g., admin@truesight.me)')
    parser.add_argument('--title', required=True, help='Video title')
    parser.add_argument('--description', default='', help='Video description')
    parser.add_argument('--privacy', choices=['public', 'unlisted', 'private'], 
                       default='public', help='Privacy setting (default: public)')
    parser.add_argument('--tags', nargs='+', help='Video tags (space-separated)')
    parser.add_argument('--list-accounts', action='store_true', 
                       help='List available accounts and exit')
    
    args = parser.parse_args()
    
    # List accounts if requested
    if args.list_accounts:
        accounts = get_available_accounts()
        if accounts:
            print("Available YouTube accounts:")
            for account in accounts:
                print(f"  - {account}")
        else:
            print("No accounts configured.")
            print("Add credentials as: credentials/{email}_credentials.json")
        sys.exit(0)
    
    # Validate video file
    video_path = Path(args.video_file)
    if not video_path.exists():
        print(f"❌ Error: Video file not found: {args.video_file}")
        sys.exit(1)
    
    # Check if account exists
    accounts = get_available_accounts()
    if args.account not in accounts:
        print(f"❌ Error: Account '{args.account}' not found.")
        print(f"Available accounts: {', '.join(accounts) if accounts else 'none'}")
        print(f"Add credentials as: credentials/{args.account}_credentials.json")
        sys.exit(1)
    
    # Upload video
    print(f"🔐 Authenticating with YouTube account: {args.account}")
    uploader = YouTubeUploader(args.account)
    
    try:
        print(f"📤 Uploading: {video_path.name}")
        print(f"   Title: {args.title}")
        print(f"   Privacy: {args.privacy}")
        print(f"   File size: {video_path.stat().st_size / (1024*1024):.1f} MB")
        print()
        
        # Collect upload progress
        last_progress = 0
        for result in uploader.upload_video(
            str(video_path), 
            args.title, 
            args.description, 
            args.privacy, 
            args.tags
        ):
            if result.get('status') == 'uploading':
                progress = result.get('progress', 0)
                if progress != last_progress:
                    print(f"\r   Upload progress: {progress}%", end='', flush=True)
                    last_progress = progress
            elif result.get('status') == 'complete':
                print(f"\n✅ Upload complete!")
                video_id = result.get('video_id')
                video_url = result.get('video_url')
                print(f"   Video ID: {video_id}")
                print(f"   URL: {video_url}")
                sys.exit(0)
            elif result.get('status') == 'error':
                print(f"\n❌ Error uploading video:")
                print(f"   {result.get('error', 'Unknown error')}")
                if result.get('error_details'):
                    print(f"   Details: {result.get('error_details')}")
                sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n❌ Upload cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()


