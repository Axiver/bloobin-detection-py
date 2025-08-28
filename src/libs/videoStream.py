import argparse
import asyncio
import json
import logging
import os
import platform
import ssl
import sys
from typing import Optional

from aiohttp import web
import aiohttp_cors
from aiortc import (
    MediaStreamTrack,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaPlayer, MediaRelay
# from libs.camera import PiCameraStream

ROOT = os.path.dirname(__file__)
args = None
pcs = set()
relay = None
webcam = None
track = None

# Configure logging
logger = logging.getLogger(__name__)

"""
Create WebRTC streamable tracks
"""
def create_local_tracks() -> tuple[Optional[MediaStreamTrack], Optional[MediaStreamTrack]]:
    global relay, webcam, track

    # Play from the system's default webcam.
    #
    # In order to serve the same webcam to multiple users we make use of
    # a `MediaRelay`. The webcam will stay open, so it is our responsability
    # to stop the webcam when the application shuts down in `on_shutdown`.
    resolution = (1920, 1080)
    if args.resolution:
        resolution = tuple(map(int, args.resolution.split("x")))

    if relay is None:
        # Play from the system's default webcam.
        #
        # In order to serve the same webcam to multiple users we make use of
        # a `MediaRelay`. The webcam will stay open, so it is our responsability
        # to stop the webcam when the application shuts down in `on_shutdown`.
        options = {"framerate": "30", "video_size": f"{resolution[0]}x{resolution[1]}"} # Join the resolution tuple into a string
        
        if platform.system() == "Windows":
            try:
                webcam = MediaPlayer(
                    "video=JOYACCESS JA-Webcam", format="dshow", options=options
                )
                track = webcam.video  # Get the MediaStreamTrack from the MediaPlayer
                logger.info("Successfully initialized webcam")
            except Exception as e:
                logger.error(f"Failed to initialize webcam: {e}")
                # Try fallback to default webcam
                try:
                    logger.info("Attempting to use default webcam as fallback")
                    webcam = MediaPlayer(
                        "video=Integrated Webcam", format="dshow", options=options
                    )
                    track = webcam.video
                    logger.info("Successfully initialized fallback webcam")
                except Exception as fallback_e:
                    logger.error(f"Fallback webcam also failed: {fallback_e}")
                    track = None
        # else:
        #     webcam = PiCameraStream(size=resolution)
        #     track = webcam  # already a MediaStreamTrack
        
        relay = MediaRelay()
    
    # Only try to subscribe if we have a track
    if track is not None:
        return None, relay.subscribe(track)
    else:
        logger.warning("No video track available - server will run without video streaming")
        return None, None


def force_codec(pc: RTCPeerConnection, sender: RTCRtpSender, forced_codec: str) -> None:
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )

"""
Serve the WebRTC player
"""
async def index(request: web.Request) -> web.Response:
    content = open(os.path.join(ROOT, "../static/index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

"""
Handle the WebRTC offer
"""
async def offer(request: web.Request) -> web.Response:
    try:
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            logger.info("Connection state is %s" % pc.connectionState)
            if pc.connectionState == "failed":
                await pc.close()
                pcs.discard(pc)

        # open media source
        audio, video = create_local_tracks()

        # Only add tracks if they exist
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

        # Check if we have any media tracks
        if not audio and not video:
            logger.warning("No media tracks available - connection will be audio/video free")

        await pc.setRemoteDescription(offer)

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
            ),
        )
    except Exception as e:
        logger.error(f"Error in offer handler: {e}")
        # Return a proper error response instead of crashing
        return web.Response(
            content_type="application/json",
            text=json.dumps({"error": str(e)}),
            status=500
        )

"""
WebRTC shutdown handler
"""
async def on_shutdown(app: web.Application) -> None:
    logger.info("Shutting down WebRTC server...")
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
            webcam._stop()
        # elif isinstance(webcam, PiCameraStream):
        #     webcam._stop()

"""
Runs the WebRTC server
"""
def start_stream(serve_player=False):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Disable aioice logging to reduce noise
    logging.getLogger("aioice.ice").setLevel(logging.ERROR)
    logging.getLogger("aioice.rtp").setLevel(logging.ERROR)
    logging.getLogger("aioice.stun").setLevel(logging.ERROR)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_post("/offer", offer)

    if serve_player:
        app.router.add_get("/", index)

    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    for route in list(app.router.routes()):
        cors.add(route)

    try:
        logger.info(f"Starting WebRTC server on {args.host}:{args.port}")
        web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_context)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

"""
Main handler for starting via CLI
"""
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--resolution",
        type=str,
        help="Set custom video resolution as WIDTHxHEIGHT (e.g. 1280x720)",
    )
    parser.add_argument(
        "--play-without-decoding",
        help=(
            "Read the media without decoding it (experimental). "
            "For now it only works with an MPEGTS container with only H.264 video."
        ),
        action="store_true",
    )
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

    start_stream(serve_player=True)