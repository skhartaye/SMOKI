@echo off
echo 🚀 Setting up SMOKi Website...

REM Backend setup
echo 🔧 Setting up backend...
cd backend
copy .env.example .env
echo ✏️  Please edit backend\.env with your database credentials
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
cd ..

REM Frontend setup
echo 🎨 Setting up frontend...
cd frontend
copy .env.example .env
npm install
cd ..

echo ✅ Setup complete!
echo.
echo 📋 Next steps:
echo 1. Edit backend\.env with your database credentials
echo 2. Edit frontend\.env with your backend URL (default: http://localhost:8000)
echo 3. Start backend: cd backend ^&^& venv\Scripts\activate ^&^& python -m uvicorn main:app --reload
echo 4. Start frontend: cd frontend ^&^& npm run dev
echo 5. Access: http://localhost:5173
echo.
echo 🔑 Default login: admin1234 / superadmin
pause