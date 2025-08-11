@echo off
:: Navigate to the Django project root
cd /d "%~dp0"

:: Step 1: Activate the Anaconda environment and start the Django server
start "Django Server" cmd /k "C:\Users\dcaffaro\Anaconda3\Scripts\activate.bat nordenv && python manage.py"


pause
