# AI session logs

This whole project (planning, M1–M8, M10) was done in **one Claude Code session**, exported unedited here:

- `claude-code/d1566ae3-4f29-422e-95e1-c4fb688a6326.jsonl`: the raw Claude Code transcript (JSON Lines, one event per line: user messages, assistant messages, tool calls and tool results, in order). It was copied from `~/.claude/projects/<project>/` at the end of every milestone, so the committed copy is the complete session up to the final commit.

To read it quickly, filter for the user's messages: lines with `"type":"user"` whose content is plain text rather than a tool result.

Places where the tool was caught being wrong, or where a measurement overturned its expectation, are also listed in `Progress.md` (per-milestone "mistakes caught") and in `results/discarded/README.md` (every discarded run and why).
