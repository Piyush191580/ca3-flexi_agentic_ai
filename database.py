"""SQLite persistence layer for the Automated Vaccination Reminder System."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "vaccination_system.db"
STATUS_SCHEDULED = "Scheduled"
STATUS_DUE_TODAY = "Due Today"
STATUS_OVERDUE = "Overdue"
STATUS_COMPLETED = "Completed"

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, dob TEXT NOT NULL,
            gender TEXT, category TEXT NOT NULL, email TEXT, phone TEXT, registered_on TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS vaccine_doses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            vaccine_name TEXT NOT NULL, dose_label TEXT NOT NULL, due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Scheduled', administered_date TEXT,
            reminder_count INTEGER NOT NULL DEFAULT 0, last_reminded_on TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS reminder_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            dose_id INTEGER NOT NULL REFERENCES vaccine_doses(id) ON DELETE CASCADE, patient_name TEXT NOT NULL,
            vaccine_name TEXT NOT NULL, dose_label TEXT NOT NULL, urgency TEXT NOT NULL, channel TEXT NOT NULL,
            message TEXT NOT NULL, sent_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS reschedule_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, dose_id INTEGER NOT NULL REFERENCES vaccine_doses(id) ON DELETE CASCADE,
            patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE, old_due_date TEXT NOT NULL,
            new_due_date TEXT NOT NULL, reason TEXT, changed_at TEXT NOT NULL)""")

def reset_db():
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS reschedule_logs")
        conn.execute("DROP TABLE IF EXISTS reminder_logs")
        conn.execute("DROP TABLE IF EXISTS vaccine_doses")
        conn.execute("DROP TABLE IF EXISTS patients")
    init_db()

def add_patient(name, dob, gender, category, email, phone):
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO patients (name,dob,gender,category,email,phone,registered_on) VALUES (?,?,?,?,?,?,?)",
                           (name,dob,gender,category,email,phone,datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid

def list_patients():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM patients ORDER BY id DESC").fetchall()]

def get_patient(patient_id):
    with get_connection() as conn:
        r = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        return dict(r) if r else None

def bulk_add_doses(patient_id, doses):
    with get_connection() as conn:
        conn.executemany("INSERT INTO vaccine_doses (patient_id,vaccine_name,dose_label,due_date,status) VALUES (?,?,?,?,?)",
                         [(patient_id,v,d,due,STATUS_SCHEDULED) for v,d,due in doses])

def get_doses_for_patient(patient_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM vaccine_doses WHERE patient_id=? ORDER BY due_date,id", (patient_id,)).fetchall()]

def list_all_doses(include_completed=True):
    query = """SELECT vd.*, p.name AS patient_name, p.category AS patient_category,
               p.email AS patient_email, p.phone AS patient_phone
               FROM vaccine_doses vd JOIN patients p ON p.id=vd.patient_id"""
    params = ()
    if not include_completed:
        query += " WHERE vd.status != ?"
        params = (STATUS_COMPLETED,)
    query += " ORDER BY vd.due_date ASC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]

def update_dose_status(dose_id, status):
    with get_connection() as conn:
        conn.execute("UPDATE vaccine_doses SET status=? WHERE id=?", (status,dose_id))

def mark_administered(dose_id, administered_date=None):
    administered_date = administered_date or date.today().isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE vaccine_doses SET status=?, administered_date=? WHERE id=?",
                     (STATUS_COMPLETED,administered_date,dose_id))

def reschedule_dose(dose_id, new_due_date, reason=""):
    with get_connection() as conn:
        row = conn.execute("SELECT patient_id,due_date FROM vaccine_doses WHERE id=?", (dose_id,)).fetchone()
        if not row:
            raise ValueError("Dose not found.")
        old = row["due_date"]
        conn.execute("UPDATE vaccine_doses SET due_date=?, status=?, administered_date=NULL, last_reminded_on=NULL WHERE id=?",
                     (new_due_date, STATUS_SCHEDULED, dose_id))
        conn.execute("INSERT INTO reschedule_logs (dose_id,patient_id,old_due_date,new_due_date,reason,changed_at) VALUES (?,?,?,?,?,?)",
                     (dose_id,row["patient_id"],old,new_due_date,reason,datetime.now().isoformat(timespec="seconds")))

def get_reschedule_logs(limit=300):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM reschedule_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

def record_reminder_sent(dose_id):
    with get_connection() as conn:
        conn.execute("UPDATE vaccine_doses SET reminder_count=reminder_count+1,last_reminded_on=? WHERE id=?",
                     (datetime.now().isoformat(timespec="seconds"),dose_id))

def log_reminder(patient_id,dose_id,patient_name,vaccine_name,dose_label,urgency,channel,message):
    with get_connection() as conn:
        conn.execute("INSERT INTO reminder_logs (patient_id,dose_id,patient_name,vaccine_name,dose_label,urgency,channel,message,sent_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (patient_id,dose_id,patient_name,vaccine_name,dose_label,urgency,channel,message,datetime.now().isoformat(timespec="seconds")))

def get_reminder_logs(limit=300):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM reminder_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

def get_dashboard_stats():
    with get_connection() as conn:
        q=lambda sql,p=(): conn.execute(sql,p).fetchone()["c"]
        return {"total_patients":q("SELECT COUNT(*) c FROM patients"),"total_doses":q("SELECT COUNT(*) c FROM vaccine_doses"),
                "completed":q("SELECT COUNT(*) c FROM vaccine_doses WHERE status=?",(STATUS_COMPLETED,)),
                "overdue":q("SELECT COUNT(*) c FROM vaccine_doses WHERE status=?",(STATUS_OVERDUE,)),
                "due_today":q("SELECT COUNT(*) c FROM vaccine_doses WHERE status=?",(STATUS_DUE_TODAY,)),
                "scheduled":q("SELECT COUNT(*) c FROM vaccine_doses WHERE status=?",(STATUS_SCHEDULED,)),
                "reminders_sent":q("SELECT COUNT(*) c FROM reminder_logs"),
                "rescheduled":q("SELECT COUNT(*) c FROM reschedule_logs")}

def get_analytics():
    with get_connection() as conn:
        status=[dict(r) for r in conn.execute("SELECT status,COUNT(*) count FROM vaccine_doses GROUP BY status").fetchall()]
        monthly=[dict(r) for r in conn.execute("SELECT substr(administered_date,1,7) month,COUNT(*) count FROM vaccine_doses WHERE status=? AND administered_date IS NOT NULL GROUP BY month ORDER BY month",(STATUS_COMPLETED,)).fetchall()]
        categories=[dict(r) for r in conn.execute("SELECT category,COUNT(*) count FROM patients GROUP BY category").fetchall()]
        channels=[dict(r) for r in conn.execute("SELECT channel,COUNT(*) count FROM reminder_logs GROUP BY channel").fetchall()]
    return {"status":status,"monthly":monthly,"categories":categories,"channels":channels}
