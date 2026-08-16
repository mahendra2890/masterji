"""The playbooks: what the curation policy promises in public, and the
reading-time bound that holds it.
"""




from .. import prompts
from ..models import Phase
from .base import CoachTestCase


class CorpusReadingTimeTests(CoachTestCase):
    """The promise that argues against a vector database, held against the tree.

    playbooks/README.md, the root README and prompts.py all rest the "no vector
    DB" argument on the same property: the corpus is small enough that a person
    can read what the coach judges them on. That claim had drifted three times
    before anyone measured it — six files at the 13 August review, ten at the
    14 August one, sixteen the same afternoon, while six surfaces still said
    "ten minutes" — because every playbook was admitted on its own merits and
    no diff that added one carried a sentence about the folder's size.

    So these are BOUNDS rather than the current measurement. A test pinned to
    today's word count would fail on every honest admission and teach the next
    session to edit the number until it passed, which is the drift again with
    extra steps. A bound fails only when the claim in the docs stops being
    true — and #261 settled that the corpus may keep growing, so the bound is
    the tripwire that decision was left without.
    """

    # The rate the docs' minutes are quoted at. Ordinary prose reading; the
    # playbooks are plain English with no code in them.
    WORDS_PER_MINUTE = 200
    # "about a quarter of an hour", per phase. What a builder is actually
    # served: PLAYBOOKS_BY_PHASE[phase] is the whole of what reaches the model.
    PHASE_MINUTES = 15
    # "under an hour" for the lot — the reader who wants to audit the coach
    # rather than tonight's shelf.
    CORPUS_MINUTES = 60

    def _minutes(self, words):
        return words / self.WORDS_PER_MINUTE

    def _words(self, name):
        return len(prompts._playbook(name).split())

    def test_no_phase_asks_for_more_than_a_quarter_of_an_hour(self):
        for phase, names in prompts.PLAYBOOKS_BY_PHASE.items():
            with self.subTest(phase=phase):
                minutes = self._minutes(sum(self._words(n) for n in names))
                self.assertLessEqual(
                    minutes,
                    self.PHASE_MINUTES,
                    f"{phase} now needs ~{minutes:.0f} min of reading. Either the "
                    f"shelf comes back under {self.PHASE_MINUTES}, or the claim in "
                    "playbooks/README.md, README.md, prompts.py and Tour.tsx "
                    "changes with it — see #261, which decided the corpus may "
                    "grow and left this bound as the tripwire.",
                )

    def test_the_whole_corpus_stays_under_an_hour(self):
        files = [p for p in prompts.PLAYBOOKS_DIR.glob("*.md") if p.stem != "README"]
        minutes = self._minutes(sum(len(p.read_text().split()) for p in files))
        self.assertLessEqual(
            minutes,
            self.CORPUS_MINUTES,
            f"The corpus is now ~{minutes:.0f} min over {len(files)} files, and "
            "three surfaces say it is under an hour.",
        )

    def test_every_playbook_on_a_shelf_is_a_file_that_exists(self):
        """The bounds above are only worth something if they measure the same
        files the coach is actually handed. A name in PLAYBOOKS_BY_PHASE with
        no file behind it would raise at request time, not here."""
        for phase, names in prompts.PLAYBOOKS_BY_PHASE.items():
            for name in names:
                with self.subTest(phase=phase, playbook=name):
                    self.assertTrue((prompts.PLAYBOOKS_DIR / f"{name}.md").is_file())


