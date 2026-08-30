# Hashemwise

A self-hosted Telegram bot for tracking shared expenses in a group — a Splitwise
substitute that depends on nothing but Telegram's own API. SQLite for storage,
one container to run, and **no inbound ports**: it uses long polling, so nothing
listens on your server and no firewall rule is needed.

## What it does

- Records expenses: amount, description, who paid, who shares it, split equally
  or by exact amounts.
- Records settlements when someone actually hands money over.
- Shows each person's net position and the shortest list of payments that
  settles the whole group.
- Runs many groups at once, each with its own currency, language and members.
- English and Persian, chosen per group.
- Corrections without rewriting the past: entries are voided, never deleted, and
  an edit records a replacement that points back at what it replaced.

## Correctness

The arithmetic is the point of this project, so it is worth being explicit about
how it is protected.

**Money is never a float.** Every amount is an `int` count of minor units —
Toman for IRT, cents for USD/EUR/GBP. `0.1 + 0.2 != 0.3` in binary floating
point, and a ledger built on that drifts until its own consistency checks fail
at random. There is no `REAL` column in the schema and a test asserts it stays
that way.

**Splits are exact.** `split_equal` uses `divmod` and distributes the remainder
deliberately, starting from the payer, so `sum(shares) == total` holds for every
input rather than almost always. An uneven split is shown before it is saved.

**Balances sum to zero, or nothing is shown.** `net(u) = paid - owed + sent -
received`, and a group's nets must sum to exactly zero. If they ever do not, the
data is corrupt: the bot refuses to display the numbers and alerts the
administrator rather than showing plausible wrong figures.

**1,187 tests**, including Hypothesis property tests over thousands of randomly
generated ledgers — every one must settle to exactly zero in at most `n-1`
payments — and worked examples checked against arithmetic done on paper.

---

# Installation

