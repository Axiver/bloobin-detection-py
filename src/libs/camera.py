from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from picamera2.outputs import Output
from libcamera import controls
from io import BytesIO
import time
import av
import asyncio
from fractions import Fraction
from aiortc import MediaStreamTrack
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, TimeoutError

## Initialise the camera
def init_camera():
  # Initialise the camera
  camera = Picamera2()
  config = camera.create_still_configuration(main={"size": (4608, 2592)}, display="main")
  camera.configure(config)
  camera.start_preview(Preview.QT)
  camera.start()
  camera.set_controls({"AfMode": controls.AfModeEnum.Continuous, "AfRange": controls.AfRangeEnum.Macro, "AfSpeed": controls.AfSpeedEnum.Fast})
  return camera

## Capture image
def captureImage(camera):
  print("Capturing image...")
  # Initialise a image data buffer and capture an image
  data = BytesIO()
  camera.capture_file(data, format='jpeg')
  print("Image captured")
  return data

# Encode a VGA stream, and capture a higher resolution still image half way through.
# def test_function():
#   picam2 = Picamera2()
#   half_resolution = [dim // 2 for dim in picam2.sensor_resolution]
#   main_stream = {"size": half_resolution}
#   lores_stream = {"size": (640, 480)}
#   video_config = picam2.create_video_configuration(main_stream, encode="main", display="main")
#   picam2.configure(video_config)

#   encoder = H264Encoder(10000000)

#   with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
#     sock.connect(("REMOTEIP", 10001))
#     stream = sock.makefile("wb")
#     picam2.start_recording(encoder, FileOutput(stream))

#     time.sleep(5)

#     # It's better to capture the still in this thread, not in the one driving the camera.
#     request = picam2.capture_request()
#     request.save("main", "test.jpg")
#     request.release()
#     print("Still image captured!")

#     time.sleep(20)


