# AETHER

AETHER is a local interior redesign and 360 walkthrough app. Upload a room photo, choose a room type and style, generate a redesigned render, and open the panorama in the 3D viewer.

## What It Does

- Authenticates users locally with SQLite-backed sessions.
- Uploads room photos and stores them on disk.
- Generates a redesigned room image from the uploaded photo and selected preferences.
- Synthesizes a 360 panorama from the redesigned image.
- Tracks saved and favorite tours.
- Exports redesigns, panoramas, reports, and JSON payloads.

## Run From GitHub On Another System

These steps are for someone cloning the project from GitHub on a new computer.

### 1. Install Prerequisites

Install these first:

- Git: https://git-scm.com/downloads
- Python 3.10 or newer: https://www.python.org/downloads/

During Python installation on Windows, enable **Add python.exe to PATH**.

Check both tools:

```powershell
git --version
python --version
pip --version
```

If `python` opens the Microsoft Store on Windows, install Python from python.org or disable the Windows app execution alias for Python in Windows settings.

### 2. Clone The Repository

```powershell
git clone https://github.com/01-HITESH/AETHER.git
cd AETHER
```

### 3. Create A Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies

```powershell
pip install -r BACKEND\requirements.txt
```

On macOS or Linux, use forward slashes:

```bash
pip install -r BACKEND/requirements.txt
```

### 5. Start The App

Windows PowerShell:

```powershell
.\run.ps1
```

Windows Command Prompt:

```bat
run.bat
```

macOS or Linux:

```bash
PYTHONPATH=. python3 -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000 --reload
```

### 6. Open In Browser

```text
http://127.0.0.1:8000/app/
```

The API health check is available at:

```text
http://127.0.0.1:8000/api/health
```

### 7. First Use

1. Register with any email and password.
2. Upload a JPG or PNG room photo under 20 MB.
3. Select room type, style, and requirements.
4. Generate the redesign.
5. Open the 3D walkthrough or export the result.

No external API key is required.

## Run Locally In This Workspace

```powershell
cd "C:\2.0 project"
.\run.ps1
```

Open:

```text
http://127.0.0.1:8000/app/
```

## Dependencies

- Python 3.10+
- `fastapi`
- `uvicorn`
- `python-multipart`
- `pillow`
- `numpy`

Install dependencies with:

```powershell
pip install -r BACKEND\requirements.txt
```

## Project Layout

- `BACKEND/app.py` - FastAPI app, auth, uploads, redesign generation, panorama generation, exports.
- `FRONTEND/` - static app pages and shared runtime.
- `run.ps1` / `run.bat` - local launch scripts.
- `BACKEND/data/` - runtime data created at launch.

## Data Storage

Generated files live under `BACKEND/data/`:

- `database/aether.sqlite3` - SQLite database.
- `uploads/` - original uploaded room photos.
- `tours/` - generated redesigns, panoramas, and thumbnails.
- `exports/` - exported JSON and report files.

The backend also migrates from the legacy `BACKEND/data/aether.sqlite3` path if it exists.

## Main Workflow

1. Register or log in.
2. Upload a room image.
3. Pick a room type and style.
4. Add requirements.
5. Generate the design.
6. Review the redesign and open the 3D walkthrough.
7. Save, favorite, or export the result.

## API Overview

- `GET /api/health` - health check.
- `POST /api/auth/register` - create account.
- `POST /api/auth/login` - sign in.
- `POST /api/auth/logout` - clear session.
- `GET /api/me` - current profile and stats.
- `PATCH /api/me` - update profile or settings.
- `PATCH /api/me/password` - change password.
- `POST /api/upload` - upload a room photo.
- `POST /api/tours` - generate a redesign and panorama.
- `GET /api/tours` - list saved tours.
- `GET /api/tours/{tour_id}` - load one tour.
- `POST /api/tours/{tour_id}/save` - toggle saved.
- `POST /api/tours/{tour_id}/favorite` - toggle favorite.
- `DELETE /api/tours/{tour_id}` - delete a tour.
- `GET /api/tours/{tour_id}/export/{kind}` - export image, panorama, report, or JSON.

## Model Note

This build does not call a hosted AI image model. The redesign is generated locally with Pillow and NumPy, then converted into a panorama for the viewer.

## Troubleshooting

- If the app does not start, confirm the virtual environment is activated and dependencies are installed.
- If PowerShell blocks `run.ps1`, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and then run `.\run.ps1` again.
- If port 8000 is already in use, stop the other process or start Uvicorn with a different port such as `--port 8001`.
- If `python` opens Microsoft Store, install Python from python.org and make sure it is on PATH.
- If uploads fail, use JPG or PNG under 20 MB.
- If the viewer is blank, confirm a tour was generated and the panorama file exists in `BACKEND/data/tours/`.

## Current Root

The app is served from `/app/`, while `/` redirects there automatically.
