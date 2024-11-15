# Import dependencies
from gpiozero import DistanceSensor
from libs.gptApi import is_recyclable
from libs.receptacle import open_receptacle, close_receptacle
from picamera2 import Picamera2, Preview
from libcamera import controls
from time import sleep
from io import BytesIO
import os, base64
from dotenv import load_dotenv

# 
# GPIO Mappings
# Ultrasonic Sensor - Trigger: 23, Echo: 24
# Motor - IN1: 22, IN2: 27
# 

# Constants
THRESHOLD_DISTANCE = 40; # in cm

# Load bin mode
load_dotenv(verbose=True, override=True)
BIN_MODE = os.environ.get("BIN_MODE").upper()

# Set log levels
os.environ["LIBCAMERA_LOG_LEVELS"] = "3" # Configure libcamera to only log errors

# Functions
# Encode file to base64
def base64_encode(image):
  return base64.b64encode(image).decode("utf-8")

## Initialise sensors
def init_sensors():
  global sensor, camera

  # Initialise sensors
  print("Initialising sensors")

  # Create a new ultrasonic sensor
  sensor = DistanceSensor(trigger=23, echo=24, threshold_distance=THRESHOLD_DISTANCE / 100)

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
  print(f"RizzCycle ready to gobble up {BIN_MODE} trash")

## Capture image
def captureImage():
  print("Capturing image")
  # Initialise a image data buffer and capture an image
  data = BytesIO()
  camera.capture_file(data, format='jpeg')
  print("Image captured")
  return data

## Main
def main():
  # Initialise sensors
  init_sensors()
  isBusy = False # Flag to indicate if the bin is busy

  # Only run the loop if the bin is not busy
  while not isBusy:
    # print(f"Distance: {sensor.distance * 100} cm")

    # Check if the distance is within the threshold distance
    if (sensor.distance < THRESHOLD_DISTANCE / 100):
      print("Within threshold distance")
      isBusy = True # Set the bin to busy
      imageData = captureImage()

      # Convert the image data to a base64 string
      print("Converting image to base64")
      imageBase64 = base64_encode(imageData.getvalue())

      # Send the image to the GPT API
      print("Sending image to GPT API")
      canBeRecycled = is_recyclable(imageBase64, BIN_MODE)
      print(f"Can be recycled: {canBeRecycled}")

      # Reset the flag
      isBusy = False

      # Check if the item can be recycled
      if canBeRecycled:
        # Open the receptacle
        open_receptacle()
        sleep(3)

        # Close the receptacle
        close_receptacle()

      # else:
        # Close the receptacle
        # close_receptacle()

    else:
      # Sleep for 1s
      sleep(1)

main()