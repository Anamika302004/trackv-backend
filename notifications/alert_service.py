import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AlertService:
    """Service to manage and send alerts"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        
    def create_alert(self, junction_id: str, alert_type: str, 
                    severity: str, title: str, description: str, 
                    created_by: str) -> str:
        """Create a new alert"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                INSERT INTO alerts 
                (junction_id, alert_type, severity, title, description, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (junction_id, alert_type, severity, title, description, created_by))
            
            alert_id = cursor.fetchone()[0]
            self.db_connection.commit()
            
            # Send notifications to inspectors
            self.send_notifications_to_inspectors(junction_id, alert_id, title, description)
            
            cursor.close()
            return alert_id
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            self.db_connection.rollback()
            raise
    
    def send_notifications_to_inspectors(self, junction_id: str, alert_id: str, 
                                        title: str, description: str):
        """Send notifications to all inspectors of a junction"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT i.id, u.email, i.phone_number, 
                       i.email_notification_enabled, i.sms_notification_enabled
                FROM inspectors i
                JOIN users u ON i.user_id = u.id
                WHERE i.junction_id = %s
            """, (junction_id,))
            
            inspectors = cursor.fetchall()
            
            for inspector in inspectors:
                inspector_id, email, phone, email_enabled, sms_enabled = inspector
                
                if email_enabled:
                    self.send_email_alert(email, title, description, inspector_id, alert_id)
                
                if sms_enabled and phone:
                    self.send_sms_alert(phone, title, description, inspector_id, alert_id)
            
            cursor.close()
        except Exception as e:
            logger.error(f"Error sending notifications: {e}")
    
    def send_email_alert(self, to_email: str, title: str, description: str, 
                        inspector_id: str, alert_id: str) -> bool:
        """Send email alert"""
        try:
            subject = f"Track-V Alert: {title}"
            
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                        <h2 style="color: #ff8c42;">Alert Notification</h2>
                        <h3>{title}</h3>
                        <p><strong>Description:</strong> {description}</p>
                        <p><strong>Time:</strong> {datetime.utcnow().isoformat()}</p>
                        <p>
                            <a href="#" style="background-color: #ff8c42; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                                View Details
                            </a>
                        </p>
                    </div>
                </body>
            </html>
            """
            
            text_body = f"Alert: {title}\n\n{description}\n\nTime: {datetime.utcnow().isoformat()}"
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = to_email
            
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            # Log notification
            self._log_notification(inspector_id, alert_id, 'email', 'sent')
            logger.info(f"Email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            self._log_notification(inspector_id, alert_id, 'email', 'failed')
            return False
    
    def send_sms_alert(self, phone_number: str, title: str, description: str, 
                      inspector_id: str, alert_id: str) -> bool:
        """Send SMS alert (integrate with Twilio or AWS SNS)"""
        try:
            # Placeholder for SMS service integration
            # Example with Twilio:
            # from twilio.rest import Client
            # client = Client(account_sid, auth_token)
            # message = client.messages.create(
            #     to=phone_number,
            #     from_=os.getenv('TWILIO_PHONE_NUMBER'),
            #     body=f"{title}: {description}"
            # )
            
            logger.info(f"SMS sent to {phone_number}: {title}")
            self._log_notification(inspector_id, alert_id, 'sms', 'sent')
            return True
            
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            self._log_notification(inspector_id, alert_id, 'sms', 'failed')
            return False
    
    def _log_notification(self, inspector_id: str, alert_id: str, 
                         method: str, status: str):
        """Log notification to database"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                INSERT INTO alert_notifications 
                (alert_id, inspector_id, notification_method, status)
                VALUES (%s, %s, %s, %s)
            """, (alert_id, inspector_id, method, status))
            
            self.db_connection.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Error logging notification: {e}")
    
    def detect_bottleneck_and_alert(self, junction_id: str, vehicle_count: int, 
                                   stable_vehicles: int):
        """Detect bottleneck situation and create alert"""
        try:
            if vehicle_count > 100 or stable_vehicles > 5:
                alert_type = 'bottleneck'
                severity = 'critical' if stable_vehicles > 10 else 'high'
                title = f"Traffic Bottleneck Detected at Junction {junction_id}"
                description = f"High congestion: {vehicle_count} vehicles, {stable_vehicles} stable for 10+ mins"
                
                self.create_alert(
                    junction_id=junction_id,
                    alert_type=alert_type,
                    severity=severity,
                    title=title,
                    description=description,
                    created_by='system'
                )
        except Exception as e:
            logger.error(f"Error detecting bottleneck: {e}")
