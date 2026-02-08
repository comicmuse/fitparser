#!/usr/bin/env python3
"""
Selenium-based Strava FIT file downloader.

Uses browser automation to log into Strava and download original FIT files.
This is necessary because Strava's export_original endpoint requires browser
session cookies that cannot be obtained through OAuth tokens alone.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


class StravaSeleniumDownloader:
    """
    Download FIT files from Strava using browser automation.
    
    This class handles:
    - Browser initialization (headless or visible)
    - Strava login via OAuth or email/password
    - FIT file downloads
    - Download directory management
    """
    
    def __init__(
        self,
        download_dir: Path,
        headless: bool = True,
        oauth_access_token: Optional[str] = None
    ):
        """
        Initialize the Selenium downloader.
        
        Args:
            download_dir: Directory where files should be downloaded
            headless: Run browser in headless mode (no visible window)
            oauth_access_token: Optional OAuth access token for login
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.oauth_access_token = oauth_access_token
        self.driver: Optional[webdriver.Chrome] = None
        self._is_logged_in = False
    
    def _init_driver(self) -> webdriver.Chrome:
        """Initialize Chrome WebDriver with appropriate options."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless=new')
        
        # Essential options for stability
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Set download preferences
        prefs = {
            'download.default_directory': str(self.download_dir.absolute()),
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'safebrowsing.enabled': False
        }
        chrome_options.add_experimental_option('prefs', prefs)
        
        # Install and use ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        logger.info(f"Initialized Chrome WebDriver (headless={self.headless})")
        return driver
    
    def _login_with_oauth(self) -> bool:
        """
        Login to Strava using OAuth access token.
        
        Returns:
            True if login successful, False otherwise
        """
        if not self.oauth_access_token:
            return False
        
        try:
            # Navigate to a page with access token to establish session
            # Note: Token in URL is visible in browser logs, but this is a local headless browser
            # and the session is only used for immediate download, then discarded
            url = f"https://www.strava.com/dashboard?access_token={self.oauth_access_token}"
            self.driver.get(url)
            
            # Wait a moment for the page to load
            time.sleep(2)
            
            # Check if we're logged in by looking for dashboard elements
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "athlete-name"))
                )
                logger.info("Successfully logged in via OAuth token")
                return True
            except TimeoutException:
                logger.warning("OAuth login may have failed - dashboard not loaded")
                return False
        
        except Exception as e:
            logger.error(f"Error during OAuth login: {e}")
            return False
    
    def _login_with_email(self, email: str, password: str) -> bool:
        """
        Login to Strava using email and password.
        
        Args:
            email: Strava account email
            password: Strava account password
            
        Returns:
            True if login successful, False otherwise
        """
        try:
            # Navigate to login page
            self.driver.get("https://www.strava.com/login")
            
            # Wait for login form to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            
            # Fill in login form
            email_input = self.driver.find_element(By.ID, "email")
            password_input = self.driver.find_element(By.ID, "password")
            
            email_input.send_keys(email)
            password_input.send_keys(password)
            
            # Submit form
            login_button = self.driver.find_element(By.ID, "login-button")
            login_button.click()
            
            # Wait for login to complete (dashboard should load)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "athlete-name"))
            )
            
            logger.info("Successfully logged in via email/password")
            return True
        
        except (TimeoutException, NoSuchElementException) as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def login(self, email: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Login to Strava.
        
        Tries OAuth token first if available, falls back to email/password.
        
        Args:
            email: Optional email for login
            password: Optional password for login
            
        Returns:
            True if login successful, False otherwise
        """
        if not self.driver:
            self.driver = self._init_driver()
        
        # Try OAuth first
        if self.oauth_access_token:
            if self._login_with_oauth():
                self._is_logged_in = True
                return True
            logger.warning("OAuth login failed, trying email/password if provided")
        
        # Fall back to email/password
        if email and password:
            if self._login_with_email(email, password):
                self._is_logged_in = True
                return True
        
        logger.error("All login methods failed")
        return False
    
    def download_fit_file(self, activity_id: int, target_path: Path) -> bool:
        """
        Download FIT file for a specific activity.
        
        Args:
            activity_id: Strava activity ID
            target_path: Where to save the downloaded file
            
        Returns:
            True if download successful, False otherwise
        """
        if not self._is_logged_in:
            logger.error("Not logged in - call login() first")
            return False
        
        try:
            # Navigate to export URL
            export_url = f"https://www.strava.com/activities/{activity_id}/export_original"
            logger.info(f"Downloading activity {activity_id} from {export_url}")
            
            self.driver.get(export_url)
            
            # Wait for download to start (file should appear in download directory)
            # The download happens automatically when visiting the export_original URL
            # Check immediately, then wait if needed
            time.sleep(1)  # Brief initial wait for download to initiate
            
            # Check if file was downloaded
            # Strava names the file as: {activity_id}.fit.gz or similar
            # We need to find the downloaded file and move it to target location
            
            # Wait up to 30 seconds for download to complete
            max_wait = 30
            start_time = time.time()
            downloaded_file = None
            
            while time.time() - start_time < max_wait:
                # Look for .fit files in download directory
                for file_path in self.download_dir.glob('*.fit*'):
                    # Skip if it's a partial download (.crdownload, .tmp, etc.)
                    if file_path.suffix in ['.crdownload', '.tmp', '.part']:
                        continue
                    
                    # Check if file is recent (within last 60 seconds)
                    if time.time() - file_path.stat().st_mtime < 60:
                        downloaded_file = file_path
                        break
                
                if downloaded_file:
                    break
                
                time.sleep(1)
            
            if not downloaded_file:
                logger.error(f"Download timed out for activity {activity_id}")
                return False
            
            # Move/rename file to target location
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Handle .gz files - extract if needed
            if downloaded_file.suffix == '.gz':
                import gzip
                import shutil
                with gzip.open(downloaded_file, 'rb') as f_in:
                    with open(target_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                downloaded_file.unlink()  # Remove .gz file
            else:
                downloaded_file.rename(target_path)
            
            logger.info(f"Successfully downloaded activity {activity_id} to {target_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error downloading activity {activity_id}: {e}")
            return False
    
    def close(self):
        """Close the browser and clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed")
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self.driver = None
                self._is_logged_in = False
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


if __name__ == "__main__":
    # Example usage
    import sys
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    
    if len(sys.argv) < 2:
        print("Usage: python strava_selenium_downloader.py ACTIVITY_ID")
        sys.exit(1)
    
    activity_id = int(sys.argv[1])
    
    # Configuration from environment
    download_dir = Path(os.getenv('DOWNLOAD_BASE_DIR', './downloads'))
    access_token = os.getenv('STRAVA_ACCESS_TOKEN')
    email = os.getenv('STRAVA_EMAIL')
    password = os.getenv('STRAVA_PASSWORD')
    
    # Use headless mode unless STRAVA_BROWSER_VISIBLE is set
    headless = os.getenv('STRAVA_BROWSER_VISIBLE', '').lower() != 'true'
    
    # Create downloader
    with StravaSeleniumDownloader(
        download_dir=download_dir / 'temp',  # Temp dir for initial download
        headless=headless,
        oauth_access_token=access_token
    ) as downloader:
        # Login
        if not downloader.login(email=email, password=password):
            print("Failed to login to Strava")
            sys.exit(1)
        
        # Download file
        target_path = download_dir / f"{activity_id}.fit"
        if downloader.download_fit_file(activity_id, target_path):
            print(f"Downloaded to: {target_path}")
        else:
            print("Download failed")
            sys.exit(1)
