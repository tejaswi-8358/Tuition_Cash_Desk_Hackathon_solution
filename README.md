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

## Optional AI insights

Set your key and, optionally, the model in the terminal that runs uvicorn, before starting it:

```powershell
$env:ANTHROPIC_API_KEY = "your-key"
$env:ANTHROPIC_MODEL = "claude-haiku-4-5"
python -m uvicorn app.main:app --port 8000
```

Without a key the app shows rule-based insights instead, and labels them as rule-based. The model name is configurable because model identifiers change over time.

## Sample vs live data

- The app shows a banner when data is sample data.
- `python -m app.seed` creates sample records, marked `is_sample=true`.
- You can replace the sample records by creating your own records.
- Re-running the seed erases all data in `backend/data/app.db`.

## Known limitations

- Payments are recorded manually only. There is no bank or WhatsApp API. WhatsApp links open wa.me with a prefilled message, which the owner sends.
- There is no login. The app is single-owner and intended for local use only.
- `npm audit` reports 4 advisories in dependencies.
- The frontend bundle is about 620 kB.

## Tests

Backend tests are not yet written.
