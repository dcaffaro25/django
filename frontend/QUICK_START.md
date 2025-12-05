# Quick Start Guide

## Starting the React App

### Step 1: Install Dependencies

Open a terminal in the `frontend` directory and run:

```bash
npm install
```

This will install all required dependencies including:
- React, TypeScript, Vite
- shadcn/ui components
- React Query, React Router
- All other dependencies

### Step 2: Configure Environment Variables

Create a `.env` file in the `frontend` directory:

```env
VITE_API_BASE_URL=http://localhost:8000
```

**For production**, set this to your production API URL:
```env
VITE_API_BASE_URL=https://server-production-e754.up.railway.app
```

### Step 3: Start the Development Server

```bash
npm run dev
```

The app will start on `http://localhost:5173` (Vite default port).

### Step 4: Access the App

1. Open your browser to `http://localhost:5173`
2. You should see the login page
3. Log in with your credentials
4. Select a tenant from the sidebar dropdown
5. Start using the app!

## Troubleshooting

### npm not found
- Make sure Node.js is installed: https://nodejs.org/
- Restart your terminal after installing Node.js
- Try using `npx` or check if Node.js is in your PATH

### Port already in use
- Vite will automatically try the next available port
- Or specify a port: `npm run dev -- --port 3000`

### API Connection Issues
- Make sure your Django backend is running
- Check `VITE_API_BASE_URL` in `.env` matches your backend URL
- Check CORS settings on Django backend

### Missing Dependencies
- Delete `node_modules` and `package-lock.json`
- Run `npm install` again

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## Next Steps

1. **Login**: Use your Django user credentials
2. **Select Tenant**: Choose a tenant from the sidebar dropdown
3. **Explore**: Navigate through all the pages:
   - Accounting: Transactions, Journal Entries, Accounts
   - Banking: Bank Transactions, Reconciliation
   - Financial Statements
   - Billing: Business Partners, Products, Contracts
   - HR: Employees, Time Tracking, Payroll
   - Settings: Integration Rules, Substitution Rules

Enjoy testing the app! 🚀

