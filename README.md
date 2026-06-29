# AETHER

AETHER is a local interior redesign and 360 walkthrough app. Users can create an account, upload a room photo, choose a room type and style, generate a redesigned render, and open the generated panorama in the 3D viewer.

The app runs locally with FastAPI, SQLite, static frontend pages, Pillow, and NumPy. It does not require an external database, cloud account, hosted AI API, or API key.

## Features

- Local account registration and login.
- SQLite-backed user database with sessions, profile settings, upload records, tour records, and account history.
- Password storage with salted PBKDF2 hashes. Plain-text passwords are never stored.
- Account settings page for updating the visible username.
- Original-quality profile picture upload for JPG, PNG, and WebP files up to 25 MB.
- Dark/light mode toggle saved to the user profile settings and mirrored in browser local storage.
- Room photo upload for JPG and PNG files up to 20 MB.
- Local redesign generation from the uploaded photo and selected preferences.
- 360 panorama generation for the interactive walkthrough viewer.
- Saved and favorite design tracking.
- Export support for redesigns, panoramas, HTML reports, and JSON tour data.

## Requirements

Install these before running the project:

- Git: https://git-scm.com/downloads
- Python 3.10 or newer: https://www.python.org/downloads/

On Windows, enable **Add python.exe to PATH** during Python installation.

Check the installed tools:

```powershell
git --version
python --version
pip --version
```

If `python` opens the Microsoft Store on Windows, install Python from python.org or disable the Windows app execution alias for Python in Windows Settings.

## Run From GitHub

### 1. Clone The Repository

```powershell
git clone https://github.com/01-HITESH/AETHER.git
cd AETHER
```

### 2. Create A Virtual Environment

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

### 3. Install Dependencies

Windows:

```powershell
pip install -r BACKEND\requirements.txt
```

macOS or Linux:

```bash
pip install -r BACKEND/requirements.txt
```

