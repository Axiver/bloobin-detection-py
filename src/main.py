# Import dependencies
from gpiozero import DistanceSensor
from libs.gptApi import is_recyclable
from libs.receptacle import toggle_receptacle
from libs.camera import captureImage, init_camera, PiCameraStream
from libs.videoStream import start_stream
from libs.qrcode_handler import QRCodeDetector
from libs.socket_server import WebSocketServer
from time import sleep
import os, base64, asyncio
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
  print("Initialising sensors...")

  # Create a new ultrasonic sensor
  sensor = DistanceSensor(trigger=23, echo=24, threshold_distance=THRESHOLD_DISTANCE / 100)

  # Initialise the camera
  # camera = init_camera()
  
  # Sleep for 2 seconds to allow the camera to warm up
  sleep(2)
  print("Sensors initialised")
  print(f"RizzCycle ready to gobble up {BIN_MODE} trash")

## Process the detected object
async def processObject():
  global isBusy

  try:
    # Capture and send the image
    image = captureImage(camera)

    # Encode the image to base64
    imageBase64 = base64_encode(image.getvalue())

    print("Sending image to GPT API...")
    canBeRecycled = is_recyclable(imageBase64, BIN_MODE)

    print(f"Can be recycled: {canBeRecycled}")

    # Act based on recyclability
    if canBeRecycled:
      asyncio.create_task(toggle_receptacle())

  finally:
    isBusy = False # Allow detection to process new objects

## Checks for object in front of the sensor
async def checkObject():
  global isBusy
  isBusy = False

  while True:
    if sensor.distance < THRESHOLD_DISTANCE / 100:
      print("Object detected within threshold distance")

      if not isBusy:
          isBusy = True # Prevent multiple simultaneous processing
          # asyncio.create_task(processObject())
    # else:
      # print("No object detected. Sleeping...")
    
    await asyncio.sleep(1)

async def handle_qr_codes(qr_codes: list[str]):
  global websocket_server
  print(f"QR codes detected: {qr_codes}")
  await websocket_server.broadcast_message({
    "type": "qr_codes",
    "data": qr_codes
  })

async def start_qr_scanning():
  global qr_detector
  asyncio.create_task(qr_detector.start_qr_scanning(handle_qr_codes)) # Start the QR code scanning in a new thread

async def stop_qr_scanning():
  global qr_detector
  qr_detector.stop_qr_scanning()

## Main
async def main():
  global qr_detector, websocket_server

  # Initialise sensors
  init_sensors()

  # Initialise the camera
  picam_stream = PiCameraStream()

  # Start the WebRTC server
  start_stream(stream_args={"play_without_decoding": True, "video_codec": "video/H264"}, threaded=True, stream=picam_stream)

  # Initialise the QR code detector
  qr_detector = QRCodeDetector(picam_stream)

  # Start the WebSocket server
  websocket_server = WebSocketServer(start_qr_scanning=start_qr_scanning, stop_qr_scanning=stop_qr_scanning)
  await websocket_server.start_server()
  # asyncio.create_task(websocket_server.keep_alive())

  # Check if there is an object in front of the sensor
  await checkObject()

asyncio.run(main())