from __future__ import annotations
import logging
from datetime import date,timedelta
from pathlib import Path
import gradio as gr
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import database as db
import schedule_engine
import email_config
from email.message import EmailMessage
import smtplib
from reminder_agent import ReminderAgent
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(name)s] %(message)s")
db.init_db(); agent=ReminderAgent(); EXPORT_DIR=Path(__file__).parent/"exports"; EXPORT_DIR.mkdir(exist_ok=True)
STATUS_RANK={db.STATUS_OVERDUE:0,db.STATUS_DUE_TODAY:1,db.STATUS_SCHEDULED:2}
RECORD_COLUMNS=["Vaccine","Dose","Due Date","Status","Administered On"]; SENT_COLUMNS=["Patient","Vaccine","Dose","Urgency","Channel","Message"]
LOG_COLUMNS=["Sent At","Patient","Vaccine","Dose","Urgency","Channel","Message"]
SAMPLE_PATIENTS=[("Aarav Sharma",timedelta(days=40),"Male","aarav.parent@example.com","9800000001"),("Isha Verma",timedelta(days=36),"Female","isha.parent@example.com","9800000002"),("Rohan Mehta",timedelta(days=365*29),"Male","rohan.mehta@example.com","9800000003"),("Sneha Kulkarni",timedelta(days=365*45),"Female","sneha.k@example.com","9800000004")]

def _patient_choices(): return [(f"{p['name']} — {p['category']} (ID {p['id']})",p['id']) for p in db.list_patients()]
def _stats_html(s):
    cards=[("Patients",s["total_patients"]),("Scheduled",s["scheduled"]),("Due Today",s["due_today"]),("Overdue",s["overdue"]),("Completed",s["completed"]),("Reminders",s["reminders_sent"]),("Rescheduled",s["rescheduled"])]
    return '<div style="display:flex;flex-wrap:wrap;gap:6px">'+''.join(f'<div style="flex:1;min-width:110px;text-align:center;border:1px solid #ddd;border-radius:12px;padding:14px;background:#fafbff"><div style="font-size:1.7em;font-weight:700">{v}</div><div>{k}</div></div>' for k,v in cards)+'</div>'
def _pending_df(doses):
    rows=[]; today=date.today()
    for d in doses:
        rows.append({"Patient":d["patient_name"],"Vaccine":d["vaccine_name"],"Dose":d["dose_label"],"Due Date":d["due_date"],"Status":d["status"],"Days":(date.fromisoformat(d["due_date"])-today).days,"_rank":STATUS_RANK.get(d["status"],3)})
    return pd.DataFrame(rows).sort_values(["_rank","Days"]).drop(columns="_rank").reset_index(drop=True) if rows else pd.DataFrame(columns=["Patient","Vaccine","Dose","Due Date","Status","Days"])
def _status_chart(s):
    labels=["Scheduled","Due Today","Overdue","Completed"]; vals=[s["scheduled"],s["due_today"],s["overdue"],s["completed"]]
    fig,ax=plt.subplots(figsize=(6,3.3)); bars=ax.bar(labels,vals); ax.bar_label(bars,padding=3); ax.set_title("Vaccination Status Distribution"); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False); fig.tight_layout(); return fig
def _log_df():
    logs=db.get_reminder_logs(1000); return pd.DataFrame([{"Sent At":x["sent_at"],"Patient":x["patient_name"],"Vaccine":x["vaccine_name"],"Dose":x["dose_label"],"Urgency":x["urgency"],"Channel":x["channel"],"Message":x["message"]} for x in logs],columns=LOG_COLUMNS)

