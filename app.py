#!/usr/bin/env python3
"""
Flask web application for YouTube video upload management.

Provides a web interface for uploading videos to multiple YouTube accounts.
"""

import os
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from youtube_uploader import YouTubeUploader, get_available_accounts, add_account, CREDENTIALS_DIR
import secrets
from logger_config import logger

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Generate a secret key for sessions
CORS(app)

# Log application startup
logger.info("=" * 60)
logger.info("Video Editor Application Starting")
logger.info(f"Upload folder: {UPLOAD_FOLDER}")
logger.info(f"Thumbnails folder: {THUMBNAILS_FOLDER}")
logger.info("=" * 60)

# Configuration
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)
THUMBNAILS_FOLDER = UPLOAD_FOLDER / 'thumbnails'
THUMBNAILS_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv', 'webm'}


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    """Serve thumbnail images."""
    try:
        logger.debug(f"Serving thumbnail: {filename}")
        return send_from_directory(str(THUMBNAILS_FOLDER), filename)
    except Exception as e:
        logger.error(f"Error serving thumbnail {filename}: {e}", exc_info=True)
        return '', 404


@app.route('/')
def index():
    """Render main page."""
    accounts = get_available_accounts()
    return render_template('index.html', accounts=accounts)


@app.route('/api/accounts', methods=['GET'])
def list_accounts():
    """Get list of available YouTube accounts."""
    accounts = get_available_accounts()
    return jsonify({'accounts': accounts})


@app.route('/api/upload', methods=['POST'])
def upload_video():
    """Handle video upload request."""
    try:
        # Check if file is present
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Get form data
        account_email = request.form.get('account')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        privacy = request.form.get('privacy', 'public')
        tags_str = request.form.get('tags', '')
        
        if not account_email:
            return jsonify({'error': 'No account specified'}), 400
        
        if not title:
            return jsonify({'error': 'Title is required'}), 400
        
        # Parse tags
        tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()] if tags_str else []
        
        # Save uploaded file
        filename = file.filename
        filepath = UPLOAD_FOLDER / filename
        file.save(str(filepath))
        
        # Upload to YouTube
        uploader = YouTubeUploader(account_email)
        
        # Collect upload progress
        results = []
        for result in uploader.upload_video(str(filepath), title, description, privacy, tags):
            results.append(result)
        
        # Get final result
        final_result = results[-1] if results else {'status': 'error', 'error': 'No response from upload'}
        
        # Clean up uploaded file
        if filepath.exists():
            filepath.unlink()
        
        if final_result.get('status') == 'complete':
            return jsonify({
                'success': True,
                'video_id': final_result.get('video_id'),
                'video_url': final_result.get('video_url'),
                'progress': 100
            })
        else:
            return jsonify({
                'success': False,
                'error': final_result.get('error', 'Upload failed'),
                'error_details': final_result.get('error_details')
            }), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/accounts')
def accounts_page():
    """Render account management page."""
    accounts = get_available_accounts()
    from oauth_flow import get_oauth_client_path
    has_oauth_client = get_oauth_client_path() is not None
    return render_template('accounts.html', accounts=accounts, has_oauth_client=has_oauth_client)


