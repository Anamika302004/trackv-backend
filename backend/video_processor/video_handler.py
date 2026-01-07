import cv2
import numpy as np
import os
import threading
from typing import Dict, Optional
import yt_dlp
import requests
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class VideoHandler:
    """Base class for different video source types"""
    
    def __init__(self):
        self.cap = None
        self.frame_rate = 30
        
    def get_video_stream(self):
        raise NotImplementedError
    
    def release(self):
        if self.cap:
            self.cap.release()

class UploadedVideoHandler(VideoHandler):
    """Handle uploaded video files"""
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        
    def get_video_stream(self):
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Video file not found: {self.file_path}")
        
        self.cap = cv2.VideoCapture(self.file_path)
        if not self.cap.isOpened():
            raise Exception(f"Failed to open video: {self.file_path}")
        
        self.frame_rate = self.cap.get(cv2.CAP_PROP_FPS)
        return self.cap
    
    def get_total_frames(self) -> int:
        return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) if self.cap else 0
    
    def get_resolution(self) -> tuple:
        if not self.cap:
            return (0, 0)
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (width, height)

class YouTubeVideoHandler(VideoHandler):
    """Handle YouTube videos using yt-dlp"""
    
    def __init__(self, youtube_url: str, quality: str = "480p"):
        super().__init__()
        self.youtube_url = youtube_url
        self.quality = quality
        self.video_stream_url = None
        
    def get_video_stream(self):
        try:
            ydl_opts = {
                'format': f'best[ext=mp4][height<={int(self.quality[:-1])}]',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.youtube_url, download=False)
                self.video_stream_url = info['url']
            
            self.cap = cv2.VideoCapture(self.video_stream_url)
            if not self.cap.isOpened():
                raise Exception("Failed to open YouTube video stream")
            
            self.frame_rate = self.cap.get(cv2.CAP_PROP_FPS) or 30
            return self.cap
        except Exception as e:
            logger.error(f"Error fetching YouTube video: {e}")
            raise

class CCTVCameraHandler(VideoHandler):
    """Handle CCTV camera streams"""
    
    def __init__(self, camera_ip: str, port: int = 8080, 
                 username: str = None, password: str = None):
        super().__init__()
        self.camera_ip = camera_ip
        self.port = port
        self.username = username
        self.password = password
        self.stream_url = None
        
    def get_video_stream(self):
        # Common CCTV stream URLs
        auth_str = f"{self.username}:{self.password}@" if self.username else ""
        
        stream_urls = [
            f"rtsp://{auth_str}{self.camera_ip}:{self.port}/stream1",
            f"rtsp://{auth_str}{self.camera_ip}:{self.port}/h264",
            f"http://{auth_str}{self.camera_ip}:{self.port}/video",
        ]
        
        for url in stream_urls:
            try:
                self.cap = cv2.VideoCapture(url)
                if self.cap.isOpened():
                    self.stream_url = url
                    self.frame_rate = self.cap.get(cv2.CAP_PROP_FPS) or 30
                    return self.cap
            except Exception as e:
                logger.warning(f"Failed to connect to {url}: {e}")
        
        raise Exception(f"Could not connect to CCTV camera at {self.camera_ip}")

