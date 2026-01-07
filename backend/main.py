from flask import Flask, jsonify
from flask_cors import CORS
from backend.api.routes import api_bp
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(api_bp)

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Track-V API Server Running'}), 200

@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'healthy',
        'timestamp': __import__('datetime').datetime.utcnow().isoformat(),
        'service': 'Track-V Traffic Optimizer'
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
