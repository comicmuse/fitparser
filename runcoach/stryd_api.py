"""Stryd API client."""

from __future__ import annotations

import datetime
import os
import requests
from typing import Dict, List, Optional


class StrydAPI:
    BASE_URL = "https://www.stryd.com/b"

    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.session_id: Optional[str] = None
        self.user_id: Optional[str] = None

    def authenticate(self) -> str:
        try:
            response = requests.post(
                f"{self.BASE_URL}/email/signin",
                json={"email": self.email, "password": self.password},
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error during authentication: {e}")

        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.status_code} - {response.text}")

        data = response.json()
        self.session_id = data.get("token")
        self.user_id = data.get("id")

        if not self.session_id:
            raise Exception("Authentication response missing token")

        return self.session_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer: {self.session_id}"}

    def get_activities(self, days: int = 30) -> List[Dict]:
        if not self.session_id:
            self.authenticate()

        end_date = datetime.datetime.now() + datetime.timedelta(days=1)
        start_date = end_date - datetime.timedelta(days=days)

        response = requests.get(
            f"{self.BASE_URL}/api/v1/users/calendar",
            headers=self._headers(),
            params={
                "srtDate": start_date.strftime("%m-%d-%Y"),
                "endDate": end_date.strftime("%m-%d-%Y"),
                "sortBy": "StartDate",
            },
        )

        if response.status_code != 200:
            raise Exception(f"Failed to fetch activities: {response.status_code} - {response.text}")

        return response.json().get("activities", [])

    def get_planned_workouts(self, days_ahead: int = 30, days_back: int = 7) -> List[Dict]:
        """Fetch planned workouts from the training calendar.

        Uses api.stryd.com with a user-specific path and unix timestamp params,
        which returns full workout block structure. Falls back to the legacy
        www.stryd.com endpoint if user_id is unavailable.
        """
        if not self.session_id:
            self.authenticate()

        start_date = datetime.datetime.now() - datetime.timedelta(days=days_back)

        if self.user_id:
            url = f"https://api.stryd.com/b/api/v1/users/{self.user_id}/calendar"
            params: dict = {"from": int(start_date.timestamp()), "include_deleted": "false"}
        else:
            end_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)
            url = f"{self.BASE_URL}/api/v1/users/calendar"
            params = {
                "srtDate": start_date.strftime("%m-%d-%Y"),
                "endDate": end_date.strftime("%m-%d-%Y"),
                "sortBy": "StartDate",
            }

        response = requests.get(url, headers=self._headers(), params=params)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch calendar: {response.status_code} - {response.text}")

        return response.json().get("workouts", [])

    def download_fit_file(
        self,
        activity_id: str,
        output_dir: str = "fit_files",
        filename: Optional[str] = None,
    ) -> Optional[str]:
        if not self.session_id:
            self.authenticate()

        os.makedirs(output_dir, exist_ok=True)
        url = f"{self.BASE_URL}/api/v1/activities/{activity_id}/fit"

        try:
            response = requests.get(url, headers=self._headers())
            if response.status_code != 200:
                return None

            try:
                fit_url = response.json().get("url")
            except (ValueError, KeyError):
                fit_url = None

            content = requests.get(fit_url).content if fit_url else response.content
            filepath = os.path.join(output_dir, f"{filename or activity_id}.fit")
            with open(filepath, "wb") as f:
                f.write(content)
            return filepath

        except requests.exceptions.RequestException:
            return None

    def get_activity_details(self, activity_id: str) -> Optional[Dict]:
        if not self.session_id:
            self.authenticate()

        try:
            response = requests.get(
                f"{self.BASE_URL}/api/v1/activities/{activity_id}",
                headers=self._headers(),
            )
            return response.json() if response.status_code == 200 else None
        except requests.exceptions.RequestException:
            return None
