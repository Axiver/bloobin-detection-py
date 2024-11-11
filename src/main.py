# Import dependencies
from gpiozero import DistanceSensor
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
  sensor = DistanceSensor(trigger=23, echo=24, threshold_distance=THRESHOLD_DISTANCE)
  sensor.when_activated = lambda: print(f"Activated; Distance: {sensor.distance * 100} cm")
  sensor.when_deactivated = lambda: print(f"Deactivated; Distance: {sensor.distance * 100} cm")

main()