def send_test_email():
    recipient=(email_config.TEST_RECEIVER_EMAIL or "").strip()
    if not recipient or "YOUR_PERSONAL_EMAIL" in recipient:
        return "### ❌ Email not sent\nEnter your personal/receiver email in `email_config.py`, save it, and click the button again. **No page refresh is required.**"
    password=email_config.APP_PASSWORD
    if not password or password.startswith("PASTE_YOUR_"):
        return "### ❌ Email not sent\nEnter your 16-character Gmail App Password in `email_config.py`, save it, and click the button again. **No page refresh is required.**"
    msg=EmailMessage()
    msg["Subject"]="Vaccination Reminder System - Test Email"
    msg["From"]=email_config.SENDER_EMAIL
    msg["To"]=recipient
    msg.set_content("Hello!\n\nThis is a real test email from the Automated Vaccination Reminder System.\n\nThe Gmail connection is working successfully.\n")
    try:
        with smtplib.SMTP(email_config.SMTP_HOST, int(email_config.SMTP_PORT), timeout=20) as server:
            server.starttls()
            server.login(email_config.SENDER_EMAIL, password)
            server.send_message(msg)
        return "### ✅ Test email sent\nCheck the receiver inbox (and Spam if needed)."
    except Exception as exc:
        return f"### ❌ Email failed\n`{exc}`"

def refresh_dashboard():
    agent.perceive(); s=db.get_dashboard_stats(); return _stats_html(s),_pending_df(db.list_all_doses(False)),_status_chart(s)

def register_patient(name,dob,gender,email,phone):
    name=(name or '').strip(); dob=(dob or '').strip()
    if not name:
        a,b,c=refresh_dashboard()
        return "### ❌ Registration failed\nEnter patient name and click **Register Patient** again. **No page refresh is required.**", pd.DataFrame(), gr.update(choices=_patient_choices()), a,b,c
    try:
        d=date.fromisoformat(dob)
    except:
        a,b,c=refresh_dashboard()
        return "### ❌ Registration failed\nDOB must be in **YYYY-MM-DD** format. Correct it and click **Register Patient** again. **No page refresh is required.**", pd.DataFrame(), gr.update(choices=_patient_choices()), a,b,c
    if d>date.today():
        a,b,c=refresh_dashboard()
        return "### ❌ Registration failed\nDOB cannot be in the future. Correct it and click **Register Patient** again. **No page refresh is required.**", pd.DataFrame(), gr.update(choices=_patient_choices()), a,b,c
    cat=schedule_engine.determine_category(d); pid=db.add_patient(name,d.isoformat(),gender or "Not specified",cat,(email or '').strip(),(phone or '').strip()); sched=schedule_engine.generate_schedule(d,cat); db.bulk_add_doses(pid,sched)
    sdf=pd.DataFrame(sched,columns=["Vaccine","Dose","Due Date"]).sort_values("Due Date"); conf=f"### ✅ Registered\n**{name}** registered as **{cat}** patient (ID {pid}) with {len(sched)} scheduled dose(s)."
    a,b,c=refresh_dashboard(); return conf,sdf,gr.update(choices=_patient_choices(),value=pid),a,b,c
def seed_sample_data():
    for name,delta,gender,email,phone in SAMPLE_PATIENTS:
        d=date.today()-delta; cat=schedule_engine.determine_category(d); pid=db.add_patient(name,d.isoformat(),gender,cat,email,phone); db.bulk_add_doses(pid,schedule_engine.generate_schedule(d,cat,registered_on=date.today()))
    a,b,c=refresh_dashboard(); return "### ✅ Sample data loaded",gr.update(choices=_patient_choices()),a,b,c

def _patient_dashboard(pid):
    if not pid: return "Select a patient.",pd.DataFrame(),pd.DataFrame(),""
    p=db.get_patient(int(pid)); doses=db.get_doses_for_patient(int(pid)); today=date.today();
    for d in doses:
        if d["status"]!=db.STATUS_COMPLETED:
            diff=(date.fromisoformat(d["due_date"])-today).days; d["status"]=db.STATUS_OVERDUE if diff<0 else db.STATUS_DUE_TODAY if diff==0 else db.STATUS_SCHEDULED
    completed=sum(d["status"]==db.STATUS_COMPLETED for d in doses); overdue=sum(d["status"]==db.STATUS_OVERDUE for d in doses); pending=len(doses)-completed; pct=(completed/len(doses)*100) if doses else 0
    md=f"## 👤 {p['name']}\n**Category:** {p['category']} &nbsp; **DOB:** {p['dob']} &nbsp; **Email:** {p['email'] or '—'}\n\n### Progress: {pct:.0f}%\n**{completed} completed · {pending} pending · {overdue} overdue**"
    rows=[{"Vaccine":d["vaccine_name"],"Dose":d["dose_label"],"Due Date":d["due_date"],"Status":d["status"],"Administered On":d["administered_date"] or "—"} for d in doses]
    upcoming=[r for r in rows if r["Status"]!=db.STATUS_COMPLETED]
    return md,pd.DataFrame(rows,columns=RECORD_COLUMNS),pd.DataFrame(upcoming,columns=RECORD_COLUMNS),f"**Completion rate:** {pct:.1f}%"
