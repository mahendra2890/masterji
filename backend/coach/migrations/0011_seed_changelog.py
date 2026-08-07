"""The changelog's first twenty-four entries — everything from the first
working build to the day the changelog itself shipped.

Seeded as data rather than typed into the admin so every environment (a
fresh clone, a preview deploy, production) tells the same story, and so the
history isn't one accidental `flush` away from being lost. Everything after
this is written in the admin.

Newest first below, inserted oldest first: entries share a `shipped_on`, and
the model orders by ("-shipped_on", "-id"), so the row created last leads
its day.
"""

from datetime import date

from django.db import migrations

SEED = [
    (
        date(2026, 8, 8),
        "NEW",
        "The changelog you're reading",
        "Masterji asks you for proof of work every evening, so he keeps a "
        "record of his own too. Every change worth noticing lands in this "
        "list — written from the admin, so an entry can appear the day it "
        "ships rather than the day someone remembers — and the link in the "
        "header carries a dot until you've read the newest one.",
    ),
    (
        date(2026, 8, 8),
        "CHANGED",
        "Leaving IDEA takes a route to customers, not ten names",
        "The gate out of IDEA used to ask for ten specific people you could "
        "reach. But the honest answer is often a group you can walk up to — "
        "the mess aunties on your campus, the three shops on your street — "
        "and that was getting refused for the wrong reason. Now Masterji asks "
        "who has the problem and how you'll get in front of the first few "
        "this week. A list of ten names still passes; it just isn't the only "
        "way through any more.",
    ),
    (
        date(2026, 8, 8),
        "FIXED",
        "Admin tables stop crowding themselves off-screen",
        "Behind the scenes: one long check-in could stretch its column until "
        "every other column fell off the right edge. Widths are capped now, "
        "so a row can be read at a glance.",
    ),
    (
        date(2026, 8, 7),
        "FIXED",
        "The record is there to be read, not glimpsed",
        "Check-in text in the phase drill-in and in the sidebar record was "
        "clipped to one line, and the part that mattered was always the part "
        "cut off. Both wrap now.",
    ),
    (
        date(2026, 8, 7),
        "NEW",
        "A cold start says so",
        "Masterji runs on a free instance that falls asleep, and the first "
        "request of the day can take half a minute to wake it. Instead of a "
        "blank screen you now get a note telling you he's on his way — in the "
        "app and on the admin.",
    ),
    (
        date(2026, 8, 7),
        "FIXED",
        "A dead session signs you out instead of breaking",
        "An expired or unreadable login cookie used to surface as a server "
        "error. Now it reads as what it is — signed out — and hands you the "
        "sign-in page.",
    ),
    (
        date(2026, 8, 7),
        "CHANGED",
        "One pane at a time on a phone",
        "Stacked, the dashboard and the chat made a page four screens tall "
        "with today's task buried in the middle of it. On a phone they're two "
        "tabs now — Today and Masterji — and a dot on Today tells you the day "
        "is still open.",
    ),
    (
        date(2026, 8, 6),
        "NEW",
        "Screenshot proofs, and a read on the morning's task",
        "Evening proof can carry a screenshot, and Masterji looks at the "
        "image rather than at your description of it. The task you declare in "
        "the morning also gets read the moment you declare it: if it's work "
        "for a phase you're not in, he says so at 9am instead of letting you "
        "find out at 9pm. Off-phase work is flagged, never blocked — the gate "
        "is what makes a sideways day cost something.",
    ),
    (
        date(2026, 8, 6),
        "CHANGED",
        "Pushed-back tries stay on the record",
        "A proof that gets pushed back is no longer overwritten by the one "
        "that finally lands. The misses fold away behind the accepted proof: "
        "out of the way, but not deleted.",
    ),
    (
        date(2026, 8, 6),
        "NEW",
        "Closed ideas open up, with their whole record",
        "A retired idea isn't just a line in an archive. Open it and the days "
        "come with it — what you declared, what you proved, what got pushed "
        "back — and it stays reachable while a new goal is running, because a "
        "record can't do its work if it's only visible in the four seconds "
        "between goals.",
    ),
    (
        date(2026, 8, 6),
        "CHANGED",
        "Every accepted proof counts as a day of work",
        "The streak is about the idea in front of you. The day count is about "
        "you. Retiring a goal resets the first and never touches the second.",
    ),
    (
        date(2026, 8, 6),
        "METHOD",
        "How Masterji decides is public — including how a method gets in",
        "Everything the coach judges by lives in the repo as plain markdown, "
        "one playbook per phase, small enough to read in ten minutes and "
        "crediting The Mom Test, The Lean Startup and MAKE by name. Added on "
        "top of the playbooks: the curation policy — what earns a method a "
        "place in the corpus, and why scraped founder tweets never will. The "
        "demo and the README now point straight at it.",
    ),
    (
        date(2026, 8, 6),
        "METHOD",
        "A shipping-cadence playbook for BUILD",
        "Distilled from the way Pieter Levels works: ship something small "
        "now, put it in front of people, and let them tell you what comes "
        "next. BUILD had gates but no cadence to hold you to.",
    ),
    (
        date(2026, 8, 6),
        "CHANGED",
        "The IDEA gate says what it wants, everywhere it speaks",
        "Leaving IDEA meant naming ten people who have the problem — a rule "
        "the gate enforced while the copy stayed vague about it. The phase "
        "hint, the proof ask and the refusal all say the same thing now. "
        "(That ask was loosened two days later — see the top of this list.)",
    ),
    (
        date(2026, 8, 6),
        "CHANGED",
        "A refusal that names the next move",
        "The gate's \"no\" used to be a bare count — two of three proofs, come "
        "back later. Every refusal now carries the next concrete action with "
        "it, and a single module owns all the builder-facing phase copy, so "
        "the phase hint, the proof ask and the refusal can't drift into three "
        "different answers about the same rule.",
    ),
    (
        date(2026, 8, 6),
        "FIXED",
        "The sidebar scrolls on its own",
        "Goal, gate, today's loop, the record and the archive stacked into a "
        "column taller than the page and dragged the whole layout down past "
        "the chat, which had its own scroll and stayed put. The dashboard "
        "column scrolls independently now.",
    ),
    (
        date(2026, 8, 6),
        "FIXED",
        "The instance stops dying under its own model calls",
        "Masterji's own calls to the model were enough to knock over the "
        "small box he runs on. Fewer moving parts per turn — and if the model "
        "is unreachable, your proof is still accepted with a stock reaction. "
        "The daily loop never breaks because an API flaked.",
    ),
    (
        date(2026, 8, 5),
        "NEW",
        "Retire an idea and start the next one",
        "One goal at a time is enforced by the database, but one goal was "
        "never meant to mean forever. Close it out — achieved or dropped — in "
        "one honest sentence, and Masterji reacts to the ending on the "
        "record. Achieving your goal is never blocked by the phase you "
        "happened to be in.",
    ),
    (
        date(2026, 8, 5),
        "NEW",
        "More than one task a day",
        "Done for today doesn't have to mean done for the day. Once the "
        "evening proof lands you can declare the next task, as many "
        "declare-then-prove cycles as the day actually had.",
    ),
    (
        date(2026, 8, 5),
        "FIXED",
        "The phase gate can't be walked past",
        "Two routes around the gate closed. Every check-in is stamped with "
        "the phase it was made in, so proofs count where they were earned — "
        "and not even the admin can move a row into a phase it didn't happen "
        "in.",
    ),
    (
        date(2026, 8, 5),
        "NEW",
        "Click a finished phase to see its record",
        "The stepper isn't only a progress bar. Tap a phase you've left and "
        "you get the window it covered and every check-in inside it.",
    ),
    (
        date(2026, 8, 5),
        "CHANGED",
        "What counts as proof, printed on the form",
        "The proof box used to be an empty box. The phase's ask now sits "
        "above it, with an example of a proof that was actually accepted.",
    ),
    (
        date(2026, 8, 5),
        "METHOD",
        "IDEA gets a playbook of its own — the problem statement",
        "The first phase was being coached on general principles. It has its "
        "own playbook now, distilled from Ash Maurya's Lean Canvas and "
        "Jobs-to-be-Done: one paragraph naming who specifically has the "
        "problem, what they do about it today, and why that isn't good "
        "enough. That anatomy is what your declarations get read against.",
    ),
    (
        date(2026, 8, 5),
        "NEW",
        "Masterji exists — the first working build",
        "One goal, four phases (IDEA → VALIDATION → BUILD → LAUNCH), a task "
        "declared every morning and proof owed every evening. Phases open on "
        "accepted proofs and the server counts them, so the coach can be "
        "talked to but the gate can't be talked around. Shipped with Google "
        "sign-in, a Hinglish toggle, and a canned demo you can read without "
        "an account.",
    ),
]


def seed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    # Oldest first, so within a shipped_on the newer entry gets the higher id.
    for shipped_on, kind, title, body in reversed(SEED):
        # get_or_create, not bulk_create: re-running this on a database that
        # already has the seed (a squash, a restore) must not double it.
        Entry.all_objects.get_or_create(
            shipped_on=shipped_on,
            title=title,
            defaults={"kind": kind, "body": body, "is_active": True},
        )


def unseed(apps, schema_editor):
    Entry = apps.get_model("coach", "ChangelogEntry")
    # Only the rows this migration wrote — anything published since then is
    # somebody's editing work, not ours to drop.
    Entry.all_objects.filter(title__in=[title for _, _, title, _ in SEED]).delete()


class Migration(migrations.Migration):
    dependencies = [("coach", "0010_changelogentry")]
    operations = [migrations.RunPython(seed, unseed)]
