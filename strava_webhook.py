#!/usr/bin/env python3
"""
Strava webhook receiver for automatic FIT file downloads.

Flask application that:
- Receives webhook events from Strava
- Validates webhook subscriptions
- Processes new activity events
- Downloads FIT files asynchronously
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Dict, Any

from flask import Flask, request, jsonify
from dotenv import load_dotenv

from strava_downloader import StravaClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration from environment variables
VERIFY_TOKEN = os.getenv('STRAVA_VERIFY_TOKEN', '')
CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '')
ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN', '')
REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN', '')
DOWNLOAD_BASE_DIR = os.getenv('DOWNLOAD_BASE_DIR', './downloads')
STATE_FILE = os.getenv('STATE_FILE', './downloaded_activities.json')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '5000'))

# Initialize Strava client (will be used by download threads)
strava_client = None
if CLIENT_ID and CLIENT_SECRET:
    strava_client = StravaClient(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        access_token=ACCESS_TOKEN,
        refresh_token=REFRESH_TOKEN,
        download_base_dir=DOWNLOAD_BASE_DIR,
        state_file=STATE_FILE
    )
    logger.info("Strava client initialized")
else:
    logger.warning("Strava client not initialized - missing CLIENT_ID or CLIENT_SECRET")


def download_activity_async(activity_id: int) -> None:
    """
    Download activity in a separate thread to avoid blocking webhook response.
    
    Args:
        activity_id: Strava activity ID to download
    """
    try:
        logger.info(f"Starting async download for activity {activity_id}")
        if strava_client:
            result = strava_client.download_fit_file(activity_id)
            if result:
                logger.info(f"Successfully downloaded activity {activity_id} to {result}")
            else:
                logger.info(f"Activity {activity_id} not downloaded (not eligible or already exists)")
        else:
            logger.error("Cannot download - Strava client not initialized")
    except Exception as e:
        logger.error(f"Error in async download for activity {activity_id}: {e}")


@app.route('/webhook', methods=['GET'])
def webhook_verification():
    """
    Handle webhook verification from Strava.
    
    Strava sends a GET request with hub.mode, hub.challenge, and hub.verify_token.
    We must validate the verify_token and echo back the challenge.
    """
    try:
        mode = request.args.get('hub.mode')
        challenge = request.args.get('hub.challenge')
        verify_token = request.args.get('hub.verify_token')
        
        logger.info(f"Webhook verification request: mode={mode}, verify_token={verify_token}")
        
        if mode == 'subscribe' and verify_token == VERIFY_TOKEN:
            logger.info("Webhook verification successful")
            return jsonify({'hub.challenge': challenge})
        else:
            logger.warning(f"Webhook verification failed: invalid token or mode")
            return jsonify({'error': 'Verification failed'}), 403
            
    except Exception as e:
        logger.error(f"Error in webhook verification: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/webhook', methods=['POST'])
def webhook_event():
    """
    Handle webhook events from Strava.
    
    Strava sends POST requests when activities are created, updated, or deleted.
    We process 'create' events for activities asynchronously.
    """
    try:
        event_data = request.json
        
        # Log all events for debugging
        logger.info(f"Received webhook event: {event_data}")
        
        # Extract event details
        object_type = event_data.get('object_type')
        aspect_type = event_data.get('aspect_type')
        object_id = event_data.get('object_id')
        owner_id = event_data.get('owner_id')
        event_time = event_data.get('event_time')
        
        # Log event details
        logger.info(
            f"Event: {aspect_type} {object_type} "
            f"(ID: {object_id}, Owner: {owner_id}, Time: {event_time})"
        )
        
        # Only process 'create' events for activities
        if object_type == 'activity' and aspect_type == 'create':
            logger.info(f"Processing new activity creation: {object_id}")
            
            # Start download in background thread to respond quickly
            download_thread = threading.Thread(
                target=download_activity_async,
                args=(object_id,),
                daemon=True
            )
            download_thread.start()
            logger.info(f"Async download thread started for activity {object_id}")
        else:
            logger.info(f"Ignoring event: {aspect_type} {object_type}")
        
        # Always respond with 200 OK quickly to avoid Strava timeout
        return jsonify({'status': 'received'}), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")
        # Still return 200 to avoid Strava retrying
        return jsonify({'status': 'error', 'message': str(e)}), 200


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'client_initialized': strava_client is not None
    })


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with basic info."""
    return jsonify({
        'service': 'Strava Webhook Receiver',
        'version': '1.0',
        'endpoints': {
            '/webhook': 'Webhook endpoint (GET for verification, POST for events)',
            '/health': 'Health check',
            '/': 'This info page'
        }
    })


def validate_config() -> bool:
    """
    Validate that required configuration is present.
    
    Returns:
        True if configuration is valid, False otherwise
    """
    required_vars = {
        'STRAVA_CLIENT_ID': CLIENT_ID,
        'STRAVA_CLIENT_SECRET': CLIENT_SECRET,
        'STRAVA_VERIFY_TOKEN': VERIFY_TOKEN
    }
    
    missing = [name for name, value in required_vars.items() if not value]
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Please set these in your .env file")
        return False
    
    if not ACCESS_TOKEN and not REFRESH_TOKEN:
        logger.warning(
            "No ACCESS_TOKEN or REFRESH_TOKEN set. "
            "You'll need to authorize the app before it can download files."
        )
    
    return True


def main():
    """
    Run the webhook server.
    
    Usage:
        python strava_webhook.py
    
    The server will listen on the port specified by WEBHOOK_PORT (default 5000).
    """
    logger.info("=" * 60)
    logger.info("Strava Webhook Receiver")
    logger.info("=" * 60)
    
    if not validate_config():
        logger.error("Configuration validation failed. Exiting.")
        exit(1)
    
    logger.info(f"Download directory: {DOWNLOAD_BASE_DIR}")
    logger.info(f"State file: {STATE_FILE}")
    logger.info(f"Starting webhook server on port {WEBHOOK_PORT}")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=WEBHOOK_PORT,
        debug=False  # Set to True for development
    )


if __name__ == '__main__':
    main()
