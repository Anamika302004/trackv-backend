"""
Advanced Vehicle Detection and Congestion Analysis
Handles stable vehicle detection and alert generation
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CongestionAnalyzer:
    """
    Analyzes vehicle detections to identify congestion patterns and stable vehicles
    """

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.vehicle_tracking = {}
        self.stable_threshold_minutes = 10  # Alert after 10 minutes of stability

    def check_and_create_alerts(self, junction_id: int, detections: Dict, video_feed_id: int = None) -> List[Dict]:
        """
        Check detections for stable vehicles and create alerts if threshold exceeded
        """
        alerts_created = []
        current_time = datetime.now()

        try:
            # Get existing stable vehicles for this junction
            existing_stable = self.supabase.table("congestion_alerts").select("*").eq(
                "junction_id", junction_id
            ).eq("alert_status", "active").eq("alert_type", "stable_vehicle").execute()

            stable_vehicles = existing_stable.data or []

            # Check if we should create new alert based on vehicle count
            if detections["vehicle_count"] > 30:  # High congestion threshold
                try:
                    alert_data = {
                        "junction_id": junction_id,
                        "video_feed_id": video_feed_id,
                        "alert_type": "high_congestion",
                        "stable_duration_minutes": 0,
                        "alert_status": "active"
                    }
                    alert = self.supabase.table("congestion_alerts").insert(alert_data).execute()
                    alerts_created.append(alert.data[0])
                    logger.info(f"[v0] Created high congestion alert for junction {junction_id}")
                except Exception as e:
                    logger.error(f"[v0] Error creating congestion alert: {e}")

            # Track vehicle stability
            vehicle_key = f"junction_{junction_id}"
            
            if vehicle_key not in self.vehicle_tracking:
                self.vehicle_tracking[vehicle_key] = {
                    "first_detected": current_time,
                    "vehicle_count": detections["vehicle_count"],
                    "last_update": current_time
                }
            else:
                # Update tracking
                self.vehicle_tracking[vehicle_key]["last_update"] = current_time
                self.vehicle_tracking[vehicle_key]["vehicle_count"] = detections["vehicle_count"]

            # Check if vehicles have been stable for threshold
            tracking_data = self.vehicle_tracking[vehicle_key]
            duration = (current_time - tracking_data["first_detected"]).total_seconds() / 60

            if duration > self.stable_threshold_minutes:
                # Check if we already have an alert for this
                has_alert = any(
                    alert["stable_duration_minutes"] >= self.stable_threshold_minutes
                    for alert in stable_vehicles
                )

                if not has_alert:
                    try:
                        alert_data = {
                            "junction_id": junction_id,
                            "video_feed_id": video_feed_id,
                            "alert_type": "stable_vehicle",
                            "stable_duration_minutes": int(duration),
                            "alert_status": "active"
                        }
                        alert = self.supabase.table("congestion_alerts").insert(alert_data).execute()
                        alerts_created.append(alert.data[0])
                        logger.info(f"[v0] Created stable vehicle alert for junction {junction_id} (duration: {int(duration)}min)")
                    except Exception as e:
                        logger.error(f"[v0] Error creating stable vehicle alert: {e}")
            else:
                # Reset if vehicle count decreased significantly
                if detections["vehicle_count"] < 10:
                    if vehicle_key in self.vehicle_tracking:
                        del self.vehicle_tracking[vehicle_key]

        except Exception as e:
            logger.error(f"[v0] Error in check_and_create_alerts: {e}")

        return alerts_created

    def send_notifications(self, alert_id: int, alert_data: Dict) -> bool:
        """
        Send notifications to assigned inspector and related users
        """
        try:
            # Get assigned inspector
            if alert_data.get("assigned_inspector_id"):
                inspector = self.supabase.table("inspectors").select("*").eq(
                    "id", alert_data["assigned_inspector_id"]
                ).single().execute()

                inspector_data = inspector.data

                # Create in-app notification
                self.supabase.table("notifications").insert({
                    "user_id": inspector_data["user_id"],
                    "alert_id": alert_id,
                    "notification_type": "in_app",
                    "message": f"New {alert_data['alert_type']} alert at your assigned junction"
                }).execute()

                # TODO: Send email and SMS using external services
                logger.info(f"[v0] Notification sent to inspector {inspector_data['id']}")

            # Notify junction officer
            junction = self.supabase.table("junctions").select("*").eq(
                "id", alert_data["junction_id"]
            ).single().execute()

            officers = self.supabase.table("users").select("*").eq(
                "assigned_junction_id", alert_data["junction_id"]
            ).eq("user_type", "officer").execute()

            for officer in officers.data or []:
                self.supabase.table("notifications").insert({
                    "user_id": officer["id"],
                    "alert_id": alert_id,
                    "notification_type": "in_app",
                    "message": f"Alert at {junction.data['name']}: {alert_data['alert_type']}"
                }).execute()

            return True

        except Exception as e:
            logger.error(f"[v0] Error sending notifications: {e}")
            return False

    def generate_report(self, junction_id: int, report_type: str = "daily") -> Dict:
        """
        Generate traffic report for a junction
        """
        try:
            # Get detections for the period
            if report_type == "daily":
                start_date = datetime.now().date()
            elif report_type == "weekly":
                start_date = datetime.now().date() - timedelta(days=7)
            elif report_type == "monthly":
                start_date = datetime.now().date() - timedelta(days=30)
            else:
                start_date = datetime.now().date()

            detections = self.supabase.table("vehicle_detections").select("*").eq(
                "junction_id", junction_id
            ).gte("created_at", str(start_date)).execute()

            detection_data = detections.data or []

            # Calculate statistics
            total_vehicles = sum(d["vehicle_count"] for d in detection_data)
            avg_vehicles = total_vehicles / len(detection_data) if detection_data else 0
            peak_vehicles = max((d["vehicle_count"] for d in detection_data), default=0)

            # Get alerts
            alerts = self.supabase.table("congestion_alerts").select("*").eq(
                "junction_id", junction_id
            ).gte("created_at", str(start_date)).execute()

            # Create report
            report = {
                "junction_id": junction_id,
                "report_type": report_type,
                "report_date": str(datetime.now().date()),
                "total_vehicles_detected": total_vehicles,
                "average_vehicles": round(avg_vehicles, 2),
                "peak_vehicles": peak_vehicles,
                "alerts_generated": len(alerts.data or []),
                "report_data": {
                    "detection_count": len(detection_data),
                    "alert_details": [
                        {
                            "type": a.get("alert_type"),
                            "status": a.get("alert_status"),
                            "duration_minutes": a.get("stable_duration_minutes", 0)
                        }
                        for a in alerts.data or []
                    ]
                }
            }

            # Store report
            self.supabase.table("reports").insert(report).execute()
            logger.info(f"[v0] Report generated for junction {junction_id}")

            return report

        except Exception as e:
            logger.error(f"[v0] Error generating report: {e}")
            return {}