class LocalCameraHandler(VideoHandler):
    """Handle local webcam/camera"""
    
    def __init__(self, camera_index: int = 0):
        super().__init__()
        self.camera_index = camera_index
        
    def get_video_stream(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise Exception(f"Could not access camera at index {self.camera_index}")
        
        self.frame_rate = self.cap.get(cv2.CAP_PROP_FPS) or 30
        return self.cap

class VideoProcessor:
    """Process videos and extract frames with analysis"""
    
    def __init__(self, video_handler: VideoHandler, junction_id: str):
        self.video_handler = video_handler
        self.junction_id = junction_id
        self.frame_count = 0
        self.is_processing = False
        self.stop_event = threading.Event()
        
    def process_video_stream(self, callback=None):
        """Process video stream frame by frame"""
        try:
            cap = self.video_handler.get_video_stream()
            self.is_processing = True
            
            while self.is_processing and not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    logger.info("Video stream ended or failed")
                    break
                
                self.frame_count += 1
                
                # Resize frame for processing efficiency
                processed_frame = cv2.resize(frame, (640, 480))
                
                if callback:
                    callback(processed_frame, self.frame_count)
                
                # Yield frame every 30th frame to reduce overhead
                if self.frame_count % 30 == 0:
                    yield processed_frame, self.frame_count
        
        finally:
            self.video_handler.release()
            self.is_processing = False
    
    def stop_processing(self):
        """Stop video processing"""
        self.is_processing = False
        self.stop_event.set()
    
    def compress_frame(self, frame: np.ndarray, quality: int = 80) -> bytes:
        """Compress frame to JPEG bytes for streaming"""
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ret:
            return buffer.tobytes()
        return None

class VideoAnalysisService:
    """Service to manage multiple video streams and analysis"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
        self.active_processors = {}
        self.analysis_results = {}
        
    def add_youtube_feed(self, junction_id: str, youtube_url: str, feed_name: str):
        """Add YouTube feed"""
        try:
            handler = YouTubeVideoHandler(youtube_url)
            processor = VideoProcessor(handler, junction_id)
            
            feed_id = f"{junction_id}_{feed_name}_{int(datetime.now().timestamp())}"
            self.active_processors[feed_id] = processor
            
            # Start processing in background thread
            thread = threading.Thread(
                target=self._process_feed,
                args=(feed_id, processor)
            )
            thread.daemon = True
            thread.start()
            
            return feed_id
        except Exception as e:
            logger.error(f"Error adding YouTube feed: {e}")
            raise
    
    def add_cctv_feed(self, junction_id: str, camera_ip: str, 
                     feed_name: str, username: str = None, password: str = None):
        """Add CCTV camera feed"""
        try:
            handler = CCTVCameraHandler(camera_ip, username=username, password=password)
            processor = VideoProcessor(handler, junction_id)
            
            feed_id = f"{junction_id}_{feed_name}_{int(datetime.now().timestamp())}"
            self.active_processors[feed_id] = processor
            
            thread = threading.Thread(
                target=self._process_feed,
                args=(feed_id, processor)
            )
            thread.daemon = True
            thread.start()
            
            return feed_id
        except Exception as e:
            logger.error(f"Error adding CCTV feed: {e}")
            raise
    
    def upload_and_process_video(self, junction_id: str, file_path: str, feed_name: str):
        """Upload and process video file"""
        try:
            handler = UploadedVideoHandler(file_path)
            processor = VideoProcessor(handler, junction_id)
            
            feed_id = f"{junction_id}_{feed_name}_{int(datetime.now().timestamp())}"
            self.active_processors[feed_id] = processor
            
            thread = threading.Thread(
                target=self._process_feed,
                args=(feed_id, processor)
            )
            thread.daemon = True
            thread.start()
            
            return feed_id
        except Exception as e:
            logger.error(f"Error processing uploaded video: {e}")
            raise
    
    def _process_feed(self, feed_id: str, processor: VideoProcessor):
        """Process feed and store results"""
        from backend.video_processor.opencv_analyzer import OpenCVAnalyzer
        
        analyzer = OpenCVAnalyzer()
        
        for frame, frame_count in processor.process_video_stream():
            try:
                detections = analyzer.process_frame(frame)
                
                # Store results every 30 frames
                if frame_count % 30 == 0:
                    self.analysis_results[feed_id] = {
                        'frame_count': frame_count,
                        'vehicle_count': detections['vehicle_count'],
                        'vehicle_types': detections['vehicle_types'],
                        'timestamp': datetime.utcnow(),
                        'detections': detections['detections']
                    }
                    
                    # Save to database
                    self._save_analysis_result(feed_id, processor.junction_id, detections)
            
            except Exception as e:
                logger.error(f"Error processing frame in feed {feed_id}: {e}")
    
    def _save_analysis_result(self, feed_id: str, junction_id: str, detections: Dict):
        """Save analysis results to database"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute("""
                INSERT INTO traffic_analysis_results 
                (junction_id, feed_id, analysis_timestamp, vehicle_count, vehicle_types)
                VALUES (%s, %s, NOW(), %s, %s)
            """, (junction_id, feed_id, detections['vehicle_count'], 
                  str(detections['vehicle_types'])))
            
            self.db_connection.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Error saving analysis result: {e}")
    
    def get_feed_results(self, feed_id: str) -> Dict:
        """Get latest results for a feed"""
        return self.analysis_results.get(feed_id, {})
    
    def stop_feed(self, feed_id: str):
        """Stop processing a feed"""
        if feed_id in self.active_processors:
            self.active_processors[feed_id].stop_processing()
            del self.active_processors[feed_id]
