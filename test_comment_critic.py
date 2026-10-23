#!/usr/bin/env python3
"""Run: python3 test_comment_critic.py — fails loudly if the detector drifts."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, uuid

HOOK = str(pathlib.Path(__file__).parent / "hooks" / "comment-critic.py")
SEEN = pathlib.Path(tempfile.gettempdir()) / "comment-critic-seen"
long_block = "\n".join(f"// line {i}" for i in range(24))
short_block = "\n".join(f"// line {i}" for i in range(4))


def hook(payload, env=None):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def run(payload, env=None, cwd=None):
    """One write, then the end of its turn: the write stays silent, the Stop speaks."""
    turn = dict(session_id=uuid.uuid4().hex, cwd=payload.get("cwd") or os.getcwd())
    code, err = hook(dict(payload, **turn), env)
    assert code == 0 and not err, f"a write must stay silent until the turn ends: {err}"
    return hook(dict(turn, hook_event_name="Stop"), env)


# --- the direct tool payloads -------------------------------------------------
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}})
assert code == 2 and "24 lines" in err, err

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

env = dict(os.environ, COMMENT_CRITIC_THRESHOLD="30")
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.swift", "content": long_block}}, env)
assert code == 0, "raised threshold must silence a 24-line block"

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
    body = "\n".join(fmt % i for i in range(24))
    code, err = run({"tool_name": "Write", "tool_input": {"file_path": name, "content": body}})
    assert (code == 2) is should, f"{name} with {fmt!r}: expected fire={should}, got {code}"

# Block comments count even when their lines carry no marker of their own.
c_block = "/*\n" + "\n".join(f"   paragraph {i}" for i in range(23)) + "\n*/"
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.c", "content": c_block}})
assert code == 2 and "25 lines" in err, err  # the delimiters are comment lines too

docstring = '"""\n' + "\n".join(f"prose {i}" for i in range(23)) + '\n"""'
code, err = run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": docstring}})
assert code == 2 and "25 lines" in err, err

# A long string that happens to be triple-quoted is data, not prose.
query = 'SQL = """\n' + "\n".join(f"  select {i}," for i in range(23)) + '\n"""'
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": query}})
assert code == 0, "an assigned multi-line string is not a comment block"

# A one-line block comment opens nothing.
oneline = "\n".join("/* %d */" % i for i in range(24))
code, _ = run({"tool_name": "Write", "tool_input": {"file_path": "a.c", "content": oneline}})
assert code == 2, "24 one-line comments are still 24 comment lines"

def block_for(path, n=24):
    """A comment block in the language the path implies — otherwise a vendored-path test would
    pass because the marker was wrong, not because the path was skipped."""
    mark = {"py": "#", "rb": "#", "sh": "#", "ex": "#", "jl": "#", "tf": "#",
            "sql": "--", "hs": "--", "lua": "--",
            "clj": ";", "el": ";", "tex": "%", "erl": "%"}.get(
        pathlib.PurePath(path).suffix.lstrip("."), "//")
    return "\n".join(f"{mark} line {i}" for i in range(n))


# A generated file announces itself in its head, wherever it sits in the tree.
HEADERS = {
    "api/v1/service.pb.go": "// Code generated by protoc-gen-go. DO NOT EDIT.",
    "lib/model.g.dart": "// GENERATED CODE - DO NOT MODIFY BY HAND",
    "app/Api.designer.cs": "// <auto-generated>",
    "proto/thing_pb2.py": "# Generated by the protocol buffer compiler.  DO NOT EDIT!",
    "src/schema.ts": "// @generated",
    "src/store.js": "// This file was automatically generated.",
    "gen/thrift.go": "// Autogenerated by Thrift Compiler (0.14.1)",
}
sandbox2 = tempfile.mkdtemp()
for name, header in HEADERS.items():
    f = pathlib.Path(sandbox2) / name
    f.parent.mkdir(parents=True, exist_ok=True)
    body = block_for(name, 24)
    f.write_text(header + "\n" + body + "\n")
    code, _ = run({"tool_name": "Write", "cwd": sandbox2,
                   "tool_input": {"file_path": name, "content": body}})
    assert code == 0, f"{name} declares itself generated and must be skipped"

    # The same file without the header is ordinary source.
    f.write_text(body + "\n")
    code, _ = run({"tool_name": "Write", "cwd": sandbox2,
                   "tool_input": {"file_path": name, "content": body}})
    assert code == 2, f"{name} without the header is your code"

# Prose about generated *things* is not a generator disowning the *file*. Skipping on it is a
# silent false negative, the one failure nobody notices — so each of these must still fire.
NOT_BANNERS = [
    "// Tokens are auto-generated per session",
    "// IDs are automatically generated by the database",
    "// The schema is auto-generated upstream; do not edit it here.",
    "// DO NOT EDIT without updating the schema first.",
    "// Generated column values are cached",
]
for i, line in enumerate(NOT_BANNERS):
    f = pathlib.Path(sandbox2) / f"prose{i}.go"
    f.write_text(line + "\n" + block_for("x.go") + "\n")
    code, _ = run({"tool_name": "Write", "cwd": sandbox2,
                   "tool_input": {"file_path": f"prose{i}.go", "content": block_for("x.go")}})
    assert code == 2, f"must not be read as a generator banner: {line}"

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

# --- what a comment says, not how long it is ----------------------------------
def says(path, body):
    return run({"tool_name": "Write", "tool_input": {"file_path": path, "content": body}})


SMELLS = {
    "narrates the change": ("a.swift", "// Updated to use the shared cache\nlet c = Cache.shared"),
    "narrates the change ": ("a.py", "x = load()  \n# Previously this read from disk\nx = fetch()"),
    "commented-out code": ("a.ts", "// const old = compute(a, b);\n// render(old);\nrender(a)"),
    "restates the code": ("a.go", "// Get the user\nuser := getUser()"),
    "longer than the 1 lines": ("a.rs", "// one\n// two\n// three\n// four\nlet x = 1;"),
}
for want, (path, body) in SMELLS.items():
    code, err = says(path, body)
    assert code == 2 and want.strip() in err, f"{want!r} not reported for {body!r}: {err}"

# The finding quotes the comment and the code under it, so the model can judge it.
code, err = says("a.swift", "// Updated to use the shared cache\nlet c = Cache.shared")
assert "    // Updated to use the shared cache" in err and "    let c = Cache.shared" in err, err

# A comment that says why passes, however close to the code its words are.
GOOD = [
    ("a.swift", "// Retry once: the token may have just expired upstream\nretry(once: true)"),
    ("a.py", "# Added items are flushed on save, not on insert\nself.pending.append(x)"),
    ("a.ts", "// The previously selected row keeps focus\nfocus(prev)"),
    ("a.go", "// See RFC 9110 section 15\nreturn 404"),
    ("a.py", "def f():\n    # Sorted, because the API returns rows unordered\n    rows.sort()\n"
             "    return rows\n"),
    ("a.c", "/* Note (see below) */\nint x = 1;"),
    ("a.js", "/** @type {import('prettier').Config} */\nmodule.exports = {"),
    ("a.rs", "// JUEL: ${varName}\n&expr[2..]"),
    ("a.go", "// Now use UpdateThreadLabels to add another label\nset(labels)"),
    # a docstring explains the whole body, blank lines and all
    ("a.py", 'def f():\n    """One.\n\n    Two.\n    Three.\n    """\n    a = 1\n\n    b = 2\n'
             "    c = 3\n    d = 4\n    return a\n\n\ndef g():\n    pass\n"),
]
# ...but a paragraph comment explains only its paragraph.
code, err = says("a.py", "def f():\n    # one\n    # two\n    # three\n    # four\n    a = 1\n\n"
                         "    b = 2\n    c = 3\n    d = 4\n    e = 5\n")
assert code == 2 and "longer than the 1 lines" in err, err
for path, body in GOOD:
    code, err = says(path, body)
    assert code == 0, f"a why-comment was flagged: {body!r}\n{err}"

# An Edit is judged against the file on disk: real line numbers, and only what it touched.
disk = tempfile.mkdtemp()
src = pathlib.Path(disk) / "a.swift"
src.write_text("// Updated to use the old thing\nlet a = 1\n\nlet b = 2\n"
               "// Updated to use the shared cache\nlet c = Cache.shared\n")
code, err = run({"tool_name": "Edit", "cwd": disk, "tool_input": {
    "file_path": "a.swift", "new_string": "// Updated to use the shared cache\nlet c = Cache.shared"}})
assert code == 2 and "a.swift:5 " in err, err
assert "old thing" not in err, "a comment the edit did not touch is not its to answer for"

# The code under the comment comes from disk too, not the edit's fragment.
src.write_text("// one\n// two\n// three\n// four\nfunc f() {\n  a()\n  b()\n  c()\n}\n")
code, err = run({"tool_name": "Edit", "cwd": disk, "tool_input": {
    "file_path": "a.swift", "new_string": "// one\n// two\n// three\n// four\nfunc f() {"}})
assert code == 0, f"the function is 5 lines on disk, longer than its comment: {err}"

# The policy reaches the session and every subagent before anything is written.
for event in ("SessionStart", "SubagentStart"):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"hook_event_name": event}),
                       capture_output=True, text=True)
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert p.returncode == 0 and out["hookEventName"] == event, p
    assert "three questions" in out["additionalContext"], out

# --- one review per turn ------------------------------------------------------
turn_dir = tempfile.mkdtemp()
a, b = pathlib.Path(turn_dir) / "a.swift", pathlib.Path(turn_dir) / "b.py"
NARRATE = "// Updated to use the shared cache\nlet c = Cache.shared\n"


def write(f, body, **extra):
    f.write_text(body)
    return hook(dict(extra, tool_name="Write", cwd=turn_dir,
                     tool_input={"file_path": f.name, "content": body}))


def stop(event="Stop", **extra):
    return hook(dict(extra, hook_event_name=event, cwd=turn_dir))


# Writes across files collect into a single review, which is then spent.
s = dict(session_id="batch")
assert write(a, NARRATE, **s) == (0, "")
assert write(b, "# Previously this read from disk\nx = fetch()\n", **s) == (0, "")
code, err = stop(**s)
assert code == 2 and err.count("narrates") == 2 and "a.swift:1 " in err and "b.py:1 " in err, err
assert stop(**s) == (0, ""), "a review is spent once given"

# A comment fixed later in the same turn is not reported; one that moved is, at its new line.
s = dict(session_id="fixed")
write(a, NARRATE, **s)
write(b, "# Previously this read from disk\nx = fetch()\n", **s)
a.write_text("let c = Cache.shared\n")
b.write_text("import os\n\n# Previously this read from disk\nx = fetch()\n")
code, err = stop(**s)
assert code == 2 and "a.swift" not in err and "b.py:3 " in err, err

# The review's own follow-up turn ends without a second review, and leaves nothing behind.
s = dict(session_id="loop")
write(a, NARRATE, **s)
assert stop(stop_hook_active=True, **s) == (0, "")
assert stop(**s) == (0, ""), "findings dropped on the follow-up must not resurface next turn"

# A subagent answers for its own comments; the parent's review does not inherit them.
s = dict(session_id="parent")
write(a, NARRATE, agent_id="sub1", **s)
assert stop(**s) == (0, ""), "the parent did not write it"
code, err = stop("SubagentStop", agent_id="sub1", **s)
assert code == 2 and "narrates" in err, err

# A quote is labelled as file content, clipped, and stripped of control characters.
s = dict(session_id="quote")
write(a, "// Updated to use the cache \x1b[2J" + "x" * 300 + "\nlet c = 1\n", **s)
code, err = stop(**s)
assert code == 2 and "not instructions" in err and "\x1b" not in err, err
assert max(map(len, err.split("\n"))) < 200 and "x" * 121 not in err, err

# Nothing written, nothing said.
assert stop(session_id="quiet") == (0, "")

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
    "sed -i":       "sed -i '' 's|let x = 1|" + "\\n".join(f"// s{i}" for i in range(24)) + "|' a.swift",
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

# Through the Bash path too, where only the added lines are in hand and the header is on disk.
reset()
gen = pathlib.Path(repo) / "api.pb.go"
gen.write_text("// Code generated by protoc-gen-go. DO NOT EDIT.\nvar x = 1\n")
subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "gen"],
               cwd=repo, check=True)
gen.write_text("// Code generated by protoc-gen-go. DO NOT EDIT.\n" + block_for("x.go") + "\n")
code, err = run({"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": repo})
assert code == 0, f"a generated file must be skipped on the diff path too: {err}"

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

# A smell lands through Bash too, at its line in the file rather than in the hunk.
reset()
subprocess.run("printf 'let x = 1\\n// Previously this was a guard\\nlet y = 2\\n' > a.swift",
               cwd=repo, shell=True, check=True)
code, err = run({"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": repo})
assert code == 2 and "a.swift:2 " in err and "narrates" in err, err

# Outside a git repo, Bash is silent rather than crashing.
plain = tempfile.mkdtemp()
SEEN.unlink(missing_ok=True)
code, err = run({"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": plain})
assert code == 0 and "Traceback" not in err, err

shutil.rmtree(repo, ignore_errors=True)
shutil.rmtree(plain, ignore_errors=True)
SEEN.unlink(missing_ok=True)

# --- Antigravity: PostToolUse queues, PreInvocation injects ---------------------
def agy(payload, *args):
    p = subprocess.run([sys.executable, HOOK, *args], input=json.dumps(payload),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)

conv = {"conversationId": "test-agy", "workspacePaths": [tempfile.mkdtemp()]}
agy(conv, "--inject")  # drain leftovers
assert agy({**conv, "toolCall": {"name": "write_to_file",
            "args": {"TargetFile": "/x/a.swift", "CodeContent": short_block}}}) == {}
assert agy(conv, "--inject") == {}, "short block must queue nothing"
agy({**conv, "toolCall": {"name": "multi_replace_file_content", "args": {"TargetFile": "/x/a.ts",
     "ReplacementChunks": [{"ReplacementContent": long_block}]}}})
steps = agy(conv, "--inject")["injectSteps"]
assert "24 lines" in steps[0]["ephemeralMessage"], steps
assert agy(conv, "--inject") == {}, "injected findings must be drained"

# --- Kiro: PostToolUse queues, Stop blocks once with the findings ---------------
def kiro(payload, *args):
    p = subprocess.run([sys.executable, HOOK, "--kiro", *args], input=json.dumps(payload),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else None

sess = {"session_id": "test-kiro", "cwd": tempfile.mkdtemp()}
kiro(sess, "--inject")  # drain leftovers
assert kiro({**sess, "tool_name": "fs_write",
             "tool_input": {"path": "/x/a.swift", "text": short_block}}) is None
assert kiro(sess, "--inject") is None, "short block must queue nothing"
kiro({**sess, "tool_name": "str_replace",
      "tool_input": {"path": "/x/a.ts", "oldStr": "x", "newStr": long_block}})
kiro({**sess, "tool_name": "fs_write", "tool_input": {"path": "/x/README.md", "text": long_block}})
stop = kiro(sess, "--inject")
assert stop["decision"] == "block" and "/x/a.ts:1 (24 lines)" in stop["reason"], stop
assert "README" not in stop["reason"], "markdown must not fire"
assert kiro(sess, "--inject") is None, "a drained queue must let the next stop through"
assert kiro({**sess, "tool_name": "read_file", "tool_input": {"path": "/x/a.ts"}}) is None
print("ok")
