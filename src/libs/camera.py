from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from libcamera import controls
from io import BytesIO
import time
import socket

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
def test_function():
  picam2 = Picamera2()
  half_resolution = [dim // 2 for dim in picam2.sensor_resolution]
  main_stream = {"size": half_resolution}
  lores_stream = {"size": (640, 480)}
  video_config = picam2.create_video_configuration(main_stream, encode="main", display="main")
  picam2.configure(video_config)

  encoder = H264Encoder(10000000)

  with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.connect(("REMOTEIP", 10001))
    stream = sock.makefile("wb")
    picam2.start_recording(encoder, FileOutput(stream))

    time.sleep(5)

    # It's better to capture the still in this thread, not in the one driving the camera.
    request = picam2.capture_request()
    request.save("main", "test.jpg")
    request.release()
    print("Still image captured!")

    time.sleep(20)

