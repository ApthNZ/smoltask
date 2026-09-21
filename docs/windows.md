# Running smoltask on Windows 11

smoltask is a small Python web app with a SQLite file behind it and no build
step, so on a laptop the simplest thing is to run it directly. Docker is
covered at the end, but you don't need it — and for this app the plain Python
route has a real advantage, explained under *Which day is it* below.

Nothing in the app is platform-specific — no POSIX-only calls, and every
dependency ships a Windows wheel.

## What you need

- **Python 3.10 or newer.** CI runs the test suite on 3.10 and the container
  image is built on 3.14, so anything in that range is fine.
- **Git**, optionally. You can download the code as a zip instead.

Install both from an ordinary PowerShell window:

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
```

Close and reopen PowerShell afterwards so the new `PATH` takes effect.

> **`py` or `python`?** This guide uses `py`, the launcher that ships with the
> python.org and winget installers and picks the right version when you have
> several. If `py` is not recognised, `python` works just as well — substitute
> it throughout.
>
> **If `python` opens the Microsoft Store instead of running:** that's the
> Windows app-execution alias. Use `py`, or turn the alias off under
> Settings → Apps → Advanced app settings → App execution aliases.

## Install

```powershell
cd $HOME
git clone https://github.com/ApthNZ/smoltask.git
cd smoltask
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No `git`? Download <https://github.com/ApthNZ/smoltask/archive/refs/heads/main.zip>,
right-click → Extract All, then `cd` into the extracted folder and run the last
two commands.

> **Why `.\.venv\Scripts\python.exe` and not `activate`?** Activating a virtual
> environment runs a PowerShell script, and a default Windows 11 install blocks
> that with *"running scripts is disabled on this system"*. Calling the venv's
> `python.exe` directly sidesteps the whole problem. If you would rather
> activate, either run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy
> Bypass` first (it lasts only for that window), or use `cmd` and
> `.\.venv\Scripts\activate.bat`.

## Run it

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --port 8108
```

Then open <http://127.0.0.1:8108>.

The first run creates `smoltask.db` in the project folder and the page is
empty, which is the correct starting state — there is no demo fixture, because
the first thing you should see is your own first task. The capture line has
focus: type, press Enter, and it exists. The keys are in the
[README](../README.md); the two worth knowing on day one are `p` to run triage
and `Ctrl+Z` to undo a tick.

Stop the server with `Ctrl+C`.

## Which day is it

Every "today" question in the app — the day's tick count, due today, the
morning ritual, a date turning red — is answered against the *server's* local
date, and the server is this laptop. Run it the way above and it simply uses
your Windows clock and timezone, which is right by definition. This is the one
place the Python route is genuinely easier than Docker, where the container
starts in UTC and has to be told otherwise.

If the page ever toasts *"This server thinks today is … ; your machine says …"*,
the two disagree and the app is telling you rather than being quietly wrong.
Running natively that means either Windows' own date/timezone is wrong
(Settings → Time & language), or you changed the timezone while uvicorn was
running — restart the server after changing it.

## A shortcut so you don't type that every time

Save this as `smoltask.bat` in the project folder:

```bat
@echo off
cd /d "%~dp0"
start "" http://127.0.0.1:8108
.\.venv\Scripts\python.exe -m uvicorn app:app --port 8108
```

Double-clicking it starts the server and opens your browser. A console window
stays open while it runs; closing that window stops the app.

To start it automatically when you log in, press `Win+R`, run `shell:startup`,
and put a shortcut to `smoltask.bat` in the folder that opens. For a list you
are meant to look at every morning, that is worth doing.

## Where your data lives

Everything is in `smoltask.db` in the project folder — open tasks and the whole
archive. Back it up by copying that file, but stop the server first or you may
copy it mid-write. You will also see `smoltask.db-wal` and `smoltask.db-shm`
beside it while the app is running; they disappear on a clean shutdown and
don't need copying separately.

To keep the database somewhere else, set `SMOLTASK_DB` before starting:

```powershell
$env:SMOLTASK_DB = "$HOME\OneDrive\smoltask\smoltask.db"
.\.venv\Scripts\python.exe -m uvicorn app:app --port 8108
```

