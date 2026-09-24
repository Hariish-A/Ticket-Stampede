# Instructions (persistent — read first, every session)

These rules apply to any AI agent (Claude Code, Cursor, Copilot, etc.) working in this repo.
**Only the user changes this file**, or an agent changes it when the user explicitly asks.

## 0. Session start checklist
1. Read `Instructions.md` (this file), then `Plan.md`, then `Progress.md`.
2. Continue from the "Next up" section of `Progress.md`. Do not restart or re-plan finished work.
3. If `Plan.md` and the code disagree, stop and tell the user. Do not quietly "fix" either one.

## 1. What the evaluators want (short version of the brief)
- **Build both sides of the system.** Half a system is an incomplete submission.
- Problem 1 is judged on **coding and architecture**.
- Doing exactly what is asked is a **"No"**. They want to see:
  - something we noticed that they didn't ask about, and that matters;
  - a constraint taken further than required;
  - a failure mode we went looking for, **measured**, and handled;
  - the obvious approach tried, measured, rejected with evidence, and replaced.
- **Depth beats breadth.** One hard constraint solved properly beats gesturing at four.
- **They do not reward** volume or scaffolding, or polish over substance. Every part must be explainable under questioning.
- Time budget: **12–15 hours over 5–7 days.** Better small and working than big and half-running.

## 2. Required deliverables (the gate)
- [ ] Runs from a clean checkout using only the README, **in under 5 minutes on a clean machine**.
- [ ] `/logs` holds the full exported transcript of every AI coding session. **No logs means no evaluation.**
- [ ] `DECISIONS.md`, **no more than 2 pages**: architecture chosen and what was rejected, time-limit trade-offs, how it was tested, where it breaks, next steps with 2 more weeks.
- [ ] `README.md`: how to run it, quickly.
- [ ] Private GitHub repo shared with the evaluators.

## 3. Working rules for the AI agent
- **The user makes the decisions.** For any real design choice, give a recommendation with a reason and let the user decide. Record the decision (and who made it) in `Plan.md`.
- **Say when you're wrong, or when the user is.** If something doesn't hold up, say so plainly. Evaluators look for places where the candidate caught the tool being wrong.
- **Measure, don't assert.** Claims about performance or correctness (for example "no overselling", "handles N req/s") need a test or benchmark that shows them. Save the numbers.
- **No speculative scaffolding.** Don't add layers, abstractions, or features the plan doesn't call for.
- **Weaknesses get written down as we find them.** Put them in the "Known weaknesses" section of `Progress.md` so they reach `DECISIONS.md`.
- **Keep the run simple.** Prefer a single command (for example `docker compose up`, or one script) and pin versions.
- Don't commit or push unless the user asks.

## 3a. What "start <milestone>" means (the user's standing rule, 2026-09-24)
When the user says "start M<n>" (or "start" anything), the task is only done when that item is:
1. **completely developed**: everything in its Build list in `Plan.md` §6;
2. **tested**: the automated tests pass, and its demo command has been run and meets the acceptance criteria;
3. **a working deliverable**: the results are saved in `results/`, and `Progress.md` and the README are updated;
4. **committed and pushed to the private GitHub repo.**

After that, report back to the user. Don't start the next milestone without being asked.

## 4. Keeping the context files current
- `Progress.md`: update at the **end of every meaningful step**: what was done, files touched, test status, what's next, and any open questions. Append to the log; don't rewrite history.
- `Plan.md`: update when a design decision is made or changed. Keep the old decision under "Decision changes", with the reason it changed.
- `Instructions.md`: change only on the user's instruction.

## 5. Session logs (`/logs`)
- Logging starts from the session right after setup (2026-09-24).
- The raw transcripts are what the evaluators want. Claude Code stores them as JSONL under
  `C:\Users\Hariish A\.claude\projects\d--Official-Projects-Ticket-Stampede\*.jsonl`.
  Copy or export each session into `/logs/` (for example `logs/claude-code/<date>-<session-id>.jsonl`, plus an optional readable `.md` export).
- Transcripts from other tools (Cursor, Copilot chat, etc.) go into `/logs/<tool>/`.
- `Progress.md` is **not** a substitute for `/logs`.
