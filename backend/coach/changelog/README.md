# Changelog entries

One file per entry. `manage.py load_changelog` turns each of them into a
`ChangelogEntry` row, and `start.sh` runs it on every boot, so an entry is live
the moment the deploy that carries it is.

**Write an entry here, not a migration.** Every builder-visible change still
owes a row in the same pull request that ships it — that rule has not moved.
What has moved is where the row is written. Until this directory existed the
only way to write one was a data migration, which meant every substantive pull
request touched the migration graph, which is why two parallel sessions
collided on the leaf essentially every time.

One file per entry is the point. Two sessions writing two entries write two
different files, and there is nothing to collide on.

## The shape

Filename: `YYYY-MM-DD-a-few-words.md`. The date prefix is what keeps this
README out of the loader's glob, so it is not decoration.

```markdown
---
shipped_on: 2026-08-14
kind: CHANGED
title: The coach knows how long it has been
---

Masterji could see your phase, your count and your streak, and not one date.
He now gets two facts: how long the current phase has been open, and how long
since your last complete day.
```

- `shipped_on` — the day the change reached builders, not the day you typed
  the row. The date on a changelog is a claim about the product.
- `kind` — one of `NEW`, `CHANGED`, `FIXED`, `METHOD`. Checked on load,
  because `choices` are not enforced on write and a typo once shipped a chip
  with no text on it.
- `title` — 120 characters, the column's limit.
- `is_active` — optional, defaults to `true`. `false` writes the row without
  showing it, for a change that is merged but not yet live.
- The body is everything after the header. Write it in the builder's language:
  what changed for them, and what did not. Wrap it however reads best in
  review — the loader collapses the wrapping, because the frontend renders the
  body as a single paragraph.

## Two things worth knowing

**Loading twice is a no-op.** The key is `(shipped_on, title)` and the loader
only ever creates. So editing a file after it has been deployed changes
nothing — to fix something already published, edit the row in the admin. The
file is where a row is born, not a statement of what it must say forever.

**Entries from before this directory are still in the migrations.**
`0001`–`0070` seeded 57 rows and they stay there; rewriting shipped migrations
is not on the table. So the full changelog lives in two places, and it stops
growing in the older one.
