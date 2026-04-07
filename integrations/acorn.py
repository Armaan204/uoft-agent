"""
integrations/acorn.py — ACORN session client.

ACORN (Accessible Campus Online Resource Network) is UofT's student
information system.  It has no public API, so this module drives the
web interface programmatically using the ACORN_USERNAME and
ACORN_PASSWORD environment variables.

Planned functions
-----------------
- login()               : authenticate and store the session cookie.
- get_transcript()      : scrape the unofficial transcript page and
                          return a list of course records with grades
                          and credit values.
- get_current_courses() : return the student's current enrolment from
                          the timetable view.

Authentication state is kept in a module-level session object; callers
do not need to manage cookies directly.
"""
