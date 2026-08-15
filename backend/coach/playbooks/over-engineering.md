# Playbook: Over-Engineering Smells
*(inspired by Dan McKinley's "Choose Boring Technology" and Joel Spolsky's
"Things You Should Never Do, Part I" — Masterji's own distillation)*

Over-engineering feels like work — that's what makes it dangerous. It produces
commits, diagrams and a warm sense of professionalism, and not one new user.

## The smells
1. **Infrastructure before users.** Kubernetes, microservices, queues, or
   "multi-region" anything for a product with zero users. One small server
   and one database survive your first thousand users. Your problem is
   getting to ten.
2. **The framework migration.** Switching stacks mid-build because a blog
   post said the new one scales better. Scaling is a problem you earn.
3. **The abstraction for the future.** A plugin system, a generic engine, a
   config format — for the one use case you actually have. Build for the
   case in front of you; generalize the third time, not the first.
4. **Auth maximalism.** SSO, roles, permissions matrices, audit logs — for a
   tool whose only users are you and the three people you interviewed.
5. **The rewrite.** "The code is messy, I'll redo it properly." Week-one code
   is supposed to be messy. Messy code with users beats clean code without.
6. **Tool polishing.** Perfecting the dev environment, CI pipeline, linter
   config — the metawork treadmill. One afternoon, then ship features.

## The counter-question
For every technical decision: **"What breaks at ten users?"** If the honest
answer is "nothing", take the boring option and move on. Postgres, one
server, one repo, boring framework you already know.

## The second idea
It always shows up, usually in BUILD, usually on a hard day: a new idea,
and it is obviously better than the one you are on. It is the same smell as
the rewrite, one level up — the rewrite says this code is bad, and this one
says this *product* is.

Here is why it looks better: **it has no bugs yet, because it has no users
yet.** Everything you know about the idea you are building, you learned by
building it. You know nothing about the new one, and that absence is
reading to you as quality. Your current idea looked exactly this good three
weeks ago.

What to do with it: **write it down, in one line, and keep going.** One
line, today's date, somewhere you will find it. That is enough to stop it
circling, and writing it down costs nothing you were spending on the build.

And the one honest test for actually switching, named *before* you look at
the answer or you will bend it: **what would have to be true about the idea
I am on for stopping to be right?** Not "am I bored". Something checkable —
nobody I showed it to came back; the one person who said they would pay has
stopped replying. Then ask whether it is true today. If it is, that is not a
new idea, it is this one having been tested, and closing it honestly is a
real move with a real record behind it. If it is not, you have your answer
and it took four minutes.

Masterji only lets you run one goal at a time, and that is a rule in the
database, not a mood. This section is the method underneath it: a refusal
with nothing under it is the one thing this product says it is not.

## When the fancy thing IS right
When a real, current user is hitting a real, current wall — not a projected
one. Pain first, engineering second. Write the pain down; that note is the
design doc.

## What Masterji does with this
This playbook is loaded in BUILD, and only there: it is the phase where tech
decisions are finally the real work, so it is the phase where a field guide to
getting them wrong belongs. Hold every choice against the one-week rule and the
counter-question.

Earlier phases need none of it. Stacks, scaling and rewrites are deferred in
IDEA and VALIDATION by those phases' own rules (`PHASE_RULES` in
[../prompts.py](../prompts.py)), which decline the topic in one line and turn
the builder back to the problem statement or the conversations — and only when
the builder raises it first. This file used to claim it governed those phases
too, which it never did; loading it there would also break the curation rule
next door, that a playbook applying to every phase applies to none.
