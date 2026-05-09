#!/bin/bash
# Daily ASO niche scan — triggered by launchd at 09:00 Chișinău time.
# Logs go to logs/daily-YYYY-MM-DD.log next to this script.

set -e

PROJECT_DIR="/Users/mihaww/Desktop/aso-niche-finder"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/daily-$(date +%Y-%m-%d).log"

cd "$PROJECT_DIR"

ADAM_ID="6746982805"
COUNTRY="RO"
USER_ID="1789c9b1-73e7-4653-a6b7-01470694e825"

echo "=== $(date) — daily ASO niche scan starting ===" >> "$LOG_FILE"

/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -c "
import sys, datetime
sys.path.insert(0, '.')
from core.pipeline import run_pipeline, default_output_path
from core.app_lookup import get_app_name
from bot.telegram_sender import send_document

adam_id = '${ADAM_ID}'
country = '${COUNTRY}'

output_path = default_output_path(adam_id, country)
stats = run_pipeline(adam_id, country, output_path, user_id='${USER_ID}', record=True)

if stats['new_keywords'] == 0:
    print('No new keywords today — skipping Telegram send')
    sys.exit(0)

app_name = get_app_name(adam_id, country=country)
caption = (
    f'🎯 ASO Daily Report\n'
    f'\n'
    f'📱 App: {app_name}\n'
    f'🌍 Country: {country}\n'
    f'📅 {datetime.date.today().isoformat()}\n'
    f'\n'
    f'🆕 New keywords discovered: {stats[\"new_keywords\"]}'
)
send_document(output_path, caption=caption)
print('Sent to Telegram')
" >> "$LOG_FILE" 2>&1

echo "=== $(date) — done ===" >> "$LOG_FILE"
