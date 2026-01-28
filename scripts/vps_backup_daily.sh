#!/bin/bash
# Daily backup loop - run in screen: screen -S backup /var/www/ancientnerds/scripts/vps_backup_daily.sh

while true; do
    echo ""
    echo "=========================================="
    echo "Starting daily backup at $(date)"
    echo "=========================================="

    /var/www/ancientnerds/scripts/vps_backup.sh

    echo ""
    echo "Next backup in 24 hours..."
    echo "=========================================="

    sleep 86400  # 24 hours
done
