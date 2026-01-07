"""
Track-V Backend Server
Handles video processing, vehicle detection, and API endpoints
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import json
from datetime import datetime
from supabase import create_client, Client
from werkzeug.utils import secure_filename
import base64
import time

load_dotenv()

app = Flask(__name__)
CORS(app)

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# File upload configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {'mp4', 'webm', 'avi', 'mov', 'mkv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/api/junctions', methods=['GET'])
def get_junctions():
    """Get all junctions"""
    try:
        response = supabase.table('junctions').select('*').eq('is_active', True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/junctions', methods=['POST'])
def create_junction():
    """Create a new junction"""
    try:
        data = request.get_json()
        response = supabase.table('junctions').insert({
            'name': data.get('name'),
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'description': data.get('description', '')
        }).execute()
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vehicle-detections', methods=['GET'])
def get_detections():
    """Get vehicle detection records"""
    try:
        limit = request.args.get('limit', 100, type=int)
        response = supabase.table('vehicle_detections').select('*').order('detection_timestamp', desc=True).limit(limit).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vehicle-detections', methods=['POST'])
def create_detection():
    """Record a vehicle detection"""
    try:
        data = request.get_json()
        response = supabase.table('vehicle_detections').insert({
            'junction_id': data.get('junction_id'),
            'video_feed_id': data.get('video_feed_id'),
            'vehicle_count': data.get('vehicle_count'),
            'vehicle_types': data.get('vehicle_types', {}),
            'confidence_score': data.get('confidence_score'),
            'is_congested': data.get('is_congested', False)
        }).execute()
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get congestion alerts"""
    try:
        status = request.args.get('status', 'active')
        response = supabase.table('congestion_alerts').select('*').eq('alert_status', status).order('created_at', desc=True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['POST'])
def create_alert():
    """Create a congestion alert"""
    try:
        data = request.get_json()
        response = supabase.table('congestion_alerts').insert({
            'junction_id': data.get('junction_id'),
            'video_feed_id': data.get('video_feed_id'),
            'alert_type': data.get('alert_type', 'stable_vehicle'),
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'stable_duration_minutes': data.get('stable_duration_minutes', 0),
            'assigned_inspector_id': data.get('assigned_inspector_id')
        }).execute()
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports', methods=['GET'])
def get_reports():
    """Get traffic reports"""
    try:
        report_type = request.args.get('type', 'daily')
        response = supabase.table('reports').select('*').eq('report_type', report_type).order('report_date', desc=True).limit(10).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports', methods=['POST'])
def create_report():
    """Generate a report"""
    try:
        data = request.get_json()
        response = supabase.table('reports').insert({
            'junction_id': data.get('junction_id'),
            'report_type': data.get('report_type', 'daily'),
            'total_vehicles_detected': data.get('total_vehicles_detected', 0),
            'peak_hours': data.get('peak_hours', {}),
            'average_congestion_level': data.get('average_congestion_level', 0),
            'alerts_generated': data.get('alerts_generated', 0),
            'report_data': data.get('report_data', {})
        }).execute()
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications', methods=['POST'])
def send_notification():
    """Send notification to user"""
    try:
        data = request.get_json()
        response = supabase.table('notifications').insert({
            'user_id': data.get('user_id'),
            'alert_id': data.get('alert_id'),
            'notification_type': data.get('notification_type', 'email'),
            'message': data.get('message')
        }).execute()
        # TODO: Implement actual email/SMS sending
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video-feeds', methods=['GET'])
def get_video_feeds():
    """Get all video feeds"""
    try:
        junction_id = request.args.get('junction_id')
        query = supabase.table('video_feeds').select('*, junctions(name)')
        
        if junction_id:
            query = query.eq('junction_id', int(junction_id))
        
        response = query.eq('is_active', True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video-feeds', methods=['POST'])
def create_video_feed():
    """Create a new video feed"""
    try:
        data = request.get_json()
        feed_type = data.get('feed_type')
        
        # For file uploads, handle file separately
        if feed_type == 'uploaded' and 'file' in request.files:
            file = request.files['file']
            if not file or not allowed_file(file.filename):
                return jsonify({'error': 'Invalid file'}), 400
            
            if file.size > MAX_FILE_SIZE:
                return jsonify({'error': 'File too large'}), 400
            
            # Upload to Supabase storage
            file_data = file.read()
            path = f"videos/{int(time.time())}-{secure_filename(file.filename)}"
            
            supabase.storage.from_('video-feeds').upload(path, file_data)
            feed_url = f"{SUPABASE_URL}/storage/v1/object/public/video-feeds/{path}"
        else:
            feed_url = data.get('feed_url')
        
        response = supabase.table('video_feeds').insert({
            'feed_name': data.get('feed_name'),
            'junction_id': data.get('junction_id'),
            'feed_type': feed_type,
            'feed_url': feed_url,
            'camera_id': data.get('camera_id'),
            'description': data.get('description', '')
        }).execute()
        
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video-feeds/<int:feed_id>', methods=['DELETE'])
def delete_video_feed(feed_id):
    """Delete a video feed"""
    try:
        response = supabase.table('video_feeds').delete().eq('id', feed_id).execute()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspectors', methods=['GET'])
def get_inspectors():
    """Get all inspectors"""
    try:
        junction_id = request.args.get('junction_id')
        query = supabase.table('inspectors').select('*, junctions(name), users(full_name)')
        
        if junction_id:
            query = query.eq('junction_id', int(junction_id))
        
        response = query.eq('is_active', True).execute()
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspectors', methods=['POST'])
def create_inspector():
    """Create a new inspector"""
    try:
        data = request.get_json()
        response = supabase.table('inspectors').insert({
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'junction_id': data.get('junction_id'),
            'user_id': data.get('user_id')
        }).execute()
        return jsonify(response.data), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inspectors/<int:inspector_id>', methods=['DELETE'])
def delete_inspector(inspector_id):
    """Delete an inspector"""
    try:
        response = supabase.table('inspectors').delete().eq('id', inspector_id).execute()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/init-junctions', methods=['POST'])
def init_junctions():
    """Initialize 4 default junctions"""
    try:
        junctions_data = [
            {'name': 'Junction 1 - North', 'latitude': 28.7041, 'longitude': 77.1025, 'description': '4-lane highway intersection (North Gate)'},
            {'name': 'Junction 2 - South', 'latitude': 28.6915, 'longitude': 77.1037, 'description': '4-lane junction (South District)'},
            {'name': 'Junction 3 - East', 'latitude': 28.7100, 'longitude': 77.1200, 'description': '4-lane intersection (East Bypass)'},
            {'name': 'Junction 4 - West', 'latitude': 28.6950, 'longitude': 77.0900, 'description': '4-lane junction (West Zone)'}
        ]
        
        for junction_data in junctions_data:
            try:
                response = supabase.table('junctions').insert(junction_data).execute()
            except Exception as e:
                if 'duplicate key' not in str(e):
                    raise
        
        return jsonify({'success': True, 'message': 'Junctions initialized'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    # Initialize junctions on startup
    print("Initializing junctions...")
    init_junctions()
    app.run(debug=True, host='0.0.0.0', port=port)
