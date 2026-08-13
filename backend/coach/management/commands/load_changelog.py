"""Load changelog entries from files in the tree, idempotently, on every boot.

Changelog rows used to arrive as data migrations, and 57 of `coach`'s 74
migrations were exactly that. Combined with the house rule that every
builder-visible change ships a `ChangelogEntry` row in the same pull request,
that meant *every substantive pull request wrote a migration* — which is why
two parallel sessions collided on the migration leaf essentially every time.
`check_migration_leaf` detects that collision. This removes the reason it
happens, and hands migrations back their actual job, which is schema.

One file per entry, and that is the whole mechanism: two sessions writing two
entries write two different files and there is nothing to collide on. A single
`entries.json` would have moved the collision rather than removed it — both
sessions appending to the end of one array is the same conflict wearing a
different extension.

Idempotent on `(shipped_on, title)`, which is the key the migrations already
used: `get_or_create`, never update. So an entry edited in the admin keeps the
edit through the next deploy — the file is where a row is *born*, not a
statement of what it must say forever, and the admin stays the place to fix a
typo in something already published.

What this does not do is move `0001`–`0070`. Rewriting shipped migrations is
not on the table, so the old rows keep arriving the old way and this is the
rule for new ones; the win accrues from the next pull request onward rather
than retroactively.

Strict on a malformed file — a bad entry fails CI through
`ChangelogFileTests`, before it can reach a deploy. `start.sh` still calls this
with `|| true`, on the same reasoning as `ensure_admin`: a changelog is not
worth refusing to boot over.
"""

import re
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from coach.models import ChangelogEntry

# coach/management/commands/ -> coach/changelog/
ENTRIES_DIR = Path(__file__).resolve().parents[2] / "changelog"

# Entries are date-prefixed by convention, which is also what keeps README.md
# out of the glob without needing a special case for it.
ENTRY_GLOB = "[0-9]*.md"

REQUIRED = ("shipped_on", "kind", "title")


class ChangelogFileError(CommandError):
    """A file in the entries directory that cannot become a row.

    A subclass so tests can be specific about it, and a `CommandError` so the
    command exits non-zero without a traceback nobody needs.
    """


def _unwrap(body: str) -> str:
    """Collapse every run of whitespace to one space.

    `components/Changelog.tsx` renders the body as a single `<p>`, so a
    paragraph break has nowhere to land and HTML would eat the newlines
    anyway. Doing it here rather than at the renderer means the file can be
    hard-wrapped for review while the row holds the same one-paragraph string
    the migrations wrote, so the two sources cannot drift into two shapes.
    """
    return re.sub(r"\s+", " ", body).strip()


def parse_entry(text: str, name: str) -> dict:
    """One file's text to the fields of one row, or raise saying which file.

    The header is three required keys and one optional, `key: value` per line.
    Deliberately not YAML: it would be a dependency for four keys, and the
    failure mode of a real YAML parser here — quietly reading `title: 3:15` as
    something other than a string — is worse than not having one.
    """
    if not text.startswith("---\n"):
        raise ChangelogFileError(
            f"{name}: expected a `---` header on the first line. "
            "See backend/coach/changelog/README.md for the shape."
        )

    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ChangelogFileError(f"{name}: the `---` header is never closed.")
    _, header, body = parts

    fields: dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ChangelogFileError(f"{name}: header line is not `key: value` — {line!r}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()

    missing = [key for key in REQUIRED if not fields.get(key)]
    if missing:
        raise ChangelogFileError(f"{name}: header is missing {', '.join(missing)}.")

    try:
        shipped_on = date.fromisoformat(fields["shipped_on"])
    except ValueError:
        raise ChangelogFileError(
            f"{name}: shipped_on is {fields['shipped_on']!r}, not a YYYY-MM-DD date."
        ) from None

    # Checked here rather than left to the model, because `choices` are not
    # enforced on write: `get_or_create` never reaches `full_clean`, so a typo
    # ships. One did — 0058 seeded a row as "ADDED" and the chip rendered with
    # no text at all, because the frontend looks the label up in a total map.
    if fields["kind"] not in ChangelogEntry.Kind.values:
        raise ChangelogFileError(
            f"{name}: kind is {fields['kind']!r}, which the frontend cannot "
            f"render. One of {', '.join(ChangelogEntry.Kind.values)}."
        )

    if len(fields["title"]) > 120:
        raise ChangelogFileError(
            f"{name}: title is {len(fields['title'])} characters; the column holds 120."
        )

    unwrapped = _unwrap(body)
    if not unwrapped:
        raise ChangelogFileError(f"{name}: the body is empty.")

    is_active = fields.get("is_active", "true").lower()
    if is_active not in ("true", "false"):
        raise ChangelogFileError(
            f"{name}: is_active is {fields['is_active']!r}; expected true or false."
        )

    return {
        "shipped_on": shipped_on,
        "kind": fields["kind"],
        "title": fields["title"],
        "body": unwrapped,
        "is_active": is_active == "true",
    }


def read_entries(directory: Path) -> list[dict]:
    """Every entry file in a directory, oldest filename first.

    Sorted so a fresh database creates rows in the same order the dates run —
    `ChangelogEntry` breaks a same-day tie on `-id`, so insertion order is the
    within-day ordering a reader sees, exactly as it was when the seeds were
    migrations applied in sequence.
    """
    if not directory.is_dir():
        return []
    return [
        parse_entry(path.read_text(encoding="utf-8"), path.name)
        for path in sorted(directory.glob(ENTRY_GLOB))
    ]


class Command(BaseCommand):
    help = "Create any changelog entry in backend/coach/changelog/ that is not already a row."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default=str(ENTRIES_DIR),
            help="Where the entry files live. Only tests should need this.",
        )

    def handle(self, *args, **options):
        entries = read_entries(Path(options["dir"]))
        created = 0
        for entry in entries:
            # `all_objects`, so an entry someone retired by soft-deleting it
            # does not come back from the dead on the next boot.
            _, was_created = ChangelogEntry.all_objects.get_or_create(
                shipped_on=entry["shipped_on"],
                title=entry["title"],
                defaults={
                    "kind": entry["kind"],
                    "body": entry["body"],
                    "is_active": entry["is_active"],
                },
            )
            created += was_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Changelog: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
                f"on file, {created} new."
            )
        )
