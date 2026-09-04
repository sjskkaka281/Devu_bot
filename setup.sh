#!/bin/bash
# -------------------------------------------------------------
# DEVU TELEGRAM BOT - 1-CLICK TERMUX INSTALLER
# -------------------------------------------------------------

echo "======================================================"
echo "    💖 DEVU TELEGRAM BOT INSTALLER FOR TERMUX 💖      "
echo "======================================================"
echo ""

# Update repositories and install dependencies
echo "[1/4] Termux packages update ho rahe hain..."
pkg update -y && pkg upgrade -y

echo "[2/4] Python aur zaroori tools install ho rahe hain..."
pkg install -y python git

echo "[3/4] Python libraries install ho rahi hain..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/4] Setup complete!"
echo "======================================================"
echo "Ab aap apna bot start karne ke liye ye command chalayein:"
echo "python bot.py"
echo "======================================================"
