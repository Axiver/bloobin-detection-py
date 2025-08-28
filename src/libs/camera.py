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
    puts av.Packet objects onto an asyncio.Queue for consumption.
    """
    def __init__(self, queue, loop):
        super().__init__()
        self.queue = queue
        self.loop = loop
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
            self.loop.call_soon_threadsafe(self.queue.put_nowait, pkt)
            self.frame_index += 1
        except Exception:
            import traceback
            traceback.print_exc()

"""
Custom MediaStreamTrack for Picamera2
"""
class PiCameraStream(MediaStreamTrack):
    """
    A MediaStreamTrack that yields already-encoded av.Packet (H.264) for passthrough.
    Run server with: --play-without-decoding --video-codec video/H264
    """
    kind = "video"

    def __init__(self, size=(1920, 1080), bitrate=10_000_000):
        super().__init__()  # initialize MediaStreamTrack
        # capture current running loop (important: Picamera callback runs in another thread)
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            # if called outside an event loop, fall back (shouldn't happen in aiohttp handler)
            self.loop = asyncio.get_event_loop()

        self.picam2 = Picamera2()

        # Use an encoder-friendly format and resolution.
        # YUV420 (YUV420) is commonly supported by hardware encoders.
        # Prefer common sizes (1280x720, 1920x1080) — avoid sensor-native odd formats.
        video_config = self.picam2.create_video_configuration(
            main={"size": size, "format": "YUV420"},
            encode="main",
        )
        self.picam2.configure(video_config)

        # Create encoder with a sane bitrate
        self.encoder = H264Encoder(bitrate)
        self.queue = asyncio.Queue()

        # Start recording to our QueueOutput which will push av.Packet into asyncio queue.
        self.picam2.start_recording(self.encoder, QueueOutput(self.queue, self.loop))

        # track running state
        self._stopped = False

    async def recv(self):
        """
        Return an av.Packet (encoded H264) for passthrough.
        aiortc will accept av.Packet from recv() if configured to use encoded mode.
        """
        if self._stopped:
            raise asyncio.CancelledError()

        packet: av.Packet = await self.queue.get()

        # aiortc expects packet objects; ensure they have pts and time_base if possible.
        # Some aiortc versions expect packet.pts to be in stream time_base units (e.g. 1/90000).
        # If your consumer complains, you may convert pts to 90kHz clock:
        #   if hasattr(packet, "pts") and hasattr(packet, "time_base"):
        #       packet.pts = int(packet.pts * (90_000 * packet.time_base))
        return packet

    def stop(self):
        """
        Stop Picamera2 and encoder cleanly.
        """
        if self._stopped:
            return
        self._stopped = True
        try:
            # stop_recording may raise if already stopped - ignore
            self.picam2.stop_recording()
        except Exception:
            pass
        try:
            self.picam2.close()
        except Exception:
            pass
        # also stop MediaStreamTrack base
        try:
            super().stop()
        except Exception:
            pass