def _overdue_choices(pid=None):
    agent.perceive()
    rows=[]
    for d in db.list_all_doses(False):
        if d['status'] != db.STATUS_OVERDUE:
            continue
        if pid and int(d['patient_id']) != int(pid):
            continue
        rows.append((f"{d['patient_name']} — {d['vaccine_name']} {d['dose_label']} (due {d['due_date']})",d['id']))
    return rows

def load_patient_record(pid):
    md,df,up,pct=_patient_dashboard(pid)
    doses=db.get_doses_for_patient(int(pid)) if pid else []
    pending=[(f"{d['vaccine_name']} — {d['dose_label']} (due {d['due_date']})",d['id']) for d in doses if d['status']!=db.STATUS_COMPLETED]
    missed=_overdue_choices(pid) if pid else []
    return df,gr.update(choices=pending,value=None),md,up,pct,gr.update(choices=missed,value=None)

def load_missed_patient(pid):
    return gr.update(choices=_overdue_choices(pid),value=None)

def do_mark(pid,dose):
    if not pid or not dose:
        df,choice,md,up,pct,od=load_patient_record(pid) if pid else (pd.DataFrame(),gr.update(choices=[]),"Select a patient.",pd.DataFrame(),"",gr.update(choices=[]))
        a,b,c=refresh_dashboard()
        return df,choice,md,up,pct,a,b,c
    try:
        db.mark_administered(int(dose))
        df,choice,md,up,pct,od=load_patient_record(pid)
        a,b,c=refresh_dashboard()
        return df,choice,md,up,pct,a,b,c
    except Exception:
        df,choice,md,up,pct,od=load_patient_record(pid)
        a,b,c=refresh_dashboard()
        return df,choice,md,up,pct,a,b,c
def reschedule(dose,new_date,reason):
    if not dose:
        a,b,c=refresh_dashboard()
        return "### ❌ Rescheduling failed\nSelect an overdue/missed dose and click **Reschedule Vaccination** again. **No page refresh is required.**",gr.update(choices=_overdue_choices(),value=None),a,b,c
    try:
        nd=date.fromisoformat((new_date or '').strip())
    except:
        a,b,c=refresh_dashboard()
        return "### ❌ Rescheduling failed\nNew date must be in **YYYY-MM-DD** format. Correct it and click again. **No page refresh is required.**",gr.update(choices=_overdue_choices(),value=dose),a,b,c
    if nd<date.today():
        a,b,c=refresh_dashboard()
        return "### ❌ Rescheduling failed\nNew date cannot be in the past. Correct it and click again. **No page refresh is required.**",gr.update(choices=_overdue_choices(),value=dose),a,b,c
    try:
        db.reschedule_dose(int(dose),nd.isoformat(),reason or "Missed vaccination follow-up")
        a,b,c=refresh_dashboard()
        return "### ✅ Vaccination rescheduled\nThe new date has been saved. You can continue using the page without refreshing.",gr.update(choices=_overdue_choices(),value=None),a,b,c
    except Exception as exc:
        a,b,c=refresh_dashboard()
        return f"### ❌ Rescheduling failed\n`{exc}`\nCorrect the details and try again. **No page refresh is required.**",gr.update(choices=_overdue_choices(),value=dose),a,b,c

