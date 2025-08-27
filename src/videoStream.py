import argparse
import asyncio
import json
import logging
import os
import platform
import ssl
import av
import time
from typing import Optional
from fractions import Fraction

from aiohttp import web
from aiortc import (
    MediaStreamTrack,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaPlayer, MediaRelay

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import Output

ROOT = os.path.dirname(__file__)

pcs = set()
relay = None
webcam = None


class QueueOutput(Output):
    """
    Picamera2 Output that receives encoded H264 frames (bytes) and
    puts av.Packet objects onto an asyncio.Queue for consumption.
    """
    def __init__(self, queue, loop):
        super().__init__()
        self.queue = queue
        self.loop = loop
        self.frame_index = 0

    def outputframe(self, frame: bytes, keyframe=True, timestamp=None, packet=None, audio=None):
        """
        Called by Picamera2/encoder on each encoded frame.
        Signature must match encoder expectations: (frame, keyframe, timestamp, packet, audio).
        """
        try:
            pkt = av.Packet(frame)

            # attach PTS if available
            if timestamp is not None:
                # timestamp in microseconds -> 90 kHz clock units
                pkt.pts = int(timestamp * 90 / 1000)
            else:
                # fallback: current time in µs -> 90 kHz
                pts = int(time.time_ns() // 1000)
                pkt.pts = int(pts * 90 / 1000)

            pkt.time_base = Fraction(1, 90000)  # WebRTC expects 90kHz timebase
            self.loop.call_soon_threadsafe(self.queue.put_nowait, pkt)
            self.frame_index += 1
        except Exception:
            import traceback
            traceback.print_exc()


class PiCameraStream(MediaStreamTrack):
    """
    A MediaStreamTrack that yields already-encoded av.Packet (H.264) for passthrough.
    Run server with: --play-without-decoding --video-codec video/H264
    """
    kind = "video"

    def __init__(self, size=(1280, 720), bitrate=4_000_000):
        super().__init__()  # initialize MediaStreamTrack
        # capture current running loop (important: Picamera callback runs in another thread)
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            # if called outside an event loop, fall back (shouldn't happen in aiohttp handler)
            self.loop = asyncio.get_event_loop()

        self.picam2 = Picamera2()

        # Use an encoder-friendly format and resolution.
        # YUV420 (YUV420) is commonly supported by hardware encoders.
        # Prefer common sizes (1280x720, 1920x1080) — avoid sensor-native odd formats.
        video_config = self.picam2.create_video_configuration(
            main={"size": size, "format": "YUV420"},
            encode="main",
        )
        self.picam2.configure(video_config)

        # Create encoder with a sane bitrate
        self.encoder = H264Encoder(bitrate)
        self.queue = asyncio.Queue()

        # Start recording to our QueueOutput which will push av.Packet into asyncio queue.
        self.picam2.start_recording(self.encoder, QueueOutput(self.queue, self.loop))

        # track running state
        self._stopped = False

    async def recv(self):
        """
        Return an av.Packet (encoded H264) for passthrough.
        aiortc will accept av.Packet from recv() if configured to use encoded mode.
        """
        if self._stopped:
            raise asyncio.CancelledError()

        packet: av.Packet = await self.queue.get()

        # aiortc expects packet objects; ensure they have pts and time_base if possible.
        # Some aiortc versions expect packet.pts to be in stream time_base units (e.g. 1/90000).
        # If your consumer complains, you may convert pts to 90kHz clock:
        #   if hasattr(packet, "pts") and hasattr(packet, "time_base"):
        #       packet.pts = int(packet.pts * (90_000 * packet.time_base))
        return packet

    def stop(self):
        """
        Stop Picamera2 and encoder cleanly.
        """
        if self._stopped:
            return
        self._stopped = True
        try:
            # stop_recording may raise if already stopped - ignore
            self.picam2.stop_recording()
        except Exception:
            pass
        try:
            self.picam2.close()
        except Exception:
            pass
        # also stop MediaStreamTrack base
        try:
            super().stop()
        except Exception:
            pass

def create_local_tracks() -> tuple[Optional[MediaStreamTrack], Optional[MediaStreamTrack]]:
    global relay, webcam

    # Play from the system's default webcam.
    #
    # In order to serve the same webcam to multiple users we make use of
    # a `MediaRelay`. The webcam will stay open, so it is our responsability
    # to stop the webcam when the application shuts down in `on_shutdown`.
    options = {"framerate": "30", "video_size": "640x480"}
    if relay is None:
        if platform.system() == "Windows":
            webcam = MediaPlayer(
                "video=JOYACCESS JA-Webcam", format="dshow", options=options
            )
            track = webcam  # already a MediaStreamTrack
        else:
            webcam = PiCameraStream()
            track = webcam  # already a MediaStreamTrack
        relay = MediaRelay()
    return None, relay.subscribe(track)


def force_codec(pc: RTCPeerConnection, sender: RTCRtpSender, forced_codec: str) -> None:
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


async def index(request: web.Request) -> web.Response:
    content = open(os.path.join(ROOT, "./static/index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def offer(request: web.Request) -> web.Response:
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        print("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    # open media source
    audio, video = create_local_tracks()

    if audio:
        audio_sender = pc.addTrack(audio)
        if args.audio_codec:
            force_codec(pc, audio_sender, args.audio_codec)
        elif args.play_without_decoding:
            raise Exception("You must specify the audio codec using --audio-codec")

    if video:
        video_sender = pc.addTrack(video)
        if args.video_codec:
            force_codec(pc, video_sender, args.video_codec)
        elif args.play_without_decoding:
            raise Exception("You must specify the video codec using --video-codec")

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app: web.Application) -> None:
    # Close peer connections.
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

    # If a shared webcam was opened, stop it.
    if webcam is not None:
        if isinstance(webcam, MediaPlayer):
            if webcam.video:
                webcam.video.stop()
            if webcam.audio:
                webcam.audio.stop()
            webcam.stop()
        elif isinstance(webcam, PiCameraStream):
            webcam.stop()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument(
        "--audio-codec", help="Force a specific audio codec (e.g. audio/opus)"
    )
    parser.add_argument(
        "--video-codec", help="Force a specific video codec (e.g. video/H264)"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_context)