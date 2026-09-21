#!/usr/bin/env python3
"""Run: python3 test_comment_critic.py — fails loudly if the detector drifts."""
import json, subprocess, sys, pathlib

HOOK = str(pathlib.Path(__file__).parent / "hooks" / "comment-critic.py")


def run(payload, env=None):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


long_block = "\n".join(f"// line {i}" for i in range(12))
short_block = "\n".join(f"// line {i}" for i in range(4))

code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}})
assert code == 2 and "12 lines" in err, err

code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": short_block}})
assert code == 0

code, _ = run({"tool_name": "Edit", "tool_input": {"file_path": "a.py", "new_string": long_block}})
assert code == 2

heredoc = f"cat > out.swift <<'EOF'\n{long_block}\nEOF"
code, err = run({"tool_name": "Bash", "tool_input": {"command": heredoc}})
assert code == 2 and "out.swift" in err, err

code, _ = run({"tool_name": "Bash", "tool_input": {"command": f"cat > notes.md <<'EOF'\n{long_block}\nEOF"}})
assert code == 0, "markdown must not fire"

code, _ = run({"tool_name": "Read", "tool_input": {"file_path": "a.swift"}})
assert code == 0

# A Write of markdown must not fire — the Bash path filtered by extension, this one did not.
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "README.md", "content": long_block}})
assert code == 0, "markdown Write must not fire"

# Two short blocks from separate edits must not concatenate into one long one.
code, _ = run({"tool_name": "MultiEdit", "tool_input": {"file_path": "a.swift", "edits": [
    {"new_string": short_block}, {"new_string": short_block}]}})
assert code == 0, "separate edits must not merge into one run"

# A junk threshold must fall back, not traceback on every write.
import os
env = dict(os.environ, COMMENT_CRITIC_THRESHOLD="eight")
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 2 and "Traceback" not in err, err

env = dict(os.environ, COMMENT_CRITIC_THRESHOLD="20", COMMENT_CRITIC_HOME="docs/backlog/")
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 0, "raised threshold must silence a 12-line block"

print("ok")
