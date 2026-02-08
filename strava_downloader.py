#!/usr/bin/env python3
"""
Strava API client for OAuth2 authentication and FIT file downloads.

Handles:
- OAuth2 token management (get, refresh, store)
- Activity fetching
- FIT file downloads
- State management to prevent duplicate downloads
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests

# Try to import Selenium support (optional dependency)
try:
    from strava_selenium_downloader import StravaSeleniumDownloader
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DownloadedActivity:
    """Track information about downloaded activities."""
    activity_id: int
    download_time: str
    file_path: str


def sanitize_activity_name(name: str) -> str:
    """
    Sanitize activity name for use in filename.
    
    Rules:
    - Convert to lowercase
    - Replace spaces with underscores
    - Keep only alphanumeric characters and underscores
    - Remove emojis and punctuation
    
    Args:
        name: Activity name from Strava
        
    Returns:
        Sanitized name suitable for filename
    """
    if not name:
        return "untitled"
    
    # Convert to lowercase
    name = name.lower()
    
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    
    # Keep only alphanumeric characters and underscores
    # This removes emojis, punctuation, and special characters
    name = re.sub(r'[^a-z0-9_]', '', name)
    
    # Remove multiple consecutive underscores
    name = re.sub(r'_+', '_', name)
    
    # Remove leading/trailing underscores
    name = name.strip('_')
    
    # If empty after sanitization, use default
    if not name:
        return "untitled"
    
    return name


class StravaClient:
    """Client for Strava API interactions with OAuth2 support."""
    
    BASE_URL = "https://www.strava.com/api/v3"
    OAUTH_URL = "https://www.strava.com/oauth/token"
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        download_base_dir: str = "./downloads",
        state_file: str = "./downloaded_activities.json",
        use_selenium: bool = False,
        strava_email: Optional[str] = None,
        strava_password: Optional[str] = None
    ):
        """
        Initialize Strava client.
        
        Args:
            client_id: Strava application client ID
            client_secret: Strava application client secret
            access_token: Initial access token (optional)
            refresh_token: Refresh token for token renewal (optional)
            download_base_dir: Base directory for downloaded FIT files
            state_file: Path to JSON file tracking downloaded activities
            use_selenium: Use Selenium browser automation for downloads
            strava_email: Strava email for Selenium login (optional)
            strava_password: Strava password for Selenium login (optional)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.download_base_dir = Path(download_base_dir)
        self.state_file = Path(state_file)
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.strava_email = strava_email
        self.strava_password = strava_password
        
        # Warn if Selenium requested but not available
        if use_selenium and not SELENIUM_AVAILABLE:
            logger.warning("Selenium requested but not available. Install with: pip install selenium webdriver-manager")
        
        # Create download directory if it doesn't exist
        self.download_base_dir.mkdir(parents=True, exist_ok=True)
        
        # Load state
        self.downloaded_activities: Dict[int, DownloadedActivity] = {}
        self._load_state()
    
    def _load_state(self) -> None:
        """Load downloaded activities state from JSON file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    activities = data.get('downloaded_activities', [])
                    for act in activities:
                        activity_id = act['activity_id']
                        self.downloaded_activities[activity_id] = DownloadedActivity(**act)
                logger.info(f"Loaded state: {len(self.downloaded_activities)} activities already downloaded")
            except Exception as e:
                logger.error(f"Error loading state file: {e}")
                self.downloaded_activities = {}
        else:
            logger.info("No state file found, starting fresh")
    
    def _save_state(self) -> None:
        """Save downloaded activities state to JSON file."""
        try:
            data = {
                'downloaded_activities': [
                    asdict(activity) for activity in self.downloaded_activities.values()
                ]
            }
            # Write to temp file first, then rename for atomicity
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.state_file)
            logger.debug(f"State saved: {len(self.downloaded_activities)} activities")
        except Exception as e:
            logger.error(f"Error saving state file: {e}")
    
    def is_already_downloaded(self, activity_id: int) -> bool:
        """Check if an activity has already been downloaded."""
        return activity_id in self.downloaded_activities
    
    def get_access_token_from_code(self, authorization_code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            authorization_code: Authorization code from OAuth flow
            
        Returns:
            Dict containing access_token, refresh_token, expires_at, etc.
        """
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': authorization_code,
            'grant_type': 'authorization_code'
        }
        
        try:
            response = requests.post(self.OAUTH_URL, data=payload, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            # Update stored tokens
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            
            logger.info("Successfully obtained access token from authorization code")
            return token_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting access token from code: {e}")
            raise
    
    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh the access token using the refresh token.
        
        Returns:
            Dict containing new access_token, refresh_token, expires_at, etc.
        """
        if not self.refresh_token:
            raise ValueError("No refresh token available")
        
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        try:
            response = requests.post(self.OAUTH_URL, data=payload, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            # Update stored tokens
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            
            logger.info("Successfully refreshed access token")
            return token_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error refreshing access token: {e}")
            raise
    
    def _make_api_request(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 3,
        **kwargs
    ) -> requests.Response:
        """
        Make an API request with retry logic and token refresh.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to BASE_URL)
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
        """
        if not self.access_token:
            raise ValueError("No access token available. Please authenticate first.")
        
        url = f"{self.BASE_URL}/{endpoint}"
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f"Bearer {self.access_token}"
        
        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=30,
                    **kwargs
                )
                
                # If unauthorized, try to refresh token
                if response.status_code == 401 and self.refresh_token and attempt < max_retries - 1:
                    logger.info("Access token expired, refreshing...")
                    self.refresh_access_token()
                    headers['Authorization'] = f"Bearer {self.access_token}"
                    continue
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 60)  # Exponential backoff, capped at 60s
                    logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    raise
        
        raise RuntimeError("Should not reach here")
    
    def get_activity(self, activity_id: int) -> Dict[str, Any]:
        """
        Get activity details from Strava API.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Dict containing activity details
        """
        response = self._make_api_request('GET', f"activities/{activity_id}")
        return response.json()
    
    def _download_with_selenium(self, activity_id: int, target_path: Path) -> bool:
        """
        Download FIT file using Selenium browser automation.
        
        Args:
            activity_id: Strava activity ID
            target_path: Where to save the downloaded file
            
        Returns:
            True if download successful, False otherwise
        """
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available. Install with: pip install selenium webdriver-manager")
            return False
        
        try:
            # Create temp download directory
            temp_dir = self.download_base_dir / 'temp_selenium'
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize Selenium downloader
            with StravaSeleniumDownloader(
                download_dir=temp_dir,
                headless=True,  # Run in headless mode by default
                oauth_access_token=self.access_token
            ) as downloader:
                # Login
                if not downloader.login(email=self.strava_email, password=self.strava_password):
                    logger.error("Failed to login to Strava via Selenium")
                    return False
                
                # Download file
                if downloader.download_fit_file(activity_id, target_path):
                    logger.info(f"Successfully downloaded via Selenium: {target_path}")
                    return True
                else:
                    logger.error(f"Selenium download failed for activity {activity_id}")
                    return False
        
        except Exception as e:
            logger.error(f"Error in Selenium download: {e}")
            return False
    
    def download_fit_file(self, activity_id: int) -> Optional[Path]:
        """
        Download FIT file for an activity.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Path to downloaded file, or None if download failed
        """
        try:
            # Check if already downloaded
            if self.is_already_downloaded(activity_id):
                logger.info(f"Activity {activity_id} already downloaded, skipping")
                return Path(self.downloaded_activities[activity_id].file_path)
            
            # Get activity details first
            activity = self.get_activity(activity_id)
            activity_type = activity.get('type', '')
            
            # Only download Run or VirtualRun activities
            if activity_type not in ['Run', 'VirtualRun']:
                logger.info(f"Activity {activity_id} is type '{activity_type}', not downloading (only Run/VirtualRun)")
                return None
            
            # Get activity start time for directory structure and filename
            start_date_str = activity.get('start_date', '')
            if start_date_str:
                try:
                    start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                except Exception:
                    start_date = datetime.now()
            else:
                start_date = datetime.now()
            
            # Get activity name and sanitize it for filename
            activity_name = activity.get('name', '')
            sanitized_name = sanitize_activity_name(activity_name)
            
            # Create directory structure: {base_dir}/{yyyy}/{mm}/
            year_month_dir = self.download_base_dir / str(start_date.year) / f"{start_date.month:02d}"
            year_month_dir.mkdir(parents=True, exist_ok=True)
            
            # Create filename: yyyymmdd_activity_name.fit
            date_str = start_date.strftime('%Y%m%d')
            filename = f"{date_str}_{sanitized_name}.fit"
            file_path = year_month_dir / filename
            
            logger.info(f"Downloading FIT file for activity {activity_id} ({activity_type})")
            
            # Use Selenium if enabled, otherwise fall back to requests
            if self.use_selenium:
                success = self._download_with_selenium(activity_id, file_path)
                if not success:
                    raise Exception(f"Selenium download failed for activity {activity_id}")
            else:
                # The export_original endpoint is a web-only feature
                # We'll use the access token as a query parameter with browser-like headers
                export_url = f"https://www.strava.com/activities/{activity_id}/export_original"
                
                # Make authenticated request with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Create a session with browser-like headers
                        session = requests.Session()
                        session.headers.update({
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'DNT': '1',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'none',
                            'Sec-Fetch-User': '?1',
                        })
                        
                        # Request the export with access token
                        params = {'access_token': self.access_token}
                        response = session.get(export_url, params=params, timeout=30, allow_redirects=True)
                        
                        # Check if we got redirected to login page or got HTML
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' in content_type:
                            # We got HTML, not a FIT file - check what kind of error
                            response_text = response.text.lower()
                            
                            # Try to distinguish between authentication failure and missing file
                            login_indicators = ('sign in', 'log in', 'login')
                            if any(indicator in response_text for indicator in login_indicators):
                                # Authentication issue - suggest Selenium
                                raise Exception(
                                    f"Authentication failed: Strava's export endpoint requires browser cookies. "
                                    f"Use Selenium mode: set USE_SELENIUM=true and optionally STRAVA_EMAIL/STRAVA_PASSWORD"
                                )
                            else:
                                # Likely missing file or other issue
                                raise Exception(f"FIT file not available: Activity {activity_id} may not have an original file, or it may not be exportable.")
                        
                        # If unauthorized, try to refresh token
                        if response.status_code == 401 and self.refresh_token and attempt < max_retries - 1:
                            logger.info("Access token expired, refreshing...")
                            self.refresh_access_token()
                            continue
                        
                        response.raise_for_status()
                        break  # Success, exit retry loop
                        
                    except requests.exceptions.RequestException as e:
                        if attempt < max_retries - 1:
                            wait_time = min(2 ** attempt, 60)
                            logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"Request failed after {max_retries} attempts: {e}")
                            raise
                
                # Save file
                with open(file_path, 'wb') as f:
                    f.write(response.content)
            
            # Update state
            downloaded_activity = DownloadedActivity(
                activity_id=activity_id,
                download_time=datetime.now().isoformat(),
                file_path=str(file_path)
            )
            self.downloaded_activities[activity_id] = downloaded_activity
            self._save_state()
            
            logger.info(f"Successfully downloaded FIT file to {file_path}")
            return file_path
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"FIT file not available for activity {activity_id} (404)")
            else:
                logger.error(f"HTTP error downloading activity {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error downloading activity {activity_id}: {e}")
            return None


def save_tokens_to_env(access_token: str, refresh_token: str, env_file: str = ".env") -> None:
    """
    Save tokens to .env file.
    
    Args:
        access_token: Strava access token
        refresh_token: Strava refresh token
        env_file: Path to .env file
    """
    env_path = Path(env_file)
    
    # Read existing .env if it exists
    lines = []
    if env_path.exists():
        with open(env_path, 'r') as f:
            lines = f.readlines()
    
    # Update or add token lines
    access_token_found = False
    refresh_token_found = False
    
    for i, line in enumerate(lines):
        if line.startswith('STRAVA_ACCESS_TOKEN='):
            lines[i] = f'STRAVA_ACCESS_TOKEN={access_token}\n'
            access_token_found = True
        elif line.startswith('STRAVA_REFRESH_TOKEN='):
            lines[i] = f'STRAVA_REFRESH_TOKEN={refresh_token}\n'
            refresh_token_found = True
    
    if not access_token_found:
        lines.append(f'STRAVA_ACCESS_TOKEN={access_token}\n')
    if not refresh_token_found:
        lines.append(f'STRAVA_REFRESH_TOKEN={refresh_token}\n')
    
    # Write back to file
    with open(env_path, 'w') as f:
        f.writelines(lines)
    
    logger.info(f"Tokens saved to {env_file}")


if __name__ == '__main__':
    """
    Simple test/demo of the Strava client.
    Run with: python strava_downloader.py <activity_id>
    
    Supports Selenium mode via environment variables:
    - USE_SELENIUM=true: Enable browser automation
    - STRAVA_EMAIL: Email for login (optional, uses OAuth if not provided)
    - STRAVA_PASSWORD: Password for login (optional)
    """
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    client_id = os.getenv('STRAVA_CLIENT_ID')
    client_secret = os.getenv('STRAVA_CLIENT_SECRET')
    access_token = os.getenv('STRAVA_ACCESS_TOKEN')
    refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')
    download_base_dir = os.getenv('DOWNLOAD_BASE_DIR', './downloads')
    state_file = os.getenv('STATE_FILE', './downloaded_activities.json')
    
    # Selenium options
    use_selenium = os.getenv('USE_SELENIUM', '').lower() == 'true'
    strava_email = os.getenv('STRAVA_EMAIL')
    strava_password = os.getenv('STRAVA_PASSWORD')
    
    if not client_id or not client_secret:
        print("Error: STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env file")
        sys.exit(1)
    
    client = StravaClient(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        download_base_dir=download_base_dir,
        state_file=state_file,
        use_selenium=use_selenium,
        strava_email=strava_email,
        strava_password=strava_password
    )
    
    if len(sys.argv) > 1:
        # Download specific activity
        activity_id = int(sys.argv[1])
        print(f"Downloading activity {activity_id}...")
        if use_selenium:
            print("Using Selenium browser automation...")
        result = client.download_fit_file(activity_id)
        if result:
            print(f"Success! Downloaded to: {result}")
        else:
            print("Download failed or activity not eligible")
    else:
        print("Usage: python strava_downloader.py <activity_id>")
        print("Or import and use StravaClient class in your code")
        print()
        print("For browser-based downloads, set in .env:")
        print("  USE_SELENIUM=true")
        print("  STRAVA_EMAIL=your@email.com  (optional)")
        print("  STRAVA_PASSWORD=yourpassword (optional)")
