"""Automated Perceive -> Decide -> Act reminder agent with optional real email."""
from __future__ import annotations
import logging, smtplib, threading
from email.message import EmailMessage
from datetime import date, datetime
import database as db
import email_config
logger=logging.getLogger("ReminderAgent")
REMINDER_WINDOW_DAYS=7; OVERDUE_RECHECK_DAYS=3; UPCOMING_RECHECK_DAYS=3

def _compose_message(patient_name,vaccine_name,dose_label,due_date,urgency,days_diff):
    if urgency=="Overdue":
        return f"Dear {patient_name}, your {vaccine_name} ({dose_label}) was due on {due_date:%d %b %Y} and is now {days_diff} day(s) overdue. Please contact your vaccination centre."
    if urgency=="Due Today":
        return f"Dear {patient_name}, your {vaccine_name} ({dose_label}) is due today ({due_date:%d %b %Y}). Please plan your vaccination visit."
    return f"Dear {patient_name}, this is a reminder that {vaccine_name} ({dose_label}) is due on {due_date:%d %b %Y} (in {days_diff} day(s)). Please plan your vaccination visit."

class ReminderAgent:
    def __init__(self, reminder_window_days=REMINDER_WINDOW_DAYS):
        self.reminder_window_days=reminder_window_days; self._bg_thread=None; self._stop_event=threading.Event()
        self.is_running_background=False; self.background_interval=None; self.last_cycle_summary={}; self.cycle_count=0

    def perceive(self):
        today=date.today(); doses=db.list_all_doses(include_completed=False)
        for dose in doses:
            diff=(date.fromisoformat(dose["due_date"])-today).days
            status=db.STATUS_OVERDUE if diff<0 else db.STATUS_DUE_TODAY if diff==0 else db.STATUS_SCHEDULED
            dose["_computed_status"]=status; dose["_days_diff"]=diff
            if dose["status"]!=status: db.update_dose_status(dose["id"],status)
        return doses

    def decide(self,doses):
        actionable=[]
        for dose in doses:
            status=dose["_computed_status"]; diff=dose["_days_diff"]; last=dose.get("last_reminded_on")
            days_since=(datetime.now()-datetime.fromisoformat(last)).days if last else None
            if status==db.STATUS_OVERDUE and (days_since is None or days_since>=OVERDUE_RECHECK_DAYS): dose["_urgency"]="Overdue"; actionable.append(dose)
            elif status==db.STATUS_DUE_TODAY and (days_since is None or days_since>=UPCOMING_RECHECK_DAYS): dose["_urgency"]="Due Today"; actionable.append(dose)
            elif status==db.STATUS_SCHEDULED and 0<diff<=self.reminder_window_days and (days_since is None or days_since>=UPCOMING_RECHECK_DAYS): dose["_urgency"]="Upcoming"; actionable.append(dose)
        return actionable

    def _send_email(self,to,subject,body):
        host=email_config.SMTP_HOST
        port=int(email_config.SMTP_PORT)
        user=email_config.SENDER_EMAIL
        password=email_config.APP_PASSWORD
        sender=email_config.SENDER_EMAIL
        if not all([host,user,password]) or password.startswith("PASTE_YOUR_"):
            return False,"Email Simulation"
        msg=EmailMessage(); msg["Subject"]=subject; msg["From"]=sender; msg["To"]=to; msg.set_content(body)
        with smtplib.SMTP(host,port,timeout=20) as server:
            server.starttls(); server.login(user,password); server.send_message(msg)
        return True,"Email"

    def act(self,actionable_doses):
        sent=[]
        for dose in actionable_doses:
            due=date.fromisoformat(dose["due_date"]); message=_compose_message(dose["patient_name"],dose["vaccine_name"],dose["dose_label"],due,dose["_urgency"],abs(dose["_days_diff"]))
            channel="App Notification"
            if dose.get("patient_email"):
                try:
                    ok,channel=self._send_email(dose["patient_email"],f"Vaccination Reminder - {dose['vaccine_name']}",message)
                    if not ok: channel="Email Simulation"
                except Exception as exc:
                    logger.exception("Email failed"); channel="Email Failed"
                    message += f"\n\n[Email delivery failed: {exc}]"
            elif dose.get("patient_phone"): channel="SMS (Simulation)"
            db.log_reminder(dose["patient_id"],dose["id"],dose["patient_name"],dose["vaccine_name"],dose["dose_label"],dose["_urgency"],channel,message)
            db.record_reminder_sent(dose["id"]); sent.append({**dose,"message":message,"channel":channel})
        return sent

    def send_manual_reminder(self, dose_id):
        """Send one reminder immediately, bypassing the normal cooldown.
        Intended for manual follow-up and demonstrations; completed doses are rejected.
        """
        doses = db.list_all_doses(include_completed=False)
        dose = next((d for d in doses if int(d["id"]) == int(dose_id)), None)
        if not dose:
            raise ValueError("Dose not found or already completed.")
        today = date.today()
        due = date.fromisoformat(dose["due_date"])
        diff = (due - today).days
        dose["_days_diff"] = diff
        dose["_computed_status"] = (db.STATUS_OVERDUE if diff < 0 else db.STATUS_DUE_TODAY if diff == 0 else db.STATUS_SCHEDULED)
        dose["_urgency"] = "Overdue" if diff < 0 else "Due Today" if diff == 0 else "Upcoming"
        return self.act([dose])[0]

    def run_cycle(self):
        perceived=self.perceive(); decided=self.decide(perceived); acted=self.act(decided); self.cycle_count+=1
        summary={"cycle":self.cycle_count,"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"doses_scanned":len(perceived),"reminders_sent":len(acted),"sent":acted}; self.last_cycle_summary=summary; return summary
    def start_background(self,interval_seconds=60):
        if self.is_running_background:return
        self._stop_event.clear()
        def loop():
            while not self._stop_event.is_set():
                try:self.run_cycle()
                except Exception:logger.exception("Background reminder cycle failed")
                self._stop_event.wait(interval_seconds)
        self._bg_thread=threading.Thread(target=loop,daemon=True); self._bg_thread.start(); self.is_running_background=True; self.background_interval=interval_seconds
    def stop_background(self):
        self._stop_event.set(); self.is_running_background=False; self.background_interval=None
