#!/usr/bin/env python3
"""CORS-enabled proxy server for Infoblox NIOS WAPI."""

import os
import re
import ssl
import json
import atexit
import logging
import argparse
import urllib.request
import urllib.error
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

    def do_OPTIONS(self):  # pylint: disable=invalid-name
        """Handle preflight OPTIONS requests."""
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        # Serve proxy configuration endpoint
        if self.path == '/proxy-config':
            self._serve_proxy_config_json()
        elif self._is_wapi_request():
            self._proxy_request()
        else:
            super().do_GET()

    def do_POST(self):  # pylint: disable=invalid-name
        """Handle POST requests."""
        self._handle_wapi_or_error()

    def do_PUT(self):  # pylint: disable=invalid-name
        """Handle PUT requests."""
        self._handle_wapi_or_error()

    def do_DELETE(self):  # pylint: disable=invalid-name
        """Handle DELETE requests."""
        self._handle_wapi_or_error()

    def _handle_wapi_or_error(self):
        """Handle WAPI request or return 405 error."""
        if self._is_wapi_request():
            self._proxy_request()
        else:
            self.send_error(405)

    def _is_wapi_request(self):
        """Check if this is a WAPI request."""
        return self.WAPI_PATTERN.match(self.path) is not None

    def _get_target_server(self):
        """Extract target server from path or query."""
        match = self.WAPI_PATTERN.match(self.path)
        if match:
            server = match.group(1)
            if server:
                return server

        # Check query parameter
        target_param = 'target='
        if target_param in self.path:
            start = self.path.find(target_param) + len(target_param)
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
                value = self.headers.get(header)
                if value:
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
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            logger.error("Proxy error: %s", e)
            self.send_error(502, f"Proxy error: {e}")

    def _serve_proxy_config_json(self):
        """Serve proxy configuration as JSON for custom.js."""
        # Return the request's host as the proxy URL
        proxy_url = f"http://{self.headers.get('Host', 'localhost:9000')}"
        config = {"proxyUrl": proxy_url}
        config_json = json.dumps(config)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(config_json))
        self.end_headers()
        self.wfile.write(config_json.encode('utf-8'))

def cleanup_proxy_init():
    """Remove proxy-init.js on server shutdown."""
    try:
        if os.path.exists('styles/proxy-init.js'):
            os.remove('styles/proxy-init.js')
            logger.info("Cleaned up styles/proxy-init.js")
    except OSError as e:
        logger.warning("Could not remove proxy-init.js: %s", e)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Minimal CORS proxy for NIOS WAPI')
    parser.add_argument('--port', type=int, default=9000, help='Server port')
    args = parser.parse_args()

    # Bind to all interfaces for VPN/network access
    host = '0.0.0.0'

    # Generate proxy-init.js file for custom.js to load
    # Note: This uses localhost as custom.js will fetch /proxy-config to get the actual URL
    proxy_init_content = (
        "// Auto-generated by cors_proxy_server.py - DO NOT EDIT MANUALLY\n"
        "// custom.js will fetch the actual proxy URL from /proxy-config endpoint\n"
        "window.PROXY_CONFIG_URL = window.location.origin + '/proxy-config';\n"
    )

    try:
        with open('styles/proxy-init.js', 'w', encoding='utf-8') as f:
            f.write(proxy_init_content)
        logger.info("Generated styles/proxy-init.js")
        # Register cleanup function to remove file on exit
        atexit.register(cleanup_proxy_init)
    except OSError as e:
        logger.warning("Could not generate styles/proxy-init.js: %s", e)
        logger.warning("Proxy detection may not work until file is created")

    # Start server
    server = HTTPServer((host, args.port), NIOSProxyHandler)

    print("WARNING: SSL certificate verification is DISABLED (development only)")
    print(f"CORS Proxy Server running on http://{host}:{args.port}/ (listening on all interfaces)")
    print(f"To access from another machine, use: http://<this-machine-ip>:{args.port}/")
    print("Set NIOS_Grid_IP variable in Swagger UI to your NIOS server IP")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
