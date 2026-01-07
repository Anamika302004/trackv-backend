"""
Video Processing and Vehicle Detection Module
Uses OpenCV and YOLO for real-time vehicle detection and congestion analysis
"""

import cv2
import numpy as np
from ultralytics import YOLO
import threading
from collections import defaultdict
from datetime import datetime, timedelta
import json
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VehicleDetector:
    """
    Main class for vehicle detection from video feeds
    Handles OpenCV processing and YOLO inference
    """

    def __init__(self, model_path: str = "yolov8n.pt"):
        """Initialize YOLO model"""
        try:
            self.model = YOLO(model_path)
            self.vehicle_classes = [2, 3, 5, 7]  # car, motorcycle, bus, truck
            self.stable_vehicles = defaultdict(lambda: {"count": 0, "first_seen": None})
            logger.info("[v0] YOLO model loaded successfully")
        except Exception as e:
            logger.error(f"[v0] Error loading YOLO model: {e}")
            raise

    def detect_vehicles(self, frame: np.ndarray) -> Dict:
        """
        Detect vehicles in a frame using YOLO
        Returns detected vehicles, count, types, and confidence scores
        """
        try:
            results = self.model(frame, conf=0.5, verbose=False)
            
            detections = {
                "vehicle_count": 0,
                "vehicle_types": defaultdict(int),
                "detections": [],
                "confidence_scores": []
            }

            for result in results:
                for box in result.boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    if cls in self.vehicle_classes:
                        detections["vehicle_count"] += 1
                        detections["confidence_scores"].append(conf)
                        
                        vehicle_type = self._get_vehicle_type(cls)
                        detections["vehicle_types"][vehicle_type] += 1
                        
                        # Get bounding box coordinates
                        x1, y1, x2, y2 = box.xyxy[0]
                        detections["detections"].append({
                            "type": vehicle_type,
                            "confidence": conf,
                            "bbox": [float(x1), float(y1), float(x2), float(y2)]
                        })

            # Calculate average confidence
            if detections["confidence_scores"]:
                detections["avg_confidence"] = sum(detections["confidence_scores"]) / len(detections["confidence_scores"])
            else:
                detections["avg_confidence"] = 0

            detections["vehicle_types"] = dict(detections["vehicle_types"])
            return detections

        except Exception as e:
            logger.error(f"[v0] Error in vehicle detection: {e}")
            return {
                "vehicle_count": 0,
                "vehicle_types": {},
                "detections": [],
                "avg_confidence": 0
            }

    def detect_stable_vehicles(self, detections: Dict, frame_id: int = 0, stability_threshold: int = 10) -> List[Dict]:
        """
        Detect vehicles that have been stable (not moving) for longer than threshold minutes
        This indicates potential congestion or bottleneck situations
        """
        stable_alerts = []
        current_time = datetime.now()

        for detection in detections.get("detections", []):
            vehicle_key = f"{frame_id}_{detection['bbox'][0]}_{detection['bbox'][1]}"
            
            if vehicle_key not in self.stable_vehicles:
                self.stable_vehicles[vehicle_key] = {
                    "count": 1,
                    "first_seen": current_time,
                    "bbox": detection["bbox"]
                }
            else:
                self.stable_vehicles[vehicle_key]["count"] += 1

        # Check for vehicles stable for longer than threshold
        for vehicle_key, vehicle_info in list(self.stable_vehicles.items()):
            if vehicle_info["first_seen"]:
                duration = (current_time - vehicle_info["first_seen"]).total_seconds() / 60
                
                if duration > stability_threshold:
                    stable_alerts.append({
                        "vehicle_key": vehicle_key,
                        "stable_duration_minutes": int(duration),
                        "bbox": vehicle_info["bbox"],
                        "severity": "high" if duration > 20 else "medium"
                    })
                elif duration < stability_threshold - 5:
                    # Clean up old entries
                    del self.stable_vehicles[vehicle_key]

        return stable_alerts

    def analyze_congestion(self, detections: Dict, frame_shape: Tuple) -> Dict:
        """
        Analyze congestion level based on vehicle density and distribution
        Returns congestion score (0-100) and level (low/medium/high/critical)
        """
        frame_area = frame_shape[0] * frame_shape[1]
        vehicle_count = detections["vehicle_count"]
        
        # Vehicle density calculation
        density = (vehicle_count / frame_area) * 100000
        
        # Determine congestion level
        if density < 2:
            level = "low"
            score = density * 10
        elif density < 5:
            level = "medium"
            score = 20 + (density - 2) * 10
        elif density < 10:
            level = "high"
            score = 50 + (density - 5) * 10
        else:
            level = "critical"
            score = 100

        return {
            "congestion_score": min(score, 100),
            "congestion_level": level,
            "vehicle_density": density,
            "vehicle_count": vehicle_count
        }

    def draw_detections(self, frame: np.ndarray, detections: Dict) -> np.ndarray:
        """
        Draw bounding boxes and vehicle count on frame for visualization
        """
        annotated_frame = frame.copy()
        height, width = frame.shape[:2]
        
        # Draw vehicle detections
        for detection in detections.get("detections", []):
            x1, y1, x2, y2 = [int(coord) for coord in detection["bbox"]]
            confidence = detection["confidence"]
            vehicle_type = detection["type"]
            
            # Draw bounding box
            color = (0, 165, 255)  # Orange
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"{vehicle_type} ({confidence:.2f})"
            cv2.putText(annotated_frame, label, (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw vehicle count and timestamp
        cv2.putText(annotated_frame, f"Vehicles: {detections['vehicle_count']}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(annotated_frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)

        return annotated_frame

    @staticmethod
    def _get_vehicle_type(class_id: int) -> str:
        """Map YOLO class ID to vehicle type"""
        vehicle_types = {
            2: "car",
            3: "motorcycle",
            5: "bus",
            7: "truck"
        }
        return vehicle_types.get(class_id, "unknown")

    def process_video_file(self, video_path: str, callback=None) -> Dict:
        """
        Process a video file and return statistics
        Callback function called with detections for each frame
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video file: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_count = 0
            total_vehicles = 0
            peak_vehicles = 0
            all_detections = []

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # Resize for faster processing
                frame = cv2.resize(frame, (640, 480))
                
                detections = self.detect_vehicles(frame)
                total_vehicles += detections["vehicle_count"]
                peak_vehicles = max(peak_vehicles, detections["vehicle_count"])
                all_detections.append(detections)

                if callback:
                    callback(detections, frame_count)

                frame_count += 1
                if frame_count % 30 == 0:
                    logger.info(f"[v0] Processed {frame_count}/{total_frames} frames")

            cap.release()

            avg_vehicles = total_vehicles / max(frame_count, 1)
            duration_seconds = total_frames / fps if fps > 0 else 0

            return {
                "success": True,
                "total_frames": frame_count,
                "duration_seconds": duration_seconds,
                "fps": fps,
                "total_vehicles": total_vehicles,
                "average_vehicles": avg_vehicles,
                "peak_vehicles": peak_vehicles,
                "detections": all_detections[:100]  # Return first 100 for efficiency
            }

        except Exception as e:
            logger.error(f"[v0] Error processing video: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def process_youtube_video(self, youtube_url: str, callback=None) -> Dict:
        """
        Process a YouTube video using yt-dlp to get stream URL
        """
        try:
            import yt_dlp
            
            ydl_opts = {
                'format': 'best[ext=mp4]',
                'quiet': True,
                'no_warnings': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                stream_url = info['url']
            
            # Process the stream
            return self.process_stream(stream_url, callback=callback, max_frames=300)
            
        except Exception as e:
            logger.error(f"[v0] Error processing YouTube video: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def process_stream(self, stream_url: str, callback=None, max_frames: int = 300) -> Dict:
        """
        Process a live stream or HTTP stream
        """
        try:
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise ValueError(f"Cannot open stream: {stream_url}")

            frame_count = 0
            total_vehicles = 0
            peak_vehicles = 0
            all_detections = []

            while cap.isOpened() and frame_count < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break

                frame = cv2.resize(frame, (640, 480))
                detections = self.detect_vehicles(frame)
                
                total_vehicles += detections["vehicle_count"]
                peak_vehicles = max(peak_vehicles, detections["vehicle_count"])
                all_detections.append(detections)

                if callback:
                    callback(detections, frame_count)

                frame_count += 1

            cap.release()

            return {
                "success": True,
                "frames_processed": frame_count,
                "total_vehicles": total_vehicles,
                "average_vehicles": total_vehicles / max(frame_count, 1),
                "peak_vehicles": peak_vehicles,
                "detections": all_detections
            }

        except Exception as e:
            logger.error(f"[v0] Error processing stream: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class VideoProcessor:
    """
    Main processor class that coordinates video processing and database updates
    """
    
    def __init__(self, supabase_client):
        self.detector = VehicleDetector()
        self.supabase = supabase_client
        self.processing_threads = {}

    async def process_and_store(self, video_path: str, junction_id: int, video_feed_id: int = None) -> Dict:
        """
        Process video and store detections in database
        """
        def detection_callback(detections, frame_num):
            # Store in database
            self.supabase.table("vehicle_detections").insert({
                "junction_id": junction_id,
                "video_feed_id": video_feed_id,
                "vehicle_count": detections["vehicle_count"],
                "vehicle_types": detections["vehicle_types"],
                "confidence_score": detections.get("avg_confidence", 0),
                "is_congested": detections["vehicle_count"] > 30
            }).execute()

        result = self.detector.process_video_file(video_path, callback=detection_callback)
        return result
