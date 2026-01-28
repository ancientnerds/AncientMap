#!/bin/bash
# VPS fix script - for initial setup/troubleshooting only
#
# SECURITY WARNING: This script modifies PostgreSQL authentication!
# Only use on fresh installs or when you understand the implications.
# Configure proper authentication (.env, .pgpass) after running.

set -e

echo "=== Fixing PostgreSQL ==="

# Fix pg_hba.conf
echo "local all all trust" > /etc/postgresql/16/main/pg_hba.conf
echo "host all all 127.0.0.1/32 trust" >> /etc/postgresql/16/main/pg_hba.conf
echo "host all all ::1/128 trust" >> /etc/postgresql/16/main/pg_hba.conf

# Enable TCP listening
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" /etc/postgresql/16/main/postgresql.conf
sed -i "s/listen_addresses = '\*'/listen_addresses = 'localhost'/" /etc/postgresql/16/main/postgresql.conf

# Restart
systemctl restart postgresql@16-main
sleep 3

echo "=== Creating .env from template ==="
cd /var/www/ancientnerds

if [ -f .env.example ]; then
    echo "Copying .env.example to .env"
    echo "IMPORTANT: Edit .env and add your own API keys and passwords!"
    cp .env.example .env
else
    echo "ERROR: .env.example not found. Please copy it from the repository."
    exit 1
fi

echo ""
echo "=== NEXT STEPS ==="
echo "1. Edit /var/www/ancientnerds/.env and configure:"
echo "   - POSTGRES_PASSWORD (generate a secure password)"
echo "   - MAPBOX_ACCESS_TOKEN (get from https://account.mapbox.com/access-tokens/)"
echo "   - Other API keys as needed (see .env.example)"
echo ""
echo "2. Then run:"
echo "   source .venv/bin/activate"
echo "   python -c \"from pipeline.database import create_all_tables; create_all_tables()\""
echo "   python -m pipeline.unified_loader --source ancient_nerds"
echo ""
echo "3. Start the API:"
echo "   uvicorn api.main:app --host 127.0.0.1 --port 8000"
