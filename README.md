# ViciDial Portal

React.js + FastAPI portal with login and vicidial_list export.

---

## Project Structure

```
project/
├── backend/
│   ├── main.py              # FastAPI app
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── App.css
        ├── main.jsx
        └── pages/
            ├── Login.jsx
            └── Dashboard.jsx
```

---

## Setup & Run

### 1. Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Backend runs at: http://localhost:8000

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:3000

---

## Login Credentials (Hardcoded)

| Username | Password  |
|----------|-----------|
| admin    | admin123  |

---

## Features

- **Login Page**: Secure JWT-based auth with hardcoded credentials
- **Sidebar Navigation**: "List" menu item
- **Date Filter**: From/To date picker to filter `entry_date`
- **Data Table**: Shows `entry_date` and `source_id` from `vicidial_list`
- **Export Excel**: Downloads filtered data as `.xlsx`

---

## Database Query (vicidial_list)

```sql
SELECT entry_date, source_id 
FROM vicidial_list 
WHERE list_id='33331' 
AND DATE(entry_date) BETWEEN :from_date AND :to_date 
ORDER BY entry_date DESC;
```

---

## API Endpoints

| Method | Endpoint              | Description             |
|--------|-----------------------|-------------------------|
| POST   | /api/login            | Login, returns JWT      |
| GET    | /api/list             | Fetch filtered data     |
| GET    | /api/list/export      | Export data to Excel    |

All `/api/list*` endpoints require `Authorization: Bearer <token>` header.
