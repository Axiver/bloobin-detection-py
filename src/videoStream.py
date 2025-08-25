import os
import asyncio
import json
import logging
from typing import Optional
import numpy as np
import cv2
from aiohttp import web
from aiohttp.web import Request, Response
from av import VideoFrame, CodecContext, Packet
from fractions import Fraction
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.rtcrtpsender import RTCRtpSender
from aiortc.contrib.media import MediaRelay

# Picamera2 imports
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration constants
WIDTH = 1920
HEIGHT = 1080
FPS = 15
TARGET_BITRATE_BPS = 10_000_000  # 10 Mbps for high quality

class Picamera2VideoTrack(VideoStreamTrack):
    """
    VideoStreamTrack that streams video directly from picamera2
    """
    
    def __init__(self, picam2: Picamera2):
        super().__init__()
        self.picam2 = picam2
        self.frame_count = 0
        
        # Configure camera for H.264 streaming
        self._configure_camera()
        
    def _configure_camera(self):
        """Configure picamera2 for video streaming"""
        try:
            # Create video configuration
            video_config = self.picam2.create_video_configuration(
                main={"size": (WIDTH, HEIGHT), "format": "RGB888"},
                controls={"FrameDurationLimits": (int(1000000/FPS), int(1000000/FPS))}
            )
            
            # Apply configuration
            self.picam2.configure(video_config)
            
            # Start camera
            self.picam2.start()
            
            logger.info(f"Camera started at {WIDTH}x{HEIGHT}, {FPS} FPS")
            
        except Exception as e:
            logger.error(f"Failed to configure camera: {e}")
            raise
    
    async def recv(self):
        """Get the next video frame from picamera2"""
        try:
            # Capture raw frame from picamera2
            frame = self.picam2.capture_array()
            
            # Convert BGR to RGB (picamera2 returns BGR)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create VideoFrame for aiortc
            video_frame = VideoFrame.from_ndarray(
                frame_rgb, 
                format="rgb24"
            )
            
            # Set frame metadata
            video_frame.pts = self.frame_count
            video_frame.time_base = Fraction(1, FPS)
            
            self.frame_count += 1
            
            return video_frame
            
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            # Return a black frame as fallback
            black_frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            video_frame = VideoFrame.from_ndarray(black_frame, format="rgb24")
            video_frame.pts = self.frame_count
            video_frame.time_base = Fraction(1, FPS)
            self.frame_count += 1
            return video_frame

class WebRTCServer:
    """
    WebRTC server that handles peer connections and streams H.264 video from picamera2
    """
    
    def __init__(self):
        self.pc: Optional[RTCPeerConnection] = None
        self.video_track: Optional[Picamera2VideoTrack] = None
        self.picam2: Optional[Picamera2] = None
        self.relay = MediaRelay()
        
    async def initialize_camera(self):
        """Initialize picamera2 camera"""
        try:
            self.picam2 = Picamera2()
            self.video_track = Picamera2VideoTrack(self.picam2)
            logger.info("Camera initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize camera: {e}")
            raise
    
    async def create_peer_connection(self):
        """Create and configure RTCPeerConnection"""
        if self.pc:
            await self.pc.close()
        
        self.pc = RTCPeerConnection()
        
        # Add video track
        if self.video_track:
            sender = self.pc.addTrack(self.video_track)
            
            # Configure video encoding parameters for H.264
            if hasattr(sender, 'setParameters'):
                params = sender.getParameters()
                if params.encodings:
                    params.encodings[0].maxBitrate = TARGET_BITRATE_BPS
                    params.encodings[0].maxFramerate = FPS
                    sender.setParameters(params)
        
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state: {self.pc.connectionState}")
            if self.pc.connectionState == "failed":
                await self.pc.close()
                self.pc = None
        
        @self.pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"ICE connection state: {self.pc.iceConnectionState}")
        
        @self.pc.on("track")
        def on_track(track):
            logger.info(f"Track {track.kind} received")
        
        return self.pc
    
    async def offer_handler(self, request: Request) -> Response:
        """Handle WebRTC offer from client"""
        try:
            params = await request.json()
            offer = RTCSessionDescription(
                sdp=params["sdp"],
                type=params["type"]
            )
            
            # Create peer connection
            pc = await self.create_peer_connection()
            
            # Set remote description
            await pc.setRemoteDescription(offer)
            
            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            return web.json_response({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            })
            
        except Exception as e:
            logger.error(f"Error handling offer: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def health_check(self, request: Request) -> Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "camera": "initialized" if self.picam2 else "not_initialized",
            "encoding": "RGB",
            "resolution": f"{WIDTH}x{HEIGHT}",
            "fps": FPS
        })
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.pc:
            await self.pc.close()
            self.pc = None
        
        if self.picam2:
            self.picam2.close()
            self.picam2 = None
        
        if self.video_track:
            self.video_track = None

async def create_app():
    """Create and configure the web application"""
    app = web.Application()
    
    # Create WebRTC server instance
    webrtc_server = WebRTCServer()
    
    # Initialize camera
    await webrtc_server.initialize_camera()
    
    # Add CORS middleware
    async def cors_middleware(app, handler):
        async def middleware(request):
            if request.method == 'OPTIONS':
                response = web.Response()
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
                return response
            else:
                response = await handler(request)
                response.headers['Access-Control-Allow-Origin'] = '*'
                return response
        return middleware
    
    app.middlewares.append(cors_middleware)
    
    # Add routes
    app.router.add_post("/offer", webrtc_server.offer_handler)
    app.router.add_get("/health", webrtc_server.health_check)
    
    # Add static files for the client
    app.router.add_static("/static", path="./static", name="static")
    
    # Store server instance in app for cleanup
    app["webrtc_server"] = webrtc_server
    
    # Add cleanup on shutdown
    async def on_shutdown(app):
        await webrtc_server.cleanup()
    
    app.on_shutdown.append(on_shutdown)
    
    return app

def main():
    """Main entry point"""
    try:
        # Create and run the application
        app = asyncio.run(create_app())
        
        # Run the server
        web.run_app(
            app,
            host="0.0.0.0",
            port=8080,
            access_log=logger
        )
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    main()

  