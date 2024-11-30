# Import dependencies
from libs.receptacle import countdown_receptacle
from picamera2 import Picamera2, Preview
from libcamera import controls
from time import sleep
from io import BytesIO
import os, time, asyncio

# 
# GPIO Mappings
# Ultrasonic Sensor - Trigger: 23, Echo: 24
# Motor - IN1: 22, IN2: 27
# 

# Set log levels
os.environ["LIBCAMERA_LOG_LEVELS"] = "3" # Configure libcamera to only log errors

# Functions
# Save image to disk
def save_image(imageJpeg, filename):
  with open(f"photobooth/{filename}.jpg", "wb") as image_file:
    image_file.write(imageJpeg)

## Initialise sensors
def init_sensors():
  global camera

  # Initialise sensors
  print("Initialising camera...")

  # Initialise the camera
  camera = Picamera2()
  config = camera.create_still_configuration(main={"size": (4608, 2592)}, display="main")
  camera.configure(config)
  camera.start_preview(Preview.QT)
  camera.start()
  camera.set_controls({"AfMode": controls.AfModeEnum.Continuous, "AfRange": controls.AfRangeEnum.Macro, "AfSpeed": controls.AfSpeedEnum.Fast})
  
  # Sleep for 2 seconds to allow the camera to warm up
  sleep(2)
  print("Sensors initialised")
  print(f"RizzCycle photobooth READYYYY ✨✨✨")

## Capture image
def captureImage():
  print("Capturing image...")
  # Initialise a image data buffer and capture an image
  data = BytesIO()
  camera.capture_file(data, format='jpeg')
  print("Image captured")
  return data

## Start a photobooth cycle
def photoBoothStart():
  # Toggle the receptacle to open and close twice (4 movements in total)
  countdown_receptacle(4, "Papparazzi 📸📸📸 INCOMING")

  # Capture and send the image
  imageJpeg = captureImage()

  # Save the image to disk with the result
  print("Saving image to disk")
  currentTime = time.time()
  save_image(imageJpeg, f"{currentTime}")


## Main
async def main():
  # Initialise sensors
  init_sensors()

  # Start the photobooth cycle on a loop
  while True:
    photoBoothStart()
    await asyncio.sleep(2)

asyncio.run(main())