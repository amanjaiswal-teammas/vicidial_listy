from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import pymysql
import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse
from datetime import datetime
import jwt
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"

# Hardcoded credentials
USERS = {
    "admin": "admin123"
}

# DB config
DB_CONFIG = {
    "host": "43.224.137.235",
    "user": "root",
    "password": "India!@#123#12",
    "database": "asterisk",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/login")
def login(data: LoginRequest):
    if data.username in USERS and USERS[data.username] == data.password:
        token = jwt.encode(
            {"sub": data.username, "exp": datetime.utcnow().timestamp() + 86400},
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        return {"token": token, "username": data.username}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/list")
def get_list_data(from_date: str, to_date: str, payload=Depends(verify_token)):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT entry_date, source_id 
                FROM vicidial_list 
                WHERE list_id='33331' 
                AND DATE(entry_date) BETWEEN %s AND %s 
                ORDER BY entry_date DESC
            """
            cursor.execute(query, (from_date, to_date))
            rows = cursor.fetchall()
        conn.close()
        return {"data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/list/export")
def export_list_data(from_date: str, to_date: str, payload=Depends(verify_token)):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT entry_date, source_id 
                FROM vicidial_list 
                WHERE list_id='33331' 
                AND DATE(entry_date) BETWEEN %s AND %s 
                ORDER BY entry_date DESC
            """
            cursor.execute(query, (from_date, to_date))
            rows = cursor.fetchall()
        conn.close()

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["entry_date", "source_id"])

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="VicidialList")
        output.seek(0)

        filename = f"vicidial_list_{from_date}_to_{to_date}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
