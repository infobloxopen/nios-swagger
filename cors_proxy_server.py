#!/usr/bin/env python3
"""CORS-enabled proxy server for Infoblox NIOS WAPI."""

import os
import re
import ssl
import sys
import logging
import argparse
import urllib.request
import urllib.error
from urllib.parse import urlparse
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Simple logging setup
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class NIOSProxyHandler(SimpleHTTPRequestHandler):
    """Minimal HTTP request handler with CORS support and NIOS proxy functionality."""

    # Pre-compiled patterns
    WAPI_PATTERN = re.compile(r'^/(?:([^/]+))?/wapi/', re.IGNORECASE)

    # CORS headers
    CORS_HEADERS = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    }

    # SSL context cache
    _ssl_context = None

    def end_headers(self):
        """Add CORS headers to all responses."""
        for header, value in self.CORS_HEADERS.items():
            self.send_header(header, value)
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight OPTIONS requests."""
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        if self._is_wapi_request():
            self._proxy_request()
        else:
            super().do_GET()

    def do_POST(self):
        """Handle POST requests."""
        self._proxy_request() if self._is_wapi_request() else self.send_error(405)

    def do_PUT(self):
        """Handle PUT requests."""
        self._proxy_request() if self._is_wapi_request() else self.send_error(405)

    def do_DELETE(self):
        """Handle DELETE requests."""
        self._proxy_request() if self._is_wapi_request() else self.send_error(405)

    def _is_wapi_request(self):
        """Check if this is a WAPI request."""
        return self.WAPI_PATTERN.match(self.path) is not None

    def _get_target_server(self):
        """Extract target server from path or query."""
        match = self.WAPI_PATTERN.match(self.path)
        if match and match.group(1):
            return match.group(1)

        # Check query parameter
        if '?' in self.path and 'target=' in self.path:
            start = self.path.find('target=') + 7
            end = self.path.find('&', start)
            return self.path[start:end] if end != -1 else self.path[start:]

        return None

    def _get_ssl_context(self):
        """Get SSL context (cached)."""
        if not NIOSProxyHandler._ssl_context:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            NIOSProxyHandler._ssl_context = context
        return NIOSProxyHandler._ssl_context

    def _proxy_request(self):
        """Proxy the request to NIOS server."""
        target_server = self._get_target_server()
        if not target_server:
            self.send_error(502, "No target server configured. Set NIOS_Grid_IP variable.")
            return

        try:
            # Build target URL
            wapi_path = self.path[self.path.find('/wapi'):]
            target_url = f"https://{target_server}{wapi_path}"

            # Prepare request
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            req = urllib.request.Request(target_url, data=body, method=self.command)

            # Copy important headers
            for header in ['Content-Type', 'Accept', 'Authorization']:
                if value := self.headers.get(header):
                    req.add_header(header, value)

            # Make request
            with urllib.request.urlopen(req, context=self._get_ssl_context()) as response:
                self.send_response(response.getcode())

                # Copy response headers
                for header, value in response.headers.items():
                    if header.lower() not in ['transfer-encoding', 'connection']:
                        self.send_header(header, value)

                self.end_headers()
                self.wfile.write(response.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.send_error(502, f"Proxy error: {e}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Minimal CORS proxy for NIOS WAPI')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=9000, help='Server port')
    args = parser.parse_args()

    # Update custom.js if it exists
    try:
        with open('styles/custom.js', 'r+', encoding='utf-8') as f:
            content = f.read()
            content = content.replace('http://localhost:9000', f'http://{args.host}:{args.port}')
            f.seek(0)
            f.write(content)
            f.truncate()
    except FileNotFoundError:
        pass

    # Start server
    server = HTTPServer((args.host, args.port), NIOSProxyHandler)

    print(f"CORS Proxy Server running on http://{args.host}:{args.port}/")
    print("Set NIOS_Grid_IP variable in Swagger UI to your NIOS server IP")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