The folder must already exist. Putting it in OneDrive gives you backups for
free, though don't run two machines against the same synced file at once.

If you use the `.bat` shortcut, put the same line above the `uvicorn` line in
`cmd` form:

```bat
set "SMOLTASK_DB=%USERPROFILE%\OneDrive\smoltask\smoltask.db"
```

## Updating

```powershell
cd $HOME\smoltask
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then **restart uvicorn** — Python is not reloaded under a running server — and
**hard-reload the page** with `Ctrl+F5`, because the browser caches `app.js`
and `app.css`. A pull that appears to have changed nothing is almost always one
of those two steps missing.

Your `smoltask.db` is untouched by a pull — it's not tracked in git.

## Reaching it from another device

By default the server listens only on `127.0.0.1`, so nothing else on the
network can reach it. That is the right default: **smoltask has no login of any
kind**, so anyone who can open the page can read and edit every task, and a
to-do list says more about your work than most things you would casually
publish.

If you do want it on your home network:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8108
```

Windows Defender Firewall will prompt the first time — allow it on **private**
networks only, never public. Other devices then use `http://<your-laptop-ip>:8108`;
find the address with `ipconfig`. Don't do this on café or hotel wifi, and
think twice on a network you share with anyone.

## Troubleshooting

**`[Errno 10048] error while attempting to bind`** — something already has port
8108. Run it on another port with `--port 8118`, or find the culprit:

```powershell
Get-NetTCPConnection -LocalPort 8108 -State Listen |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Get-Process -Id $_ }
```

Most often it is a second copy of smoltask you forgot was running — check
before killing anything, because that one holds your database open.

**`.\.venv\Scripts\python.exe` is not recognised** — this reads like a missing
program, but PowerShell uses the same wording for a **path that does not
exist**. Python is fine; the virtual environment isn't there. Either the
`py -m venv .venv` step was skipped or it failed, or you are not in the project
folder. Run `dir` — you should see `app.py` and a `.venv` folder. If `.venv` is
missing:

```powershell
cd $HOME\smoltask
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**`py` is not recognised** — Python isn't installed, or PowerShell was open
before you installed it. Reopen PowerShell and try `python` instead; if both
fail, reinstall with the winget command above.

**The page loads but is blank, or looks unstyled** — a stale cache. Hard-reload
with `Ctrl+F5`.

**`ModuleNotFoundError: No module named 'fastapi'`** — you're running the system
Python rather than the one in `.venv`. Use the full `.\.venv\Scripts\python.exe`
path.

**Typing a letter ranks a task instead of writing one** — focus is in the list,
not the capture line. Plain letters are text in the capture line and shortcuts
everywhere else. Press `/` to get back to the line.

**The morning ritual didn't run** — it runs on the first load of a day that has
anything waiting, and only once. `p` runs it on demand whenever you want it.

**A date is red and you don't know why** — a date needs a human for exactly two
reasons: it has passed, or the task is ranked **Never**. Nothing else on the
page is red.

## Or with Docker Desktop

If you already run Docker Desktop, the repo's compose file works as-is:

```powershell
docker compose up -d --build
```

Then <http://127.0.0.1:8108>. Set `SMOLTASK_PORT` to change the port.

Three things differ from the Python route:

- **You must set `TZ` yourself.** A container with no timezone runs in UTC, and
  because every "today" in this app is the server's today, an unset `TZ` makes
  the page a day out for part of every day. Create a `.env` file next to
  `docker-compose.yml` with the IANA name for where you live — `TZ=Europe/London`,
  `TZ=America/Chicago` — not the Windows label like *GMT Standard Time*.
- It publishes on all interfaces, so the whole network can reach it. Given
  there is no login, change the ports line to `"127.0.0.1:${SMOLTASK_PORT:-8108}:8000"`
  if you want it kept to the laptop. The comments at the top of the compose
  file say the same thing.
- The container is pinned to uid 1000, which matters on Linux and means nothing
  on Windows. It keeps the database on a bind mount at `.\data`; if Docker
  Desktop reports a permissions error writing `/data`, delete the
  `user: "1000:1000"` line from `docker-compose.yml`.

For a laptop, though, the plain Python route above is lighter, starts faster,
and gets the date right without being told.
