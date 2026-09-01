# Changelog

All notable changes to Hashemwise. Versions follow [semantic versioning](https://semver.org).

An update never rewrites your ledger. `schema.sql` is applied with
`CREATE TABLE/INDEX IF NOT EXISTS` on every start, so new tables and indexes
appear on their own. Any release that alters an existing column will say so
here, explicitly, along with what to do about it.

## 1.1.1

### Fixed

- **The installer failed on Debian with `no such release: 12 (bookworm)`.**
  `install.sh` sources `/etc/os-release` to identify the distribution, and
  Debian defines `VERSION="12 (bookworm)"` in there - which silently replaced
  the release tag the caller had asked for. The value is now captured as
  `RELEASE_TAG` before that file is sourced. A test asserts no variable in the
  installer collides with an os-release field.
- Installations made by an earlier version of the installer were shallow
  clones, which cannot check out an older tag. The installer now deepens them
  on the way past, so rolling back works on an existing install.

## 1.1.0

### Changed

- **`/history` is readable by everyone in the group.** It was previously
  restricted to the bot administrator, which meant ordinary members could see
  aggregate balances but never what they were personally charged for a given
  expense. Deleting an entry is still administrator-only, and the delete buttons
  are not rendered for anyone else.

### Added

- **An admin group panel in the bot's private chat.** `/groups` now opens an
  interactive list: authorize a group, revoke its access, delete it permanently
  behind a confirmation, or add one manually by chat id. Group management no
  longer requires being inside the group at the time.
- **A language toggle for the admin's private chat**, stored in the database, so
  the panel and admin notifications follow it.
- **`/version`**, reporting the running version.
- Documentation for updating an existing installation, and rolling back.

### Database

- New `settings` table. Additive, created automatically on the next start. No
  migration, no change to existing data.

## 1.0.0

First release.

- Expenses with equal or exact-amount splits, participant selection, and a
  confirmation screen showing every share before anything is written.
- Settlements, net balances, and a short list of payments that clears the group.
- Soft deletes and edits that supersede rather than overwrite.
- Multiple groups, each with its own currency, language and members.
- English and Persian.
- Integer minor units throughout; balances that must sum to zero or are not
  shown at all.
