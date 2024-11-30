from gpiozero import Motor
from time import sleep, time
import asyncio, random

# 
# GPIO Mappings
# Ultrasonic Sensor - Trigger: 23, Echo: 24
# Motor - IN1: 22, IN2: 27
# 

# Constants
MAX_DISTANCE = 0.5 # Maximum distance the motor can travel (in seconds)

# Global variables
distance_travelled = 0 # Distance travelled by the motor from the close position (in seconds)
start_time = None # Start time of the motor (in seconds) (used to calculate distance travelled)
direction = "" # Direction of the motor (forward or backward) (used to calculate distance travelled)
currentProcess = None

# Initialise the motor
motor = Motor(22, 27)

# Functions
# Calculates the distance travelled by the motor, and updates the distance_travelled variable
def update_distance():
  global distance_travelled, start_time, direction

  print(f"Updating distance travelled: {distance_travelled}, start time: {start_time}, direction: {direction}")

  # Check if the motor was moving
  if start_time == None or direction == "":
    return # Motor was not moving

  # Calculate the time taken to move the motor
  end_time = time()
  time_taken = end_time - start_time

  # Calculate the distance travelled by the motor
  if direction == "open":
    distance_travelled = min(MAX_DISTANCE, distance_travelled + time_taken) # Limit the distance to the maximum distance
    print(f"Open calculation: {distance_travelled + time_taken}")
  elif direction == "close":
    distance_travelled = max(0, distance_travelled - time_taken) # Limit the distance to 0
    print(f"Close calculation: {distance_travelled - time_taken}")

  print(f"Distance travelled: {distance_travelled}")

  # Reset the start time and direction
  start_time = None
  direction = ""

# Move the motor
def move_motor(_direction, duration):
  global start_time, direction

  print(f"Moving motor {_direction} for {duration} seconds")

  # Move the motor
  if _direction == "open":
    motor.backward()
  elif _direction == "close":
    motor.forward()

  # Set the start time and direction
  start_time = time()
  direction = _direction

  # Wait for the motor to move
  sleep(duration)

  # Stop the motor
  motor.stop()

# Clear any previous movement
def clearPreviousMovement():
  print("Clearing previous movement")

  # Stops the motor
  motor.stop()

  # Update the distance travelled
  update_distance()

# Open the receptacle
def open_receptacle():
  # Stop any existing motor movement
  clearPreviousMovement()

  global distance_travelled

  print(f"Opening receptacle, distance travelled: {distance_travelled}")

  # Check if the motor has already travelled the maximum distance
  if distance_travelled >= MAX_DISTANCE:
    return
  
  # Determine the amount of distance to travel
  distance_to_travel = MAX_DISTANCE - distance_travelled

  # Open the receptacle
  move_motor("open", distance_to_travel)

# Close the receptacle
def close_receptacle():
  # Stop any existing motor movement
  clearPreviousMovement()

  global distance_travelled

  print(f"Closing receptacle, distance travelled: {distance_travelled}")

  # Check if the motor has already reached the closed position
  if distance_travelled <= 0:
    return
  
  # Determine the amount of distance to travel
  distance_to_travel = distance_travelled

  # Close the receptacle
  move_motor("close", distance_to_travel)

# Use the receptacle as a countdown
async def countdown_receptacle(seconds, action):
  # Generate a random number
  random_number = random.randint(0, 9999)

  # Set the current process
  global currentProcess
  currentProcess = random_number

  # Perform the specified number of times
  for i in range(seconds):
    # Check if this is still the current process
    if currentProcess != random_number:
      print(f"[{random_number}] Process interrupted")
      return
    
    # It is still the current process
    # Open the receptacle if the index is odd
    if (i % 2 != 0):
      # Open the receptacle
      print(f"[{random_number}] {action} in {seconds - i} (Opening)")
      open_receptacle()
      await asyncio.sleep(1)

    if (i % 2 == 0):
      # Close the receptacle
      print(f"[{random_number}] {action} in {seconds - i} (Closing)")
      close_receptacle()
      await asyncio.sleep(1)

# Toggle the receptacle
async def toggle_receptacle():
  # Generate a random number
  random_number = random.randint(0, 9999)

  # Set the current process
  global currentProcess
  currentProcess = random_number

  # Open the receptacle
  print(f"[{random_number}] Opening receptacle")
  open_receptacle()
  await asyncio.sleep(3)

  # Check if this is still the current process
  if currentProcess != random_number:
    print(f"[{random_number}] Process interrupted")
    return

  # It is still the current process
  # Close the receptacle
  print(f"[{random_number}] Closing receptacle")
  close_receptacle()

# Initialises the motor by travelling to the closed position
def init_motor():
  motor.forward()
  sleep(0.1)
  motor.stop()