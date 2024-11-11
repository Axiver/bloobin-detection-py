# Import dependencies
from gpiozero import DistanceSensor
from signal import pause
from time import sleep

# 
# GPIO Mappings
# Ultrasonic Sensor - Trigger: 23, Echo: 24
# 

# Constants
THRESHOLD_DISTANCE = 40; # in cm

# Functions
## Main
def main():
  # Create a new ultrasonic sensor
  sensor = DistanceSensor(trigger=23, echo=24, threshold_distance=THRESHOLD_DISTANCE / 100)

  while True:
    # Check if the distance is within the threshold distance
    if (sensor.distance < THRESHOLD_DISTANCE / 100):
      print("Within threshold distance")

    print(f"Distance: {sensor.distance * 100} cm")
    # Sleep for 10ms
    sleep(0.01)

main()