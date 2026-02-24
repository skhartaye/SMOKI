"""
WebRTC proxy to forward connections from frontend to RPi go2rtc server
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import websockets
import json
import os

router = APIRouter(prefix="/api/streams", tags=["webrtc"])

# RPi go2rtc server URL
RPI_WEBRTC_URL = os.getenv("RPI_WEBRTC_URL", "ws://192.168.100.198:8080")

@router.websocket("/camera/webrtc")
async def webrtc_proxy(websocket: WebSocket):
    """
    WebSocket proxy that forwards WebRTC signaling to RPi go2rtc server
    """
    await websocket.accept()
    
    rpi_ws = None
    try:
        # Connect to RPi go2rtc server
        rpi_ws_url = f"{RPI_WEBRTC_URL}/api/streams/camera/webrtc"
        print(f"Connecting to RPi WebRTC server: {rpi_ws_url}")
        
        rpi_ws = await websockets.connect(rpi_ws_url)
        print("Connected to RPi WebRTC server")
        
        # Create tasks to forward messages in both directions
        async def forward_from_client():
            try:
                while True:
                    data = await websocket.receive_text()
                    print(f"Client -> RPi: {data[:100]}")
                    await rpi_ws.send(data)
            except WebSocketDisconnect:
                print("Client disconnected")
            except Exception as e:
                print(f"Error forwarding from client: {e}")
        
        async def forward_from_rpi():
            try:
                while True:
                    data = await rpi_ws.recv()
                    print(f"RPi -> Client: {data[:100]}")
                    await websocket.send_text(data)
            except Exception as e:
                print(f"Error forwarding from RPi: {e}")
        
        # Run both tasks concurrently
        await asyncio.gather(
            forward_from_client(),
            forward_from_rpi()
        )
    
    except Exception as e:
        print(f"WebRTC proxy error: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass
    finally:
        if rpi_ws:
            try:
                await rpi_ws.close()
            except:
                pass
        try:
            await websocket.close()
        except:
            pass
