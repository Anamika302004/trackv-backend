"""
Configuration module for Track-V backend
Handles environment variables and app settings
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')
    SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    # Flask
    DEBUG = os.getenv('DEBUG', 'False') == 'True'
    PORT = int(os.getenv('PORT', 5000))
    HOST = os.getenv('HOST', '0.0.0.0')
    
    # Video Processing
    YOLO_MODEL = os.getenv('YOLO_MODEL', 'yolov8n.pt')
    VIDEO_UPLOAD_FOLDER = os.getenv('VIDEO_UPLOAD_FOLDER', './uploads')
    MAX_VIDEO_SIZE_MB = int(os.getenv('MAX_VIDEO_SIZE_MB', 500))
    
    # Notifications
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_EMAIL = os.getenv('SMTP_EMAIL')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    
    # Processing
    STABLE_VEHICLE_THRESHOLD_MINUTES = int(os.getenv('STABLE_VEHICLE_THRESHOLD_MINUTES', 10))
    CONGESTION_THRESHOLD_VEHICLES = int(os.getenv('CONGESTION_THRESHOLD_VEHICLES', 30))


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


def get_config():
    """Get configuration based on environment"""
    env = os.getenv('ENVIRONMENT', 'development')
    return DevelopmentConfig() if env == 'development' else ProductionConfig()
