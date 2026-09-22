#!/usr/bin/env python3
"""Run: python3 test_comment_critic.py — fails loudly if the detector drifts."""
import json, os, pathlib, shutil, subprocess, sys, tempfile

HOOK = str(pathlib.Path(__file__).parent / "hooks" / "comment-critic.py")
SEEN = pathlib.Path(tempfile.gettempdir()) / "comment-critic-seen"
long_block = "\n".join(f"// line {i}" for i in range(12))
short_block = "\n".join(f"// line {i}" for i in range(4))


def run(payload, env=None, cwd=None):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, cwd=cwd)
    return p.returncode, p.stderr


# --- the direct tool payloads -------------------------------------------------
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}})
assert code == 2 and "12 lines" in err, err

code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": short_block}})
assert code == 0

code, _ = run({"tool_name": "Edit", "tool_input": {"file_path": "a.py", "new_string": long_block}})
assert code == 2

code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "README.md", "content": long_block}})
assert code == 0, "markdown must not fire"

code, _ = run({"tool_name": "MultiEdit", "tool_input": {"file_path": "a.swift", "edits": [
    {"new_string": short_block}, {"new_string": short_block}]}})
assert code == 0, "separate edits must not merge into one run"

code, _ = run({"tool_name": "Read", "tool_input": {"file_path": "a.swift"}})
assert code == 0

env = dict(os.environ, COMMENT_CRITIC_THRESHOLD="eight")
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 2 and "Traceback" not in err, err

env = dict(os.environ, COMMENT_CRITIC_THRESHOLD="20")
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 0, "raised threshold must silence a 12-line block"

# The skill nudge appears only when a skill is named.
env = dict(os.environ, COMMENT_CRITIC_SKILL="backlog", COMMENT_CRITIC_HOME="docs/backlog/")
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 2 and "`backlog` skill" in err and "docs/backlog/" in err, err

env = dict(os.environ); env.pop("COMMENT_CRITIC_SKILL", None)
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 2 and "skill" not in err, err

# --- Bash writes, however they land -------------------------------------------
repo = tempfile.mkdtemp()
subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
(pathlib.Path(repo) / "a.swift").write_text("let x = 1\n")
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
               cwd=repo, check=True)

py_heredoc = (f"python3 - <<'PY'\nimport pathlib\n"
              f"pathlib.Path('a.swift').write_text('''{long_block}''')\nPY")
mechanisms = {
    "cat heredoc":  f"cat > a.swift <<'EOF'\n{long_block}\nEOF",
    "tee heredoc":  f"tee a.swift <<'EOF'\n{long_block}\nEOF",
    "python3 -":    py_heredoc,
    "printf":       f"printf '%s' '{long_block}' > a.swift",
    "echo":         f"echo '{long_block}' > a.swift",
    "sed -i":       "sed -i '' 's|let x = 1|" + "\\n".join(f"// s{i}" for i in range(12)) + "|' a.swift",
    "nested dir":   f"mkdir -p sub && cat > sub/b.swift <<'EOF'\n{long_block}\nEOF",
}
def reset():
    subprocess.run(["git", "checkout", "-q", "--", "."], cwd=repo)
    subprocess.run(["git", "clean", "-fdq"], cwd=repo)
    SEEN.unlink(missing_ok=True)


for name, cmd in mechanisms.items():
    reset()
    subprocess.run(cmd, cwd=repo, shell=True, check=True, capture_output=True)
    code, err = run({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": repo})
    assert code == 2, f"{name} did not fire"
    assert ".swift" in err, f"{name} named no file: {err}"

# A markdown write through Bash still must not fire.
reset()
subprocess.run(f"cat > notes.md <<'EOF'\n{long_block}\nEOF", cwd=repo, shell=True, check=True)
code, _ = run({"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": repo})
assert code == 0, "markdown must not fire"

# The same block must not be re-reported on every later command.
reset()
subprocess.run(f"cat > a.swift <<'EOF'\n{long_block}\nEOF", cwd=repo, shell=True, check=True)
assert run({"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": repo})[0] == 2
assert run({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": repo})[0] == 0, \
    "a reported block must not nag again"

# Outside a git repo, Bash is silent rather than crashing.
plain = tempfile.mkdtemp()
SEEN.unlink(missing_ok=True)
code, err = run({"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": plain})
assert code == 0 and "Traceback" not in err, err

shutil.rmtree(repo, ignore_errors=True)
shutil.rmtree(plain, ignore_errors=True)
SEEN.unlink(missing_ok=True)
print("ok")
