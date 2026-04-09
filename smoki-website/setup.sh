#!/bin/bash

echo "🚀 Setting up SMOKi Website..."

# Create database
echo "📊 Setting up database..."
createdb smoki_db 2>/dev/null || echo "Database may already exist"

# Backend setup
echo "🔧 Setting up backend..."
cd backend
cp .env.example .env
echo "✏️  Please edit backend/.env with your database credentials"
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# Frontend setup
echo "🎨 Setting up frontend..."
cd frontend
cp .env.example .env
npm install
cd ..

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit backend/.env with your database credentials"
echo "2. Edit frontend/.env with your backend URL (default: http://localhost:8000)"
echo "3. Start backend: cd backend && source venv/bin/activate && python -m uvicorn main:app --reload"
echo "4. Start frontend: cd frontend && npm run dev"
echo "5. Access: http://localhost:5173"
echo ""
echo "🔑 Default login: admin1234 / superadmin"