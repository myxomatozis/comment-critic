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

code, _ = run({"tool_name": "Edit", "tool_input": {"file_path": "a.ts", "new_string": long_block}})
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

# Zero config: the home and the skill are discovered from the repo when nothing is set.
bare = dict(os.environ)
bare.pop("COMMENT_CRITIC_HOME", None)
bare.pop("COMMENT_CRITIC_SKILL", None)

sandbox = tempfile.mkdtemp()
(pathlib.Path(sandbox) / "docs" / "adr").mkdir(parents=True)
(pathlib.Path(sandbox) / ".claude" / "skills" / "decisions").mkdir(parents=True)
code, err = run({"tool_name": "Write", "cwd": sandbox,
                 "tool_input": {"file_path": "a.swift", "content": long_block}}, bare)
assert code == 2 and "docs/adr/" in err, err
assert "`decisions` skill" in err, err

# A repo with no conventional home says "a doc" rather than inventing a path.
empty = tempfile.mkdtemp()
code, err = run({"tool_name": "Write", "cwd": empty,
                 "tool_input": {"file_path": "a.swift", "content": long_block}}, bare)
assert code == 2 and "belongs in a doc" in err, err

# A user-level skill is found even when the repo has no .claude/skills of its own.
user = tempfile.mkdtemp()
(pathlib.Path(user) / ".claude" / "skills" / "backlog").mkdir(parents=True)
code, err = run({"tool_name": "Write", "cwd": empty,
                 "tool_input": {"file_path": "a.swift", "content": long_block}},
                dict(bare, HOME=user))
assert code == 2 and "`backlog` skill" in err, err

# The env still wins over what was found on disk.
override = dict(bare, COMMENT_CRITIC_HOME="RULINGS.md", COMMENT_CRITIC_SKILL="scribe")
code, err = run({"tool_name": "Write", "cwd": sandbox,
                 "tool_input": {"file_path": "a.swift", "content": long_block}}, override)
assert code == 2 and "RULINGS.md" in err and "`scribe` skill" in err, err

# The skill nudge appears only when a skill is named.
env = dict(os.environ, COMMENT_CRITIC_SKILL="backlog", COMMENT_CRITIC_HOME="docs/backlog/")
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 2 and "`backlog` skill" in err and "docs/backlog/" in err, err

# A user-level skill applies in every repo, so silence needs neither project nor user skill.
nowhere = dict(bare, HOME=tempfile.mkdtemp())
code, err = run({"tool_name": "Write", "cwd": empty,
                 "tool_input": {"file_path": "a.swift", "content": long_block}}, nowhere)
assert code == 2 and "skill" not in err, "no skill found, no skill sentence"

# Per-language comment markers: a marker is only a comment in its own language.
LANGS = {
    "a.swift": ("// %d", True), "a.go": ("// %d", True), "a.rs": ("// %d", True),
    "a.py": ("# %d", True), "a.rb": ("# %d", True), "a.sh": ("# %d", True),
    "a.sql": ("-- %d", True), "a.hs": ("-- %d", True), "a.lua": ("-- %d", True),
    "a.clj": ("; %d", True), "a.el": ("; %d", True),
    "a.tex": ("%% %d", True), "a.erl": ("%% %d", True),
    "a.cs": ("// %d", True), "a.php": ("// %d", True), "a.dart": ("// %d", True),
    "a.ex": ("# %d", True), "a.jl": ("# %d", True), "a.tf": ("# %d", True),
    # a marker from the wrong language is just code
    "b.go": ("# %d", False), "b.py": ("// %d", False), "b.sql": ("// %d", False),
    "b.clj": ("# %d", False),
}
for name, (fmt, should) in LANGS.items():
    body = "\n".join(fmt % i for i in range(12))
    code, err = run({"tool_name": "Write", "tool_input": {"file_path": name, "content": body}})
    assert (code == 2) is should, f"{name} with {fmt!r}: expected fire={should}, got {code}"

