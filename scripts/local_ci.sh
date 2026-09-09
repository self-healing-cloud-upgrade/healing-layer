#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "======================================"
echo "    Niramay Local CI Pipeline         "
echo "======================================"

# 1. Run Backend Tests
echo "[1/3] Running Backend Tests..."
cd Niramay/backend

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1
pip install pytest pytest-asyncio > /dev/null 2>&1

pytest tests/
echo "✅ Backend tests passed!"
cd ../..

# 2. Run Frontend Tests
echo "[2/3] Running Frontend Tests..."
cd Niramay/frontend
npm install > /dev/null 2>&1
npm run test
echo "✅ Frontend tests passed!"
cd ../..

# 3. Simulate Docker Build
echo "[3/3] Simulating Docker Builds..."
echo "Building Backend Image..."
docker build -t niramay-backend:local Niramay/backend > /dev/null
echo "Building Frontend Image..."
docker build -t niramay-frontend:local Niramay/frontend > /dev/null
echo "✅ Docker images built successfully!"

echo "======================================"
echo " 🎉 All Checks Passed Successfully! 🎉"
echo "======================================"