def analytics():
    try:
        # Refresh computed statuses before calculating analytics.
        agent.perceive(); x=db.get_analytics(); s=db.get_dashboard_stats(); rows=[]
    except Exception as exc:
        return f"### ❌ Analytics could not be refreshed\n`{exc}`\nTry **Refresh Analytics** again. **No page refresh is required.**", pd.DataFrame(columns=["Metric","Category","Count"]), None
    for item in x["status"]: rows.append({"Metric":"Status","Category":item["status"],"Count":item["count"]})
    for item in x["categories"]: rows.append({"Metric":"Patient Category","Category":item["category"],"Count":item["count"]})
    for item in x["channels"]: rows.append({"Metric":"Reminder Channel","Category":item["channel"],"Count":item["count"]})
    completed=s["completed"]; total=s["total_doses"]; rate=(completed/total*100) if total else 0
    md=f"### 📊 Key Metrics\n**Completion Rate:** {rate:.1f}%  ·  **Overdue:** {s['overdue']}  ·  **Reminders Sent:** {s['reminders_sent']}  ·  **Rescheduled:** {s['rescheduled']}"
    # one compact analytics figure with four bars
    fig,ax=plt.subplots(figsize=(7,3.5)); labels=["Scheduled","Due","Overdue","Completed","Rescheduled"]; vals=[s['scheduled'],s['due_today'],s['overdue'],s['completed'],s['rescheduled']]; bars=ax.bar(labels,vals); ax.bar_label(bars,padding=3); ax.set_title("System Analytics Overview"); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False); fig.tight_layout()
    return md,pd.DataFrame(rows,columns=["Metric","Category","Count"]),fig

def _manual_reminder_choices():
    agent.perceive()
    return [(f"{d['patient_name']} — {d['vaccine_name']} {d['dose_label']} (due {d['due_date']})", d['id'])
            for d in db.list_all_doses(False)]

def send_reminder_again(dose_id):
    if not dose_id:
        return "### ❌ Reminder not sent\nSelect a patient/vaccine first, then click **Send Reminder Again**. **No page refresh is required.**",gr.update(choices=_manual_reminder_choices(),value=None),_log_df()
    try:
        result = agent.send_manual_reminder(int(dose_id))
    except Exception as exc:
        return f"### ❌ Reminder not sent\n`{exc}`\nCorrect the selection and click the button again. **No page refresh is required.**",gr.update(choices=_manual_reminder_choices(),value=dose_id),_log_df()
    return (
        f"### 📧 Reminder sent again\n**Patient:** {result['patient_name']}  \n**Vaccine:** {result['vaccine_name']} ({result['dose_label']})  \n**Channel:** {result['channel']}  \n**Recipient:** {result.get('patient_email') or 'No email registered'}",
        gr.update(choices=_manual_reminder_choices(), value=None),
        _log_df()
    )

def run_agent():
    z=agent.run_cycle(); sent=z['sent']; sdf=pd.DataFrame([{"Patient":s['patient_name'],"Vaccine":s['vaccine_name'],"Dose":s['dose_label'],"Urgency":s['_urgency'],"Channel":s['channel'],"Message":s['message']} for s in sent],columns=SENT_COLUMNS); a,b,c=refresh_dashboard(); return f"**Cycle #{z['cycle']}** — scanned {z['doses_scanned']} dose(s), processed **{z['reminders_sent']}** reminder(s).",sdf,_log_df(),a,b,c
def toggle(enable,interval):
    if enable: agent.start_background(max(5,int(interval or 60))); return f"🟢 Automation running every {max(5,int(interval or 60))} seconds."
    agent.stop_background(); return "🔴 Automation stopped."
