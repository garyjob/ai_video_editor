#!/bin/bash
# Simple script to run the YouTube uploader web UI with virtual environment

cd "$(dirname "$0")"

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run setup first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Set port (default: 8080, override with PORT environment variable)
PORT=${PORT:-8080}

source venv/bin/activate
PORT=$PORT python app.py

