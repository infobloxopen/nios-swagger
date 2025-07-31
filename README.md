# NIOS Swagger

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Active-brightgreen)](https://infobloxopen.github.io/nios-swagger/)
[![Last Updated](https://img.shields.io/badge/last%20updated-June%202025-blue.svg)](https://github.com/infobloxopen/nios-swagger)
[![Swagger UI](https://img.shields.io/badge/Swagger_UI-v5.27.0-orange.svg)](https://github.com/swagger-api/swagger-ui/releases/tag/v5.27.0)

A comprehensive tool for serving Swagger/OpenAPI documentation for Infoblox NIOS APIs. This repository hosts interactive API documentation that allows users to explore and test NIOS APIs directly from their browser.

## Overview

This repository provides:

- Interactive API documentation using Swagger UI v5.27.0
- Pre-compiled OpenAPI specifications for all NIOS APIs (v2.13.1, v2.13.6, v2.13.7)
- Easy browsing of API endpoints, request/response models, and examples
- Automated workflows for continuous integration and deployment

## Getting Started

### Prerequisites

- Web browser (Chrome, Firefox, Safari, Edge)
- Git (for local installation)

### Installation

1. **Online Access**: No installation required! Simply visit [https://infobloxopen.github.io/nios-swagger/](https://infobloxopen.github.io/nios-swagger/)

2. **Local Installation**:
   ```bash
   # Clone the repository
   git clone https://github.com/infobloxopen/nios-swagger.git

   # Navigate to the project directory
   cd nios-swagger

   # Start a local web server
   # Using Python 3
   python3 -m http.server 8080
   # or using Node.js
   npx http-server -p 8080

   # Access in your browser
   # Visit http://localhost:8080
   ```

## Usage

### Viewing Documentation

You can access and interact with the NIOS API documentation in two ways:

1. **Online**: Visit our GitHub Pages site at [https://infobloxopen.github.io/nios-swagger/](https://infobloxopen.github.io/nios-swagger/)
   - Always updated with the latest documentation
   - No installation required
   - Accessible from any device with a web browser

2. **Local**: Open `index.html` in your web browser after cloning the repository
   - Works offline
   - Can be customized for your needs
   - Use local development environment

### Exploring APIs

1. Browse the available API categories in the navigation panel
2. Expand operations to see detailed request parameters and response models

## Repository Structure

```
nios-swagger/
├── .github/                 # GitHub configuration files
├── index.html               # Main Swagger UI page
├── styles/                  # Custom styling
│   ├── custom.css           # Custom CSS styling
│   └── custom.js            # Custom JavaScript
└── swagger-ui/              # Swagger UI resources
    ├── swagger-ui.version   # Swagger UI version information (v5.24.0)
    ├── dist/                # Swagger UI distribution files
    └── openspec/            # OpenAPI specifications
        └── v2.13.6/         # API version specific specs
```

### Important Note

This repository contains auto-generated API documentation and is provided as a **read-only reference**. The OpenAPI specifications are automatically generated and contributions are not accepted. This documentation serves as the reference for NIOS APIs.
