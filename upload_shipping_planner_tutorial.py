#!/usr/bin/env python3
"""
Upload the Shipping Planner tutorial video to the TrueSight DAO YouTube channel.
Run from video_editor directory: python upload_shipping_planner_tutorial.py
"""
import sys
from pathlib import Path

# Add video_editor to path
sys.path.insert(0, str(Path(__file__).parent))

from youtube_uploader import YouTubeUploader

VIDEO_PATH = Path.home() / "Downloads" / "how_to_use_shipping_planner.mp4"
ACCOUNT = "admin@truesight.me"  # TrueSight DAO YouTube channel

TITLE = "How to Use the Shipping Planner | TrueSight DAO DApp"
DESCRIPTION = """Learn how to use the TrueSight DAO Shipping Planner to select inventory items and calculate shipping costs for local (USPS via EasyPost) or freight shipping.

🔗 Shipping Planner: https://dapp.truesight.me/shipping_planner.html

Features covered:
• Select member/manager and inventory items
• Choose shipping type (Local or Freight)
• Enter destination address for local shipping
• Calculate shipping cost estimates
• Save shipping manifest as PDF

TrueSight DAO: https://truesight.me"""
TAGS = ["TrueSight DAO", "shipping planner", "DApp", "logistics", "EasyPost", "freight", "inventory"]
PRIVACY = "public"

def main():
    if not VIDEO_PATH.exists():
        print(f"Video not found: {VIDEO_PATH}")
        sys.exit(1)

    print(f"Uploading to TrueSight DAO YouTube ({ACCOUNT})...")
    print(f"Video: {VIDEO_PATH.name} ({VIDEO_PATH.stat().st_size / 1e6:.1f} MB)")

    uploader = YouTubeUploader(ACCOUNT)
    for result in uploader.upload_video(
        str(VIDEO_PATH),
        title=TITLE,
        description=DESCRIPTION,
        privacy=PRIVACY,
        tags=TAGS,
    ):
        if result.get("status") == "uploading":
            print(f"  Progress: {result.get('progress', 0)}%")
        elif result.get("status") == "complete":
            print(f"\n✅ Upload complete!")
            print(f"   Video URL: {result.get('video_url')}")
        elif result.get("status") == "error":
            print(f"\n❌ Upload failed: {result.get('error')}")
            if result.get("error_details"):
                print(f"   Details: {result['error_details']}")
            sys.exit(1)

if __name__ == "__main__":
    main()
