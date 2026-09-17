# Automated Vaccination Reminder System — Enhanced Edition

Python + Gradio + SQLite + Pandas + Matplotlib.

## Features
- Automatic child/adult vaccination schedules
- Patient registration and vaccination records
- Patient-specific dashboard and completion progress
- Missed/overdue vaccination detection
- Vaccination rescheduling with history
- Real Gmail email reminders through the Reminder Agent
- Email test button
- Reminder history and cooldowns
- Analytics and charts
- CSV export
- Background reminder automation

## Real Gmail setup
1. Open `email_config.py`.
2. Keep `SENDER_EMAIL` as your project Gmail (or change it).
3. Replace `APP_PASSWORD` with your 16-character Google App Password.
4. Replace `TEST_RECEIVER_EMAIL` with the email where you want to receive tests/reminders.
5. Run `app.py`.
6. Open **Email Setup & Test** and click **Send Test Email**.
7. Once the test works, register patients with real email addresses. The Reminder Agent can then send real reminders automatically.

Gmail SMTP uses `smtp.gmail.com` on port `587`.

## Run
```bat
"C:\ProgramData\anaconda3\python.exe" -c "import database; database.init_db()"
"C:\ProgramData\anaconda3\python.exe" app.py
```

The vaccination schedules in this academic project are illustrative and should be validated against current official clinical guidance before real-world use.
