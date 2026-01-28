@echo off
REM Start Ollama limited to 14 CPU cores (leaving 2 free for web server)
REM Affinity 0x3FFF = cores 0-13 (14 cores)
echo Starting Ollama with CPU affinity (14 cores max)...
start /affinity 3FFF ollama serve
