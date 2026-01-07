import cv2
import numpy as np
from ultralytics import YOLO
from typing import Dict, List, Tuple
import time
from datetime import datetime

class OpenCVAnalyzer:
    def __init__(self):
        self.model = YOLO('yolov8n.pt')  # Load YOLOv8 nano model
        self.vehicle_classes = {
            2: 'car',
            3: 'motorbike',
            5: 'bus',
            7: 'truck'
        }
        self.stable_vehicles = {}  # Track vehicles stable for 10+ mins
        self.stable_threshold_seconds = 600  # 10 minutes
        
    def process_video(self, video_path: str) -> Dict:
        """Process video and extract traffic metrics"""
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise Exception("Could not open video file")
        
        frame_count = 0
        vehicle_data = {
            'total_vehicles': 0,
            'vehicle_types': {},
            'congestion_level': 'low',
            'bottleneck_detected': False,
            'stable_vehicles': 0,
            'frames_processed': 0,
            'average_confidence': 0
        }
        
        total_confidence = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # Detect vehicles
            results = self.model(frame)
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    if cls in self.vehicle_classes:
                        vehicle_type = self.vehicle_classes[cls]
                        vehicle_data['vehicle_types'][vehicle_type] = \
                            vehicle_data['vehicle_types'].get(vehicle_type, 0) + 1
                        vehicle_data['total_vehicles'] += 1
                        total_confidence += conf
        
        vehicle_data['frames_processed'] = frame_count
        if vehicle_data['total_vehicles'] > 0:
            vehicle_data['average_confidence'] = total_confidence / vehicle_data['total_vehicles']
        
        cap.release()
        
        # Determine congestion level
        if vehicle_data['total_vehicles'] > 100:
            vehicle_data['congestion_level'] = 'critical'
        elif vehicle_data['total_vehicles'] > 50:
            vehicle_data['congestion_level'] = 'high'
        elif vehicle_data['total_vehicles'] > 20:
            vehicle_data['congestion_level'] = 'medium'
        
        return vehicle_data
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """Process single frame for real-time analysis"""
        results = self.model(frame)
        
        detections = {
            'vehicle_count': 0,
            'vehicle_types': {},
            'detections': []
        }
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0]
                
                if cls in self.vehicle_classes:
                    vehicle_type = self.vehicle_classes[cls]
                    detections['vehicle_count'] += 1
                    detections['vehicle_types'][vehicle_type] = \
                        detections['vehicle_types'].get(vehicle_type, 0) + 1
                    
                    detections['detections'].append({
                        'type': vehicle_type,
                        'confidence': conf,
                        'bbox': [float(x1), float(y1), float(x2), float(y2)]
                    })
        
        return detections
    
    def detect_stable_vehicles(self, vehicle_positions: List[Dict]) -> int:
        """Detect vehicles stationary for > 10 minutes"""
        current_time = time.time()
        stable_count = 0
        
        for vehicle in vehicle_positions:
            vehicle_id = vehicle['id']
            position = vehicle['position']
            
            if vehicle_id not in self.stable_vehicles:
                self.stable_vehicles[vehicle_id] = {
                    'position': position,
                    'start_time': current_time
                }
            else:
                # Check if position changed significantly
                prev_pos = self.stable_vehicles[vehicle_id]['position']
                distance = np.sqrt((position[0] - prev_pos[0])**2 + 
                                 (position[1] - prev_pos[1])**2)
                
                if distance < 10:  # Less than 10 pixels movement
                    time_elapsed = current_time - self.stable_vehicles[vehicle_id]['start_time']
                    if time_elapsed > self.stable_threshold_seconds:
                        stable_count += 1
                else:
                    # Vehicle moved, reset timer
                    self.stable_vehicles[vehicle_id] = {
                        'position': position,
                        'start_time': current_time
                    }
        
        return stable_count
