# Django Development Server Startup Script
Write-Host "Starting Django Development Server..." -ForegroundColor Green
Write-Host ""

# Activate Anaconda environment and run Django
& C:\Users\dcaffaro\Anaconda3\Scripts\activate.bat nordenv
python manage.py runserver

