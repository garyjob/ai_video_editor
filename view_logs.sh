#!/bin/bash
# Quick script to view application logs

LOG_DIR="logs"
TODAY=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/video_editor_$TODAY.log"

echo "📋 Video Editor Logs"
echo "===================="
echo ""

if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️  No log file found for today: $LOG_FILE"
    echo ""
    echo "Available log files:"
    ls -lh "$LOG_DIR"/video_editor_*.log 2>/dev/null | tail -5
    exit 1
fi

echo "📁 Log file: $LOG_FILE"
echo "📊 File size: $(du -h "$LOG_FILE" | cut -f1)"
echo ""

# Show options
case "${1:-tail}" in
    tail)
        echo "📝 Last 50 lines (use 'tail -f' for real-time):"
        echo "----------------------------------------"
        tail -50 "$LOG_FILE"
        ;;
    errors)
        echo "❌ Errors and Warnings:"
        echo "----------------------------------------"
        grep -E "(ERROR|WARNING|Exception|Traceback)" "$LOG_FILE" | tail -50
        ;;
    full)
        echo "📄 Full log file:"
        echo "----------------------------------------"
        cat "$LOG_FILE"
        ;;
    recent)
        echo "🕐 Last 100 lines:"
        echo "----------------------------------------"
        tail -100 "$LOG_FILE"
        ;;
    *)
        echo "Usage: $0 [tail|errors|full|recent]"
        echo ""
        echo "  tail    - Show last 50 lines (default)"
        echo "  errors  - Show only errors and warnings"
        echo "  full    - Show entire log file"
        echo "  recent  - Show last 100 lines"
        ;;
esac

