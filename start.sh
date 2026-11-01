#!/bin/bash
# FinIntel Platform — Local startup script
# Run from the finintel/ directory

set -e
echo "=== FinIntel Financial Analytics Platform v2.0 ==="
echo ""

# Start backend
echo "[1/2] Starting FastAPI backend on http://localhost:8000 ..."
cd backend
PYTHONPATH=src uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Wait for backend
sleep 3
echo "      Backend started (PID $BACKEND_PID)"

# Start frontend
echo "[2/2] Starting React frontend on http://localhost:3000 ..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "=== Platform running ==="
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

# Handle shutdown
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT INT TERM
wait
