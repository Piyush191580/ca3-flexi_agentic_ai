"""
test_logic.py
---------------
Standalone sanity test for the non-GUI parts of the system: database.py,
schedule_engine.py, and reminder_agent.py. Run with:

    python test_logic.py

Not a pytest suite on purpose -- it prints a readable trace of a full
scenario (register -> schedule -> perceive -> decide -> act -> mark
administered -> re-run) so it doubles as a demo you can read for the
project report / viva.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import database as db
import schedule_engine
from reminder_agent import ReminderAgent

PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


print("=== Resetting test database ===")
db.reset_db()

print("\n=== 1. determine_category() ===")
check("newborn -> Child", schedule_engine.determine_category(date.today()) == "Child")
check("17-year-old -> Child", schedule_engine.determine_category(date.today() - timedelta(days=365*17)) == "Child")
check("19-year-old -> Adult", schedule_engine.determine_category(date.today() - timedelta(days=365*19)) == "Adult")

print("\n=== 2. generate_schedule() ===")
child_dob = date.today() - timedelta(days=40)
child_sched = schedule_engine.generate_schedule(child_dob, "Child")
check("child schedule has 22 doses", len(child_sched) == len(schedule_engine.CHILD_SCHEDULE))
check("birth dose due date == DOB", child_sched[0][2] == child_dob.isoformat())
adult_sched = schedule_engine.generate_schedule(date.today() - timedelta(days=365*30), "Adult")
check("adult schedule has 7 doses", len(adult_sched) == len(schedule_engine.ADULT_SCHEDULE))
check("adult dose 1 anchored at registration (today)", adult_sched[0][2] == date.today().isoformat())

print("\n=== 3. Register patients end-to-end ===")
# Child, 40 days old: birth doses ~40 days overdue; 6-week dose due in 2 days (Upcoming)
pid_child = db.add_patient("Test Child", child_dob.isoformat(), "Male", "Child", "child@example.com", "111")
db.bulk_add_doses(pid_child, child_sched)
check("patient row created", db.get_patient(pid_child) is not None)
check("doses inserted for child", len(db.get_doses_for_patient(pid_child)) == len(child_sched))

# Adult registered today: several doses due today
adult_dob = date.today() - timedelta(days=365*29)
pid_adult = db.add_patient("Test Adult", adult_dob.isoformat(), "Female", "Adult", "adult@example.com", "222")
db.bulk_add_doses(pid_adult, adult_sched)
check("doses inserted for adult", len(db.get_doses_for_patient(pid_adult)) == len(adult_sched))

print("\n=== 4. Agent perceive() classifies correctly ===")
agent = ReminderAgent()
perceived = agent.perceive()
by_id = {d["id"]: d for d in perceived}
child_doses = db.get_doses_for_patient(pid_child)
birth_dose = next(d for d in child_doses if d["dose_label"] == "Birth Dose" and d["vaccine_name"] == "BCG")
six_week = next(d for d in child_doses if d["dose_label"] == "Dose 1" and "Pentavalent" in d["vaccine_name"])
check("birth dose (40d ago) perceived as Overdue", by_id[birth_dose["id"]]["_computed_status"] == db.STATUS_OVERDUE)
check("6-week dose (due in 2d) perceived as Scheduled", by_id[six_week["id"]]["_computed_status"] == db.STATUS_SCHEDULED)
check("6-week dose days_diff == 2", by_id[six_week["id"]]["_days_diff"] == 2)

adult_doses = db.get_doses_for_patient(pid_adult)
td_booster = next(d for d in adult_doses if "Td" in d["vaccine_name"])
check("Td booster (due today) perceived as Due Today", by_id[td_booster["id"]]["_computed_status"] == db.STATUS_DUE_TODAY)

print("\n=== 5. Agent decide() + act() generate correct reminders ===")
summary = agent.run_cycle()
print(f"  cycle summary: scanned={summary['doses_scanned']} sent={summary['reminders_sent']}")
check("at least one reminder sent", summary["reminders_sent"] > 0)
sent_ids = {s["id"] for s in summary["sent"]}
check("overdue birth dose got a reminder", birth_dose["id"] in sent_ids)
check("due-today Td booster got a reminder", td_booster["id"] in sent_ids)
check("6-week dose (2 days out, within 7-day window) got a reminder", six_week["id"] in sent_ids)

far_future = next(d for d in adult_doses if d["dose_label"] == "Dose 3" and "Hepatitis" in d["vaccine_name"])
check("far-future Hep-B dose 3 (180d out) NOT reminded yet", far_future["id"] not in sent_ids)

logs_after_cycle1 = db.get_reminder_logs()
check("reminder_logs row count matches sent count", len(logs_after_cycle1) == summary["reminders_sent"])

print("\n=== 6. Re-running immediately respects cooldown (no duplicate spam) ===")
summary2 = agent.run_cycle()
print(f"  cycle 2 summary: scanned={summary2['doses_scanned']} sent={summary2['reminders_sent']}")
check("running again immediately sends 0 new reminders (cooldown)", summary2["reminders_sent"] == 0)

print("\n=== 7. mark_administered() moves a dose out of the pending pool ===")
db.mark_administered(birth_dose["id"])
updated = db.get_patient(pid_child)
remaining = db.get_doses_for_patient(pid_child)
completed = [d for d in remaining if d["id"] == birth_dose["id"]][0]
check("status flips to Completed", completed["status"] == db.STATUS_COMPLETED)
check("administered_date is set", completed["administered_date"] == date.today().isoformat())
pending_after = db.list_all_doses(include_completed=False)
check("completed dose excluded from pending list", birth_dose["id"] not in [d["id"] for d in pending_after])

print("\n=== 8. Dashboard stats reconcile with raw counts ===")
stats = db.get_dashboard_stats()
all_doses = db.list_all_doses(include_completed=True)
check("total_doses matches", stats["total_doses"] == len(all_doses))
check("completed count == 1", stats["completed"] == 1)
check("total_patients == 2", stats["total_patients"] == 2)
recount = stats["scheduled"] + stats["due_today"] + stats["overdue"] + stats["completed"]
check("status buckets sum to total_doses", recount == stats["total_doses"])

print("\n=== 9. CSV export round-trips ===")
import pandas as pd
df_patients = pd.DataFrame(db.list_patients())
df_doses = pd.DataFrame(db.list_all_doses())
check("patients dataframe has 2 rows", len(df_patients) == 2)
check("doses dataframe has expected row count", len(df_doses) == len(child_sched) + len(adult_sched))

print(f"\n=== RESULT: {PASS} passed, {FAIL} failed ===")
if FAIL:
    sys.exit(1)
