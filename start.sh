#!/bin/bash
# -------------------------------------------------------------
# DEVU TELEGRAM BOT - AUTO RESTART RUNNER
# Keeps Devu running 24/7 and restarts if Termux sleeps or crashes.
# -------------------------------------------------------------

echo "Starting Devu Telegram Bot..."

while true; do
    python3 bot.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        echo "[!] Devu bot crashed with exit code $EXIT_CODE. Restarting in 5 seconds..."
        sleep 5
    else
        echo "[*] Devu bot stopped gracefully."
        break
    fi
done