### 4. Start The App

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
PYTHONPATH=. python3 -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000
```

The Windows scripts now prefer `.venv\Scripts\python.exe` when a virtual environment exists. If `.venv` is missing, they fall back to the `python` command available on PATH.

### 5. Open The App

Open this URL in your browser:

```text
http://127.0.0.1:8000/app/
```

Use `/app/` as the stable entry URL. Avoid bookmarking nested frontend HTML paths because page folder names can change between builds.

The root URL redirects to the app:

```text
http://127.0.0.1:8000/
```

The API health check is:

```text
http://127.0.0.1:8000/api/health
```

## First Use

1. Register with an email address, username, and password.
2. Open the profile/settings page to update the username, upload a profile picture, or switch between dark and light mode.
3. Upload a room photo as JPG or PNG under 20 MB.
4. Select room type, style, and design requirements.
5. Generate the redesign.
6. Open the interactive 3D walkthrough.
7. Save, favorite, export, or delete generated designs.

## Dependencies

The Python dependencies are listed in `BACKEND/requirements.txt`:

- `fastapi`
- `uvicorn`
- `python-multipart`
- `pillow`
- `numpy`

Install them with:

```powershell
pip install -r BACKEND\requirements.txt
```

## Project Layout

- `BACKEND/app.py` - FastAPI application, database setup, auth, profile management, uploads, redesign generation, panorama generation, exports, and media serving.
- `BACKEND/requirements.txt` - Python dependency list.
- `FRONTEND/` - static page mockups and app screens.
- `FRONTEND/shared/aether.js` - shared frontend runtime for API calls, auth guards, navigation, profile settings, theme handling, and page wiring.
- `FRONTEND/shared/pano-viewer.js` - interactive panorama viewer runtime.
- `run.ps1` - Windows PowerShell launcher.
- `run.bat` - Windows Command Prompt launcher.
- `BACKEND/data/` - runtime data created locally when the app runs. This folder is ignored by Git.

## Data Storage

AETHER stores runtime data locally under `BACKEND/data/`.

- `BACKEND/data/database/aether.sqlite3` - main SQLite database.
- `BACKEND/data/uploads/` - original uploaded room photos.
- `BACKEND/data/profile_images/` - uploaded user profile pictures stored at original quality.
- `BACKEND/data/tours/` - generated redesigns, panoramas, and thumbnails.
- `BACKEND/data/exports/` - generated export files.

The backend automatically creates these folders at startup. If an older database exists at `BACKEND/data/aether.sqlite3`, the app copies it to `BACKEND/data/database/aether.sqlite3` during startup.

## Database Tables

The SQLite database is initialized automatically and includes:

- `users` - account email, display name/username, salted password hash, settings JSON, profile image metadata, created timestamp, and updated timestamp.
- `sessions` - hashed bearer session tokens linked to users.
- `uploads` - room upload metadata including file path, content type, width, height, and owner.
- `tours` - generated design metadata, saved/favorite flags, source image path, redesign image path, panorama path, and thumbnail path.
- `user_history` - account activity events such as account creation, sign-in, profile updates, password changes, uploads, design generation, saves, favorites, and deletions.

Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-user salt before being stored.

## Account Settings

The profile/settings page supports:

- Updating the displayed username.
- Viewing the registered email ID.
- Uploading a profile picture without recompression.
- Switching between dark and light mode.
- Viewing recent account activity.
- Updating notification/preference toggles already present in the UI.
- Changing the account password.

Profile pictures accept:

- JPG/JPEG
- PNG
- WebP

The maximum profile picture size is 25 MB. The uploaded bytes are written directly to disk after validation, so the app preserves the original file quality.

## Main Workflow

1. Register or log in.
2. Upload a room image.
3. Pick a room type and style.
4. Add requirements.
5. Generate the design.
6. Review the redesign and open the 3D walkthrough.
7. Save, favorite, export, or delete the result.

## API Overview

- `GET /api/health` - health check.
- `POST /api/auth/register` - create an account.
- `POST /api/auth/login` - sign in.
- `POST /api/auth/logout` - clear the current session.
- `GET /api/me` - return current profile, stats, and recent account history.
- `PATCH /api/me` - update username and profile settings, including theme preference.
- `PATCH /api/me/password` - change password.
- `POST /api/me/profile-image` - upload an original-quality profile picture.
- `POST /api/upload` - upload a room photo.
- `POST /api/tours` - generate a redesign and panorama.
- `GET /api/tours` - list the current user's tours.
- `GET /api/tours/{tour_id}` - load one tour.
- `POST /api/tours/{tour_id}/save` - toggle saved status.
- `POST /api/tours/{tour_id}/favorite` - toggle favorite status.
- `DELETE /api/tours/{tour_id}` - delete a tour.
- `GET /api/tours/{tour_id}/export/{kind}` - export an image, panorama, report, or JSON payload.
- `GET /media/{path}` - serve generated media from `BACKEND/data/`.

## Model Note

This build does not call a hosted AI image model. The redesign is generated locally with Pillow and NumPy, then converted into a panorama for the viewer.

## Troubleshooting

- If the app does not start, confirm the virtual environment exists and dependencies are installed.
- If PowerShell blocks `run.ps1`, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and then run `.\run.ps1` again.
- If port `8000` is already in use, stop the other process or start Uvicorn manually with another port, for example `--port 8001`.
- If `python` opens Microsoft Store, install Python from python.org and make sure Python is on PATH.
- If uploads fail, use JPG or PNG under 20 MB for room photos.
- If profile image upload fails, use JPG, PNG, or WebP under 25 MB.
- If login fails after deleting files under `BACKEND/data/`, register a new local account because the SQLite database was removed.
- If the viewer is blank, confirm a tour was generated and the panorama file exists in `BACKEND/data/tours/`.
- If the browser says the site cannot be reached, make sure the terminal running Uvicorn is still open and that `http://127.0.0.1:8000/api/health` returns `{"ok":true}`.
- If the health check works but the browser keeps opening an old nested page, open `http://127.0.0.1:8000/app/` directly and hard refresh the browser tab.

## Git Notes

`BACKEND/data/` is intentionally ignored by Git because it contains local accounts, profile images, uploaded rooms, generated designs, and exported files. A fresh clone starts with an empty local database that is created on first run.
