# Complete Deployment Guide: AncientMap to Contabo VPS

## Domain: ancientnerds.com | User: ancientnerds

---

## Table of Contents

1. [Pre-Deployment Checklist](#1-pre-deployment-checklist)
2. [Initial VPS Access & Security](#2-initial-vps-access--security)
3. [Create ancientnerds User](#3-create-ancientnerds-user)
4. [Firewall Setup (UFW)](#4-firewall-setup-ufw)
5. [Fail2ban Installation](#5-fail2ban-installation)
6. [Install Required Software](#6-install-required-software)
7. [Database Setup (PostgreSQL + PostGIS)](#7-database-setup-postgresql--postgis)
8. [Upload Project via Bitvise SFTP](#8-upload-project-via-bitvise-sftp)
9. [Backend Deployment (FastAPI)](#9-backend-deployment-fastapi)
10. [Frontend Deployment (React)](#10-frontend-deployment-react)
11. [Nginx Configuration](#11-nginx-configuration)
12. [SSL/HTTPS with Let's Encrypt](#12-sslhttps-with-lets-encrypt)
13. [Domain Configuration](#13-domain-configuration)
14. [Systemd Services](#14-systemd-services)
15. [Security Hardening Checklist](#15-security-hardening-checklist)
16. [Monitoring & Maintenance](#16-monitoring--maintenance)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Pre-Deployment Checklist

### On Your Local Machine (Windows)

Before uploading, you need to:

#### 1.1 Create Production Environment File

Create a new file `.env.production` (DO NOT upload .env with dev passwords):

```bash
# Database - USE STRONG PASSWORDS
POSTGRES_USER=ancient_map
POSTGRES_PASSWORD=YOUR_SUPER_STRONG_PASSWORD_HERE_32_CHARS
POSTGRES_DB=ancient_map
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false
API_RELOAD=false
API_SECRET_KEY=GENERATE_WITH_openssl_rand_hex_64

# CORS - Your domain
API_CORS_ORIGINS=https://ancientnerds.com,https://www.ancientnerds.com

# Rate Limiting
RATE_LIMIT_ANONYMOUS=100
RATE_LIMIT_FREE=1000
RATE_LIMIT_PRO=50000
RATE_LIMIT_ENTERPRISE=0

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Data directories
DATA_RAW_DIR=/home/ancientnerds/ancient-map/data/raw
DATA_PROCESSED_DIR=/home/ancientnerds/ancient-map/data/processed
LOG_LEVEL=WARNING

# External API Keys (rotate these!)
SKETCHFAB_API_KEY=your_new_sketchfab_key
MAPBOX_ACCESS_TOKEN=your_mapbox_token
TURNSTILE_SECRET_KEY=your_production_turnstile_key
```

#### 1.2 Build Frontend for Production

```powershell
cd C:\PythonProjects\AncientMap\ancient-nerds-map
npm install
npm run build
```

This creates the `dist/` folder ready for deployment.

#### 1.3 Files to NOT Upload

Create or update `.gitignore` and ensure these are NOT uploaded:
- `.env` (contains dev secrets)
- `config.json` (contains API keys)
- `.venv/` (virtual environment)
- `node_modules/`
- `__pycache__/`
- `*.pyc`
- `backups/` (database backups)

---

## 2. Initial VPS Access & Security

### 2.1 First Login to Contabo VPS

Open Bitvise SSH Client:
1. Host: Your Contabo VPS IP (e.g., `123.456.789.0`)
2. Port: 22
3. Username: `root`
4. Password: From Contabo email

### 2.2 Update System Immediately

```bash
apt update && apt upgrade -y
apt install -y curl wget git vim nano htop unzip software-properties-common
```

### 2.3 Set Timezone and Hostname

```bash
# Set timezone
timedatectl set-timezone UTC

# Set hostname
hostnamectl set-hostname ancientnerds-vps

# Update hosts file
echo "127.0.0.1 ancientnerds-vps" >> /etc/hosts
```

---

## 3. Create ancientnerds User

### 3.1 Create User with Sudo Privileges

```bash
# Create user
adduser ancientnerds

# You'll be prompted for:
# - Password (use a STRONG password, 16+ characters)
# - Full Name: Ancient Nerds Admin
# - Room Number: (press Enter)
# - Work Phone: (press Enter)
# - Home Phone: (press Enter)
# - Other: (press Enter)
# - Is the information correct? Y

# Add to sudo group
usermod -aG sudo ancientnerds

# Verify sudo access
su - ancientnerds
sudo whoami  # Should output: root
exit
```

### 3.2 Create Project Directory

```bash
# As root
mkdir -p /home/ancientnerds/ancient-map
chown -R ancientnerds:ancientnerds /home/ancientnerds/ancient-map
```

---

## 4. Firewall Setup (UFW)

```bash
# Login as ancientnerds
sudo apt install -y ufw

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp comment 'SSH'

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# Enable UFW
sudo ufw enable

# Check status
sudo ufw status verbose
```

Expected output:
```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere       # SSH
80/tcp                     ALLOW       Anywhere       # HTTP
443/tcp                    ALLOW       Anywhere       # HTTPS
```

---

## 5. Fail2ban Installation

```bash
sudo apt install -y fail2ban

# Create local config (never edit main config)
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Edit local config
sudo nano /etc/fail2ban/jail.local
```

Find and modify the `[sshd]` section:

```ini
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 3
banaction = ufw

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 24h
```

Add Nginx protection (add at end of file):

```ini
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
bantime = 1h

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 1h

[nginx-botsearch]
enabled = true
filter = nginx-botsearch
port = http,https
logpath = /var/log/nginx/access.log
maxretry = 2
bantime = 24h
```

```bash
# Start and enable fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Check status
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

---

## 6. Install Required Software

### 7.1 Python 3.11+

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

### 7.2 Node.js 20 LTS

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version  # Should show v20.x.x
```

### 7.3 PostgreSQL 16 with PostGIS

```bash
# Add PostgreSQL repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt update

# Install PostgreSQL and PostGIS
sudo apt install -y postgresql-16 postgresql-16-postgis-3 postgresql-client-16
```

### 7.4 Redis

```bash
sudo apt install -y redis-server

# Configure Redis
sudo nano /etc/redis/redis.conf
```

Find and modify:
```
supervised systemd
maxmemory 256mb
maxmemory-policy allkeys-lru
```

```bash
sudo systemctl enable redis-server
sudo systemctl restart redis-server
```

### 7.5 Nginx

```bash
sudo apt install -y nginx
sudo systemctl enable nginx
```

### 7.6 Certbot for SSL

```bash
sudo apt install -y certbot python3-certbot-nginx
```

---

## 7. Database Setup (PostgreSQL + PostGIS)

### 8.1 Configure PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql
```

In PostgreSQL prompt:

```sql
-- Create database
CREATE DATABASE ancient_map;

-- Create user with strong password
CREATE USER ancient_map WITH ENCRYPTED PASSWORD 'YOUR_SUPER_STRONG_PASSWORD_32_CHARS';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ancient_map TO ancient_map;

-- Connect to database
\c ancient_map

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO ancient_map;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ancient_map;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ancient_map;

-- Exit
\q
```

### 8.2 Configure PostgreSQL Authentication

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

Add this line (after the existing local entries):
```
local   ancient_map     ancient_map                             md5
host    ancient_map     ancient_map     127.0.0.1/32            md5
```

```bash
# Restart PostgreSQL
sudo systemctl restart postgresql
```

### 8.3 Test Connection

```bash
psql -U ancient_map -d ancient_map -h localhost -W
# Enter your password
# Run: SELECT PostGIS_Version();
# Exit: \q
```

---

## 8. Upload Project via Bitvise SFTP

### 9.1 Prepare Files for Upload

On your Windows machine, organize files:

```
Files to Upload:
├── api/                    (entire folder)
├── pipeline/               (entire folder)
├── scripts/                (entire folder)
├── ancient-nerds-map/dist/ (built frontend only!)
├── data/                   (if you have processed data)
├── logo/                   (branding assets)
├── requirements.txt
├── upload_server.py
├── .env.production         (rename to .env on server)
└── config.json.production  (create sanitized version)
```

### 8.2 Configure Bitvise for SFTP

In Bitvise SSH Client:
1. Go to "Login" tab
2. Host: your-vps-ip
3. Port: 22
4. Username: ancientnerds
5. Initial method: password
6. Password: your ancientnerds user password

### 8.3 Upload via Bitvise SFTP

1. Open Bitvise SSH Client
2. Click "Log in" to connect
3. Click "New SFTP Window" button
4. Navigate to `/home/ancientnerds/ancient-map/` on the right panel
5. Drag and drop files from left panel (your local PC)

**Upload order:**
1. First: `requirements.txt`
2. Then: `api/`, `pipeline/`, `scripts/` folders
3. Then: `ancient-nerds-map/dist/` folder
4. Then: `data/` folder (if large, consider using rsync instead)
5. Finally: `.env.production` (rename to `.env` on server)

### 8.4 Alternative: Use rsync for Large Files

On Windows with WSL or Git Bash:

```bash
rsync -avz --progress \
  /c/PythonProjects/AncientMap/ \
  ancientnerds@YOUR_VPS_IP:/home/ancientnerds/ancient-map/ \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='config.json'
```

---

## 9. Backend Deployment (FastAPI)

### 10.1 Create Python Virtual Environment

```bash
cd /home/ancientnerds/ancient-map

# Create venv with Python 3.11
python3.11 -m venv .venv

# Activate venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### 10.2 Rename Environment File

```bash
mv .env.production .env
chmod 600 .env  # Restrict permissions
```

### 10.3 Initialize Database

```bash
# Run database initialization script
python scripts/init_db.py
```

### 10.4 Test FastAPI Locally

```bash
# Test run
cd /home/ancientnerds/ancient-map
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8000

# In another SSH session, test:
curl http://127.0.0.1:8000/health
# Should return: {"status":"healthy"}

# Ctrl+C to stop
```

---

## 10. Frontend Deployment (React)

### 11.1 Move Built Files

```bash
# Create web root directory
sudo mkdir -p /var/www/ancientnerds.com

# Move dist files
sudo cp -r /home/ancientnerds/ancient-map/ancient-nerds-map/dist/* /var/www/ancientnerds.com/

# Set ownership
sudo chown -R www-data:www-data /var/www/ancientnerds.com

# Set permissions
sudo chmod -R 755 /var/www/ancientnerds.com
```

### 11.2 Update Frontend Config for Production

If your frontend has API URL configuration, ensure it points to:
- `https://ancientnerds.com/api` (we'll proxy this via Nginx)

---

## 11. Nginx Configuration

### 12.1 Create Nginx Config

```bash
sudo nano /etc/nginx/sites-available/ancientnerds.com
```

Paste this configuration:

```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
limit_conn_zone $binary_remote_addr zone=addr:10m;

# Upstream for FastAPI
upstream fastapi {
    server 127.0.0.1:8000;
    keepalive 32;
}

# HTTP - Redirect to HTTPS (will be enabled after SSL cert)
server {
    listen 80;
    listen [::]:80;
    server_name ancientnerds.com www.ancientnerds.com;

    # For Let's Encrypt verification
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS - Main server block
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ancientnerds.com www.ancientnerds.com;

    # SSL certificates (will be created by Certbot)
    ssl_certificate /etc/letsencrypt/live/ancientnerds.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ancientnerds.com/privkey.pem;

    # SSL Security Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Hide Nginx version
    server_tokens off;

    # Document root for React frontend
    root /var/www/ancientnerds.com;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript application/xml+rss application/atom+xml image/svg+xml;

    # Connection limits
    limit_conn addr 100;

    # Frontend - React SPA
    location / {
        limit_req zone=general burst=20 nodelay;
        try_files $uri $uri/ /index.html;

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # API Proxy to FastAPI
    location /api/ {
        limit_req zone=api burst=50 nodelay;

        # Remove /api prefix when proxying
        rewrite ^/api/(.*) /$1 break;

        proxy_pass http://fastapi;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    # Upload endpoint (if using upload_server.py)
    location /upload/ {
        limit_req zone=api burst=10 nodelay;
        client_max_body_size 10M;

        rewrite ^/upload/(.*) /$1 break;

        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Block common attack patterns
    location ~ /\. {
        deny all;
    }

    location ~* (\.php$|\.asp$|\.aspx$|\.jsp$|\.cgi$) {
        deny all;
    }

    # Logs
    access_log /var/log/nginx/ancientnerds.access.log;
    error_log /var/log/nginx/ancientnerds.error.log;
}
```

### 12.2 Enable Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/ancientnerds.com /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# If you see errors about SSL certs (expected - we'll create them next)
# Comment out the HTTPS server block temporarily for now
```

### 12.3 Temporary HTTP-only Config (for SSL setup)

Create a temporary config without SSL:

```bash
sudo nano /etc/nginx/sites-available/ancientnerds.com.temp
```

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name ancientnerds.com www.ancientnerds.com;

    root /var/www/ancientnerds.com;
    index index.html;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        rewrite ^/api/(.*) /$1 break;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Use temp config
sudo rm /etc/nginx/sites-enabled/ancientnerds.com
sudo ln -s /etc/nginx/sites-available/ancientnerds.com.temp /etc/nginx/sites-enabled/ancientnerds.com

# Create certbot webroot
sudo mkdir -p /var/www/certbot

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

---

## 12. SSL/HTTPS with Let's Encrypt

### 13.1 Ensure Domain Points to VPS

Before running Certbot, verify your domain resolves to your VPS:

```bash
dig ancientnerds.com +short
# Should show your VPS IP
```

### 13.2 Obtain SSL Certificate

```bash
sudo certbot --nginx -d ancientnerds.com -d www.ancientnerds.com
```

Certbot will prompt:
1. Enter email: your-email@example.com
2. Agree to terms: Y
3. Share email with EFF: N (optional)
4. Redirect HTTP to HTTPS: 2 (Yes)

### 13.3 Apply Full HTTPS Config

Now replace temporary config with full config:

```bash
sudo rm /etc/nginx/sites-enabled/ancientnerds.com
sudo ln -s /etc/nginx/sites-available/ancientnerds.com /etc/nginx/sites-enabled/ancientnerds.com
sudo nginx -t
sudo systemctl reload nginx
```

### 13.4 Test SSL Renewal

```bash
sudo certbot renew --dry-run
```

### 13.5 Set Up Auto-Renewal (automatic with systemd timer)

```bash
# Check timer is active
sudo systemctl status certbot.timer

# Should show: Active: active (waiting)
```

---

## 13. Domain Configuration

### 14.1 Contabo DNS Settings

Log into Contabo Control Panel:

1. Go to DNS Management
2. Select ancientnerds.com
3. Add/Edit these records:

```
Type    Name    Value                   TTL
A       @       YOUR_VPS_IP             3600
A       www     YOUR_VPS_IP             3600
AAAA    @       YOUR_VPS_IPv6           3600 (if applicable)
AAAA    www     YOUR_VPS_IPv6           3600 (if applicable)
```

### 14.2 Alternative: Use External DNS (Cloudflare - Recommended)

If using Cloudflare:

1. Add site to Cloudflare
2. Update nameservers at Contabo to Cloudflare's
3. Add A records in Cloudflare pointing to VPS
4. Enable proxy (orange cloud) for DDoS protection
5. Set SSL/TLS mode to "Full (strict)"

---

## 14. Systemd Services

### 15.1 FastAPI Service

```bash
sudo nano /etc/systemd/system/ancient-map-api.service
```

```ini
[Unit]
Description=AncientMap FastAPI Service
After=network.target postgresql.service redis.service
Requires=postgresql.service

[Service]
Type=simple
User=ancientnerds
Group=ancientnerds
WorkingDirectory=/home/ancientnerds/ancient-map
Environment="PATH=/home/ancientnerds/ancient-map/.venv/bin"
EnvironmentFile=/home/ancientnerds/ancient-map/.env
ExecStart=/home/ancientnerds/ancient-map/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

# Security
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/ancientnerds/ancient-map/data

[Install]
WantedBy=multi-user.target
```

### 15.2 Upload Server Service (Optional)

```bash
sudo nano /etc/systemd/system/ancient-map-upload.service
```

```ini
[Unit]
Description=AncientMap Upload Server
After=network.target ancient-map-api.service

[Service]
Type=simple
User=ancientnerds
Group=ancientnerds
WorkingDirectory=/home/ancientnerds/ancient-map
Environment="PATH=/home/ancientnerds/ancient-map/.venv/bin"
EnvironmentFile=/home/ancientnerds/ancient-map/.env
ExecStart=/home/ancientnerds/ancient-map/.venv/bin/python upload_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 15.3 Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable ancient-map-api
sudo systemctl enable ancient-map-upload

# Start services
sudo systemctl start ancient-map-api
sudo systemctl start ancient-map-upload

# Check status
sudo systemctl status ancient-map-api
sudo systemctl status ancient-map-upload

# View logs
sudo journalctl -u ancient-map-api -f
sudo journalctl -u ancient-map-upload -f
```

---

## 15. Security Hardening Checklist

### 16.1 Automatic Security Updates

```bash
sudo apt install -y unattended-upgrades apt-listchanges

sudo dpkg-reconfigure -plow unattended-upgrades
# Select: Yes

# Configure
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

Ensure these lines are uncommented:
```
"${distro_id}:${distro_codename}-security";
```

### 16.2 Install Additional Security Tools

```bash
# Rootkit hunter
sudo apt install -y rkhunter
sudo rkhunter --update
sudo rkhunter --check --skip-keypress

# ClamAV antivirus
sudo apt install -y clamav clamav-daemon
sudo freshclam
```

### 16.3 Disable Unnecessary Services

```bash
# List enabled services
systemctl list-unit-files --state=enabled

# Disable if not needed
sudo systemctl disable cups.service       # Printing
sudo systemctl disable avahi-daemon.service  # Network discovery
```

### 16.4 Secure Shared Memory

```bash
sudo nano /etc/fstab
```

Add this line:
```
tmpfs     /run/shm     tmpfs     defaults,noexec,nosuid     0     0
```

### 16.5 Network Hardening

```bash
sudo nano /etc/sysctl.conf
```

Add:
```bash
# IP Spoofing protection
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Disable source packet routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0

# Ignore send redirects
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Block SYN attacks
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# Log Martians
net.ipv4.conf.all.log_martians = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
```

Apply:
```bash
sudo sysctl -p
```

---

## 16. Monitoring & Maintenance

### 17.1 Log Monitoring

```bash
# View authentication logs (SSH attempts)
sudo tail -f /var/log/auth.log

# View Nginx access logs
sudo tail -f /var/log/nginx/ancientnerds.access.log

# View API logs
sudo journalctl -u ancient-map-api -f

# View fail2ban logs
sudo tail -f /var/log/fail2ban.log
```

### 17.2 Database Backup Script

```bash
sudo nano /home/ancientnerds/scripts/backup_db.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/ancientnerds/backups"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="ancient_map_$DATE.sql.gz"

mkdir -p $BACKUP_DIR

pg_dump -U ancient_map -h localhost ancient_map | gzip > "$BACKUP_DIR/$FILENAME"

# Keep only last 7 days
find $BACKUP_DIR -name "ancient_map_*.sql.gz" -mtime +7 -delete

echo "Backup completed: $FILENAME"
```

```bash
chmod +x /home/ancientnerds/scripts/backup_db.sh

# Add to crontab (daily at 3 AM)
crontab -e
```

Add:
```
0 3 * * * /home/ancientnerds/scripts/backup_db.sh >> /home/ancientnerds/logs/backup.log 2>&1
```

### 17.3 Monitoring Tools (Optional)

```bash
# Install htop for system monitoring
sudo apt install -y htop

# Install ncdu for disk usage
sudo apt install -y ncdu

# Check disk usage
df -h
ncdu /

# Check memory
free -h

# Check running processes
htop
```

### 17.4 Log Rotation

Create custom log rotation:

```bash
sudo nano /etc/logrotate.d/ancient-map
```

```
/home/ancientnerds/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 ancientnerds ancientnerds
    sharedscripts
}
```

---

## 17. Troubleshooting

### 18.1 Common Issues

**Cannot SSH to server:**
- Use Contabo VNC console to access server
- Check `/var/log/auth.log` for errors
- Verify SSH is running: `systemctl status sshd`
- Check firewall allows port 22: `sudo ufw status`

**Nginx won't start:**
```bash
sudo nginx -t  # Check syntax
sudo tail -f /var/log/nginx/error.log
```

**FastAPI not responding:**
```bash
sudo systemctl status ancient-map-api
sudo journalctl -u ancient-map-api -n 50
curl http://127.0.0.1:8000/health
```

**Database connection refused:**
```bash
sudo systemctl status postgresql
sudo -u postgres psql -c "SELECT 1;"
```

**SSL certificate issues:**
```bash
sudo certbot certificates
sudo certbot renew --force-renewal
```

### 18.2 Useful Commands

```bash
# Check listening ports
sudo ss -tlnp

# Check firewall rules
sudo ufw status numbered

# Check fail2ban bans
sudo fail2ban-client status sshd

# Unban an IP
sudo fail2ban-client set sshd unbanip YOUR_IP

# Check disk space
df -h

# Check memory
free -h

# Find large files
sudo find / -type f -size +100M -exec ls -lh {} \;

# Check service logs
sudo journalctl -u SERVICE_NAME --since "1 hour ago"
```

---

## Quick Reference Card

### Essential URLs
- Website: https://ancientnerds.com
- API: https://ancientnerds.com/api
- Health Check: https://ancientnerds.com/api/health

### SSH Access
```bash
ssh ancientnerds@YOUR_VPS_IP
```

### Service Management
```bash
sudo systemctl {start|stop|restart|status} ancient-map-api
sudo systemctl {start|stop|restart|status} ancient-map-upload
sudo systemctl {start|stop|restart|status} nginx
sudo systemctl {start|stop|restart|status} postgresql
sudo systemctl {start|stop|restart|status} redis-server
```

### Logs
```bash
sudo journalctl -u ancient-map-api -f
sudo tail -f /var/log/nginx/ancientnerds.error.log
sudo tail -f /var/log/auth.log
```

### Security Checks
```bash
sudo ufw status
sudo fail2ban-client status
sudo rkhunter --check
```

---

## Security Best Practices Summary

1. **Never use root** - Always use ancientnerds user with sudo
2. **Strong password** - Use a complex password for ancientnerds user
3. **UFW firewall** - Only ports 22, 80, 443 open
4. **Fail2ban** - Auto-bans after 3 failed SSH attempts
5. **HTTPS everywhere** - SSL enforced via Let's Encrypt
6. **Security headers** - HSTS, CSP, X-Frame-Options
7. **Rate limiting** - Nginx limits prevent DDoS
8. **Automatic updates** - Security patches applied automatically
9. **Regular backups** - Daily database backups with 7-day retention
10. **Monitor logs** - Check /var/log/auth.log for suspicious activity

---

*Last updated: December 2024*
*For AncientMap Archaeological Research Platform*
