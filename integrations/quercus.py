"""
integrations/quercus.py — Quercus (Canvas LMS) API client.

Quercus is the University of Toronto's instance of Instructure Canvas.
This module authenticates with a Bearer token (QUERCUS_API_TOKEN) and
wraps the Canvas REST API endpoints needed by the agent.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
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

    def get_file_download_url(self, file_id: int | str) -> str:
        """Resolve a Canvas file ID to a direct download URL via the files API.

        GET /api/v1/files/{id} returns a JSON object with a 'url' field
        containing a pre-signed S3 URL valid for a short time.
        """
        file_meta = self._get(f"/files/{file_id}")
        url = file_meta.get("url")
        if not url:
            raise QuercusError(f"Files API returned no download URL for file {file_id}")
        return url

    def get_syllabus(self, course_id: int | str) -> dict:
        """Return the syllabus body and resolved PDF download URLs for a course.

        Fetches the course with include[]=syllabus_body, parses the HTML for
        Canvas /files/ links, extracts the file ID from each, and resolves it
        to a direct download URL via the Canvas files API.

        Returns a dict with keys:
          syllabus_body  — raw HTML string (may be None)
          pdf_urls       — list of de-duplicated direct S3 download URLs
        """
        course = self._get(f"/courses/{course_id}", params={"include[]": "syllabus_body"})
        html = course.get("syllabus_body") or ""
        pdf_urls = []
        if html:
            soup = BeautifulSoup(html, "html.parser")
            seen_ids = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                match = re.search(r"/files/(\d+)", href)
                if match:
                    file_id = match.group(1)
                    if file_id in seen_ids:
                        continue
                    seen_ids.add(file_id)
                    try:
                        pdf_urls.append(self.get_file_download_url(file_id))
                    except QuercusError:
                        pass  # skip files we can't resolve
        return {"syllabus_body": html, "pdf_urls": pdf_urls}

    def get_course_files(self, course_id: int | str) -> list:
        """Return all files uploaded to a course.

        Each file dict includes display_name, filename, content-type, url
        (pre-signed download URL), and size.
        """
        return self._get(f"/courses/{course_id}/files")

    def get_assignment_groups(self, course_id: int | str) -> list:
        """Return assignment groups for a course, each with its percentage weight.

        Passes include[]=assignments so each group dict contains a nested
        'assignments' list — avoids a separate get_assignments() call when
        both the group weight and the individual items are needed together.
        """
        return self._get(
            f"/courses/{course_id}/assignment_groups",
            params={"include[]": "assignments"},
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
