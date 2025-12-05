# Starting Django Development Server

The startup scripts automatically detect and use the available Python installation on your system.

## Automatic Detection

The scripts will try to find Python in this order:

1. **Python in PATH** (system Python or activated conda environment)
2. **Conda environment** (`nordenv` at `C:\Users\dcaffaro\Anaconda3\envs\nordenv\`)
3. **Python launcher** (`py` command on Windows)
4. **Common Python installation paths**

## Quick Start

### Option 1: Batch File (Works on all Windows)
Double-click `start-django-server.bat`

### Option 2: PowerShell Script
```powershell
.\start-django.ps1
```

### Option 3: Manual (If Python is in PATH)
```bash
python manage.py runserver
```

### Option 4: With Conda (If using conda)
```bash
conda activate nordenv
python manage.py runserver
```

## Server Details

- **URL**: `http://127.0.0.1:8000/` or `http://localhost:8000/`
- **API Base**: `http://localhost:8000/`
- **Login Endpoint**: `http://localhost:8000/login/`
- **Tenant API Pattern**: `http://localhost:8000/{tenant_subdomain}/api/...`

## Troubleshooting

### "Python not found"
- Make sure Python is installed
- Add Python to your PATH, OR
- Use conda: `conda activate nordenv`
- Or use the batch file which handles detection automatically

### "Module not found" errors
- Make sure you're in the correct conda environment (if using conda)
- Install dependencies: `pip install -r requirements.txt`

### Port already in use
- Stop any other Django server running on port 8000
- Or specify a different port: `python manage.py runserver 8001`

## Integration with React

1. **Start Django**: Use one of the methods above
2. **Start React**: 
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
3. **Configure**: Make sure `frontend/.env` has:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

Both servers should now be running and communicating!

