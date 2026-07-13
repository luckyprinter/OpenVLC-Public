#!/bin/bash
echo "==================================================="
echo "OpenVLC System Suite - Linux/Mac Setup and Launcher"
echo "==================================================="
echo ""

# Check if python3 is installed
if ! command -v python3 &> /dev/null
then
    echo "[ERROR] python3 could not be found."
    echo "Please install Python 3.10+ using your package manager."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements
echo "[INFO] Installing required dependencies..."
pip install -r requirements.txt

# Launch the application
echo "[INFO] Launching OpenVLC..."
python3 run_v3.py

# Deactivate
deactivate
