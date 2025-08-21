# VettaVista Backend

Local Python server that powers VettaVista's AI-driven job search and application enhancement features.

## Overview

This backend component of VettaVista provides:
- Two-stage job filtering logic
- AI integration with Claude
- Resume and cover letter customization
- Data storage and management
- Local API endpoints for frontend communication

## Development

### Requirements
- Python 3.9+
- `pip` or Poetry for dependency management

### Setup

```bash
# Install with Poetry
poetry install

# Or with pip
pip install -e .

# Run development server
python modules/server.py

# Build package
python -m build
```
