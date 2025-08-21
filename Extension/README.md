# VettaVista Extension

Browser extension that enhances LinkedIn job search by integrating AI-powered filtering and application tools.

## Overview

This is the frontend/extension component of VettaVista.

## Development

### Requirements
- Node.js 16+
- npm or yarn

### Setup

```bash
# Install dependencies
npm install

# Build for development
npm run build:dev

# Build for production
npm run build
```

### Loading in Browser

#### Chrome
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `dist/` directory

#### Firefox
1. Go to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on..."
3. Select any file in the `dist_ff/` directory
