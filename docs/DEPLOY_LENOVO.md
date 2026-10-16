# Deploying NOVA on the Lenovo LOQ

Every step says **which laptop** to use. Commands are PowerShell unless noted. Replace `<you>` with your Windows user name.

> The Lenovo does **not** need Claude, Claude Code, a Claude subscription, an API key, Git or any dev tools.
> It only needs Python 3.12 and an internet connection for the one-time install.

---
## Step 1 - Package the project  (**Dell**)

From the project folder `D:\DesktopAI-Assistant`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export_project.ps1
```
This creates `dist\nova-<date>-<time>.zip` (no `.venv`, no database, no models, no secrets, ~60 KB).

*Alternative - GitHub:* create a **private** repository, push, and `git clone` it on the Lenovo (install Git there first:
`winget install Git.Git`). `.gitignore` already keeps `.venv`, models, databases, logs, `.env` and `config.json` out.

## Step 2 - Move it  (**Dell -> Lenovo**)
Copy the ZIP by USB stick, OneDrive/Google Drive, or email to yourself.

## Step 3 - Install Python 3.12  (**Lenovo**)
Check first - it may already be installed:
```powershell
py -3.12 --version
```
If that fails:
```powershell
winget install -e --id Python.Python.3.12
```
(or download from https://www.python.org/downloads/ and tick **Add python.exe to PATH**). Open a **new** PowerShell window afterwards.

## Step 4 - Extract  (**Lenovo**)
Right-click the ZIP -> *Extract All* to e.g. `C:\Users\<you>\NOVA` (you get `C:\Users\<you>\NOVA\nova\...`).
Avoid OneDrive-synced folders: they would try to sync the 300 MB virtual environment.

## Step 5 - Set up the environment  (**Lenovo**)
```powershell
cd C:\Users\<you>\NOVA\nova
powershell -ExecutionPolicy Bypass -File scripts\setup_lenovo.ps1
```
* `-ExecutionPolicy Bypass` applies only to this one command; it does not change your system's policy.
* It creates `.venv` inside the project, installs `requirements.txt` (PySide6-Essentials, Vosk, sounddevice) and
  runs `python -m nova --check`. Nothing is installed system-wide.
* Add `-WithDev` if you also want to run the tests on the Lenovo.

Expected `--check` result: `PASS` for Python/PySide6/vosk/microphone; `WARN` for the speech model (next step).
You can re-run it any time: `.venv\Scripts\python.exe -m nova --check`.

## Step 5b - Download the speech model  (**Lenovo**, needs internet)
**Recommended - Whisper** (accurate, ~480 MB, runs on the CPU; speech is transcribed ~1-3 s after you release the button):
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m nova --download-model whisper-small
```
Lighter: `--download-model whisper-base` (~140 MB, faster, less accurate).
Fallback: Vosk (40 MB, weak with accents/uncommon words): `--download-model vosk-small`.
Models go to `%APPDATA%\NOVA\models`. With engine = `auto` (Settings > Speech) NOVA uses Whisper when it is downloaded, otherwise Vosk.

Test the microphone and recognition without the UI (records 5 s in memory, saves nothing):
```powershell
.venv\Scripts\python.exe -m nova --mic-test
```

## Step 6 - Microphone permission  (**Lenovo**)
1. *Settings -> Privacy & security -> Microphone*: turn on **Microphone access** and **Let desktop apps access your microphone**
   (Python is a desktop app; if this is off you get "access denied" or silence).
2. *Settings -> System -> Sound -> Input*: speak and confirm the input level bar moves for the mic you want.
3. List what NOVA sees: `.venv\Scripts\python.exe -m nova --list-mics`. To use a non-default one, pick it in NOVA's
   *Settings -> Speech*.
4. Gaming laptops often expose several mics (array, headset, virtual). If NOVA says it "only heard silence", pick another.

## Step 7 - Run  (**Lenovo**)
```powershell
scripts\run_nova.bat          # no console window
scripts\run_nova_debug.bat    # with console - use this if nothing appears
```
Logs: `%APPDATA%\NOVA\logs\nova.log`. Optional: right-click `run_nova.bat` -> *Send to -> Desktop (create shortcut)*.
NOVA deliberately does **not** auto-start with Windows yet (that comes after Phase 1 is proven reliable).

