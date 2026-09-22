#!/usr/bin/env python3
"""PostToolUse hook: flag comment blocks long enough to need justifying.

Default threshold is 8 lines — roughly p80 of a real codebase's comment blocks, so it fires on
outliers by distribution rather than by taste. Set COMMENT_CRITIC_THRESHOLD to retune it against
your own; COMMENT_CRITIC_HOME names where rulings live and COMMENT_CRITIC_SKILL the skill that
files them, if either exists.
Advisory: the edit already happened. It asks the three questions; it cannot answer them.
"""
import json
import os
import pathlib
import re
import subprocess
import tempfile
import sys

_raw = os.environ.get("COMMENT_CRITIC_THRESHOLD", "")
THRESHOLD = int(_raw) if _raw.isdigit() else 8
HOME = os.environ.get("COMMENT_CRITIC_HOME", "a doc")
SKILL = os.environ.get("COMMENT_CRITIC_SKILL", "")
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
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def bash_added(cwd):
    """Yield (path, start_line, length) for long comment blocks this command added.

    Bash writes a file a hundred ways — a heredoc, `sed -i`, a python one-liner, a generator
    script. Parsing the command to find them is unwinnable, so this asks git what landed instead.
    Unstaged only: the just-written change, not the whole branch's uncommitted work.
    """
    def git(*args):
        return subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True, timeout=3)

    try:
        diff = git("diff", "-U0", "--no-color", "--no-ext-diff")
        new = git("ls-files", "--others", "--exclude-standard")
    except Exception:
        return
    if diff.returncode or new.returncode:
        return

    # A file git has never seen has no diff — every line of it is new.
    for name in new.stdout.split("\n"):
        if name.endswith(SOURCE):
            try:
                body = (pathlib.Path(cwd) / name).read_text(errors="replace")
            except OSError:
                continue
            for start, length in runs(body):
                yield name, start, length

    path, base, added = None, 0, []
    for line in diff.stdout.split("\n") + ["diff --git "]:
        if line.startswith(("diff --git ", "@@ ")):
            if path and added:
                for s, n in runs("\n".join(added)):
                    yield path, base + s - 1, n
            added = []
            hunk = _HUNK.match(line)
            if hunk:
                base = int(hunk.group(1))
        elif line.startswith("+++ b/"):
            target = line[6:]
            path = target if target.endswith(SOURCE) else None
        elif line.startswith("+") and path:
            added.append(line[1:])


def written(tool, data):
    if tool == "Write":
        return data.get("content", "")
    if tool == "Edit":
        return data.get("new_string", "")
    if tool == "MultiEdit":
        return "\n\n".join(e.get("new_string", "") for e in data.get("edits", []))
    return ""


def unseen(hits, cwd):
    """Drop hits already reported. A block stays in the diff until fixed or committed, so
    without this every later Bash command repeats the same warning until it is noise."""
    cache = pathlib.Path(tempfile.gettempdir()) / "comment-critic-seen"
    try:
        old = set(cache.read_text().split("\n"))
    except OSError:
        old = set()
    fresh = [h for h in hits if f"{cwd}:{h[0]}:{h[2]}" not in old]
    if fresh:
        try:
            keys = list(old | {f"{cwd}:{h[0]}:{h[2]}" for h in fresh})
            cache.write_text("\n".join(keys[-500:]))
        except OSError:
            pass
    return fresh


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool = payload.get("tool_name", "")
    if tool not in {"Write", "Edit", "MultiEdit", "Bash"}:
        return 0

    tool_input = payload.get("tool_input", {})
    if tool == "Bash":
        cwd = payload.get("cwd") or os.getcwd()
        hits = unseen(list(bash_added(cwd)), cwd)
    else:
        path = tool_input.get("file_path", "?")
        if not path.endswith(SOURCE):
            return 0
        hits = [(path, s, n) for s, n in runs(written(tool, tool_input))]
    if not hits:
        return 0

    found = [(s, n) for _, s, n in hits]
    path = ", ".join(dict.fromkeys(h[0] for h in hits))
    where = ", ".join(f"~line {s} ({n} lines)" for s, n in found[:3])
    print(
        f"Comment block over {THRESHOLD} lines in {path}: {where}.\n"
        "Three questions: is it needed? will it change what someone does? "
        "can it be shorter?\n"
        "Comment why, not what. If the explanation is longer than the code, cut the explanation. "
        f"A ruling or a measurement belongs in {HOME} — link, don't restate."
        + (f" Record it with the `{SKILL}` skill; do not hand-roll the file." if SKILL else ""),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
