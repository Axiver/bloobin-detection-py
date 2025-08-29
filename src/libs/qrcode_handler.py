import cv2
from pyzbar.pyzbar import decode
from typing import Callable

class QRCodeDetector:
  def __init__(self, picam_stream):
      self.picam_stream = picam_stream
      self.scanning = False

  def detect_qr_codes(self, frame):
    """
    Detect QR codes in a YUV420 frame from picamera2.
    :param frame: numpy array (Y plane from YUV420)
    :return: list of detected QR codes
    """
    if frame is None:
      return []

    # If frame is multi-plane (YUV420 stacked), extract just the Y channel
    if len(frame.shape) == 3 and frame.shape[2] > 1:
      # Some configurations give shape (H, W, 3) but with Y,U,V packed
      gray_frame = frame[:, :, 0]  
    else:
      # Already single-channel (Y only)
      gray_frame = frame

    qr_codes = decode(gray_frame)
    return qr_codes


  def extract_qr_data(self, qr_codes):
    """
    Extract and print data from detected QR codes.
    """
    results = []
    if qr_codes:
      for qr_code in qr_codes:
        qr_data = qr_code.data.decode("utf-8")
        results.append(qr_data)
    return results

  def process_frame(self, frame):
    """
    Convenience function to process a single frame.
    :param frame: numpy array from picamera2
    :return: list of decoded QR code strings
    """
    qr_codes = self.detect_qr_codes(frame)
    return self.extract_qr_data(qr_codes)

  async def start_qr_scanning(self, callback: Callable[[str], None]):
    self.scanning = True
    while self.scanning is True:
      frame = self.picam_stream.capture_array()  # numpy array
      qr_codes = self.process_frame(frame)
      if len(qr_codes) > 0:
        await callback(qr_codes)

  async def stop_qr_scanning(self):
    self.scanning = False