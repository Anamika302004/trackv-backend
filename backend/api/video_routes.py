from flask import Blueprint, request, jsonify, send_file
from backend.video_processor.video_handler import VideoAnalysisService
from backend.notifications.alert_service import AlertService
from functools import wraps
import os
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)

video_bp = Blueprint('video', __name__, url_prefix='/api/video')

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        # Validate token...
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@video_bp.route('/upload', methods=['POST'])
@token_required
def upload_video(db_connection):
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video provided'}), 400
        
        video_file = request.files['video']
        junction_id = request.form.get('junction_id')
        feed_name = request.form.get('feed_name', 'Uploaded Video')
        
        if not junction_id:
            return jsonify({'error': 'Junction ID required'}), 400
        
        if not allowed_file(video_file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Save file
        filename = secure_filename(f"{junction_id}_{feed_name}_{video_file.filename}")
        save_path = f"/videos/{junction_id}/{filename}"
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        video_file.save(save_path)
        
        # Start processing
        video_service = VideoAnalysisService(db_connection)
        feed_id = video_service.upload_and_process_video(junction_id, save_path, feed_name)
        
        return jsonify({
            'feed_id': feed_id,
            'message': 'Video uploaded and processing started',
            'status': 'processing'
        }), 201
        
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        return jsonify({'error': str(e)}), 500

@video_bp.route('/youtube', methods=['POST'])
@token_required
def add_youtube_feed(db_connection):
    try:
        data = request.get_json()
        youtube_url = data.get('youtube_url')
        junction_id = data.get('junction_id')
        feed_name = data.get('feed_name', 'YouTube Feed')
        
        if not youtube_url or not junction_id:
            return jsonify({'error': 'YouTube URL and Junction ID required'}), 400
        
        video_service = VideoAnalysisService(db_connection)
        feed_id = video_service.add_youtube_feed(junction_id, youtube_url, feed_name)
        
        return jsonify({
            'feed_id': feed_id,
            'message': 'YouTube feed added and processing started',
            'status': 'processing'
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding YouTube feed: {e}")
        return jsonify({'error': str(e)}), 500

@video_bp.route('/cctv', methods=['POST'])
@token_required
def add_cctv_feed(db_connection):
    try:
        data = request.get_json()
        camera_ip = data.get('camera_ip')
        junction_id = data.get('junction_id')
        feed_name = data.get('feed_name', 'CCTV Feed')
        username = data.get('username')
        password = data.get('password')
        
        if not camera_ip or not junction_id:
            return jsonify({'error': 'Camera IP and Junction ID required'}), 400
        
        video_service = VideoAnalysisService(db_connection)
        feed_id = video_service.add_cctv_feed(
            junction_id, camera_ip, feed_name, username, password
        )
        
        return jsonify({
            'feed_id': feed_id,
            'message': 'CCTV feed connected and processing started',
            'status': 'processing'
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding CCTV feed: {e}")
        return jsonify({'error': str(e)}), 500

@video_bp.route('/feed/<feed_id>/results', methods=['GET'])
@token_required
def get_feed_results(feed_id, db_connection):
    try:
        video_service = VideoAnalysisService(db_connection)
        results = video_service.get_feed_results(feed_id)
        
        return jsonify(results), 200
        
    except Exception as e:
        logger.error(f"Error fetching feed results: {e}")
        return jsonify({'error': str(e)}), 500

@video_bp.route('/feed/<feed_id>/stop', methods=['POST'])
@token_required
def stop_feed(feed_id, db_connection):
    try:
        video_service = VideoAnalysisService(db_connection)
        video_service.stop_feed(feed_id)
        
        return jsonify({'message': 'Feed stopped'}), 200
        
    except Exception as e:
        logger.error(f"Error stopping feed: {e}")
        return jsonify({'error': str(e)}), 500
