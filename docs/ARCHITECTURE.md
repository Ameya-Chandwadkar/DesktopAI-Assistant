# NOVA architecture (Phase 1)

## Two machines, two roles

| | **Dell Latitude 5400** (development) | **Lenovo LOQ** (target) |
|---|---|---|
| Purpose | Write/debug code with Claude, run automated tests | Run NOVA day to day |
| Needs | Python 3.12, `requirements-dev.txt`, Claude Pro / Claude Code | Python 3.12, `requirements.txt` only |
| Claude needed? | Yes (this is where you use your Claude Pro subscription) | **No.** NOVA never talks to Claude in Phase 1 |
| Transfer | `scripts\export_project.ps1` -> ZIP (or GitHub) | extract/clone, run `scripts\setup_lenovo.ps1` |
| NOVA's data | throw-away test data only | `%APPDATA%\NOVA\` (database, logs, speech models) |

Nothing in the code refers to either machine. Folders, browser, microphone, model location and custom apps
come from the Settings window (stored in SQLite) or `config.example.json` -> `--import-config`.

## What can be tested where

| Part | Dell (automated) | Needs the Lenovo (manual) |
|---|---|---|
| Command parser, action allowlist/validation, URL & path safety, file search, history, settings, engine logic (fake OS layer) | yes | - |
| Push-to-talk state machine (fake audio + fake recogniser) | yes | - |
| UI wiring (headless Qt) and how it looks (screenshot on Dell) | yes | look & feel on the Lenovo's screen/DPI |
| Real microphone + Vosk accuracy | no | **yes** |
| Launching *its* installed Chrome / VS Code / Word, default PDF viewer | no (different PC) | **yes** |
| The ZIP -> venv -> `--check` install procedure | rehearsed on the Dell in a clean folder | confirm on the real PC |

## Layers

```
 UI (PySide6)            nova/ui/          panel, settings, history, background workers
    │  text (typed or recognised)
    ▼
 Assistant               nova/controller.py   one utterance in -> Outcome out; keeps the pending
    │                                          result list ("pick number 2"); writes history
    ├─► LocalParser      nova/nlu/parser.py   deterministic text -> Action (or None)
    ▼
 Action  (name + args)   nova/actions/models.py
    │
    ▼
 Registry                nova/actions/registry.py   ALLOWLIST + strict argument validation
    │
    ▼
 ActionEngine            nova/actions/engine.py     the only code that runs actions
    ├─► files/search.py, files/safety.py            partial-name search; extension + folder rules
    ├─► actions/apps.py                             spoken name -> installed .exe
    ├─► actions/web.py                              URL validation (http/https only)
    └─► actions/system.py   (WindowsSystem)         the ONLY module that touches the OS

 Speech                  nova/speech/       mic.py (capture) -> ptt.py (push-to-talk) -> vosk_backend.py
 Storage / config        nova/db.py, nova/config.py, nova/paths.py, nova/log.py
```

Everything above `system.py` and below the UI is Qt-free and runs in plain `pytest`.

### Data flow for "find resume pdf"
1. Mic button held -> `MicCapture` streams 16 kHz audio *in memory* -> `PushToTalk` feeds Vosk -> partial text shown live.
2. Button released -> final text -> `Assistant.submit(text, "voice")` on a worker thread.
3. `LocalParser` -> `Action("search_files", {query:"resume", kind:"pdf"})`.
4. `registry.validate()` checks name, argument names, types, lengths.
5. Engine searches configured folders -> 0 hits: "not found"; 1+ hits: result list (`NEEDS_CHOICE`).
6. User clicks an entry or says "number two" -> `Action("open_file", {path})` -> path re-validated
   (inside configured folder? allowed extension? still exists?) -> `os.startfile`.
7. Result + history entry shown / saved.

## Safety model

* **Allowlist, no escape hatch.** Exactly five actions exist: `open_url`, `open_youtube`, `open_app`,
  `search_files`, `open_file`. There is no "run command"/"run code" action, so even a future LLM can only
  choose from these. A test asserts the allowlist contents.
* **No shell.** Apps start via `subprocess.Popen([exe, ...])` (a list, `shell=False`) or `os.startfile`.
  App names are matched against a fixed catalogue + the user's custom apps, never executed as typed.
* **URLs**: only `http`/`https`, valid host, no embedded credentials (`https://google.com@evil.com`), no
  control characters. `file:`, `javascript:`, `ms-settings:` etc. are refused.
* **Files**: only inside folders in Settings (adding a folder = explicit authorisation); `..` traversal and
  symlinks/junctions are not followed; only document/image extensions open, so `.exe/.bat/.ps1/.lnk/.vbs`
  can never be "opened" via a file search.
* **Confirmation gate**: `ActionSpec.requires_confirmation` makes the engine refuse until confirmed. No Phase 1
  action is destructive, so none uses it yet; it is tested and ready for Phase 3 (delete/overwrite/send).
* **Privacy**: raw audio is never written to disk. Logs contain action names/status/argument *names*, not
  what you said or which files. Command history (what you said) is stored locally and can be switched off or cleared.
* **Secrets**: none needed in Phase 1. Phase 2 reads the API key from an environment variable only.

## Threading
UI thread only touches widgets. File search/command execution and model loading run in `QThreadPool`;
audio capture + recognition run in one `PushToTalk` thread whose callbacks are re-emitted as Qt signals
(`SpeechBridge`). `Database` is protected by a lock.

## Phase 2 extension points (not built yet)
* `nlu/llm.py`: runs only when `LocalParser.parse()` returns `None`; must return the same `Action` objects, which
  go through the same `validate()` -> engine path.
* Optional TTS and wake word attach to `Assistant`/`PushToTalk` without touching the engine.
* `faster-whisper` can implement the `Recognizer` protocol in `speech/vosk_backend.py` (CUDA on the RTX 3050).
