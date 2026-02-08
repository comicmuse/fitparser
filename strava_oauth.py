#!/usr/bin/env python3
"""
Interactive OAuth2 authorization flow for Strava.

This script handles the complete OAuth2 flow:
1. Opens browser to Strava authorization page
2. Runs local HTTP server to receive the callback
3. Exchanges authorization code for tokens
4. Saves tokens to .env file

Usage:
    python strava_oauth.py
"""

from __future__ import annotations

import os
import sys
import webbrowser
import html
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from typing import Optional
import logging

from dotenv import load_dotenv

from strava_downloader import StravaClient, save_tokens_to_env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variable to store the authorization code
authorization_code: Optional[str] = None
auth_error: Optional[str] = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""
    
    def log_message(self, format, *args):
        """Override to use logger instead of stderr."""
        logger.info(f"HTTP: {format % args}")
    
    def do_GET(self):
        """Handle GET request from OAuth callback."""
        global authorization_code, auth_error
        
        # Parse the URL
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        
        # Check for authorization code
        if 'code' in query_params:
            authorization_code = query_params['code'][0]
            logger.info(f"Received authorization code: {authorization_code[:10]}...")
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            success_html = """
            <html>
            <head><title>Authorization Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: green;">✓ Authorization Successful!</h1>
                <p>You have successfully authorized the application.</p>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())
            
        elif 'error' in query_params:
            auth_error = query_params['error'][0]
            error_description = query_params.get('error_description', ['Unknown error'])[0]
            logger.error(f"Authorization error: {auth_error} - {error_description}")
            
            # Send error response
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Escape error values to prevent XSS
            safe_error = html.escape(auth_error)
            safe_description = html.escape(error_description)
            
            error_html = f"""
            <html>
            <head><title>Authorization Failed</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">✗ Authorization Failed</h1>
                <p><strong>Error:</strong> {safe_error}</p>
                <p><strong>Description:</strong> {safe_description}</p>
                <p>Please close this window and try again.</p>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
            
        else:
            # Unknown callback
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Invalid callback</h1></body></html>")


def run_oauth_flow(
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://localhost:8000",
    port: int = 8000
) -> tuple[Optional[str], Optional[str]]:
    """
    Run the complete OAuth2 flow.
    
    Args:
        client_id: Strava application client ID
        client_secret: Strava application client secret
        redirect_uri: Redirect URI for OAuth callback (must match Strava app settings)
        port: Local port to listen on for callback
        
    Returns:
        Tuple of (access_token, refresh_token) or (None, None) on failure
    """
    global authorization_code, auth_error
    
    # Reset global variables
    authorization_code = None
    auth_error = None
    
    # Build authorization URL with proper URL encoding
    scope = "activity:read"
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={quote(str(client_id))}"
        f"&redirect_uri={quote(redirect_uri)}"
        f"&response_type=code"
        f"&approval_prompt=force"
        f"&scope={quote(scope)}"
    )
    
    logger.info("=" * 60)
    logger.info("Starting OAuth2 Authorization Flow")
    logger.info("=" * 60)
    logger.info(f"Redirect URI: {redirect_uri}")
    logger.info(f"Scope: {scope}")
    logger.info("")
    logger.info("Opening browser for authorization...")
    logger.info("If the browser doesn't open automatically, visit this URL:")
    logger.info(f"  {auth_url}")
    logger.info("")
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Start local HTTP server to receive callback
    logger.info(f"Starting local server on port {port}...")
    logger.info("Waiting for authorization callback...")
    logger.info("(Press Ctrl+C to cancel)")
    logger.info("")
    
    server = HTTPServer(('localhost', port), OAuthCallbackHandler)
    
    # Handle one request (the OAuth callback)
    try:
        while authorization_code is None and auth_error is None:
            server.handle_request()
        
        server.server_close()
        
    except KeyboardInterrupt:
        logger.info("\nAuthorization cancelled by user")
        server.server_close()
        return None, None
    
    # Check if we got an error
    if auth_error:
        logger.error(f"Authorization failed: {auth_error}")
        return None, None
    
    # Check if we got the authorization code
    if not authorization_code:
        logger.error("No authorization code received")
        return None, None
    
    # Exchange authorization code for tokens
    logger.info("")
    logger.info("Exchanging authorization code for access token...")
    
    try:
        client = StravaClient(
            client_id=client_id,
            client_secret=client_secret
        )
        
        token_data = client.get_access_token_from_code(authorization_code)
        
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_at = token_data.get('expires_at')
        
        if not access_token or not refresh_token:
            logger.error("Failed to get tokens from response")
            return None, None
        
        logger.info("✓ Successfully obtained tokens!")
        logger.info(f"  Access token: {access_token[:20]}...")
        logger.info(f"  Refresh token: {refresh_token[:20]}...")
        logger.info(f"  Expires at: {expires_at}")
        
        return access_token, refresh_token
        
    except Exception as e:
        logger.error(f"Error exchanging authorization code: {e}")
        return None, None


