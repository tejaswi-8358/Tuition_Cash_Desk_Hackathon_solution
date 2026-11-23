# Tuition Cash Desk

A back office for home tutors that tracks invoices, payments, overdue chasing, bills and a 90-day cash forecast with what-if scenarios. Sample data is labelled as sample in the app.

## Prerequisites

- Python 3.9+
- Node.js 18+ with npm

## 1. Start the API

```powershell
cd backend
python -m pip install -r requirements.txt
python -m app.seed
python -m uvicorn app.main:app --port 8000
```

- `python -m app.seed` resets the database and loads sample data.
- The API runs at http://127.0.0.1:8000 and the interactive docs at http://127.0.0.1:8000/docs.

## 2. Start the web app

Open a **new terminal** (leave the API running in the first one):

```powershell
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. Use `localhost` rather than `127.0.0.1`, because the API allows that origin.

## Production build check

```powershell
cd frontend
npm run build
```
## Features
Today: a daily overview with overdue totals, alerts, and a chase list. Send WhatsApp reminders or copy the message.
Dashboard: headline numbers (outstanding, overdue, received this month, customers), an aging chart, and an overdue table.
Invoices: create invoices with line items, filter by status, search by customer.
Invoice detail: record payments (cash, bank, UPI, other), see balance updates, and review reminder history.
Customers: outstanding and overdue balance per student, with a default payment delay for each customer.
Forecast: 30/60/90-day cash projection with a baseline and a scenario line, a safe-balance level, and what-if tests (late payment, expense increase, customer leaving).
Bills: recurring and one-off expenses, which can be paused or reactivated.
Settings: business name, currency symbol, opening cash, and safe balance.
Tech stack
Backend: Python, FastAPI, SQLAlchemy 2
Frontend: React 18, Vite, React Router, Recharts
Database: SQLite, stored at backend/data/app.db

