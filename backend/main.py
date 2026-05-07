from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
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

CS_CONFIG = {
    "host": "192.168.11.244",
    "user": "root",
    "password": "India!@#123#12",
    "database": "connection_store",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str


class DBCredentialCreate(BaseModel):
    host: str
    host_name: str
    user: str
    password: str
    database_name: str


class DBCredentialUpdate(BaseModel):
    host: Optional[str] = None
    host_name: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    database_name: Optional[str] = None


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def get_cs_connection():
    return pymysql.connect(**CS_CONFIG)

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
def get_list_data(date: str, payload=Depends(verify_token)):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT list_id, entry_date, source_id 
                FROM vicidial_list 
                WHERE list_id IN ('33331', '33332', '33333')
                AND DATE(entry_date) = %s
                ORDER BY entry_date DESC
            """
            cursor.execute(query, (date,))
            rows = cursor.fetchall()
        conn.close()
        return {"data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/list/export")
def export_list_data(date: str, payload=Depends(verify_token)):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT list_id, entry_date, source_id 
                FROM vicidial_list 
                WHERE list_id IN ('33331', '33332', '33333')
                AND DATE(entry_date) = %s
                ORDER BY entry_date DESC
            """
            cursor.execute(query, (date,))
            rows = cursor.fetchall()
        conn.close()

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["list_id", "entry_date", "source_id"])

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="VicidialList")
        output.seek(0)

        filename = f"vicidial_list_{date}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db-credentials", status_code=201)
def create_credential(data: DBCredentialCreate, payload=Depends(verify_token)):
    """Create a new DB credential entry."""
    try:
        conn = get_cs_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO db_credentials (host, host_name, user, password, database_name)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (data.host, data.host_name, data.user, data.password, data.database_name)
            )
            conn.commit()
            new_id = cursor.lastrowid

            cursor.execute("SELECT * FROM db_credentials WHERE id = %s", (new_id,))
            record = cursor.fetchone()
        conn.close()
        record["password"] = "••••••••"  # mask password in response
        return {"message": "Created successfully", "data": record}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db-credentials")
def list_credentials(payload=Depends(verify_token)):
    """Get all DB credential entries (passwords masked)."""
    try:
        conn = get_cs_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, host, host_name, user, database_name, created_at, updated_at FROM db_credentials ORDER BY id DESC"
            )
            rows = cursor.fetchall()
        conn.close()
        return {"data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db-credentials/{credential_id}")
def get_credential(credential_id: int, payload=Depends(verify_token)):
    """Get a single DB credential by ID (password masked)."""
    try:
        conn = get_cs_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, host, host_name, user, database_name, created_at, updated_at FROM db_credentials WHERE id = %s",
                (credential_id,)
            )
            record = cursor.fetchone()
        conn.close()
        if not record:
            raise HTTPException(status_code=404, detail="Credential not found")
        return {"data": record}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/db-credentials/{credential_id}")
