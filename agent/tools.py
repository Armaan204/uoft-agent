"""
agent/tools.py — Claude tool definitions and dispatch.

Defines the JSON schema for every tool that the agent can call, and
maps each tool name to the Python function that implements it.

Tool catalogue (planned)
------------------------
- get_courses          : list the student's enrolled courses from Quercus
- get_grades           : fetch grades for a course from Quercus
- get_transcript       : pull cumulative grades / GPA from ACORN
- get_syllabus_weights : extract assessment weights from a syllabus PDF
- calculate_required   : compute the mark needed on a future assessment
"""
