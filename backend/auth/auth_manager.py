import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict
import psycopg2
from psycopg2.extras import RealDictCursor
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class AuthManager:
    def __init__(self):
        self.db_connection = self._get_db_connection()
        self.jwt_secret = os.getenv('SUPABASE_JWT_SECRET', 'your-secret-key')
        self.jwt_algorithm = 'HS256'
        self.token_expiry_hours = 24
        
    def _get_db_connection(self):
        """Connect to Supabase PostgreSQL database"""
        try:
            conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST'),
                database=os.getenv('POSTGRES_DATABASE'),
                user=os.getenv('POSTGRES_USER'),
                password=os.getenv('POSTGRES_PASSWORD'),
                port=5432
            )
            return conn
        except Exception as e:
            print(f"Database connection error: {e}")
            raise
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    def _generate_jwt_token(self, user_id: str, email: str, role: str) -> str:
        """Generate JWT token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'role': role,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=self.token_expiry_hours)
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def register(self, email: str, password: str, full_name: str, 
                phone_number: str, role: str) -> Dict:
        """Register new user"""
        try:
            cursor = self.db_connection.cursor(cursor_factory=RealDictCursor)
            
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                raise Exception("Email already registered")
            
            # Validate role
            if role not in ['ips_officer', 'traffic_inspector', 'admin']:
                raise Exception("Invalid role")
            
            # Hash password
            password_hash = self._hash_password(password)
            
            # Insert user
            cursor.execute("""
                INSERT INTO users (email, password_hash, full_name, phone_number, role)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, email, full_name, role
            """, (email, password_hash, full_name, phone_number, role))
            
            user = cursor.fetchone()
            self.db_connection.commit()
            cursor.close()
            
            return {
                'user_id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'],
                'role': user['role'],
                'message': 'Registration successful'
            }
        except Exception as e:
            self.db_connection.rollback()
            raise e
    
    def login(self, email: str, password: str) -> Dict:
        """Login user"""
        try:
            cursor = self.db_connection.cursor(cursor_factory=RealDictCursor)
            
            # Get user
            cursor.execute("""
                SELECT id, email, password_hash, full_name, role, status
                FROM users WHERE email = %s
            """, (email,))
            
            user = cursor.fetchone()
            if not user:
                raise Exception("Invalid email or password")
            
            if user['status'] != 'active':
                raise Exception("Account is not active")
            
            # Verify password
            if not self._verify_password(password, user['password_hash']):
                raise Exception("Invalid email or password")
            
            # Update last login
            cursor.execute("""
                UPDATE users SET last_login = NOW() WHERE id = %s
            """, (user['id'],))
            self.db_connection.commit()
            
            # Generate token
            token = self._generate_jwt_token(str(user['id']), user['email'], user['role'])
            
            cursor.close()
            
            return {
                'token': token,
                'user': {
                    'id': str(user['id']),
                    'email': user['email'],
                    'full_name': user['full_name'],
                    'role': user['role']
                }
            }
        except Exception as e:
            raise e
    
    def verify_token(self, token: str) -> Dict:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Token expired")
        except jwt.InvalidTokenError:
            raise Exception("Invalid token")
    
    def send_notification_email(self, to_email: str, subject: str, 
                               body: str, html_body: Optional[str] = None) -> bool:
        """Send email notification"""
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            sender_email = os.getenv('SENDER_EMAIL')
            sender_password = os.getenv('SENDER_PASSWORD')
            
            if not all([sender_email, sender_password]):
                print("Email config not set up")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = to_email
            
            # Attach text and HTML versions
            part1 = MIMEText(body, 'plain')
            msg.attach(part1)
            
            if html_body:
                part2 = MIMEText(html_body, 'html')
                msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Email sending error: {e}")
            return False
    
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS notification (placeholder - integrate with Twilio/AWS SNS)"""
        try:
            # Integrate with Twilio or AWS SNS
            print(f"SMS to {phone_number}: {message}")
            return True
        except Exception as e:
            print(f"SMS error: {e}")
            return False