def update_credential(credential_id: int, data: DBCredentialUpdate, payload=Depends(verify_token)):
    """Update one or more fields of a DB credential."""
    try:
        conn = get_cs_connection()
        with conn.cursor() as cursor:
            # Check exists
            cursor.execute("SELECT id FROM db_credentials WHERE id = %s", (credential_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Credential not found")

            # Build dynamic SET clause from only provided fields
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            if not fields:
                raise HTTPException(status_code=400, detail="No fields provided to update")

            set_clause = ", ".join(f"{k} = %s" for k in fields)
            values = list(fields.values()) + [credential_id]

            cursor.execute(
                f"UPDATE db_credentials SET {set_clause} WHERE id = %s",
                values
            )
            conn.commit()

            # Return updated record (no password)
            cursor.execute(
                "SELECT id, host, host_name, user, database_name, created_at, updated_at FROM db_credentials WHERE id = %s",
                (credential_id,)
            )
            record = cursor.fetchone()
        conn.close()
        return {"message": "Updated successfully", "data": record}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





def get_dynamic_connection(credential_id: int):
    conn = get_cs_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM db_credentials WHERE id = %s", (credential_id,))
        cred = cursor.fetchone()
    conn.close()

    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    return pymysql.connect(
        host=cred["host"],
        user=cred["user"],
        password=cred["password"],
        database=cred["database_name"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )



@app.get("/api/dynamic-report")
def dynamic_report(
    credential_id: int,
    start_date: str,
    end_date: str,
    payload=Depends(verify_token)
):
    try:
        conn = get_dynamic_connection(credential_id)

        with conn.cursor() as cursor:
            query = f"""
            SELECT
                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,
                IF(t2.status IS NULL OR t2.status='DROP','VDCL',t2.user) AS Agent,
                t2.campaign_id,
                t2.phone_number AS PhoneNumber,
                t2.status,
                t2.term_reason,
                SEC_TO_TIME(t2.length_in_sec) AS CallDuration,
                SEC_TO_TIME(queue_seconds) AS Queuetime,
                SEC_TO_TIME(t6.p) AS ParkedTime,
                t3.dispo_sec,
                IF(t3.dispo_sec IS NULL, SEC_TO_TIME(0),
                    IF(t3.sub_status IN ('LOGIN','Feed') OR t3.talk_sec=t3.dispo_sec OR t3.talk_sec=0,
                        SEC_TO_TIME(1),
                        IF(t3.dispo_sec>100,
                            SEC_TO_TIME(t3.dispo_sec-(t3.dispo_sec/100)*100),
                            SEC_TO_TIME(t3.dispo_sec)
                        )
                    )
                ) AS WrapTime,
                IF(queue_seconds <= 20, 1, 0) AS Call20,
                FROM_UNIXTIME(t2.end_epoch) AS Endtime,
                CASE
                    WHEN fb.call_start IS NOT NULL
                    THEN 'Transferred'
                    ELSE 'Not Transferred'
                END AS CallTransferStatus,
            
                fb.`option` AS FeedbackOption,
            
                fb.call_start AS CallTransferTime,
            
                fb.calltime AS CallTransferEndTime,
            
                TIMEDIFF(fb.calltime, fb.call_start) AS CSATIVRDuration
            FROM vicidial_closer_log t2
            LEFT JOIN call_log t1 ON t1.uniqueid = t2.uniqueid
            LEFT JOIN vicidial_agent_log t3 ON t1.uniqueid = t3.uniqueid
            LEFT JOIN (
                SELECT uniqueid, SUM(parked_sec) p
                FROM park_log
                WHERE STATUS='GRABBED'
                AND DATE(parked_time) BETWEEN %s AND %s
                GROUP BY uniqueid
            ) t6 ON t2.uniqueid = t6.uniqueid
            LEFT JOIN feedback_log fb
                ON fb.uniqueid = t2.uniqueid
            WHERE DATE(t2.call_date) BETWEEN %s AND %s
            AND t2.campaign_id IN (
                'GNC_Authentication','GNC_Inbound','GNC_Offer_Order',
                'GNC_Order_Related','GNC_Other_Queries',
                'GNC_Product_Info','GNC_Product_Quality'
            )
            AND t2.term_reason != 'AFTERHOURS'
            AND t2.lead_id IS NOT NULL
            """

            cursor.execute(query, (start_date, end_date, start_date, end_date))
            rows = cursor.fetchall()

        conn.close()

        return {"data": rows, "total": len(rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/dynamic-report/export")
def export_dynamic_report(
    credential_id: int,
    start_date: str,
    end_date: str,
    payload=Depends(verify_token)
):
    try:
        conn = get_dynamic_connection(credential_id)

        with conn.cursor() as cursor:
            query = """
            SELECT
                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,
                FROM_UNIXTIME(t2.end_epoch) AS Endtime,
                IF(t2.status IS NULL OR t2.status='DROP','VDCL',t2.user) AS Agent,
                t2.campaign_id,
                t2.phone_number AS PhoneNumber,
                t2.status,
                t2.term_reason,
                SEC_TO_TIME(t2.length_in_sec) AS CallDuration,
                SEC_TO_TIME(queue_seconds) AS Queuetime,
                SEC_TO_TIME(IFNULL(t6.p,0)) AS ParkedTime,
                t3.dispo_sec,
                IF(t3.dispo_sec IS NULL, SEC_TO_TIME(0),
                    IF(t3.sub_status IN ('LOGIN','Feed') OR t3.talk_sec=t3.dispo_sec OR t3.talk_sec=0,
                        SEC_TO_TIME(1),
                        IF(t3.dispo_sec>100,
                            SEC_TO_TIME(t3.dispo_sec-(t3.dispo_sec/100)*100),
                            SEC_TO_TIME(t3.dispo_sec)
                        )
                    )
                ) AS WrapTime,
                IF(queue_seconds <= 20, 1, 0) AS Call20,
                CASE
                    WHEN fb.call_start IS NOT NULL
                    THEN 'Transferred'
                    ELSE 'Not Transferred'
                END AS CallTransferStatus,
            
                fb.`option` AS FeedbackOption,
            
                fb.call_start AS CallTransferTime,
            
                fb.calltime AS CallTransferEndTime,
            
                IFNULL(
                    TIMEDIFF(fb.calltime, fb.call_start),
                    '00:00:00'
                ) AS CSATIVRDuration
            FROM vicidial_closer_log t2
            LEFT JOIN call_log t1 ON t1.uniqueid = t2.uniqueid
            LEFT JOIN vicidial_agent_log t3 ON t1.uniqueid = t3.uniqueid
            LEFT JOIN (
                SELECT uniqueid, SUM(parked_sec) p
                FROM park_log
                WHERE STATUS='GRABBED'
                AND DATE(parked_time) BETWEEN %s AND %s
                GROUP BY uniqueid
            ) t6 ON t2.uniqueid = t6.uniqueid
            LEFT JOIN feedback_log fb
                ON fb.uniqueid = t2.uniqueid
            WHERE DATE(t2.call_date) BETWEEN %s AND %s
            AND t2.campaign_id IN (
                'GNC_Authentication','GNC_Inbound','GNC_Offer_Order',
                'GNC_Order_Related','GNC_Other_Queries',
                'GNC_Product_Info','GNC_Product_Quality'
            )
            AND t2.term_reason != 'AFTERHOURS'
            AND t2.lead_id IS NOT NULL
            """

            cursor.execute(query, (start_date, end_date, start_date, end_date))
            rows = cursor.fetchall()

        conn.close()

        # Convert to DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            df = pd.DataFrame(columns=[
                "CallDate","StartTime","Endtime","Agent","campaign_id",
                "PhoneNumber","status","term_reason","CallDuration",
                "Queuetime","ParkedTime","dispo_sec","WrapTime","Call20",
                "CallTransferStatus","FeedbackOption","CallTransferTime","CallTransferEndTime","CSATIVRDuration"
            ])

        # Create Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="DynamicReport")

        output.seek(0)

        filename = f"dynamic_report_{start_date}_to_{end_date}.xlsx"

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))