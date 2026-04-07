"""
integrations/quercus.py — Quercus (Canvas LMS) API client.

Quercus is the University of Toronto's instance of Instructure Canvas.
This module authenticates with a Bearer token (QUERCUS_API_TOKEN) and
wraps the Canvas REST API endpoints needed by the agent.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()


class QuercusError(Exception):
    """Raised when a Quercus API request fails."""


class QuercusClient:
    BASE_URL = "https://q.utoronto.ca/api/v1"

    def __init__(self):
        token = os.getenv("QUERCUS_API_TOKEN")
        if not token:
            raise QuercusError("QUERCUS_API_TOKEN is not set")
        self._headers = {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict = None) -> list | dict:
        """Make an authenticated GET request and return parsed JSON.

        Handles Canvas pagination automatically — if the response is a
        list, subsequent pages are fetched via the Link header and
        concatenated before returning.
        """
        url = f"{self.BASE_URL}{path}"
        results = []

        while url:
            response = requests.get(url, headers=self._headers, params=params)
            if not response.ok:
                raise QuercusError(
                    f"GET {url} returned {response.status_code}: {response.text}"
                )

            data = response.json()

            # If the response is a single object, return it immediately
            if isinstance(data, dict):
                return data

            results.extend(data)

            # Follow Canvas pagination via the Link header
            url = None
            params = None  # params are already encoded in the next URL
            link_header = response.headers.get("Link", "")
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break

        return results

    def get_courses(self) -> list:
        """Return the student's active course enrolments.

        Fetches /courses with enrollment_state=active and includes the
        syllabus body so the calculator can parse grade weights from it.
        """
        return self._get(
            "/courses",
            params={
                "enrollment_state": "active",
                "include[]": "syllabus_body",
            },
        )

    def get_assignments(self, course_id: int | str) -> list:
        """Return all assignments for a course.

        Each assignment dict includes name, points_possible, due_at,
        and grading_type.
        """
        return self._get(f"/courses/{course_id}/assignments")

    def get_submissions(self, course_id: int | str) -> list:
        """Return the student's own submissions for every assignment in a course.

        Each submission dict includes assignment_id, score, grade, and
        submitted_at.  Requires the student's own token — will not work
        with a teacher token scoped to a specific student.
        """
        return self._get(
            f"/courses/{course_id}/students/submissions",
            params={"student_ids[]": "self"},
        )

    def get_grades(self, course_id: int | str) -> dict:
        """Return the student's current grade summary for a course.

        Fetches the enrollment record which contains current_score,
        current_grade, final_score, and final_grade.
        """
        enrollments = self._get(
            f"/courses/{course_id}/enrollments",
            params={"type[]": "StudentEnrollment", "user_id": "self"},
        )
        if not enrollments:
            raise QuercusError(f"No student enrollment found for course {course_id}")
        return enrollments[0]