# Block comments count even when their lines carry no marker of their own.
c_block = "/*\n" + "\n".join(f"   paragraph {i}" for i in range(11)) + "\n*/"
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.c", "content": c_block}})
assert code == 2 and "13 lines" in err, err  # the delimiters are comment lines too

docstring = '"""\n' + "\n".join(f"prose {i}" for i in range(11)) + '\n"""'
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": docstring}})
assert code == 2 and "13 lines" in err, err

# A long string that happens to be triple-quoted is data, not prose.
query = 'SQL = """\n' + "\n".join(f"  select {i}," for i in range(11)) + '\n"""'
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": query}})
assert code == 0, "an assigned multi-line string is not a comment block"

# A one-line block comment opens nothing.
oneline = "\n".join("/* %d */" % i for i in range(12))
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.c", "content": oneline}})
assert code == 2, "twelve one-line comments are still twelve comment lines"

def block_for(path, n=12):
    """A comment block in the language the path implies — otherwise a vendored-path test would
    pass because the marker was wrong, not because the path was skipped."""
    mark = {"py": "#", "rb": "#", "sh": "#", "ex": "#", "jl": "#", "tf": "#",
            "sql": "--", "hs": "--", "lua": "--",
            "clj": ";", "el": ";", "tex": "%", "erl": "%"}.get(
        pathlib.PurePath(path).suffix.lstrip("."), "//")
    return "\n".join(f"{mark} line {i}" for i in range(n))


# Vendored trees are not yours to police, through either path.
for junk in ("node_modules/left-pad/index.js", "Pods/Alamofire/Source/A.swift",
             "vendor/github.com/x/y.go", "deep/nested/third_party/z/a.py",
             "build/generated/G.java", ".venv/lib/site-packages/q.py",
             "target/debug/b.rs", "deps/phoenix/lib/a.ex", ".dart_tool/x/a.dart",
             "obj/Release/A.cs", ".stack-work/x/A.hs", "__pycache__/a.py"):
    assert run({"tool_name": "Write",
                "tool_input": {"file_path": pathlib.PurePath(junk).name,
                               "content": block_for(junk)}})[0] == 2, \
        f"{junk} would fire if it were not vendored"
    code, _ = run({"tool_name": "Write", "tool_input": {"file_path": junk,
                                                        "content": block_for(junk)}})
    assert code == 0, f"{junk} must be skipped"

# A path merely containing the word is still policed: only whole segments count.
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "src/vendored_helpers.py",
                                                    "content": block_for("x.py")}})
assert code == 2, "vendored_helpers.py is your code"

# COMMENT_CRITIC_SKIP adds to the list without replacing it.
env = dict(os.environ, COMMENT_CRITIC_SKIP="Generated, legacy")
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "app/Generated/API.swift",
                                                    "content": long_block}}, env)
assert code == 0, "an added name must be skipped"
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "node_modules/a/b.js",
                                                    "content": long_block}}, env)
assert code == 0, "the defaults must survive an addition"

# A leading minus un-skips a default, for a repo whose real source lives in one.
env = dict(os.environ, COMMENT_CRITIC_SKIP="-build")
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "build/tool.py",
                                                    "content": block_for("x.py")}}, env)
assert code == 2, "-build must put build/ back under the rule"
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "node_modules/a/b.js",
                                                    "content": long_block}}, env)
assert code == 0, "un-skipping one name must not disarm the rest"

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
skipped = {
    "new vendored file":     f"mkdir -p node_modules/x && cat > node_modules/x/i.js <<'EOF'\n{long_block}\nEOF",
    "tracked vendor change": f"cat > vendor/v.swift <<'EOF'\n{long_block}\nEOF",
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

# The same two, vendored: git sees them, the guard does not.
subprocess.run(["mkdir", "-p", "vendor"], cwd=repo, check=True)
(pathlib.Path(repo) / "vendor" / "v.swift").write_text("let v = 1\n")
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "vendor"],
               cwd=repo, check=True)
for name, cmd in skipped.items():
    reset()
    subprocess.run(cmd, cwd=repo, shell=True, check=True, capture_output=True)
    code, err = run({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": repo})
    assert code == 0, f"{name} should be skipped, got: {err}"

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
