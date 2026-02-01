#!/usr/bin/env python3
"""Simple Entity HTTP Server for L0 Deployment Demo"""
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sys

class EntityHandler(BaseHTTPRequestHandler):
    def __init__(self, entity_id, *args, **kwargs):
        self.entity_id = entity_id
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                "status": "healthy",
                "entity_id": self.entity_id,
                "version": "1.0.0"
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

def run_server(port, entity_id):
    handler = lambda *args, **kwargs: EntityHandler(entity_id, *args, **kwargs)
    server = HTTPServer(('0.0.0.0', port), handler)
    print(f"[{entity_id}] Server running on port {port}")
    server.serve_forever()

if __name__ == '__main__':
    import threading
    
    # Start Entity A on port 8001
    t1 = threading.Thread(target=run_server, args=(8001, 'entity-a'), daemon=True)
    t1.start()
    
    # Start Entity B on port 8002
    t2 = threading.Thread(target=run_server, args=(8002, 'entity-b'), daemon=True)
    t2.start()
    
    print("="*60)
    print("L0 DEPLOYMENT: Entity A/B Running")
    print("="*60)
    print("Entity A: http://localhost:8001")
    print("Entity B: http://localhost:8002")
    print("API Server: http://localhost:8000")
    print("="*60)
    
    # Keep running
    try:
        while True:
            asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
