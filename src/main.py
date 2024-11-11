# Import dependencies
from gpiozero import DistanceSensor
from picamera2 import Picamera2
from time import sleep

# 
# GPIO Mappings
# Ultrasonic Sensor - Trigger: 23, Echo: 24
# 

# Constants
THRESHOLD_DISTANCE = 40; # in cm

# Functions
## Initialise sensors
def initSensors():
  global sensor, camera

  # Initialise sensors
  print("Initialising sensors")

  # Create a new ultrasonic sensor
  sensor = DistanceSensor(trigger=23, echo=24, threshold_distance=THRESHOLD_DISTANCE / 100)

  # Initialise the camera
  camera = Picamera2()
  
  # Sleep for 2 seconds to allow the camera to warm up
  sleep(2)
  print("Sensors initialised")

## Capture image
def captureImage():
  print("Capturing image")
  # Capture an image
  camera.capture('./images/test.jpg')
  print("Image captured")

## Main
def main():
  # Initialise sensors
  initSensors()

  while True:
    # Check if the distance is within the threshold distance
    if (sensor.distance < THRESHOLD_DISTANCE / 100):
      print("Within threshold distance")
      captureImage()

    print(f"Distance: {sensor.distance * 100} cm")
    # Sleep for 10ms
    sleep(0.01)

main()