"""
integrations/quercus.py — Quercus (Canvas LMS) API client.

Quercus is the University of Toronto's instance of Instructure Canvas.
This module authenticates with a Bearer token (QUERCUS_API_TOKEN) and
wraps the Canvas REST API endpoints needed by the agent.
"""

import os
import re
from hashlib import sha256
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


class QuercusError(Exception):
    """Raised when a Quercus API request fails."""


def _cached_paginated_get(token: str, path: str, params: dict | list | None = None) -> list | dict:
    """Make an authenticated GET request with Canvas pagination handling."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{QuercusClient.BASE_URL}{path}"
    results = []

    while url:
        response = requests.get(url, headers=headers, params=params)
        if not response.ok:
            raise QuercusError(f"GET {url} returned {response.status_code}: {response.text}")

        data = response.json()
        if isinstance(data, dict):
            return data

        results.extend(data)
        url = None
        params = None
        link_header = response.headers.get("Link", "")
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    return results


@st.cache_data(ttl=300, show_spinner=False)
def _cached_get_assignment_groups(_token: str, token_cache_key: str, course_id: int | str) -> list:
    """Cached assignment-group lookup scoped by token and course."""
    return _cached_paginated_get(
        _token,
        f"/courses/{course_id}/assignment_groups",
        params={"include[]": "assignments"},
    )


@st.cache_data(ttl=300, show_spinner=False)
def _cached_get_submissions(_token: str, token_cache_key: str, course_id: int | str) -> list:
    """Cached submission lookup scoped by token and course."""
    return _cached_paginated_get(
        _token,
        f"/courses/{course_id}/students/submissions",
        params={"student_ids[]": "self"},
    )


class QuercusClient:
    BASE_URL = "https://q.utoronto.ca/api/v1"
    _UPCOMING_TERM_WINDOW_DAYS = 45

    def __init__(self, token: str = None):
        token = token or os.getenv("QUERCUS_API_TOKEN")
        if not token:
            raise QuercusError("QUERCUS_API_TOKEN is not set")
        self._token = token
        self._token_cache_key = sha256(token.encode("utf-8")).hexdigest()
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

    # Keywords whose presence in a course name marks it as a resource page,
    # not a real academic course.
    _RESOURCE_PAGE_KEYWORDS = [
        "co-op compass",
        "undergrads",
        "community",
        "sandbox",
        "test course",
    ]

    def get_courses(self) -> list:
        """Return the student's active academic course enrolments.

        Fetches /courses with enrollment_state=active and include[]=term so
        the enrollment term metadata is available for filtering.

        Filtering strategy
        ------------------
        1. Exclude resource pages by name.
        2. Exclude courses whose term is missing or undated ("Default Term").
        3. Prefer courses whose term contains the current date.
        4. If none are current, prefer the nearest upcoming term within a short
           window.
        5. If neither exists, fall back to the most recent dated term.

        This keeps the selection dynamic across years and semesters instead of
        hardcoding a specific term name like "2026 Winter".
        """
        # Pass include[] twice — requests accepts a list of tuples for this
        courses = self._get(
            "/courses",
            params=[
                ("enrollment_state", "active"),
                ("include[]", "syllabus_body"),
                ("include[]", "term"),
            ],
        )

        now = datetime.now(timezone.utc)
        eligible = []
        for course in courses:
            # 1. Resource-page name filter
            name_lower = course.get("name", "").lower()
            if any(kw in name_lower for kw in self._RESOURCE_PAGE_KEYWORDS):
                continue

            # 2. Ignore undated/default-term entries
            term = course.get("term") or {}
            start_at = self._parse_canvas_datetime(term.get("start_at"))
            end_at = self._parse_canvas_datetime(term.get("end_at"))
            if start_at is None or end_at is None:
                continue

            eligible.append({
                "course": course,
                "start_at": start_at,
                "end_at": end_at,
            })

        if not eligible:
            return []

        current = [e["course"] for e in eligible if e["start_at"] <= now <= e["end_at"]]
        if current:
            return current

        # Prefer the nearest upcoming term if the current term has not started yet.
        upcoming = [
            e for e in eligible
            if 0 <= (e["start_at"] - now).total_seconds() <= self._UPCOMING_TERM_WINDOW_DAYS * 86400
        ]
        if upcoming:
            nearest_start = min(e["start_at"] for e in upcoming)
            return [e["course"] for e in upcoming if e["start_at"] == nearest_start]

        latest_end = max(e["end_at"] for e in eligible)
        return [e["course"] for e in eligible if e["end_at"] == latest_end]

    @staticmethod
    def _parse_canvas_datetime(value: str | None) -> datetime | None:
        """Parse Canvas ISO timestamps like '2026-05-31T04:00:00Z'."""
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

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
        return _cached_get_submissions(
            self._token,
            self._token_cache_key,
            course_id,
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

    def get_file_metadata(self, file_id: int | str) -> dict:
        """Return Canvas metadata for one file ID."""
        return self._get(f"/files/{file_id}")

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

    def get_front_page(self, course_id: int | str) -> dict:
        """Return the course homepage (front page) wiki page.

        The front page body is plain HTML and often contains links to the
        course outline, syllabus, or schedule as named anchor tags.
        Returns a dict with at least a 'body' key (may be None if unset).
        """
        return self._get(f"/courses/{course_id}/front_page")

    def get_page(self, course_id: int | str, page_url_or_id: str) -> dict:
        """Return one Canvas wiki page by URL slug or page ID."""
        return self._get(f"/courses/{course_id}/pages/{page_url_or_id}")

    def get_course_modules(self, course_id: int | str) -> list:
        """Return all modules for a course, with their items inline.

        Passes include[]=items so each module dict contains a nested 'items'
        list.  Items of type 'File' carry a 'content_id' (the Canvas file ID)
        that can be resolved to a download URL via get_file_download_url().
        """
        return self._get(
            f"/courses/{course_id}/modules",
            params={"include[]": "items"},
        )

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
        Canvas group responses may also include grading `rules` such as
        drop_lowest, drop_highest, and never_drop, which the calculator uses
        to mirror Canvas grade math.
        """
        return _cached_get_assignment_groups(
            self._token,
            self._token_cache_key,
            course_id,
        )

    def get_canvas_weights(self, course_id: int | str) -> dict[str, float] | None:
        """Return grade weights from Canvas assignment group configuration.

        Canvas lets instructors set a percentage weight directly on each
        assignment group.  When at least one group has a non-zero weight,
        this method returns a dict mapping group name → weight percentage
        so the caller can skip syllabus parsing entirely.

        Returns None when no groups have weights configured (all zeros),
        indicating that syllabus parsing is required.
        """
        groups = self.get_assignment_groups(course_id)
        weights = {
            g["name"]: float(g.get("group_weight") or 0)
            for g in groups
        }
        if any(w > 0 for w in weights.values()):
            return weights
        return None

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

    def get_latest_announcements(self, course_ids: list[int | str], days_back: int = 180) -> list[dict]:
        """Return the most recent published announcement for each course."""
        if not course_ids:
            return []

        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days_back)).date().isoformat()
        end_date = now.date().isoformat()
        params = [
            ("latest_only", "true"),
            ("active_only", "true"),
            ("start_date", start_date),
            ("end_date", end_date),
        ]
        for course_id in course_ids:
            params.append(("context_codes[]", f"course_{course_id}"))

        return self._get("/announcements", params=params)

    def get_course_announcements(self, course_id: int | str, limit: int = 10, days_back: int = 180) -> list[dict]:
        """Return recent announcements for one course."""
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days_back)).date().isoformat()
        end_date = now.date().isoformat()
        params = [
            ("active_only", "true"),
            ("start_date", start_date),
            ("end_date", end_date),
            ("context_codes[]", f"course_{course_id}"),
        ]
        announcements = self._get("/announcements", params=params)
        announcements.sort(key=lambda item: item.get("posted_at") or "", reverse=True)
        return announcements[:limit]

    def get_announcement_detail(self, announcement_id: int | str) -> dict:
        """Return one announcement by Canvas announcement ID."""
        return self._get(f"/announcements/{announcement_id}")
