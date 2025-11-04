# YouTube Downloader - Replit Configuration

## Overview
A simple YouTube video and audio downloader built with Flask and yt-dlp. This application allows users to download YouTube videos in various formats (MP4, MP3) and qualities. Downloads are processed server-side and uploaded to Gofile for easy access.

## Project Status
**Current State**: Fully functional and configured for Replit environment
**Last Updated**: November 4, 2025

## Features
- Download YouTube videos in MP4 format (720p, 480p)
- Extract audio in MP3 format (320kbps, 128kbps)
- Real-time download progress tracking with Server-Sent Events (SSE)
- Dark/Light theme toggle
- Responsive UI with Tailwind CSS
- Uploads completed downloads to Gofile cloud storage

## Technology Stack
- **Backend**: Python 3.11, Flask 3.0.3
- **Video Processing**: yt-dlp, FFmpeg
- **Frontend**: HTML, Tailwind CSS, Vanilla JavaScript
- **File Storage**: Gofile API integration
- **Production Server**: Gunicorn

## Project Structure
```
.
├── app.py                 # Main Flask application
├── templates/
│   └── index.html        # Frontend UI
├── static/
│   ├── css/
│   │   ├── styles.css    # Custom styles
│   │   └── output.css    # Tailwind output
│   └── js/
│       └── script.js     # Frontend logic
├── requirements.txt      # Python dependencies
└── .gitignore           # Git ignore rules
```

## Environment Variables (Optional)
- `GOFILE_TOKEN`: API token for Gofile uploads (required for download functionality)
- `COOKIE_FILE_CONTENTS`: YouTube cookies for age-restricted or login-required videos
- `PORT`: Server port (default: 5000)

## Development Setup
The application is already configured and running in Replit:
1. **Dependencies**: All Python packages and FFmpeg are installed
2. **Workflow**: Flask dev server running on port 5000
3. **Host Configuration**: Configured for 0.0.0.0 to work with Replit's proxy

## Deployment
Configured for Replit Autoscale deployment:
- **Target**: Autoscale (stateless web app)
- **Production Server**: Gunicorn with port reuse
- **Command**: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app`

## Important Notes
1. **Gofile Token Required**: For the download functionality to work, you need to set the `GOFILE_TOKEN` secret in Replit
2. **YouTube Cookies**: Optional, only needed for age-restricted or login-required videos
3. **Single Videos Only**: This app downloads individual videos, not playlists
4. **Legal Usage**: Respect copyright laws and YouTube's terms of service

## Known Limitations
- Uses Tailwind CDN in development (warning in console is expected)
- Downloads are uploaded to Gofile rather than served directly (intentional for cloud storage)
- No playlist support (by design)

## Recent Changes
- **Nov 4, 2025**: Initial Replit setup
  - Added python-dotenv to requirements.txt
  - Updated .gitignore with Python-specific ignores
  - Configured workflow for port 5000 with webview
  - Set up deployment with Gunicorn
  - Verified application runs successfully

## User Preferences
None specified yet.

## Architecture Decisions
- **Gofile Integration**: Videos are uploaded to Gofile cloud storage after download to avoid large file transfers and provide persistent download links
- **SSE for Progress**: Server-Sent Events provide real-time download progress without polling
- **Threading**: Background threads handle downloads to avoid blocking the web server
- **Temporary Storage**: Downloads use temp directories that are cleaned up automatically
