#!/usr/bin/env python3
"""PostToolUse hook: flag comment blocks long enough to need justifying.

Default threshold is 8 lines — roughly p80 of a real codebase's comment blocks, so it fires on
outliers by distribution rather than by taste. Set COMMENT_CRITIC_THRESHOLD to retune it against
your own; COMMENT_CRITIC_HOME names where rulings live, if they live somewhere.
Advisory: the edit already happened. It asks the three questions; it cannot answer them.
"""
import json
import os
import re
import sys

THRESHOLD = int(os.environ.get("COMMENT_CRITIC_THRESHOLD", 8))
HOME = os.environ.get("COMMENT_CRITIC_HOME", "a doc")
COMMENT = re.compile(r"^\s*(//|///|#|\*(?!/))")


def runs(text):
    """Yield (start_line, length) for each comment block longer than THRESHOLD."""
    start = length = 0
    for n, line in enumerate(text.split("\n"), 1):
        if COMMENT.match(line):
            if not length:
                start = n
            length += 1
        else:
            if length > THRESHOLD:
                yield start, length
            length = 0
    if length > THRESHOLD:
        yield start, length


#: Source extensions only. A markdown heredoc is nearly all `#` headings and would fire on every
#: document written, which is how a hook gets switched off.
SOURCE = (".swift", ".py", ".sh", ".rb", ".js", ".ts", ".tsx", ".java", ".kt",
          ".c", ".h", ".cpp", ".m", ".mm", ".go", ".rs")
#: `cmd > path.swift`, `cmd >> path.swift`, `tee path.swift` — the write targets worth scanning.
REDIRECT = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*['\"]?([^\s'\"|;&]+)")
#: A quoted or bare heredoc body, up to its terminator at the start of a line.
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\1", re.S)


def bash_source_targets(command):
    """The source files this command redirects into. Also the only filename a Bash payload offers."""
    return [t for t in REDIRECT.findall(command) if t.endswith(SOURCE)]


def bash_source_writes(command):
    """The heredoc bodies this command writes into a source file, joined.

    Auto mode steers file writes through Bash heredocs rather than Write/Edit, so a hook matching
    only the edit tools sees none of them. Scans the body, not the whole command, so a script that
    merely mentions a path is not read as one that writes it.
    """
    if not bash_source_targets(command):
        return ""
    return "\n".join(body for _, body in HEREDOC.findall(command))


def written(tool, data):
    if tool == "Write":
        return data.get("content", "")
    if tool == "Edit":
        return data.get("new_string", "")
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string", "") for e in data.get("edits", []))
    if tool == "Bash":
        return bash_source_writes(data.get("command", ""))
    return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in {"Write", "Edit", "MultiEdit", "Bash"}:
        return 0

    tool_input = payload.get("tool_input", {})
    # A Bash payload carries no `file_path`, and "?" tells the reader nothing about where to look.
    if tool == "Bash":
        path = ", ".join(bash_source_targets(tool_input.get("command", ""))) or "?"
    else:
        path = tool_input.get("file_path", "?")
    found = list(runs(written(tool, tool_input)))
    if not found:
        return 0

    where = ", ".join(f"~line {s} ({n} lines)" for s, n in found[:3])
    print(
        f"Comment block over {THRESHOLD} lines in {path}: {where}.\n"
        "Three questions, per CLAUDE.md: is it needed? will it change what someone does? "
        "can it be shorter?\n"
        "Comment why, not what. If the explanation is longer than the code, cut the explanation. "
        f"A ruling or a measurement belongs in {HOME} — link, don't restate.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