First, create your bot: message [@BotFather](https://t.me/BotFather), send
`/newbot`, and keep the token. Get your own numeric user id from
[@userinfobot](https://t.me/userinfobot).

You can leave BotFather's privacy mode **on** (the default). Every free-text
step is asked with a forced reply, which Telegram delivers to the bot regardless.

Then pick one of the three routes below.

## Option 1 — One line, fully automated (recommended)

On any Debian or Ubuntu server, paste this and press enter:

```bash
curl -fsSL https://raw.githubusercontent.com/tahashemi/hashemwise/main/install.sh | sudo bash
```

It installs Docker if missing (from Docker's own GPG-signed repository), clones
the project to `/opt/hashemwise`, **asks you for your bot token and Telegram
id**, writes them to a `.env` readable only by root, builds the image, starts
the bot, and waits until Telegram has actually accepted the token before telling
you it worked.

Re-running the same command updates to the latest version. Your ledger and your
`.env` are left alone.

To supply the answers without being prompted — for scripting or a fresh VM
image:

```bash
curl -fsSL https://raw.githubusercontent.com/tahashemi/hashemwise/main/install.sh | sudo BOT_TOKEN=123456:AA... SUPER_ADMIN_ID=123456789 bash
```

> Piping a script into `sudo bash` executes whatever the URL serves. If you would
> rather read it first — a good habit for any installer, this one included —
> download it, read it, then run it:
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/tahashemi/hashemwise/main/install.sh -o install.sh
> ```

| Setting | How to change it |
|---|---|
| Install location | `INSTALL_DIR=/srv/hashemwise` before `bash` |
| Branch | `BRANCH=develop` before `bash` |
| Proxy to Telegram | `TELEGRAM_PROXY=socks5://host:1080` before `bash` |

## Option 2 — Docker, by hand

For anyone who would rather run the steps themselves.

```bash
git clone https://github.com/tahashemi/hashemwise.git
```

Then, inside the clone, copy `.env.example` to `.env` and set `BOT_TOKEN` and
`SUPER_ADMIN_ID` in it. Keep `DB_PATH=/app/data/ledger.db` — it must sit inside
the mounted volume, or the ledger is written into the container and lost on the
next rebuild.

```bash
mkdir -p data && sudo chown -R 10001:10001 data
```

That `chown` is not optional. The container deliberately runs as unprivileged
uid `10001`, so a root-owned `data/` leaves the bot unable to create its
database.

```bash
docker compose up -d --build
```

Useful afterwards:

```bash
docker compose logs -f
```

`docker compose restart` restarts it, `docker compose down` stops it while
leaving the ledger in `./data`, and `docker compose up -d --build` applies an
update after a `git pull`.

## Option 3 — Plain Python, no Docker

Python 3.11 or newer. Nothing here needs a compiler.

```bash
git clone https://github.com/tahashemi/hashemwise.git
```

Inside the clone, create a virtual environment and install the runtime
dependencies:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill it in. For this route set
`DB_PATH=data/ledger.db` — a path relative to the project — not the `/app/...`
path Docker uses. Then run it:

```bash
mkdir -p data && .venv/bin/python -m src.main
```

That runs in the foreground. To keep it alive across reboots, install it as a
systemd service at `/etc/systemd/system/hashemwise.service`:

```ini
[Unit]
Description=Hashemwise expense bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/hashemwise
ExecStart=/opt/hashemwise/.venv/bin/python -m src.main
EnvironmentFile=/opt/hashemwise/.env
Restart=always
RestartSec=10

# The bot needs nothing beyond its own directory and outbound network.
User=hashemwise
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/hashemwise/data

[Install]
WantedBy=multi-user.target
```

Create the user it runs as, hand it the directory, protect the secrets file, and
start it:

```bash
sudo useradd --system --no-create-home hashemwise
```

```bash
sudo chown -R hashemwise:hashemwise /opt/hashemwise && sudo chmod 600 /opt/hashemwise/.env
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now hashemwise
```

```bash
sudo journalctl -u hashemwise -f
```

Updating on this route: `git pull`, then
`.venv/bin/pip install -r requirements.txt`, then
`sudo systemctl restart hashemwise`.

---

# Using it

1. Add the bot to your Telegram group.
2. You get a private message with an **Authorize** button — press it. (Or run
   `/auth` in the group; it only works for `SUPER_ADMIN_ID`.)
3. Run `/setup` in the group: pick a currency, pick a language, then send the
   member names one per line.
4. Each person runs `/join` once and taps their own name to link their Telegram
   account. Anyone who never joins stays a named member and still appears in
   every split.
5. `/expense` to record something, `/settle` when money changes hands,
   `/balances` to see where everyone stands.

## Commands

| Command | Who | What |
|---|---|---|
| `/start` | anyone | short introduction |
| `/help` | anyone | what every command does |
| `/setup` | group members | currency, language, members |
| `/join` | group members | link your Telegram account to a name |
| `/members` | group members | list members |
| `/expense`, `/add` | group members | record an expense |
| `/settle` | group members | record a payment between two people |
| `/balances` | group members | net positions and suggested payments |
| `/history` | **bot admin only** | every entry with its per-person breakdown, and delete |
| `/cancel` | anyone | abandon the current wizard |
| `/auth`, `/deauth`, `/groups` | **bot admin only** | manage group access |

## Configuration

| Variable | Required | Meaning |
|---|---|---|
| `BOT_TOKEN` | yes | from @BotFather |
| `SUPER_ADMIN_ID` | yes | your numeric Telegram user id; the only account that may authorize groups, view `/history` or delete entries |
| `DB_PATH` | no | `/app/data/ledger.db` under Docker, `data/ledger.db` otherwise |
| `TELEGRAM_PROXY` | no | `http://…` or `socks5://…` where `api.telegram.org` is unreachable |
| `LOG_LEVEL` | no | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

## Notes on behaviour

**A group's currency locks once it has entries.** Amounts are stored as minor
units scaled to that currency and there is no exchange rate to reinterpret them
with, so changing it would silently alter what every historical figure means.
Re-running `/setup` on a live group skips to the language step.

**The equal-split remainder goes to the payer.** 100 across three people is
34/33/33 and the odd unit lands on whoever paid. Deterministic, at most `n-1`
minor units, and shown on the confirmation screen every time.

**Suggested payments are few, not provably fewest.** The greedy reduction always
produces at most `n-1` transfers instead of the `n×(n-1)/2` pairwise debts.
Minimum cash flow is NP-hard in general, so the bot does not claim optimality.

**Members are added by name, not @username.** Telegram gives bots no way to turn
a username into a user id. `/setup` creates named members and `/join` links
accounts, because a `/join` command carries its sender's id.

**An in-progress wizard does not survive a restart.** State is held in memory to
avoid running a second service. Nothing is written until you press Confirm, so a
lost wizard loses no ledger data.

## Backing up

The whole ledger is one SQLite file, and `.backup` is safe to run while the bot
is live:

```bash
sqlite3 /opt/hashemwise/data/ledger.db ".backup '/root/hashemwise-backup.db'"
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```

| Module | Responsibility |
|---|---|
| `src/money.py` | parsing, formatting, splitting — pure, no I/O |
| `src/debt_engine.py` | greedy reduction — pure, integer only |
| `src/ledger.py` | net balances and the sign convention |
| `src/db/` | schema, connection PRAGMAs, every SQL statement |
| `src/render.py` | message text — pure |
| `src/handlers/` | the Telegram wizards |

`money.py`, `debt_engine.py` and `render.py` import neither aiogram nor the
database, so all the arithmetic and all the wording are testable without a bot
token, a network or a container.

## Licence

MIT.