@app.route('/api/accounts/add', methods=['POST'])
def add_youtube_account():
    """Add a new YouTube account via file upload."""
    try:
        # Check if file is present
        if 'credentials_file' not in request.files:
            return jsonify({'error': 'No credentials file provided'}), 400
        
        file = request.files['credentials_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({'error': 'File must be a JSON file'}), 400
        
        # Get account email from form
        account_email = request.form.get('account_email', '').strip()
        if not account_email:
            return jsonify({'error': 'Account email is required'}), 400
        
        # Validate email format (basic check)
        if '@' not in account_email or '.' not in account_email.split('@')[1]:
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Save uploaded file temporarily
        import tempfile
        import shutil
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.json', delete=False) as tmp_file:
            file.save(tmp_file.name)
            tmp_path = tmp_file.name
        
        try:
            # Validate JSON format
            import json as json_module
            with open(tmp_path, 'r') as f:
                json_module.load(f)  # Validate it's valid JSON
            
            # Add account using the uploader module
            logger.info(f"Adding YouTube account: {account_email}")
            add_account(account_email, tmp_path)
            logger.info(f"Successfully added account: {account_email}")
            return jsonify({
                'success': True, 
                'message': f'Account {account_email} added successfully',
                'account': account_email
            })
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON file format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/delete', methods=['POST'])
def delete_youtube_account():
    """Delete a YouTube account (remove credentials and tokens)."""
    try:
        data = request.json
        account_email = data.get('account_email')
        
        if not account_email:
            return jsonify({'error': 'account_email is required'}), 400
        
        credentials_file = CREDENTIALS_DIR / f'{account_email}_credentials.json'
        token_file = CREDENTIALS_DIR / f'{account_email}_token.json'
        
        deleted = []
        if credentials_file.exists():
            credentials_file.unlink()
            deleted.append('credentials')
        
        if token_file.exists():
            token_file.unlink()
            deleted.append('token')
        
        if not deleted:
            return jsonify({'error': f'Account {account_email} not found'}), 404
        
        return jsonify({
            'success': True,
            'message': f'Account {account_email} deleted successfully',
            'deleted': deleted
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/authenticate', methods=['POST'])
def authenticate_account_endpoint():
    """Start OAuth flow - generate authorization URL for web-based authentication."""
    try:
        from oauth_flow import start_oauth_flow, get_oauth_client_path
        
        data = request.json
        account_email = data.get('account_email', '').strip()
        
        # Email is optional - we'll extract it from OAuth response
        # But if provided, validate format
        if account_email:
            if '@' not in account_email or '.' not in account_email.split('@')[1]:
                return jsonify({'error': 'Invalid email format'}), 400
        
        # Check if OAuth client exists
        oauth_client_path = get_oauth_client_path()
        if oauth_client_path is None:
            return jsonify({
                'error': 'No OAuth client credentials found. Please add at least one credentials file first.'
            }), 400
        
        # Get base URL for redirect
        port = int(os.environ.get('PORT', 8080))
        redirect_uri = f"http://localhost:{port}/oauth/callback"
        
        # Start OAuth flow
        oauth_data = start_oauth_flow(account_email, oauth_client_path, redirect_uri)
        
        # Store state and account email (if provided) in session for verification
        session['oauth_state'] = oauth_data['state']
        session['oauth_account'] = account_email  # May be empty, will be extracted from OAuth
        
        return jsonify({
            'success': True,
            'authorization_url': oauth_data['authorization_url'],
            'account': account_email
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/oauth/callback')
def oauth_callback():
    """Handle OAuth callback and complete authentication."""
    try:
        from oauth_flow import complete_oauth_flow, get_oauth_client_path
        
        # Get authorization code and state from query parameters
        authorization_code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        # Check for errors
        if error:
            error_description = request.args.get('error_description', error)
            return render_template('oauth_error.html', 
                                 error=error, 
                                 error_description=error_description)
        
        if not authorization_code:
            return render_template('oauth_error.html', 
                                 error='missing_code',
                                 error_description='No authorization code received')
        
        # Verify state matches session
        session_state = session.get('oauth_state')
        account_email = session.get('oauth_account')
        
        if not session_state or state != session_state:
            return render_template('oauth_error.html',
                                   error='invalid_state',
                                   error_description='Invalid or missing state parameter')
        
        if not account_email:
            return render_template('oauth_error.html',
                                 error='missing_account',
                                 error_description='Account email not found in session')
        
        # Get OAuth client
        oauth_client_path = get_oauth_client_path()
        if oauth_client_path is None:
            return render_template('oauth_error.html',
                                 error='no_oauth_client',
                                 error_description='OAuth client credentials not found')
        
        # Get redirect URI
        port = int(os.environ.get('PORT', 8080))
        redirect_uri = f"http://localhost:{port}/oauth/callback"
        
        # Complete OAuth flow (account_email may be empty, will be extracted)
        result = complete_oauth_flow(
            account_email or '',  # Pass empty string if not provided
            authorization_code,
            oauth_client_path,
            redirect_uri,
            state
        )
        
        # Clear session
        session.pop('oauth_state', None)
        session.pop('oauth_account', None)
        
        if result.get('status') == 'success':
            # Use extracted email from OAuth response
            final_email = result.get('authenticated_email') or account_email
            return render_template('oauth_success.html', 
                                 account_email=final_email,
                                 channel_info=result.get('channel_info', {}))
        else:
            return render_template('oauth_error.html',
                                error='authentication_failed',
                                error_description=result.get('error', 'Unknown error'))
        
    except Exception as e:
        return render_template('oauth_error.html',
                             error='exception',
                             error_description=str(e))


@app.route('/api/accounts/check', methods=['POST'])
def check_account_status():
    """Check authentication status of an account."""
    try:
        from oauth_flow import check_authentication_status
        
        data = request.json
        account_email = data.get('account_email', '').strip()
        
        if not account_email:
            return jsonify({'error': 'Account email is required'}), 400
        
        status = check_authentication_status(account_email)
        return jsonify(status)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Video Processing Queue Routes
@app.route('/process')
def process_page():
    """Render video processing page."""
    return render_template('process.html')


@app.route('/api/queue/upload', methods=['POST'])
def upload_to_queue():
    """Upload videos and add to processing queue."""
    logger.info("Received request to upload videos to queue")
    try:
        if 'videos' not in request.files:
            logger.warning("Upload request missing 'videos' field")
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('videos')
        logger.info(f"Received {len(files)} file(s) for upload")
        
        if not files or files[0].filename == '':
            logger.warning("No files selected in upload request")
            return jsonify({'error': 'No files selected'}), 400
        
        # Save uploaded files to uploads directory
        uploaded_paths = []
        UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
        UPLOAD_FOLDER.mkdir(exist_ok=True)
        
        for file in files:
            if file and allowed_file(file.filename):
                # Save file
                filename = file.filename
                filepath = UPLOAD_FOLDER / filename
                
                # Handle duplicate filenames
                counter = 1
                while filepath.exists():
                    name_parts = filename.rsplit('.', 1)
                    new_filename = f"{name_parts[0]}_{counter}.{name_parts[1]}" if len(name_parts) > 1 else f"{filename}_{counter}"
                    filepath = UPLOAD_FOLDER / new_filename
                    counter += 1
                
                file.save(str(filepath))
                uploaded_paths.append(str(filepath.absolute()))
                logger.info(f"Saved uploaded file: {filepath.name}")
        
        if not uploaded_paths:
            logger.warning("No valid video files were uploaded")
            return jsonify({'error': 'No valid video files uploaded'}), 400
        
        logger.info(f"Adding {len(uploaded_paths)} video(s) to processing queue")
        # Add to queue
        from video_queue import get_queue
        queue = get_queue()
        
        added_ids = queue.add(uploaded_paths)
        logger.info(f"Successfully added {len(added_ids)} video(s) to queue: {added_ids}")
        
        if not added_ids:
            return jsonify({'error': 'Failed to add videos to queue'}), 500
        
        return jsonify({
            'success': True,
            'added_count': len(added_ids),
            'item_ids': added_ids
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/queue/add', methods=['POST'])
def add_to_queue():
    """Add videos to processing queue by path (legacy/alternative method)."""
    try:
        data = request.json
        paths = data.get('paths', [])
        
        if not paths:
            return jsonify({'error': 'No paths provided'}), 400
        
        from video_queue import get_queue
        queue = get_queue()
        
        added_ids = queue.add(paths)
        
        if not added_ids:
            return jsonify({'error': 'No valid videos added. Check file paths.'}), 400
        
        return jsonify({
            'success': True,
            'added_count': len(added_ids),
            'item_ids': added_ids
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/queue/status', methods=['GET'])
def queue_status():
    """Get queue status."""
    try:
        from video_queue import get_queue
        queue = get_queue()
        
        status = queue.get_status()
        return jsonify(status)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/queue/remove/<item_id>', methods=['DELETE'])
def remove_from_queue(item_id):
    """Remove item from queue."""
    try:
        from video_queue import get_queue
        queue = get_queue()
        
        success = queue.remove(item_id)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Item not found or cannot be removed'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/queue/result/<item_id>', methods=['GET'])
def get_queue_result(item_id):
    """Get analysis result for a queue item."""
    try:
        from video_queue import get_queue
        queue = get_queue()
        
        result = queue.get_result(item_id)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Result not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/grok/process', methods=['POST'])
def process_with_grok():
    """Process analyzed videos with Grok to generate editing plan."""
    try:
        from video_queue import get_queue
        from grok_client import analyze_video_segments
        
        queue = get_queue()
        status = queue.get_status()
        
        # Collect all completed analyses
        completed_items = [item for item in status['queue'] if item['status'] == 'complete']
        
        if not completed_items:
            return jsonify({'error': 'No completed analyses found'}), 400
        
        # Build analysis data structure
        analysis_data = {
            "videos": []
        }
        
        for item in completed_items:
            result = queue.get_result(item['id'])
            if result:
                analysis_data["videos"].append(result)
        
        if not analysis_data["videos"]:
            return jsonify({'error': 'No analysis results found'}), 400
        
        # Get target duration from request
        data = request.json or {}
        target_min = data.get('target_duration_min', 15)
        target_max = data.get('target_duration_max', 60)
        
        # Call Grok
        editing_plan = analyze_video_segments(analysis_data, target_min, target_max)
        
        return jsonify({
            'success': True,
            'editing_plan': editing_plan
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)

