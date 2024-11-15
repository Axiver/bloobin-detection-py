from gpiozero import Motor
from time import sleep

# Initialise the motor
motor = Motor(22, 27)

# Functions
# Move the motor
def move_motor(direction, end_early):
  # Calculate how long the motor should move for
  duration = 0.9 if end_early else 1

  if direction == "forward":
    print(f"Moving motor forward for {duration}s")
    motor.forward()
    sleep(duration)
    print("Motor moved forward")
    
    # Stop the motor
    print("Stopping motor")
    motor.stop()
    print("Motor stopped")
  elif direction == "backward":
    # Move the motor backward
    print(f"Moving motor backward for {duration}s")
    motor.backward()
    sleep(duration)
    print("Motor moved backward")

    # Stop the motor
    print("Stopping motor")
    motor.stop()
    print("Motor stopped")
  else:
    motor.stop()

def toggle_motor(iterations):
  print("Toggling motor")

  # Toggle the motor x times
  for i in range(iterations):
    # Determine whether to move the motor forward or backward
    direction = "forward" if i % 2 == 0 else "backward"
    move_motor(direction, i == iterations - 1)
    print(f"Motor toggled {(i + 1 / 2)} times")

# toggle_motor(10) # Toggle the motor 10 times

motor.forward()
sleep(0.45)
motor.stop()
# motor.backward()
# sleep(0.5)
# motor.stop()