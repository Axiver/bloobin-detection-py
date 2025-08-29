import asyncio
import json
import logging
import threading
from typing import Callable, Set
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK


logger = logging.getLogger(__name__)

logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s'
)

class WebSocketServer:
  
  def __init__(self, host: str = "0.0.0.0", port: int = 8765, start_qr_scanning: Callable[[], None] = None, stop_qr_scanning: Callable[[], None] = None, start_processing_recycle: Callable[[], None] = None, stop_processing_recycle: Callable[[], None] = None):
    self.host = host
    self.port = port
    self.clients: Set[ServerConnection] = set()
    self.running = False
    self.start_qr_scanning = start_qr_scanning
    self.stop_qr_scanning = stop_qr_scanning
    self.start_processing_recycle = start_processing_recycle
    self.stop_processing_recycle = stop_processing_recycle
    self.server_thread = None

  async def register_client(self, websocket: ServerConnection):
    """Register a new client connection."""
    self.clients.add(websocket)
    logger.info(f"Client connected. Total clients: {len(self.clients)}")
  
  async def unregister_client(self, websocket: ServerConnection):
    """Unregister a client connection."""
    if websocket in self.clients:
      self.clients.discard(websocket)
      logger.info(f"Client disconnected. Total clients: {len(self.clients)}")
  
  async def send_message(self, websocket: ServerConnection, message: dict):
    """Send a message to a specific client."""
    try:
      await websocket.send(json.dumps(message))
    except (ConnectionClosed, ConnectionClosedOK):
      await self.unregister_client(websocket)
    except Exception as e:
      logger.error(f"Error sending message: {e}")
      await self.unregister_client(websocket)
  
  async def broadcast_message(self, message: dict, exclude: ServerConnection = None):
    """Broadcast a message to all connected clients."""
    disconnected_clients = set()
    
    for client in self.clients:
      if client != exclude:
        try:
          await client.send(json.dumps(message))
        except (ConnectionClosed, ConnectionClosedOK):
          disconnected_clients.add(client)
        except Exception as e:
          logger.error(f"Error broadcasting to client: {e}")
          disconnected_clients.add(client)
    
    # Clean up disconnected clients
    for client in disconnected_clients:
      await self.unregister_client(client)
  
  async def handle_client(self, websocket: ServerConnection):
    """Handle individual client connections."""
    await self.register_client(websocket)
    
    try:
      async for message in websocket:
        try:
          data = json.loads(message)
          await self.process_message(websocket, data)
          
        except json.JSONDecodeError:
          await self.send_message(websocket, {
            'type': 'error',
            'message': 'Invalid JSON format'
          })
        except Exception as e:
          logger.error(f"Error processing message: {e}")
          await self.send_message(websocket, {
            'type': 'error',
            'message': 'Internal server error'
          })
          
    except (ConnectionClosed, ConnectionClosedOK):
      pass
    except Exception as e:
      logger.error(f"Error in client handler: {e}")
    finally:
      await self.unregister_client(websocket)
  
  async def process_message(self, websocket: ServerConnection, data: dict):
    """Process incoming messages based on their type."""
    message_type = data.get('type', 'unknown')
    
    logger.info(f"Processing message type: {message_type}")

    if message_type == 'ping':
      await self.send_message(websocket, {
        'type': 'pong'
      })

    elif message_type == 'start_qr_scanning':
      logger.info("Received start_qr_scanning request")
      if self.start_qr_scanning:
        try:
          await self.start_qr_scanning()
          await self.send_message(websocket, {
            'type': 'response',
            'message': 'QR scanning started successfully'
          })
        except Exception as e:
          logger.error(f"Error starting QR scanning: {e}")
          await self.send_message(websocket, {
            'type': 'error',
            'message': f'Failed to start QR scanning: {str(e)}'
          })
      else:
        await self.send_message(websocket, {
          'type': 'error',
          'message': 'QR scanning not supported'
        })

    elif message_type == 'stop_qr_scanning':
      logger.info("Received stop_qr_scanning request")
      if self.stop_qr_scanning:
        try:
          await self.stop_qr_scanning()
          await self.send_message(websocket, {
            'type': 'response',
            'message': 'QR scanning stopped successfully'
          })
        except Exception as e:
          logger.error(f"Error stopping QR scanning: {e}")
          await self.send_message(websocket, {
            'type': 'error',
            'message': f'Failed to stop QR scanning: {str(e)}'
          })
      else:
        await self.send_message(websocket, {
          'type': 'error',
          'message': 'QR scanning not supported'
        })

    elif message_type == 'start_processing_recycle':
      logger.info("Received start_processing_recycle request")
      if self.start_processing_recycle:
        try:
          await self.start_processing_recycle()
        except Exception as e:
          logger.error(f"Error starting processing recycle: {e}")

    elif message_type == 'stop_processing_recycle':
      logger.info("Received stop_processing_recycle request")
      if self.stop_processing_recycle:
        try:
          await self.stop_processing_recycle()
        except Exception as e:
          logger.error(f"Error stopping processing recycle: {e}")
          
    else:
      logger.warning(f"Unknown message type received: {message_type}")
      await self.send_message(websocket, {
        'type': 'error',
        'message': f'Unknown message type: {message_type}'
      })
  
  async def start_server(self, threaded: bool = False):
    """Start the WebSocket server.
    
    :param threaded: If True, run in a separate thread
    """
    if threaded:
      # Run server in a separate thread
      def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
          loop.run_until_complete(self._run_server_in_thread())
        except Exception as e:
          logger.error(f"WebSocket server thread error: {e}")
        finally:
          loop.run_until_complete(loop.shutdown_asyncgens())
          loop.close()

      self.server_thread = threading.Thread(target=thread_target, daemon=True)
      self.server_thread.start()
      logger.info("WebSocket server started in a separate thread")
      return self.server_thread
    else:
      # Blocking mode (default behavior)
      await self._run_server_in_thread()

  async def _run_server_in_thread(self):
    """Internal method to run the server (used by both threaded and non-threaded modes)."""
    self.server = await serve(self.handle_client, self.host, self.port)
    self.running = True
    logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
    await self.server.serve_forever()
  
  async def stop_server(self):
    """Stop the WebSocket server gracefully."""
    logger.info("Stopping WebSocket server...")
    self.running = False
    
    if hasattr(self, 'server'):
      self.server.close()
      await self.server.wait_closed()
    
    # Close all client connections
    for client in list(self.clients):
      try:
        await client.close(1000, "Server shutting down")
      except Exception as e:
        logger.error(f"Error closing client connection: {e}")
    
    logger.info("WebSocket server stopped")


async def main():
  """Main entry point for the WebSocket server."""
  server = WebSocketServer()
  
  try:
    await server.start_server()
    
    # Keep the server running
    while server.running:
      await asyncio.sleep(1)
      
  except KeyboardInterrupt:
    logger.info("Keyboard interrupt received")
  finally:
    await server.stop_server()


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    logger.info("Server stopped by user")
  except Exception as e:
    logger.error(f"Fatal error: {e}")
    exit(1)