class CorpusCurationTests(CoachTestCase):
    """The curation policy is a promise this repo makes in public.

    playbooks/README.md tells the reader they can read everything the coach
    judges them on tonight in about a quarter of an hour, that borrowed
    authority is credited by name, and that a playbook applying to every phase
    applies to none. Three files landed at once — cold outreach, the money ask,
    and choosing between ideas — and a corpus grows by exactly the route that
    stops being checked.

    The reading-time half of that promise is held by CorpusReadingTimeTests
    below, which is new: this docstring used to restate the ten-minute claim
    and then check three other things, so the one number in it was the one
    thing nothing verified.
    """

    # Names only, and the phase each belongs to. The source each one credits
    # used to live here too, and the credit test read it from here — which is
    # exactly why that test could never see the two files breaking the rule.
    # It reads the folder now, so the sources live in the headers alone.
    #
    # The three that filled the thin shelves: VALIDATION carried the heaviest
    # gate on one playbook, and LAUNCH asserted a ₹99 payment tells the truth
    # while teaching no way to get one.
    NEW_PLAYBOOKS = {
        "choosing-an-idea": Phase.IDEA,
        "getting-the-conversation": Phase.VALIDATION,
        "the-first-rupee": Phase.LAUNCH,
        # TRACTION arrived with the corpus's tenth file — the phase that opened
        # the shelf and the playbook that fills it landed together, which is
        # the one arrival order the curation policy has no answer for.
        "first-users": Phase.TRACTION,
        # The two gates that were standing on nothing. BUILD cannot be left
        # without evidence a real user touched the thing, and all three of its
        # playbooks taught building; VALIDATION started counting distinct
        # people, which made WHO the first three are load-bearing, and nothing
        # taught the case where the person across the table wants you to win.
        "first-touch": Phase.BUILD,
        "people-you-know": Phase.VALIDATION,
        "reading-the-nos": Phase.VALIDATION,
        # LAUNCH said WHERE to post and never how to write it, which is the
        # step the week goes quiet on.
        "writing-the-post": Phase.LAUNCH,
        # The terminal phase carried one playbook and it taught acquisition,
        # while the phase's own bar asks for a RETURN.
        "coming-back": Phase.TRACTION,
        # IDEA's bar asks for a PLACE and for why the builder believes anyone
        # is there, and both are downstream of a segment nothing in the corpus
        # taught them to cut. The two already here teach the anatomy of the
        # statement and the choice between candidates.
        "narrowing-the-first-user": Phase.IDEA,
    }

    def test_each_new_playbook_is_wired_to_exactly_one_phase(self):
        for name, phase in self.NEW_PLAYBOOKS.items():
            with self.subTest(playbook=name):
                wired = [
                    p
                    for p, names in prompts.PLAYBOOKS_BY_PHASE.items()
                    if name in names
                ]
                self.assertEqual(wired, [phase])

    # The two honest shapes a header line may take, per playbooks/README.md
    # rules 3 and 4. The third state — a borrowed method with nobody's name on
    # it — is the one the rule exists to keep out.
    CREDIT_OPENER = "*(inspired by "
    OWN_WORK_MARKER = "Masterji's own — no external source"

    @staticmethod
    def _header(name):
        """The italic line(s) under the title, up to the first blank line.
        Four playbooks wrap theirs, so this is not `splitlines()[1]`."""
        lines = prompts._playbook(name).splitlines()[1:]
        header = []
        for line in lines:
            if not line.strip():
                break
            header.append(line.strip())
        return " ".join(header)

    def test_every_playbook_credits_its_source_or_says_it_is_ours(self):
        """Borrowed authority is fine, hidden authority is not — the rule that
        separates this corpus from a model answering out of its pretraining,
        which is the one authority the product refuses to run on.

        This reads the folder rather than NEW_PLAYBOOKS, the way
        test_the_corpus_holds_nothing_the_coach_never_reads already does. Keyed
        to that dict it could only ever check files somebody had just added,
        and the two that broke the rule — over-engineering.md and
        launch-checklist.md — were original-era files, so they were
        structurally the two it could not contain. It never had the chance to
        fail on them. "New" is not the property the rule is about.
        """
        files = [p for p in prompts.PLAYBOOKS_DIR.glob("*.md") if p.stem != "README"]
        self.assertTrue(files)
        for path in sorted(files):
            with self.subTest(playbook=path.stem):
                header = self._header(path.stem)
                credited = header.startswith(self.CREDIT_OPENER)
                self.assertTrue(
                    credited or self.OWN_WORK_MARKER in header,
                    f"{path.name}'s header line neither credits a source "
                    f'("{self.CREDIT_OPENER}…") nor marks the method as ours '
                    f'("{self.OWN_WORK_MARKER}", which must also name the gate, '
                    "rule or refusal it encodes). See playbooks/README.md.",
                )
                if credited:
                    self.assertIn("—", header, f"{path.name} names no distiller.")

    def test_the_corpus_holds_nothing_the_coach_never_reads(self):
        """Every file wired, every wired name a file. An unwired playbook is
        dead content sitting in the one folder the README calls the coach's
        entire knowledge base, and nobody would find out."""
        on_disk = {p.stem for p in prompts.PLAYBOOKS_DIR.glob("*.md")} - {"README"}
        wired = {n for names in prompts.PLAYBOOKS_BY_PHASE.values() for n in names}
        self.assertEqual(on_disk, wired)

    def test_the_new_idea_playbooks_leave_contact_to_validation(self):
        """PHASE_RULES[IDEA] is explicit that the route is desk work and zero
        contact made is exactly right, and problem-statement.md says it to the
        builder in as many words. Every further playbook in the same phase is
        the cheapest way to contradict both, so each carries the deferral
        itself rather than trusting that the first one is still being read.
        The third one earns the check hardest: it asks whether the builder
        could be standing in the room on Thursday, which is one word away from
        telling them to go."""
        for name in ("choosing-an-idea", "narrowing-the-first-user"):
            with self.subTest(playbook=name):
                self.assertIn("VALIDATION's work", prompts._playbook(name))