def export_csv():
    pd.DataFrame(db.list_patients()).to_csv(EXPORT_DIR/'patients.csv',index=False); pd.DataFrame(db.list_all_doses()).to_csv(EXPORT_DIR/'vaccine_doses.csv',index=False); pd.DataFrame(db.get_reminder_logs(100000)).to_csv(EXPORT_DIR/'reminder_logs.csv',index=False); pd.DataFrame(db.get_reschedule_logs(100000)).to_csv(EXPORT_DIR/'reschedule_logs.csv',index=False); return [str(x) for x in [EXPORT_DIR/'patients.csv',EXPORT_DIR/'vaccine_doses.csv',EXPORT_DIR/'reminder_logs.csv',EXPORT_DIR/'reschedule_logs.csv']]

ABOUT_MD="""## Automated Vaccination Reminder System — Enhanced Edition\n\n**Core:** Python + Gradio + SQLite + Pandas + Matplotlib.\n\n### Enhancements included\n- 📧 Real Gmail email delivery through SMTP using a local `email_config.py` file and Google App Password. A built-in Test Email button verifies the connection.\n- 👤 Patient-specific dashboard with progress, upcoming and completed doses.\n- ⚠️ Missed vaccination handling: overdue list, rescheduling and reschedule history.\n- 📊 Analytics: completion rate, status, patient category and reminder-channel statistics.\n- 🤖 Automated Perceive → Decide → Act reminder agent with cooldowns.\n\n**Email setup:** edit `email_config.py` with the Gmail App Password and receiver email. The app includes a Test Email button.\n\n*Vaccination schedules in this academic project are illustrative and must be validated against current official clinical guidance before real-world use.*"""

