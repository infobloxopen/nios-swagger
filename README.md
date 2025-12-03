# NIOS Swagger

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Active-brightgreen)](https://infobloxopen.github.io/nios-swagger/)
[![Last Updated](https://img.shields.io/badge/last%20updated-December%202025-blue.svg)](https://github.com/infobloxopen/nios-swagger)
[![Swagger UI](https://img.shields.io/badge/Swagger_UI-v5.27.0-orange.svg)](https://github.com/swagger-api/swagger-ui/releases/tag/v5.27.0)

A comprehensive tool for serving Swagger/OpenAPI documentation for Infoblox NIOS APIs. This repository hosts interactive API documentation that allows users to explore and test NIOS APIs directly from their browser.

## Overview

This repository provides:

- Interactive API documentation using Swagger UI v5.27.0
- Pre-compiled OpenAPI specifications for all NIOS APIs (v2.13.1, v2.13.6, v2.13.7, v2.13.8)
- CORS proxy server with zero dependencies (Python standard library only)
- Easy browsing of API endpoints, request/response models, and examples
- Automated workflows for continuous integration and deployment

## Getting Started

### Prerequisites

- Web browser (Chrome, Firefox, Safari, Edge)
- Git (for local installation)
- Python 3.7+ (for CORS proxy server, no external dependencies needed)

### Installation

1. **Online Access**: No installation required! Simply visit [https://infobloxopen.github.io/nios-swagger/](https://infobloxopen.github.io/nios-swagger/)

2. **Local Installation**:
   ```bash
   # Clone the repository
   git clone https://github.com/infobloxopen/nios-swagger.git

   # Navigate to the project directory
   cd nios-swagger

   # Option A: Start with CORS proxy (recommended for API testing)
   python3 cors_proxy_server.py
   # Access at http://localhost:9000

   # Option B: Start a simple HTTP server (view only)
   python3 -m http.server 8080
   # or using Node.js
   npx http-server -p 8080
   # Access at http://localhost:8080
   ```

## Usage

### Exploring APIs

1. Browse the available API categories in the navigation panel
2. Expand operations to see detailed request parameters and response models
3. Try it out - fill out the request parameter fields and hit "Execute" to see the full URI and an example curl command

### Testing APIs with "Try it out"

To execute API calls directly from Swagger UI against your NIOS appliance, use the included CORS proxy server. The proxy handles Cross-Origin Resource Sharing (CORS) restrictions and routes requests between your browser and NIOS.

For detailed setup instructions, configuration options, and troubleshooting, see [CORS_PROXY_GUIDE.md](CORS_PROXY_GUIDE.md).

## Repository Structure

```
nios-swagger/
├── .github/                 # GitHub configuration files
├── index.html               # Main Swagger UI page
├── README.md                # This file
├── CORS_PROXY_GUIDE.md      # Detailed CORS proxy documentation
├── cors_proxy_server.py     # CORS proxy server script
├── requirements.txt         # Python dependencies for CORS proxy
├── styles/                  # Custom styling
│   ├── custom.css           # Custom CSS styling
│   └── custom.js            # Custom JavaScript with CORS proxy support
└── swagger-ui/              # Swagger UI resources
    ├── swagger-ui.version   # Swagger UI version information (v5.27.0)
    ├── dist/                # Swagger UI distribution files
    └── openspec/            # OpenAPI specifications
        ├── v2.13.1/         # NIOS v9.0.1-v9.0.3 API specs
        ├── v2.13.6/         # NIOS v9.0.6 API specs
        ├── v2.13.7/         # NIOS v9.0.7 API specs
        └── v2.13.8/         # NIOS v9.0.8 API specs
```

### Important Note

This repository contains auto-generated API documentation and is provided as a **read-only reference**. The OpenAPI specifications are automatically generated and contributions are not accepted. This documentation serves as the reference for NIOS APIs.