## Step 8 - Configure for this PC  (**Lenovo**)
Open NOVA -> **⚙**:
* **Folders**: the folders NOVA may search/open from (defaults: Documents, Desktop, Downloads; OneDrive-redirected folders are detected). Add e.g. `D:\Study`.
* **General**: always-on-top, history on/off, preferred browser (`chrome` falls back to the default browser if missing).
* **Apps & sites**: add apps NOVA doesn't know (Spotify, a game launcher...) and sites ("college portal").
* **Speech**: microphone and model folder.

Or edit `config.example.json` -> save as `config.json` -> `.venv\Scripts\python.exe -m nova --import-config config.json`.

## Step 9 - Acceptance checklist  (**Lenovo**) - tick each one
Nothing below has been verified on the Lenovo yet.

| # | Do this | Expect |
|---|---|---|
| 1 | Start NOVA | small dark panel, top-right, mic button enabled after a few seconds ("Loading speech model…" first; note how long it takes) |
| 2 | Click another window | NOVA stays on top; unticking always-on-top in Settings lets it go behind |
| 3 | Drag the panel by its empty areas; minimize; close and reopen | moves; minimizes; reopens at the last position |
| 4 | Type `open notepad` / `open vs code` / `open chrome` | each app starts; if one isn't installed you get a clear "isn't installed" message |
| 5 | Type `open youtube`, `search youtube for lo-fi music`, `open github dot com` | opens in the chosen browser |
| 6 | Type `find <part of a real filename>` | list of matches; click one -> opens in its default app (try .docx, .pdf, .txt) |
| 7 | Search a name that matches several files, then say/type `number two` | the second one opens |
| 8 | Search a nonsense name | "couldn't find a file matching…" |
| 9 | Hold the mic, say **"open notepad"**, release | live text while speaking, then Notepad opens |
| 10 | Hold the mic, say **"search youtube for cats"** | YouTube results open |
| 11 | Tap the mic button very briefly | "too short - hold the button while you speak" |
| 12 | Mute the mic / disable it in Sound settings, try again | actionable message (silence / no microphone / privacy hint) |
| 13 | Open ≡ History; double-click an entry | list of past commands; re-runs it |
| 14 | Change a setting, close, reopen | setting persisted |

Please write down speech accuracy problems (what you said vs. what NOVA heard) - that decides whether we move to a bigger Vosk model or Whisper in Phase 2.

## Updating later
**Dell:** re-run `export_project.ps1`. **Lenovo:** extract the new ZIP *over* the existing folder (replace files). `.venv`, your
settings and your history are not in the ZIP, so they survive. If `requirements.txt` changed, re-run `setup_lenovo.ps1`.

## GPU (RTX 3050)
Phase 1 doesn't use the GPU: Vosk is CPU-only (the small model should need only a few hundred MB of RAM - confirm in Task Manager). In Phase 2, if you choose Whisper, `faster-whisper`
can use CUDA on the RTX 3050 (needs a current NVIDIA driver plus the CUDA/cuDNN runtime libraries its release requires - to be checked at that time); the `small`/`base`
models run on the CPU too. We'll decide that from your Step 9 accuracy notes, not in advance.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "running scripts is disabled" | use the exact `powershell -ExecutionPolicy Bypass -File …` form |
| `Python 3.12 was not found` | Step 3, then open a *new* PowerShell window |
| `pip install` fails | check internet/proxy; re-run the setup script (it resumes) |
| Nothing appears when starting | run `run_nova_debug.bat`; read `%APPDATA%\NOVA\logs\nova.log` |
| Mic button greyed out | status line under the panel says why (usually: speech model not downloaded - Step 5b) |
| "Couldn't open the microphone … access denied" | Step 6 privacy toggles |
| NOVA hears nothing / wrong text | pick another mic in Settings > Speech; speak after the button turns red; try the `large` model |
| "X doesn't seem to be installed" | install it, or add its `.exe` under Settings > Apps & sites |
| File not found though it exists | its folder isn't in Settings > Folders (or is deeper than 8 levels) |
