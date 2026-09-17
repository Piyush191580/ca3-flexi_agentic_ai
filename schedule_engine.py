"""
schedule_engine.py
--------------------
Generates a patient's complete vaccination timeline the moment they are
registered, so no staff member has to manually schedule each dose.

The schedules below follow the general shape of widely published national
immunization programs: a birth dose (BCG / OPV / Hepatitis-B), the
6-10-14 week primary series, boosters in the second year, and school-age /
adult boosters and annual doses. They are illustrative reference data for
this academic project and NOT medical advice -- a real deployment should
source doses and timing from a certified medical or public-health
authority and let a clinician override them per patient.
"""

from datetime import date, timedelta

CHILD_AGE_LIMIT_YEARS = 18

# Each entry: (days_after_date_of_birth, vaccine_name, dose_label)
CHILD_SCHEDULE: list[tuple[int, str, str]] = [
    (0,    "BCG",                          "Birth Dose"),
    (0,    "Oral Polio Vaccine (OPV)",      "Dose 0"),
    (0,    "Hepatitis B",                   "Birth Dose"),
    (42,   "Pentavalent (DTP-HepB-Hib)",    "Dose 1"),
    (42,   "Oral Polio Vaccine (OPV)",      "Dose 1"),
    (42,   "Rotavirus",                     "Dose 1"),
    (42,   "Pneumococcal Conjugate (PCV)",  "Dose 1"),
    (70,   "Pentavalent (DTP-HepB-Hib)",    "Dose 2"),
    (70,   "Oral Polio Vaccine (OPV)",      "Dose 2"),
    (70,   "Rotavirus",                     "Dose 2"),
    (98,   "Pentavalent (DTP-HepB-Hib)",    "Dose 3"),
    (98,   "Oral Polio Vaccine (OPV)",      "Dose 3"),
    (98,   "Rotavirus",                     "Dose 3"),
    (98,   "Pneumococcal Conjugate (PCV)",  "Dose 2"),
    (270,  "Measles-Rubella (MR)",          "Dose 1"),
    (270,  "Pneumococcal Conjugate (PCV)",  "Booster"),
    (485,  "DPT",                           "Booster 1"),
    (485,  "Oral Polio Vaccine (OPV)",      "Booster"),
    (485,  "Measles-Rubella (MR)",          "Dose 2"),
    (1825, "DPT",                           "Booster 2"),
    (3650, "Tetanus-Diphtheria (Td)",       "Dose 1"),
    (5840, "Tetanus-Diphtheria (Td)",       "Booster"),
]

# Each entry: (days_after_registration, vaccine_name, dose_label)
ADULT_SCHEDULE: list[tuple[int, str, str]] = [
    (0,   "Tetanus-Diphtheria (Td/Tdap)", "Routine Booster"),
    (0,   "Hepatitis B",                   "Dose 1"),
    (30,  "Hepatitis B",                   "Dose 2"),
    (180, "Hepatitis B",                   "Dose 3"),
    (0,   "Influenza (Flu)",               "Annual Dose"),
    (365, "Influenza (Flu)",               "Annual Booster"),
    (0,   "COVID-19",                      "Booster Dose"),
]


def determine_category(dob: date, on_date: date | None = None) -> str:
    """Child if under 18 on the reference date (registration day by default), else Adult."""
    on_date = on_date or date.today()
    age_years = (on_date - dob).days / 365.25
    return "Child" if age_years < CHILD_AGE_LIMIT_YEARS else "Adult"


def generate_schedule(dob: date, category: str,
                       registered_on: date | None = None) -> list[tuple[str, str, str]]:
    """Return [(vaccine_name, dose_label, due_date_iso), ...] for a new patient."""
    registered_on = registered_on or date.today()
    schedule = []
    source = CHILD_SCHEDULE if category == "Child" else ADULT_SCHEDULE
    anchor = dob if category == "Child" else registered_on
    for offset, vaccine, dose_label in source:
        due = anchor + timedelta(days=offset)
        schedule.append((vaccine, dose_label, due.isoformat()))
    return schedule
