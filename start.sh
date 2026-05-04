#!/bin/bash

echo "=== ViciDial Portal Startup ==="
echo ""

# Backend
echo "[1/2] Starting FastAPI backend..."
cd backend
pip install -r requirements.txt -q
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "    Backend PID: $BACKEND_PID"

cd ..

# Frontend
echo "[2/2] Starting React frontend..."
cd frontend
npm install --silent
npm run dev &
FRONTEND_PID=$!
echo "    Frontend PID: $FRONTEND_PID"

echo ""
echo "==================================="
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo "  Login    → admin / admin123"
echo "==================================="
echo ""
echo "Press Ctrl+C to stop both servers."

wait $BACKEND_PID $FRONTEND_PID
