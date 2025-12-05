# Starting the React Development Server

## Quick Start

### Option 1: Use the Startup Script (Easiest)

**Windows:**
- Double-click `start-dev.bat` in the frontend folder
- Or run: `.\start-dev.bat` in PowerShell

**PowerShell:**
- Run: `.\start-dev.ps1` in PowerShell

The script will:
1. Check if dependencies are installed (install if needed)
2. Create `.env` file if it doesn't exist
3. Start the development server

### Option 2: Manual Commands

1. **Install dependencies** (first time only):
   ```bash
   npm install
   ```

2. **Create `.env` file** (if it doesn't exist):
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

3. **Start the server**:
   ```bash
   npm run dev
   ```

## Troubleshooting

### "npm is not recognized"
- **Install Node.js**: Download from https://nodejs.org/
- **Restart your terminal** after installing Node.js
- **Verify installation**: Run `node --version` and `npm --version`

### "Port already in use"
- Vite will automatically try the next port (5174, 5175, etc.)
- Or stop the process using port 5173
- Or specify a port: `npm run dev -- --port 3000`

### "Cannot find module"
- Delete `node_modules` folder
- Delete `package-lock.json`
- Run `npm install` again

### API Connection Issues
- Make sure Django backend is running
- Check `.env` file has correct `VITE_API_BASE_URL`
- Check CORS settings on Django backend

## Expected Output

When the server starts successfully, you should see:

```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h to show help
```

Then open `http://localhost:5173` in your browser!

## Next Steps

1. Open browser to the URL shown (usually http://localhost:5173)
2. You should see the login page
3. Log in with your Django credentials
4. Select a tenant from the sidebar
5. Start exploring the app!

