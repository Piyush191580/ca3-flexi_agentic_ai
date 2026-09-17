@echo off
cd /d "C:\Users\Administrator\Music\Automated_Vaccination_Reminder_System_Final_UI_Fixed"
echo Initializing database...
"C:\ProgramData\anaconda3\python.exe" -c "import database; database.init_db()"
echo Starting Automated Vaccination Reminder System...
start "" /b "C:\ProgramData\anaconda3\python.exe" app.py
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:7860"
pause