with gr.Blocks(title="Automated Vaccination Reminder System",analytics_enabled=False) as demo:
    gr.Markdown("# 💉 Automated Vaccination Reminder System\n**Enhanced Edition — Email • Patient Dashboard • Missed Vaccinations • Analytics**")
    with gr.Tab("📊 Dashboard"):
        ds=gr.HTML(); dt=gr.Dataframe(label="Scheduled, Due & Overdue Doses",interactive=False); dp=gr.Plot(label="Status Distribution"); dbtn=gr.Button("🔄 Refresh Now"); timer=gr.Timer(6)
    with gr.Tab("📝 Register Patient"):
        gr.Markdown("Register a patient and automatically generate the schedule.")
        with gr.Row():
            with gr.Column():
                rn=gr.Textbox(label="Full Name"); rd=gr.Textbox(label="Date of Birth",placeholder="YYYY-MM-DD"); rg=gr.Radio(["Male","Female","Other"],label="Gender"); re=gr.Textbox(label="Email"); rp=gr.Textbox(label="Phone");
                with gr.Row(): rs=gr.Button("Register Patient",variant="primary"); seed=gr.Button("🎲 Load Sample Data")
            with gr.Column(): rc=gr.Markdown(); rprev=gr.Dataframe(label="Auto-Generated Schedule",interactive=False)
    with gr.Tab("👤 Patient Dashboard"):
        psel=gr.Dropdown(label="Select Patient",choices=_patient_choices()); pmd=gr.Markdown(); ptable=gr.Dataframe(label="Complete Vaccination History",interactive=False); pup=gr.Dataframe(label="Upcoming / Overdue",interactive=False); pp=gr.Markdown()
    with gr.Tab("💉 Vaccination Records"):
        rsel=gr.Dropdown(label="Select Patient",choices=_patient_choices()); rtable=gr.Dataframe(label="Vaccination History",interactive=False); rdose=gr.Dropdown(label="Pending Dose"); mark=gr.Button("✅ Mark as Administered",variant="primary")
        gr.Markdown("*If an input is invalid, correct it and click the button again — no page refresh is required.*")
    with gr.Tab("⚠️ Missed Vaccinations"):
        gr.Markdown("Select the patient first, then select one of that patient's overdue/missed doses.")
        with gr.Row():
            msel=gr.Dropdown(label="1. Select Patient",choices=_patient_choices(),scale=2)
            mrefresh=gr.Button("🔄 Refresh",scale=1)
        odose=gr.Dropdown(label="2. Select Overdue / Missed Dose",choices=[])
        with gr.Row():
            nd=gr.Textbox(label="New Vaccination Date",placeholder="YYYY-MM-DD")
            reason=gr.Textbox(label="Reason (optional)")
        res=gr.Button("📅 Reschedule Vaccination",variant="primary"); resmsg=gr.Markdown()
        gr.Markdown("*If an input is invalid, correct it and click the button again — no page refresh is required.*")
    with gr.Tab("📧 Email Setup & Test"):
        gr.Markdown("### Real Gmail Email Setup\nEdit **email_config.py** once with your Gmail App Password and receiver email. Then test the connection here.")
        gr.Markdown(f"**Sender:** `{email_config.SENDER_EMAIL}`  ·  **SMTP:** `{email_config.SMTP_HOST}:{email_config.SMTP_PORT}`")
        etest=gr.Button("📧 Send Test Email",variant="primary")
        eres=gr.Markdown()
        etest.click(send_test_email,outputs=eres)
    with gr.Tab("🤖 Automation / Reminder Agent"):
        with gr.Row(): run=gr.Button("▶️ Run Agent Now",variant="primary"); togglebox=gr.Checkbox(label="Enable background automation"); interval=gr.Number(label="Interval (seconds)",value=30,minimum=5,precision=0)
        ast=gr.Markdown(); summary=gr.Markdown(); sent=gr.Dataframe(label="Reminders This Cycle",interactive=False); logs=gr.Dataframe(label="Reminder Log",interactive=False,max_height=350)
        gr.Markdown("### 📧 Manual Follow-up / Demonstration")
        gr.Markdown("Use this when you want to demonstrate a reminder or resend one immediately. It bypasses the normal cooldown.")
        with gr.Row():
            manual_dose=gr.Dropdown(label="1. Select Patient / Vaccine",choices=_manual_reminder_choices(),scale=3)
            refresh_manual=gr.Button("🔄 Refresh List",scale=1)
            resend=gr.Button("📧 2. Send Reminder Again",variant="secondary",scale=2)
        resend_result=gr.Markdown()
    with gr.Tab("📊 Analytics"):
        gr.Markdown("Analytics updates in place. If an input/action fails, correct it and retry without refreshing the page.")
        aref=gr.Button("📈 Refresh Analytics",variant="primary"); amd=gr.Markdown(); at=gr.Dataframe(label="Analytics Details",interactive=False); ap=gr.Plot(label="Analytics Overview")
    with gr.Tab("📤 Reports & Export"):
        ex=gr.Button("⬇️ Export All Records to CSV",variant="primary"); files=gr.File(label="Download",file_count="multiple")
    with gr.Tab("ℹ️ About"): gr.Markdown(ABOUT_MD)
    outs=[ds,dt,dp]; demo.load(refresh_dashboard,outputs=outs); dbtn.click(refresh_dashboard,outputs=outs); timer.tick(refresh_dashboard,outputs=outs)
    rs.click(register_patient,[rn,rd,rg,re,rp],[rc,rprev,psel,*outs]); seed.click(seed_sample_data,[rc,psel,*outs])
    psel.change(_patient_dashboard,[psel],[pmd,ptable,pup,pp]); rsel.change(load_patient_record,[rsel],[rtable,rdose,pmd,pup,pp,odose]); msel.change(load_missed_patient,[msel],[odose]); mrefresh.click(lambda pid: gr.update(choices=_overdue_choices(pid),value=None),[msel],[odose])
    mark.click(do_mark,[rsel,rdose],[rtable,rdose,pmd,pup,pp,ds,dt,dp]); res.click(reschedule,[odose,nd,reason],[resmsg,odose,ds,dt,dp])
    run.click(run_agent,outputs=[summary,sent,logs,*outs]); togglebox.change(toggle,[togglebox,interval],ast); refresh_manual.click(lambda: gr.update(choices=_manual_reminder_choices()),outputs=manual_dose); resend.click(send_reminder_again,[manual_dose],[resend_result,manual_dose,logs]); aref.click(analytics,outputs=[amd,at,ap]); ex.click(export_csv,outputs=files)

if __name__=="__main__": demo.queue().launch(theme=gr.themes.Soft(primary_hue="blue"))
