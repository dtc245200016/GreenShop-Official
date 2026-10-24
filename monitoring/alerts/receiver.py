"""Internal Main notification sink. No host port, no third party delivery."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
import json
notifications=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        payload=json.dumps(notifications if self.path=="/notifications" else {"status":"ok"}).encode()
        self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(payload)
    def do_POST(self):
        size=int(self.headers.get("Content-Length","0"))
        if self.path!="/alerts" or not 0<size<1048576:self.send_error(400);return
        try:payload=json.loads(self.rfile.read(size))
        except (ValueError,UnicodeDecodeError):self.send_error(400);return
        entry={"received_at":datetime.now(timezone.utc).isoformat(),"payload":payload}
        notifications.append(entry);del notifications[:-100]
        print(json.dumps(entry),flush=True)
        self.send_response(200);self.end_headers();self.wfile.write(b"accepted")
HTTPServer(("0.0.0.0",8080),Handler).serve_forever()
