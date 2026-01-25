#!/bin/bash

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment not found. Please create one first:"
    echo "  python -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Make sure you have set up your environment variables."
    echo "Required variables: DATABASE_URL, SECRET_KEY"
fi

# Run the backend server
echo "Starting backend server..."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
