from picamera2 import Picamera2, Preview
from libcamera import controls
from io import BytesIO

## Initialise the camera
def init_camera():
  # Initialise the camera
  camera = Picamera2()
  config = camera.create_still_configuration(main={"size": (4608, 2592)}, display="main")
  camera.configure(config)
  camera.start_preview(Preview.QT)
  camera.start()
  camera.set_controls({"AfMode": controls.AfModeEnum.Continuous, "AfRange": controls.AfRangeEnum.Macro, "AfSpeed": controls.AfSpeedEnum.Fast})

## Capture image
def captureImage(camera):
  print("Capturing image...")
  # Initialise a image data buffer and capture an image
  data = BytesIO()
  camera.capture_file(data, format='jpeg')
  print("Image captured")
  return data