@echo off
REM ANCIENT NERDS - Research Platform - Database Setup Script for Windows
REM Run this after installing PostgreSQL

echo ============================================================
echo ANCIENT NERDS - Database Setup
echo ============================================================
echo.

REM Try to find PostgreSQL
set PGBIN=
if exist "C:\Program Files\PostgreSQL\16\bin\psql.exe" set PGBIN=C:\Program Files\PostgreSQL\16\bin
if exist "C:\Program Files\PostgreSQL\15\bin\psql.exe" set PGBIN=C:\Program Files\PostgreSQL\15\bin
if exist "C:\Program Files\PostgreSQL\14\bin\psql.exe" set PGBIN=C:\Program Files\PostgreSQL\14\bin

if "%PGBIN%"=="" (
    echo ERROR: PostgreSQL not found!
    echo.
    echo Please install PostgreSQL from:
    echo https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
    echo.
    echo Make sure to install PostGIS from Stack Builder after installation.
    pause
    exit /b 1
)

echo Found PostgreSQL at: %PGBIN%
echo.

REM Set password for non-interactive use
set PGPASSWORD=postgres

echo Creating user 'ancient_map'...
"%PGBIN%\psql" -U postgres -c "CREATE USER ancient_map WITH PASSWORD 'ancient_map_dev_password';" 2>nul
if %errorlevel% neq 0 echo User may already exist, continuing...

echo Creating database 'ancient_map'...
"%PGBIN%\psql" -U postgres -c "CREATE DATABASE ancient_map OWNER ancient_map;" 2>nul
if %errorlevel% neq 0 echo Database may already exist, continuing...

echo Granting privileges...
"%PGBIN%\psql" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE ancient_map TO ancient_map;"

echo.
echo Enabling PostGIS extension...
"%PGBIN%\psql" -U postgres -d ancient_map -c "CREATE EXTENSION IF NOT EXISTS postgis;"
if %errorlevel% neq 0 (
    echo.
    echo ERROR: PostGIS extension not found!
    echo.
    echo Please install PostGIS:
    echo 1. Run Stack Builder from Start Menu
    echo 2. Select your PostgreSQL installation
    echo 3. Choose Spatial Extensions ^> PostGIS
    echo.
    pause
    exit /b 1
)

echo Enabling pg_trgm extension...
"%PGBIN%\psql" -U postgres -d ancient_map -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

echo Enabling uuid-ossp extension...
"%PGBIN%\psql" -U postgres -d ancient_map -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"

echo.
echo ============================================================
echo Database setup complete!
echo ============================================================
echo.
echo Now run:
echo   python scripts/init_db.py
echo   python -m pipeline.main ingest all
echo.
pause
