from gpiozero import Motor
from time import sleep, time

# 
# GPIO Mappings
# Ultrasonic Sensor - Trigger: 23, Echo: 24
# Motor - IN1: 22, IN2: 27
# 

# Global variables
distance_travelled = 0 # Distance travelled by the motor from the close position (in seconds)
start_time = 0 # Start time of the motor (in seconds) (used to calculate distance travelled)
direction = "" # Direction of the motor (forward or backward) (used to calculate distance travelled)

# Initialise the motor
motor = Motor(22, 27)

# Functions
# Calculates the distance travelled by the motor, and updates the distance_travelled variable
def update_distance():
  global distance_travelled, start_time, direction

  # Check if the motor was moving
  if start_time == 0 or direction == "":
    return # Motor was not moving

  # Calculate the time taken to move the motor
  end_time = time()
  time_taken = end_time - start_time

  # Calculate the distance travelled by the motor
  if direction == "forward":
    distance_travelled += time_taken
  elif direction == "backward":
    distance_travelled -= time_taken

  # Reset the start time and direction
  start_time = 0
  direction = ""

# Move the motor
def move_motor(_direction, duration):
  global start_time, direction

  # Update the distance travelled by the motor
  update_distance()

  # Move the motor
  if direction == "forward":
    motor.forward()
  elif direction == "backward":
    motor.backward()

  # Set the start time and direction
  start_time = time()
  direction = direction

  # Wait for the motor to move
  sleep(duration)

  # Stop the motor
  motor.stop()

# Open the receptacle
def open_receptacle():
  # Stop any existing motor movement
  motor.stop()

  # Update the distance travelled by the motor
  # update_distance()

  motor.backward()
  sleep(0.5)
  motor.stop()

# Close the receptacle
def close_receptacle():
  motor.stop()
  motor.forward()
  sleep(0.45)
  motor.stop()

# Initialises the motor by travelling to the closed position
def init_motor():
  motor.forward()
  sleep(0.1)
  motor.stop()