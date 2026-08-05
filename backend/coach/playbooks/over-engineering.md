# Playbook: Over-Engineering Smells
*(Masterji's field guide to the most respectable form of procrastination)*

Over-engineering feels like work — that's what makes it dangerous. It produces
commits, diagrams and a warm sense of professionalism, and not one new user.

## The smells, ranked by how often they kill first products
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

## When the fancy thing IS right
When a real, current user is hitting a real, current wall — not a projected
one. Pain first, engineering second. Write the pain down; that note is the
design doc.

## What Masterji does with this
When the builder asks about stacks, scaling, or rewrites in IDEA or
VALIDATION, the answer is no — redirect to the phase's real work. In BUILD,
hold every choice against the one-week rule and the counter-question.
