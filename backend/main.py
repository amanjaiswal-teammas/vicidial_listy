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
import requests
from requests.auth import HTTPBasicAuth
from datetime import timedelta
from fastapi import Request
from router.ivr import router as ivr_router
from router.ivr_order_modification import router as ivr_order_modification_router
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ivr_router)
app.include_router(ivr_order_modification_router)

SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"

# Hardcoded credentials
# Hardcoded users with roles
USERS = {
    "admin": {
        "password": "admin123",
        "role": "admin"
    },
    "finnable": {
        "password": "finnable123",
        "role": "finnable"
    },
    "gnc": {
        "password": "gnc123",
        "role": "gnc"
    },
    "neemans": {
        "password": "neemans123",
        "role": "neemans"
    },
    "reginald": {
        "password": "reginald123",
        "role": "bbb"
    }
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

    user = USERS.get(data.username)

    if user and user["password"] == data.password:

        token = jwt.encode(
            {
                "sub": data.username,
                "role": user["role"],
                "exp": datetime.utcnow().timestamp() + 86400
            },
            SECRET_KEY,
            algorithm=ALGORITHM
        )

        return {
            "token": token,
            "username": data.username,
            "role": user["role"]
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")


def require_roles(allowed_roles: list):
    def checker(payload=Depends(verify_token)):

        user_role = payload.get("role")

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return payload

    return checker


@app.get("/api/list")
def get_list_data(date: str, payload=Depends(require_roles(["admin", "finnable"]))):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT list_id, entry_date, source_id 
                FROM vicidial_list 
                WHERE list_id IN ('33331', '33332', '33333', '33334')
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
def export_list_data(date: str, payload=Depends(require_roles(["admin", "finnable"]))):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT list_id, entry_date, source_id 
                FROM vicidial_list 
                WHERE list_id IN ('33331', '33332', '33333', '33334')
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



@app.get("/api/source-details")
def get_source_details(
    source_id: str,
    payload=Depends(require_roles(["admin", "finnable"]))
):
    try:
        conn = get_db_connection()

        with conn.cursor() as cursor:
            query = """
                SELECT 
                    entry_date,
                    status,
                    source_id,
                    list_id,
                    called_count,
                    last_local_call_time
                FROM vicidial_list
                WHERE source_id = %s
                ORDER BY entry_date DESC
            """

            cursor.execute(query, (source_id,))
            rows = cursor.fetchall()

        conn.close()

        return {
            "source_id": source_id,
            "total": len(rows),
            "data": rows
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/db-credentials", status_code=201)
def create_credential(data: DBCredentialCreate, payload=Depends(require_roles(["admin", "gnc"]))):
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
def list_credentials(payload=Depends(require_roles(["admin", "gnc"]))):
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
def get_credential(credential_id: int, payload=Depends(require_roles(["admin", "gnc"]))):
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
def update_credential(credential_id: int, data: DBCredentialUpdate, payload=Depends(require_roles(["admin", "gnc"]))):
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
    payload=Depends(require_roles(["admin", "gnc"]))
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
    payload=Depends(require_roles(["admin", "gnc"]))
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




@app.get("/api/neemans-apr")
def neemans_apr(
    start_date: str,
    end_date: str,
    payload=Depends(require_roles(["admin", "neemans"]))
):
    try:
        conn = get_dynamic_connection(5)

        with conn.cursor() as cursor:
            query = """
            SELECT
                t2.uniqueid,
                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,
                REPLACE(FROM_UNIXTIME(t2.start_epoch+queue_seconds),'.00','') AS CallTime,
                SEC_TO_TIME(t2.length_in_sec-queue_seconds) AS CallDuration1,
                t2.user AS Agent,
                t2.campaign_id,
                t1.caller_code AS PhoneNumber,
                t2.status,
                t2.term_reason,
                SEC_TO_TIME(t2.length_in_sec) AS CallDuration,
                SEC_TO_TIME(queue_seconds) AS Queuetime,
                SEC_TO_TIME(IFNULL(t6.p,0)) AS ParkedTime,
                t3.dispo_sec,
                IF(
                    t3.dispo_sec IS NULL,
                    SEC_TO_TIME(0),
                    IF(
                        t3.sub_status='LOGIN'
                        OR t3.sub_status='Feed'
                        OR t3.talk_sec=t3.dispo_sec
                        OR t3.talk_sec=0,
                        SEC_TO_TIME(1),
                        IF(
                            t3.dispo_sec>100,
                            SEC_TO_TIME(
                                t3.dispo_sec-(t3.dispo_sec/100)*100
                            ),
                            SEC_TO_TIME(t3.dispo_sec)
                        )
                    )
                ) AS WrapTime,
                IF(queue_seconds<=30,1,0) AS Call20,
                FROM_UNIXTIME(t2.end_epoch) AS Endtime

            FROM (
                SELECT t6.*
                FROM vicidial_closer_log t6
                JOIN (
                    SELECT
                        uniqueid,
                        MAX(closecallid) AS max_closecallid
                    FROM vicidial_closer_log
                    WHERE campaign_id IN ('Neemans_IB')
                    AND DATE(call_date) BETWEEN %s AND %s
                    GROUP BY uniqueid
                ) t7
                ON t6.uniqueid=t7.uniqueid
                AND t6.closecallid=t7.max_closecallid
            ) t2

            LEFT JOIN call_log t1
                ON t1.uniqueid=t2.uniqueid

            LEFT JOIN vicidial_agent_log t3
                ON t1.uniqueid=t3.uniqueid

            LEFT JOIN (
                SELECT
                    uniqueid,
                    SUM(parked_sec) p
                FROM park_log
                WHERE STATUS='GRABBED'
                AND DATE(parked_time) BETWEEN %s AND %s
                GROUP BY uniqueid
            ) t6
                ON t2.uniqueid=t6.uniqueid

            WHERE DATE(t2.call_date) BETWEEN %s AND %s
            AND t2.campaign_id='Neemans_IB'
            AND t2.term_reason!='AFTERHOURS'
            AND t2.lead_id IS NOT NULL
            """

            cursor.execute(
                query,
                (
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                    start_date,
                    end_date
                )
            )

            rows = cursor.fetchall()

        conn.close()

        return {
            "data": rows,
            "total": len(rows)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/neemans-apr/export")
def export_neemans_apr(
    start_date: str,
    end_date: str,
    payload=Depends(require_roles(["admin", "neemans"]))
):
    try:
        conn = get_dynamic_connection(5)

        with conn.cursor() as cursor:
            query = """
            SELECT
                t2.uniqueid,
                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,
                REPLACE(FROM_UNIXTIME(t2.start_epoch+queue_seconds),'.00','') AS CallTime,
                SEC_TO_TIME(t2.length_in_sec-queue_seconds) AS CallDuration1,
                t2.user AS Agent,
                t2.campaign_id,
                t1.caller_code AS PhoneNumber,
                t2.status,
                t2.term_reason,
                SEC_TO_TIME(t2.length_in_sec) AS CallDuration,
                SEC_TO_TIME(queue_seconds) AS Queuetime,
                SEC_TO_TIME(IFNULL(t6.p,0)) AS ParkedTime,
                t3.dispo_sec,
                IF(
                    t3.dispo_sec IS NULL,
                    SEC_TO_TIME(0),
                    IF(
                        t3.sub_status='LOGIN'
                        OR t3.sub_status='Feed'
                        OR t3.talk_sec=t3.dispo_sec
                        OR t3.talk_sec=0,
                        SEC_TO_TIME(1),
                        IF(
                            t3.dispo_sec>100,
                            SEC_TO_TIME(
                                t3.dispo_sec-(t3.dispo_sec/100)*100
                            ),
                            SEC_TO_TIME(t3.dispo_sec)
                        )
                    )
                ) AS WrapTime,
                IF(queue_seconds<=30,1,0) AS Call20,
                FROM_UNIXTIME(t2.end_epoch) AS Endtime

            FROM (
                SELECT t6.*
                FROM vicidial_closer_log t6
                JOIN (
                    SELECT
                        uniqueid,
                        MAX(closecallid) AS max_closecallid
                    FROM vicidial_closer_log
                    WHERE campaign_id IN ('Neemans_IB')
                    AND DATE(call_date) BETWEEN %s AND %s
                    GROUP BY uniqueid
                ) t7
                ON t6.uniqueid=t7.uniqueid
                AND t6.closecallid=t7.max_closecallid
            ) t2

            LEFT JOIN call_log t1
                ON t1.uniqueid=t2.uniqueid

            LEFT JOIN vicidial_agent_log t3
                ON t1.uniqueid=t3.uniqueid

            LEFT JOIN (
                SELECT
                    uniqueid,
                    SUM(parked_sec) p
                FROM park_log
                WHERE STATUS='GRABBED'
                AND DATE(parked_time) BETWEEN %s AND %s
                GROUP BY uniqueid
            ) t6
                ON t2.uniqueid=t6.uniqueid

            WHERE DATE(t2.call_date) BETWEEN %s AND %s
            AND t2.campaign_id='Neemans_IB'
            AND t2.term_reason!='AFTERHOURS'
            AND t2.lead_id IS NOT NULL
            """

            cursor.execute(
                query,
                (
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                    start_date,
                    end_date
                )
            )
            rows = cursor.fetchall()

        conn.close()

        df = pd.DataFrame(rows)

        duration_cols = [
            "CallDuration1",
            "CallDuration",
            "Queuetime",
            "ParkedTime",
            "WrapTime"
        ]

        for col in duration_cols:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: (
                        f"{int(x.total_seconds() // 3600):02d}:"
                        f"{int((x.total_seconds() % 3600) // 60):02d}:"
                        f"{int(x.total_seconds() % 60):02d}"
                    )
                    if isinstance(x, timedelta)
                    else str(x) if x is not None else ""
                )

        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(
                writer,
                index=False,
                sheet_name="Neemans_APR"
            )

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"attachment; filename=Neemans_APR_{start_date}_{end_date}.xlsx"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/neemans-cdr")
def neemans_cdr(
    start_date: str,
    end_date: str,
    payload=Depends(require_roles(["admin", "neemans"]))
):
    try:
        conn = get_dynamic_connection(5)

        with conn.cursor() as cursor:
            query = """
            SELECT
                t2.uniqueid,
                CONCAT(
                    SUBSTRING_INDEX(t2.uniqueid,'.',1),
                    '.',
                    SUBSTRING_INDEX(t2.uniqueid,'.',-1)+1
                ) AS Nuniqueid,

                t2.lead_id,
                t2.user AS Agent,
                RIGHT(t2.phone_number,10) AS PhoneNumber,

                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,

                IF(
                    FROM_UNIXTIME(t2.end_epoch) IS NULL,
                    FROM_UNIXTIME(t3.dispo_epoch),
                    FROM_UNIXTIME(t2.end_epoch)
                ) AS EndTime,

                t2.length_in_sec AS LengthInSec,
                SEC_TO_TIME(t2.length_in_sec) AS LengthInMin,

                t2.length_in_sec AS CallDuration,

                t2.status AS CallStatus,

                t3.pause_sec,
                t3.wait_sec,
                t3.talk_sec,
                t3.dead_sec,
                t3.dispo_sec AS DispoSec,

                t2.campaign_id,
                t2.comments,
                t2.term_reason

            FROM vicidial_log t2

            LEFT JOIN vicidial_agent_log t3
                ON t2.uniqueid=t3.uniqueid
                AND t2.lead_id=t3.lead_id

            WHERE DATE(t2.call_date)
            BETWEEN %s AND %s

            AND t2.lead_id IS NOT NULL

            AND t2.campaign_id IN (
                'NeemansC',
                'Neem_Out'
            )
            """

            cursor.execute(
                query,
                (
                    start_date,
                    end_date
                )
            )

            rows = cursor.fetchall()

        conn.close()

        return {
            "data": rows,
            "total": len(rows)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/neemans-cdr/export")
def export_neemans_cdr(
    start_date: str,
    end_date: str,
    payload=Depends(require_roles(["admin", "neemans"]))
):
    try:
        conn = get_dynamic_connection(5)

        with conn.cursor() as cursor:
            query = """
            SELECT
                t2.uniqueid,
                CONCAT(
                    SUBSTRING_INDEX(t2.uniqueid,'.',1),
                    '.',
                    SUBSTRING_INDEX(t2.uniqueid,'.',-1)+1
                ) AS Nuniqueid,

                t2.lead_id,
                t2.user AS Agent,
                RIGHT(t2.phone_number,10) AS PhoneNumber,

                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,

                IF(
                    FROM_UNIXTIME(t2.end_epoch) IS NULL,
                    FROM_UNIXTIME(t3.dispo_epoch),
                    FROM_UNIXTIME(t2.end_epoch)
                ) AS EndTime,

                t2.length_in_sec AS LengthInSec,
                SEC_TO_TIME(t2.length_in_sec) AS LengthInMin,

                t2.length_in_sec AS CallDuration,

                t2.status AS CallStatus,

                t3.pause_sec,
                t3.wait_sec,
                t3.talk_sec,
                t3.dead_sec,
                t3.dispo_sec AS DispoSec,

                t2.campaign_id,
                t2.comments,
                t2.term_reason

            FROM vicidial_log t2

            LEFT JOIN vicidial_agent_log t3
                ON t2.uniqueid=t3.uniqueid
                AND t2.lead_id=t3.lead_id

            WHERE DATE(t2.call_date)
            BETWEEN %s AND %s

            AND t2.lead_id IS NOT NULL

            AND t2.campaign_id IN (
                'NeemansC',
                'Neem_Out'
            )
            """

            cursor.execute(query, (start_date, end_date))
            rows = cursor.fetchall()

        conn.close()

        df = pd.DataFrame(rows)

        output = BytesIO()

        def format_duration(value):
            if isinstance(value, timedelta):
                total = int(value.total_seconds())

                hours = total // 3600
                minutes = (total % 3600) // 60
                seconds = total % 60

                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            return value

        if "LengthInMin" in df.columns:
            df["LengthInMin"] = df["LengthInMin"].apply(format_duration)

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(
                writer,
                index=False,
                sheet_name="Neemans_CDR"
            )

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"attachment; filename=Neemans_CDR_{start_date}_{end_date}.xlsx"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/neemans-agent/export")
def export_neemans_agent_report(
    date: str,
    payload=Depends(require_roles(["admin", "neemans"]))
):
    try:

        report_url = (
            f"http://192.168.11.249/vicidial/AST_agent_time_detail.php"
            f"?query_date={date}"
            f"&end_date={date}"
            f"&query_tms=00:00:00"
            f"&query_tme=23:59:59"
            f"&group[]=120001"
            f"&group[]=AW"
            f"&group[]=Cart2"
            f"&group[]=Chat"
            f"&group[]=Dalmia"
            f"&group[]=DS_test"
            f"&group[]=Email"
            f"&group[]=HR"
            f"&group[]=Neem_Out"
            f"&group[]=Neemans"
            f"&group[]=NeemansC"
            f"&group[]=Qadri_Ch"
            f"&group[]=Qadri_In"
            f"&group[]=Qadri_RE"
            f"&group[]=Reginald"
            f"&group[]=SocialM"
            f"&group[]=test"
            f"&group[]=testing"
            f"&group[]=Viega_IN"
            f"&group[]=VST_S1"
            f"&group[]=VST_S2"
            f"&group[]=VST_S3"
            f"&group[]=VST_S4"
            f"&group[]=Vst_Surv"
            f"&group[]=VSTOUT"
            f"&group[]=weryze_C"
            f"&group[]=weryze_F"
            f"&group[]=weryze_L"
            f"&group[]=weryze_O"
            f"&user_group[]=Neemans"
            f"&shift=ALL"
            f"&show_parks="
            f"&time_in_sec="
            f"&search_archived_data="
            f"&report_display_type=TEXT"
            f"&DB="
            f"&stage=NAME"
            f"&file_download=1"
        )

        response = requests.get(report_url, auth=HTTPBasicAuth("6666", "vicidialnow"), timeout=300)

        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to download report. Status code: {response.status_code}"
            )

        csv_data = BytesIO(response.content)

        return StreamingResponse(
            csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition":
                f"attachment; filename=Neemans_APR_{date}.csv"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/neemans-agent/export-246")
def export_neemans_agent_report_246(
    date: str,
    payload=Depends(require_roles(["admin", "neemans"]))
):
    try:

        report_url = (
            f"http://192.168.11.246/vicidial/AST_agent_time_detail.php"
            f"?query_date={date}"
            f"&end_date={date}"
            f"&query_tms=00:00:00"
            f"&query_tme=23:59:59"
            f"&group[]=120001"
            f"&group[]=AW"
            f"&group[]=Cart2"
            f"&group[]=Chat"
            f"&group[]=Dalmia"
            f"&group[]=DS_test"
            f"&group[]=Email"
            f"&group[]=HR"
            f"&group[]=Neem_Out"
            f"&group[]=Neemans"
            f"&group[]=NeemansC"
            f"&group[]=Qadri_Ch"
            f"&group[]=Qadri_In"
            f"&group[]=Qadri_RE"
            f"&group[]=Reginald"
            f"&group[]=SocialM"
            f"&group[]=test"
            f"&group[]=testing"
            f"&group[]=Viega_IN"
            f"&group[]=VST_S1"
            f"&group[]=VST_S2"
            f"&group[]=VST_S3"
            f"&group[]=VST_S4"
            f"&group[]=Vst_Surv"
            f"&group[]=VSTOUT"
            f"&group[]=weryze_C"
            f"&group[]=weryze_F"
            f"&group[]=weryze_L"
            f"&group[]=weryze_O"
            f"&user_group[]=Neemans"
            f"&shift=ALL"
            f"&show_parks="
            f"&time_in_sec="
            f"&search_archived_data="
            f"&report_display_type=TEXT"
            f"&DB="
            f"&stage=NAME"
            f"&file_download=1"
        )

        response = requests.get(
            report_url,
            auth=HTTPBasicAuth("6666", "vicidialnow"),
            timeout=300
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to download report. Status code: {response.status_code}"
            )

        csv_data = BytesIO(response.content)

        return StreamingResponse(
            csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition":
                f"attachment; filename=Neemans_APR_{date}.csv"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/bbb-cdr/export")
def export_bbb_cdr(
    request: Request,
    start_date: str,
    end_date: str,
    payload=Depends(require_roles(["admin", "bbb"]))
):
    try:
        conn = get_dynamic_connection(6)

        with conn.cursor() as cursor:
            query = """
            SELECT
                t2.uniqueid,
                CONCAT(
                    SUBSTRING_INDEX(t2.uniqueid,'.',1),
                    '.',
                    SUBSTRING_INDEX(t2.uniqueid,'.',-1)+1
                ) AS Nuniqueid,

                t2.lead_id,
                t2.user AS Agent,
                RIGHT(t2.phone_number,10) AS PhoneNumber,

                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,

                IF(
                    FROM_UNIXTIME(t2.end_epoch) IS NULL,
                    FROM_UNIXTIME(t3.dispo_epoch),
                    FROM_UNIXTIME(t2.end_epoch)
                ) AS EndTime,

                t2.length_in_sec AS LengthInSec,
                SEC_TO_TIME(t2.length_in_sec) AS LengthInMin,
                t2.length_in_sec AS CallDuration,

                t2.status AS CallStatus,

                t3.pause_sec AS PauseSec,
                t3.wait_sec AS WaitSec,
                t3.talk_sec,
                t3.dead_sec,
                t3.dispo_sec AS DispoSec,

                t2.campaign_id,
                t2.comments,
                t2.term_reason,

                rl.location AS RecordingLocation

            FROM vicidial_log t2

            LEFT JOIN vicidial_agent_log t3
                ON t2.uniqueid = t3.uniqueid
                AND t2.lead_id = t3.lead_id

            LEFT JOIN recording_log rl
                ON t2.uniqueid = rl.vicidial_id

            WHERE DATE(t2.call_date)
            BETWEEN %s AND %s

            AND t2.lead_id IS NOT NULL

            AND t2.campaign_id IN (
                'Abandon',
                'Email',
                'Insta',
                'RTO',
                'Website',
                'Tamil',
                'Telugu',
                'Kannada',
                'Kerala',
                'TTERM',
                'Premium',
                'RepeatAP',
                'RepeatTN',
                'RepeatPI',
                'MoEmail',
                'NDRMO',
                'NDRRM'
            )
            """

            cursor.execute(query, (start_date, end_date))
            rows = cursor.fetchall()

        conn.close()

        df = pd.DataFrame(rows)

        output = BytesIO()

        def format_duration(value):
            if isinstance(value, timedelta):
                total = int(value.total_seconds())

                hours = total // 3600
                minutes = (total % 3600) // 60
                seconds = total % 60

                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            return value

        if "LengthInMin" in df.columns:
            df["LengthInMin"] = df["LengthInMin"].apply(format_duration)

        PUBLIC_HOST = str(request.base_url).rstrip("/")

        def build_recording_url(location):
            if not location:
                return ""

            filename = location.rsplit("/", 1)[-1]

            return f"{PUBLIC_HOST}/api/recording/{filename}"

        if "RecordingLocation" in df.columns:
            df["RecordingLocation"] = df["RecordingLocation"].apply(build_recording_url)

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(
                writer,
                index=False,
                sheet_name="Reginald_CDR"
            )

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"attachment; filename=Reginald_CDR_{start_date}_{end_date}.xlsx"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/recording/{filename}")
def download_recording(
    filename: str
):
    internal_url = f"http://192.168.10.25/RECORDINGS/MP3/{filename}"

    try:
        response = requests.get(internal_url, stream=True, timeout=30)

        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Recording not found")

        return StreamingResponse(
            response.iter_content(chunk_size=8192),
            media_type=response.headers.get("Content-Type", "audio/mpeg"),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))



import math

@app.get("/api/bbb-cdr")
def get_bbb_cdr(
    request: Request,
    start_date: str,
    end_date: str,
    page: int = 1,
    limit: int = 100,
    payload=Depends(require_roles(["admin", "bbb"]))
):
    try:
        conn = get_dynamic_connection(6)

        offset = (page - 1) * limit

        with conn.cursor() as cursor:

            # Total Records
            count_query = """
            SELECT COUNT(*) AS total
            FROM vicidial_log t2
            WHERE DATE(t2.call_date) BETWEEN %s AND %s
              AND t2.lead_id IS NOT NULL
              AND t2.user <> 'VDAD'
              AND t2.campaign_id IN (
                    'Abandon',
                    'Email',
                    'Insta',
                    'RTO',
                    'Website',
                    'Tamil',
                    'Telugu',
                    'Kannada',
                    'Kerala',
                    'TTERM',
                    'Premium',
                    'RepeatAP',
                    'RepeatTN',
                    'RepeatPI',
                    'MoEmail',
                    'NDRMO',
                    'NDRRM'
              )
            """

            cursor.execute(count_query, (start_date, end_date))
            total = cursor.fetchone()["total"]

            query = """
            SELECT
                t2.uniqueid,

                CONCAT(
                    SUBSTRING_INDEX(t2.uniqueid,'.',1),
                    '.',
                    SUBSTRING_INDEX(t2.uniqueid,'.',-1)+1
                ) AS Nuniqueid,

                t2.lead_id,
                t2.user AS Agent,
                RIGHT(t2.phone_number,10) AS PhoneNumber,

                DATE(t2.call_date) AS CallDate,
                FROM_UNIXTIME(t2.start_epoch) AS StartTime,

                IF(
                    FROM_UNIXTIME(t2.end_epoch) IS NULL,
                    FROM_UNIXTIME(t3.dispo_epoch),
                    FROM_UNIXTIME(t2.end_epoch)
                ) AS EndTime,

                t2.length_in_sec AS LengthInSec,
                SEC_TO_TIME(t2.length_in_sec) AS LengthInMin,
                t2.length_in_sec AS CallDuration,

                t2.status AS CallStatus,

                t3.pause_sec AS PauseSec,
                t3.wait_sec AS WaitSec,
                t3.talk_sec,
                t3.dead_sec,
                t3.dispo_sec AS DispoSec,

                t2.campaign_id,
                t2.comments,
                t2.term_reason,

                rl.location AS RecordingLocation

            FROM vicidial_log t2

            LEFT JOIN vicidial_agent_log t3
                ON t2.uniqueid = t3.uniqueid
               AND t2.lead_id = t3.lead_id

            LEFT JOIN recording_log rl
                ON t2.uniqueid = rl.vicidial_id

            WHERE DATE(t2.call_date) BETWEEN %s AND %s
              AND t2.lead_id IS NOT NULL
              AND t2.user <> 'VDAD'
              AND t2.campaign_id IN (
                    'Abandon',
                    'Email',
                    'Insta',
                    'RTO',
                    'Website',
                    'Tamil',
                    'Telugu',
                    'Kannada',
                    'Kerala',
                    'TTERM',
                    'Premium',
                    'RepeatAP',
                    'RepeatTN',
                    'RepeatPI',
                    'MoEmail',
                    'NDRMO',
                    'NDRRM'
              )

            ORDER BY t2.call_date DESC
            LIMIT %s OFFSET %s
            """

            cursor.execute(
                query,
                (start_date, end_date, limit, offset)
            )

            rows = cursor.fetchall()

        conn.close()

        PUBLIC_HOST = str(request.base_url).rstrip("/")

        def format_duration(value):
            if isinstance(value, timedelta):
                total = int(value.total_seconds())
                h = total // 3600
                m = (total % 3600) // 60
                s = total % 60
                return f"{h:02d}:{m:02d}:{s:02d}"
            return value

        for row in rows:

            if isinstance(row.get("LengthInMin"), timedelta):
                row["LengthInMin"] = format_duration(row["LengthInMin"])

            location = row.get("RecordingLocation")

            if location:
                filename = location.rsplit("/", 1)[-1]
                row["RecordingUrl"] = (
                    f"{PUBLIC_HOST}/api/recording/{filename}"
                )
            else:
                row["RecordingUrl"] = None

            # Optional: hide internal location
            row.pop("RecordingLocation", None)

        return {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit),
            "data": rows
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))