"""
Custom aiortc-compatible output for Picamera2
"""
class QueueOutput(Output):
    """
    Picamera2 Output that receives encoded H264 frames (bytes) and
    puts av.Packet objects onto a thread-safe queue for consumption.
    """
    def __init__(self, queue, loop=None):
        super().__init__()
        self.queue = queue
        self.loop = loop  # Keep for backward compatibility but not required
        self.frame_index = 0

    def outputframe(self, frame: bytes, keyframe=True, timestamp=None, packet=None, audio=None):
        """
        Called by Picamera2/encoder on each encoded frame.
        Signature must match encoder expectations: (frame, keyframe, timestamp, packet, audio).
        """
        try:
            pkt = av.Packet(frame)

            # attach PTS if available
            if timestamp is not None:
                # timestamp in microseconds -> 90 kHz clock units
                pkt.pts = int(timestamp * 90 / 1000)
            else:
                # fallback: current time in µs -> 90 kHz
                pts = int(time.time_ns() // 1000)
                pkt.pts = int(pts * 90 / 1000)

            pkt.time_base = Fraction(1, 90000)  # WebRTC expects 90kHz timebase
            
            # Put packet in the thread-safe queue
            # Use put_nowait to avoid blocking the encoder thread
            try:
                self.queue.put_nowait(pkt)
                self.frame_index += 1
            except queue.Full:
                # Queue is full, drop the oldest frame to make room
                try:
                    self.queue.get_nowait()  # Remove oldest
                    self.queue.put_nowait(pkt)  # Add new
                    self.frame_index += 1
                except queue.Empty:
                    # Queue was emptied by another thread, just add the new frame
                    self.queue.put_nowait(pkt)
                    self.frame_index += 1
                    
        except Exception as e:
            import traceback
            print(f"Error in QueueOutput.outputframe: {e}")
            traceback.print_exc()

"""
Custom MediaStreamTrack for Picamera2 with thread-safe access
"""
class PiCameraStream(MediaStreamTrack):
    """
    A MediaStreamTrack that yields already-encoded av.Packet (H.264) for passthrough.
    Provides thread-safe access to PiCamera operations using ThreadPoolExecutor.
    Run server with: --play-without-decoding --video-codec video/H264
    """
    kind = "video"

    def __init__(self, size=(1920, 1080), bitrate=10_000_000):
        super().__init__()
        
        # Store the thread ID where this instance was created (main thread)
        self._main_thread_id = threading.current_thread().ident
        
        # Thread pool executor for PiCamera operations from other threads
        # Single worker ensures operations are serialized and thread-safe
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PiCameraExecutor")
        
        # Thread-safe queue for H.264 encoded frames
        self.queue = queue.Queue(maxsize=30)  # Limit buffer to prevent memory issues
        
        # Threading lock for thread-safe operations
        self._lock = threading.Lock()
        
        # Camera initialization (must happen in main thread)
        self.picam2 = Picamera2()
        
        # Use an encoder-friendly format and resolution
        video_config = self.picam2.create_video_configuration(
            main={"size": (4608, 2592)},
            lores={"size": size, "format": "YUV420"},
            encode="lores",
        )
        self.picam2.configure(video_config)
        
        # Create encoder with specified bitrate
        self.encoder = H264Encoder(bitrate)
        
        # Start recording to our QueueOutput
        # Note: We don't bind to a specific event loop here
        self.picam2.start_recording(self.encoder, QueueOutput(self.queue, None))
        
        print("PiCameraStream initialized with thread-safe access")
        
        # Track running state
        self._stopped = False

    async def recv(self):
        """
        Return an av.Packet (encoded H264) for passthrough.
        aiortc will accept av.Packet from recv() if configured to use encoded mode.
        """
        if self._stopped:
            raise asyncio.CancelledError()

        try:
            # Use run_in_executor to avoid blocking the event loop
            # This converts the blocking queue.get() to an async operation
            current_loop = asyncio.get_running_loop()
            packet = await current_loop.run_in_executor(
                None, 
                lambda: self.queue.get(timeout=1.0)
            )
            return packet
        except queue.Empty:
            # Queue timeout - this is normal and expected
            raise asyncio.CancelledError()
        except Exception as e:
            print(f"Error in recv(): {e}")
            raise asyncio.CancelledError()

    def capture_array(self):
        """
        Thread-safe access to capture_array from any thread.
        Uses ThreadPoolExecutor to ensure PiCamera operations happen in the main thread.
        """
        if threading.current_thread().ident == self._main_thread_id:
            # We're in the main thread, safe to call directly
            return self._capture_frame_direct()
        else:
            # We're in a different thread, use executor to call in main thread
            try:
                future = self._executor.submit(self._capture_frame_direct)
                # Use a reasonable timeout to prevent infinite blocking
                return future.result(timeout=5.0)
            except TimeoutError:
                print("Warning: capture_array() timed out after 5 seconds")
                return None
            except Exception as e:
                print(f"Error in capture_array(): {e}")
                return None

    def _capture_frame_direct(self):
        """
        Direct frame capture - only call from main thread or via executor.
        This is the actual PiCamera operation.
        """
        if self._stopped:
            raise RuntimeError("PiCameraStream is stopped")
        
        try:
            with self._lock:  # Ensure thread safety for camera operations
                return self.picam2.capture_array()
        except Exception as e:
            print(f"Error capturing frame: {e}")
            return None

    def capture_image(self):
        """
        Thread-safe access to capture_image from any thread.
        Returns a BytesIO object containing the captured image.
        """
        if threading.current_thread().ident == self._main_thread_id:
            # We're in the main thread, safe to call directly
            return self._capture_image_direct()
        else:
            # We're in a different thread, use executor
            try:
                future = self._executor.submit(self._capture_image_direct)
                return future.result(timeout=10.0)  # Longer timeout for image capture
            except TimeoutError:
                print("Warning: capture_image() timed out after 10 seconds")
                return None
            except Exception as e:
                print(f"Error in capture_image(): {e}")
                return None

    def _capture_image_direct(self):
        """
        Direct image capture - only call from main thread or via executor.
        """
        if self._stopped:
            raise RuntimeError("PiCameraStream is stopped")
        
        try:
            with self._lock:
                data = BytesIO()
                request = self.picam2.capture_request()
                # request.save("main", "test.jpg")
                request.save("main", data, format="jpeg")
                request.release()
                return data
        except Exception as e:
            print(f"Error capturing image: {e}")
            return None

    def get_camera_info(self):
        """
        Thread-safe access to camera information.
        """
        if threading.current_thread().ident == self._main_thread_id:
            return self._get_camera_info_direct()
        else:
            try:
                future = self._executor.submit(self._get_camera_info_direct)
                return future.result(timeout=2.0)
            except TimeoutError:
                print("Warning: get_camera_info() timed out")
                return None
            except Exception as e:
                print(f"Error in get_camera_info(): {e}")
                return None

    def _get_camera_info_direct(self):
        """
        Get camera information directly.
        """
        try:
            with self._lock:
                return {
                    'sensor_resolution': self.picam2.sensor_resolution,
                    'camera_controls': self.picam2.camera_controls,
                    'camera_config': self.picam2.camera_config
                }
        except Exception as e:
            print(f"Error getting camera info: {e}")
            return None

    def stop(self):
        """
        Stop PiCamera2 and encoder cleanly.
        Ensures proper cleanup of all resources including the executor.
        """
        if self._stopped:
            return
        
        self._stopped = True
        
        try:
            # Stop recording (may raise if already stopped - ignore)
            self.picam2.stop_recording()
        except Exception:
            pass
        
        try:
            # Close the camera
            self.picam2.close()
        except Exception:
            pass
        
        try:
            # Shutdown the executor gracefully
            self._executor.shutdown(wait=True, timeout=5.0)
        except Exception as e:
            print(f"Warning: Error shutting down executor: {e}")
        
        # Stop MediaStreamTrack base
        try:
            super().stop()
        except Exception:
            pass
        
        print("PiCameraStream stopped and cleaned up")

    def __del__(self):
        """
        Destructor to ensure cleanup if stop() is not called explicitly.
        """
        if not self._stopped:
            try:
                self.stop()
            except Exception:
                pass

