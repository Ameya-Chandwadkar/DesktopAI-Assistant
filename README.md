# NOVA - offline desktop voice assistant for Windows (Phase 1)

A small always-on-top panel you can talk to (push-to-talk) or type to. It opens websites, launches apps, searches your
folders for documents and opens them. Phase 1 is **fully offline and needs no AI subscription or API key**.


## What works in Phase 1
* Dark, compact, draggable, always-on-top window with minimize/close; remembers its position.
* Push-to-talk mic button (Vosk, offline) with live text; typed commands too.
* Shows what it heard, the action it chose, and the result (colour-coded).
* Open YouTube / search YouTube / any URL, in Chrome, Edge, Firefox or your default browser.
* Launch Notepad, VS Code, Chrome, Edge, Calculator, Word, Excel, … plus your own apps (Settings).
* Search configured folders by partial filename, open the match in its default app (Word, PDF viewer, …).
* Graceful messages for: missing files, apps not installed, ambiguous names (pick from a list or say "number two"),
  microphone/permission problems, missing speech model.
* Command history (re-run, clear, or turn off) and a Settings window.

## Things you can say / type
| Say | Does |
|---|---|
| `open notepad`, `launch vs code`, `open chrome`, `open file explorer` | starts the app |
| `open youtube` | opens YouTube |
| `search youtube for lo-fi music` · `play jazz on youtube` | YouTube search |
| `open github` · `go to example dot com` · `open https://example.org` | opens the site |
| `find resume` · `find resume pdf` · `search for the file called project plan` | lists matching files |
| `open file project plan` · `open the word document budget` · `open budget` | opens the match (asks if several match) |
| `number two` · `the last one` · `cancel` | answers a list of matches |

Prefixes like "hey nova", "please", "can you" are ignored. Bare `search for X` means *files*. Custom app/site names you add in
Settings work the same way (`open college portal`).

## Quick start - developer (Dell)
```powershell
cd D:\DesktopAI-Assistant
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest          # 146 tests, runs headless, touches nothing on your PC
.venv\Scripts\python.exe -m nova            # run the app
.venv\Scripts\python.exe -m nova --check    # what works on this machine
```
Other CLI flags: `--download-model small|large`, `--list-mics`, `--import-config FILE`.

## Installing on the Lenovo
See **[docs/DEPLOY_LENOVO.md](docs/DEPLOY_LENOVO.md)** (export ZIP -> extract -> `setup_lenovo.ps1` -> download model -> mic permission -> checklist).
Architecture and the Dell/Lenovo split: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Configuration
Machine-specific settings (search folders, browser, mic, custom apps/sites) live in the Settings window and are stored in
SQLite at `%APPDATA%\NOVA\nova.db`. `config.example.json` shows every key; load one with `python -m nova --import-config config.json`.
`NOVA_DATA_DIR` moves the data folder. See `.env.example`.

## Safety (summary)
Only five allowlisted actions exist and every one is argument-validated; no shell, no arbitrary commands or code; files only
from folders you configured and only document/image types; URLs only http/https; audio never saved; logs hold no transcripts.
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#safety-model).

## Project layout
```
nova/            application package (ui/, speech/, actions/, files/, nlu/, config, db, controller…)
tests/           146 pytest tests (parser, allowlist, engine, file safety, speech state machine, headless UI)
scripts/         export_project.ps1 (Dell) · setup_lenovo.ps1 · run_nova.bat · run_nova_debug.bat
docs/            ARCHITECTURE.md · DEPLOY_LENOVO.md
```

## Honest status
| Verified how | What |
|---|---|
| Automated tests on the Dell (146 pass, 1 skipped - symlink privilege) | parser, allowlist, URL/path safety, file search & ranking, engine paths incl. all error cases (with a fake OS layer), history, settings, push-to-talk logic (fake audio), zip-slip protection, headless UI wiring |
| Manually on the Dell | window renders correctly (screenshot reviewed); app starts and exits cleanly; `--check` finds this PC's apps/folders; Notepad launches through the real launcher; ZIP export -> clean folder -> fresh venv -> `--check` + all tests pass using only `PySide6-Essentials` |
| **Not tested yet** | real microphone capture and Vosk recognition (model not downloaded here), speech accuracy, anything on the Lenovo, launching Chrome/VS Code/Word and default-app opening of real files via the UI, DPI/multi-monitor behaviour. Use the checklist in `docs/DEPLOY_LENOVO.md` |

Known limits: Vosk's small model is weak with unusual words/filenames (typed search or the `large` model help); filename
matching is substring-based, not fuzzy; a UI "recording" colour only appears once the mic has actually opened (press, wait for
red, then speak).

## Claude Pro vs. the Claude API (for Phase 2)
* **Claude Pro** is a subscription for the Claude apps and Claude Code. You use it on the **Dell** to help write this code. It does not
  include API access, and the Lenovo does not need it.
* The **Claude API** is a separate pay-per-use service (an API key from the Anthropic Console, billed by tokens). If NOVA ever calls
  Claude for natural-language understanding (Phase 2, optional), it would use an API key stored in an environment variable on the Lenovo.
* Phase 1 uses neither. Opening sites, launching apps and searching files are local code and will stay local in Phase 2; the LLM would
  only run when the local parser doesn't understand a sentence.

## Roadmap
Phase 2 (AI & voice) starts only after you approve Phase 1 following Lenovo testing.
