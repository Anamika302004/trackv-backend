from flask import Blueprint, request, jsonify
from backend.auth.auth_manager import AuthManager
from functools import wraps
import os

api_bp = Blueprint('api', __name__, url_prefix='/api')
auth_manager = AuthManager()

# Middleware to verify JWT token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        
        try:
            token = token.split(' ')[1]  # Remove 'Bearer ' prefix
            payload = auth_manager.verify_token(token)
            request.user = payload
        except Exception as e:
            return jsonify({'error': str(e)}), 401
        
        return f(*args, **kwargs)
    return decorated

# Authentication Routes
@api_bp.route('/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        result = auth_manager.register(
            email=data.get('email'),
            password=data.get('password'),
            full_name=data.get('full_name'),
            phone_number=data.get('phone_number'),
            role=data.get('role', 'traffic_inspector')
        )
        
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        result = auth_manager.login(
            email=data.get('email'),
            password=data.get('password')
        )
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 401

@api_bp.route('/auth/verify', methods=['GET'])
@token_required
def verify_token():
    return jsonify({'user': request.user}), 200

# Inspectors Routes
@api_bp.route('/inspectors', methods=['GET'])
@token_required
def get_inspectors():
    try:
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            SELECT i.id, i.badge_number, u.full_name, u.email, i.phone_number,
                   i.email_notification_enabled, i.sms_notification_enabled,
                   j.name as junction_name
            FROM inspectors i
            JOIN users u ON i.user_id = u.id
            JOIN junctions j ON i.junction_id = j.id
            WHERE i.user_id = %s OR %s = 'admin'
        """, (request.user['user_id'], request.user['role']))
        
        inspectors = cursor.fetchall()
        cursor.close()
        
        return jsonify([dict(i) for i in inspectors]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/inspectors', methods=['POST'])
@token_required
def add_inspector():
    try:
        data = request.get_json()
        
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            INSERT INTO inspectors (user_id, junction_id, badge_number, phone_number)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (data['user_id'], data['junction_id'], data['badge_number'], data['phone_number']))
        
        inspector_id = cursor.fetchone()[0]
        auth_manager.db_connection.commit()
        cursor.close()
        
        return jsonify({'id': str(inspector_id), 'message': 'Inspector added'}), 201
    except Exception as e:
        auth_manager.db_connection.rollback()
        return jsonify({'error': str(e)}), 400

# Alerts Routes
@api_bp.route('/alerts', methods=['GET'])
@token_required
def get_alerts():
    try:
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            SELECT a.id, a.title, a.description, a.severity, a.alert_type,
                   a.created_at, j.name as junction_name
            FROM alerts a
            JOIN junctions j ON a.junction_id = j.id
            WHERE a.is_active = TRUE
            ORDER BY a.created_at DESC
            LIMIT 50
        """)
        
        alerts = cursor.fetchall()
        cursor.close()
        
        return jsonify([dict(a) for a in alerts]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/alerts', methods=['POST'])
@token_required
def create_alert():
    try:
        data = request.get_json()
        
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            INSERT INTO alerts (junction_id, alert_type, severity, title, description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['junction_id'],
            data['alert_type'],
            data['severity'],
            data['title'],
            data.get('description'),
            request.user['user_id']
        ))
        
        alert_id = cursor.fetchone()[0]
        auth_manager.db_connection.commit()
        
        # Send notifications to inspectors
        cursor.execute("""
            SELECT i.id, u.email, i.phone_number, i.email_notification_enabled, 
                   i.sms_notification_enabled
            FROM inspectors i
            JOIN users u ON i.user_id = u.id
            WHERE i.junction_id = %s
        """, (data['junction_id'],))
        
        inspectors = cursor.fetchall()
        for inspector in inspectors:
            if inspector[3]:  # email_notification_enabled
                auth_manager.send_notification_email(
                    inspector[1],
                    f"Alert: {data['title']}",
                    data.get('description', '')
                )
            if inspector[4]:  # sms_notification_enabled
                auth_manager.send_sms(inspector[2], data['title'])
        
        cursor.close()
        
        return jsonify({'id': str(alert_id), 'message': 'Alert created'}), 201
    except Exception as e:
        auth_manager.db_connection.rollback()
        return jsonify({'error': str(e)}), 400

# Video Feed Routes
@api_bp.route('/video-feeds', methods=['POST'])
@token_required
def upload_video_feed():
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video provided'}), 400
        
        video_file = request.files['video']
        junction_id = request.form.get('junction_id')
        feed_name = request.form.get('feed_name')
        
        # Save video file
        video_path = f"/videos/{junction_id}/{video_file.filename}"
        video_file.save(video_path)
        
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            INSERT INTO video_feeds (junction_id, feed_name, feed_type, source_path)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (junction_id, feed_name, 'upload', video_path))
        
        feed_id = cursor.fetchone()[0]
        auth_manager.db_connection.commit()
        cursor.close()
        
        return jsonify({'id': str(feed_id), 'message': 'Video uploaded'}), 201
    except Exception as e:
        auth_manager.db_connection.rollback()
        return jsonify({'error': str(e)}), 400

@api_bp.route('/video-feeds/youtube', methods=['POST'])
@token_required
def add_youtube_feed():
    try:
        data = request.get_json()
        
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            INSERT INTO video_feeds (junction_id, feed_name, feed_type, source_url)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (data['junction_id'], data['feed_name'], 'youtube', data['youtube_url']))
        
        feed_id = cursor.fetchone()[0]
        auth_manager.db_connection.commit()
        cursor.close()
        
        return jsonify({'id': str(feed_id), 'message': 'YouTube feed added'}), 201
    except Exception as e:
        auth_manager.db_connection.rollback()
        return jsonify({'error': str(e)}), 400

# Traffic Analysis Routes
@api_bp.route('/analysis/results', methods=['GET'])
@token_required
def get_analysis_results():
    try:
        junction_id = request.args.get('junction_id')
        cursor = auth_manager.db_connection.cursor()
        
        query = "SELECT * FROM traffic_analysis_results ORDER BY analysis_timestamp DESC LIMIT 100"
        params = []
        
        if junction_id:
            query = query.replace("FROM", "FROM WHERE junction_id = %s")
            params = [junction_id]
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        
        return jsonify([dict(r) for r in results]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Reports Routes
@api_bp.route('/reports', methods=['GET'])
@token_required
def get_reports():
    try:
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            SELECT * FROM reports WHERE created_by = %s
            ORDER BY created_at DESC
        """, (request.user['user_id'],))
        
        reports = cursor.fetchall()
        cursor.close()
        
        return jsonify([dict(r) for r in reports]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/reports', methods=['POST'])
@token_required
def create_report():
    try:
        data = request.get_json()
        
        cursor = auth_manager.db_connection.cursor()
        cursor.execute("""
            INSERT INTO reports (junction_id, created_by, report_type, title, 
                               date_range_start, date_range_end, summary_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['junction_id'],
            request.user['user_id'],
            data['report_type'],
            data['title'],
            data.get('date_range_start'),
            data.get('date_range_end'),
            data.get('summary_data')
        ))
        
        report_id = cursor.fetchone()[0]
        auth_manager.db_connection.commit()
        cursor.close()
        
        return jsonify({'id': str(report_id), 'message': 'Report created'}), 201
    except Exception as e:
        auth_manager.db_connection.rollback()
        return jsonify({'error': str(e)}), 400