def main():
    """Main entry point for OAuth flow."""
    load_dotenv()
    
    # Get configuration from environment
    client_id = os.getenv('STRAVA_CLIENT_ID')
    client_secret = os.getenv('STRAVA_CLIENT_SECRET')
    redirect_uri = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:8000')
    port = int(os.getenv('OAUTH_PORT', '8000'))
    
    # Validate configuration
    if not client_id or not client_secret:
        logger.error("=" * 60)
        logger.error("ERROR: Missing Strava credentials")
        logger.error("=" * 60)
        logger.error("Please set the following in your .env file:")
        logger.error("  STRAVA_CLIENT_ID=your_client_id")
        logger.error("  STRAVA_CLIENT_SECRET=your_client_secret")
        logger.error("")
        logger.error("Optional:")
        logger.error("  OAUTH_REDIRECT_URI=http://localhost:8000")
        logger.error("  OAUTH_PORT=8000")
        logger.error("")
        logger.error("See README_STRAVA.md for setup instructions.")
        sys.exit(1)
    
    # Validate redirect URI matches port
    if 'localhost' in redirect_uri:
        try:
            parsed = urlparse(redirect_uri)
            uri_port = parsed.port
            if uri_port is None:
                # Default ports: 80 for http, 443 for https
                uri_port = 80 if parsed.scheme == 'http' else 443
            if uri_port != port:
                logger.warning(f"Port mismatch: OAUTH_REDIRECT_URI uses port {uri_port} but OAUTH_PORT is {port}")
                logger.warning(f"Using port {port} from OAUTH_PORT")
        except (ValueError, AttributeError):
            pass
    
    # Run OAuth flow
    access_token, refresh_token = run_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        port=port
    )
    
    if not access_token or not refresh_token:
        logger.error("")
        logger.error("=" * 60)
        logger.error("Authorization failed")
        logger.error("=" * 60)
        sys.exit(1)
    
    # Save tokens to .env file
    logger.info("")
    logger.info("Saving tokens to .env file...")
    
    try:
        save_tokens_to_env(access_token, refresh_token)
        logger.info("✓ Tokens saved successfully!")
        logger.info("")
        logger.info("=" * 60)
        logger.info("Authorization Complete!")
        logger.info("=" * 60)
        logger.info("Your tokens have been saved to .env file.")
        logger.info("You can now run:")
        logger.info("  python strava_webhook.py")
        logger.info("to start the webhook server.")
        logger.info("")
        
    except Exception as e:
        logger.error(f"Error saving tokens: {e}")
        logger.error("")
        logger.error("Please manually add these to your .env file:")
        logger.error(f"STRAVA_ACCESS_TOKEN={access_token}")
        logger.error(f"STRAVA_REFRESH_TOKEN={refresh_token}")
        sys.exit(1)


if __name__ == '__main__':
    main()
