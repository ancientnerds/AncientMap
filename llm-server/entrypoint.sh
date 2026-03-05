#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for Ollama server to start..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama server is ready"
        break
    fi
    sleep 2
done

# Pull models if not already present
MODEL_HEAVY="${OLLAMA_MODEL_HEAVY:-qwen3.5:4b}"
MODEL_FAST="${OLLAMA_MODEL_FAST:-qwen3.5:0.8b}"

echo "Ensuring heavy model: $MODEL_HEAVY"
ollama pull "$MODEL_HEAVY"

echo "Ensuring fast model: $MODEL_FAST"
ollama pull "$MODEL_FAST"

echo "Ensuring model: nomic-embed-text"
ollama pull nomic-embed-text

echo "All models ready ($MODEL_HEAVY + $MODEL_FAST + nomic-embed-text)"

# Keep the server running
wait $SERVER_PID
