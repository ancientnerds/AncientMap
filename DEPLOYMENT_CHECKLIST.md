# Deployment Checklist - AncientNerds.com

Print this and check off each item as you complete it.

---

## Phase 1: Pre-Deployment (Your Windows PC)

- [ ] Build frontend: `cd ancient-nerds-map && npm run build`
- [ ] Create `.env.production` with strong passwords (see guide)
- [ ] Generate API secret: `openssl rand -hex 64`
- [ ] Rotate/get new API keys (Flickr, Sketchfab, Cesium)
- [ ] Note your Contabo VPS IP address: `________________`

---

## Phase 2: Initial VPS Setup

### First Login (as root)
- [ ] SSH to VPS: `ssh root@YOUR_IP`
- [ ] Update system: `apt update && apt upgrade -y`
- [ ] Install basics: `apt install -y curl wget git vim nano htop unzip software-properties-common`
- [ ] Set hostname: `hostnamectl set-hostname ancientnerds-vps`

### Create User
- [ ] Create user: `adduser ancientnerds`
- [ ] Add to sudo: `usermod -aG sudo ancientnerds`
- [ ] Create project dir: `mkdir -p /home/ancientnerds/ancient-map`
- [ ] Set ownership: `chown -R ancientnerds:ancientnerds /home/ancientnerds/ancient-map`

---

## Phase 3: Firewall & Fail2ban

### UFW Firewall
- [ ] Install: `sudo apt install -y ufw`
- [ ] Default deny: `sudo ufw default deny incoming`
- [ ] Allow SSH: `sudo ufw allow 22/tcp`
- [ ] Allow HTTP: `sudo ufw allow 80/tcp`
- [ ] Allow HTTPS: `sudo ufw allow 443/tcp`
- [ ] Enable: `sudo ufw enable`
- [ ] Verify: `sudo ufw status`

### Fail2ban
- [ ] Install: `sudo apt install -y fail2ban`
- [ ] Copy config: `sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local`
- [ ] Edit `/etc/fail2ban/jail.local`:
  - [ ] Set `bantime = 24h` in `[sshd]`
- [ ] Start: `sudo systemctl enable --now fail2ban`

---

## Phase 4: Install Software

- [ ] Python 3.11: `sudo apt install -y python3.11 python3.11-venv python3.11-dev`
- [ ] Node.js 20: `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs`
- [ ] PostgreSQL 16: (see guide for full commands)
- [ ] PostGIS: `sudo apt install -y postgresql-16-postgis-3`
- [ ] Redis: `sudo apt install -y redis-server`
- [ ] Nginx: `sudo apt install -y nginx`
- [ ] Certbot: `sudo apt install -y certbot python3-certbot-nginx`

---

## Phase 5: Database Setup

- [ ] Access postgres: `sudo -u postgres psql`
- [ ] Create database: `CREATE DATABASE ancient_map;`
- [ ] Create user: `CREATE USER ancient_map WITH ENCRYPTED PASSWORD 'YOUR_PASSWORD';`
- [ ] Grant privileges: `GRANT ALL PRIVILEGES ON DATABASE ancient_map TO ancient_map;`
- [ ] Enable PostGIS: `\c ancient_map` then `CREATE EXTENSION postgis;`
- [ ] Edit pg_hba.conf to allow local connections
- [ ] Restart PostgreSQL: `sudo systemctl restart postgresql`
- [ ] Test connection: `psql -U ancient_map -d ancient_map -h localhost`

---

## Phase 6: Upload Files (Bitvise SFTP)

### Configure Bitvise
- [ ] Host: YOUR_VPS_IP
- [ ] Port: 22
- [ ] Username: ancientnerds
- [ ] Authentication: password

### Upload
- [ ] Upload `api/` folder
- [ ] Upload `pipeline/` folder
- [ ] Upload `scripts/` folder
- [ ] Upload `ancient-nerds-map/dist/` folder
- [ ] Upload `requirements.txt`
- [ ] Upload `.env.production` (rename to `.env` on server)
- [ ] Upload `data/` folder (if needed)

---

## Phase 7: Backend Setup

- [ ] Create venv: `python3.11 -m venv .venv`
- [ ] Activate: `source .venv/bin/activate`
- [ ] Install deps: `pip install -r requirements.txt`
- [ ] Rename env: `mv .env.production .env && chmod 600 .env`
- [ ] Init database: `python scripts/init_db.py`
- [ ] Test: `uvicorn api.main:app --host 127.0.0.1 --port 8000`

---

## Phase 8: Frontend Setup

- [ ] Create web dir: `sudo mkdir -p /var/www/ancientnerds.com`
- [ ] Copy files: `sudo cp -r ~/ancient-map/ancient-nerds-map/dist/* /var/www/ancientnerds.com/`
- [ ] Set ownership: `sudo chown -R www-data:www-data /var/www/ancientnerds.com`

---

## Phase 9: Nginx & SSL

### Nginx
- [ ] Create config: `/etc/nginx/sites-available/ancientnerds.com`
- [ ] Enable site: `sudo ln -s /etc/nginx/sites-available/ancientnerds.com /etc/nginx/sites-enabled/`
- [ ] Remove default: `sudo rm /etc/nginx/sites-enabled/default`
- [ ] Test: `sudo nginx -t`
- [ ] Reload: `sudo systemctl reload nginx`

### SSL Certificate
- [ ] Ensure DNS A record points to VPS IP
- [ ] Run certbot: `sudo certbot --nginx -d ancientnerds.com -d www.ancientnerds.com`
- [ ] Test renewal: `sudo certbot renew --dry-run`

---

## Phase 10: Systemd Services

- [ ] Create API service: `/etc/systemd/system/ancient-map-api.service`
- [ ] Create upload service: `/etc/systemd/system/ancient-map-upload.service`
- [ ] Reload daemon: `sudo systemctl daemon-reload`
- [ ] Enable services: `sudo systemctl enable ancient-map-api ancient-map-upload`
- [ ] Start services: `sudo systemctl start ancient-map-api ancient-map-upload`
- [ ] Verify: `sudo systemctl status ancient-map-api`

---

## Phase 11: Final Security

- [ ] Enable auto-updates: `sudo apt install -y unattended-upgrades`
- [ ] Configure unattended-upgrades
- [ ] Install rkhunter: `sudo apt install -y rkhunter`
- [ ] Add network hardening to `/etc/sysctl.conf`
- [ ] Create backup script
- [ ] Add backup cron job

---

## Final Verification

- [ ] Open https://ancientnerds.com in browser
- [ ] Check https://ancientnerds.com/api/health returns healthy
- [ ] Test SSL: https://www.ssllabs.com/ssltest/analyze.html?d=ancientnerds.com
- [ ] Check security headers: https://securityheaders.com/?q=ancientnerds.com
- [ ] Verify fail2ban is logging: `sudo fail2ban-client status sshd`

---

## Important Credentials (Store Securely!)

| Item | Value |
|------|-------|
| VPS IP | |
| SSH Port | 22 |
| SSH User | ancientnerds |
| SSH Password | |
| DB Name | ancient_map |
| DB User | ancient_map |
| DB Password | |
| API Secret Key | |

---

## Emergency Contacts

- Contabo Support: https://contabo.com/en/support/
- Let's Encrypt Status: https://letsencrypt.status.io/

---

*Completed Date: _______________*
