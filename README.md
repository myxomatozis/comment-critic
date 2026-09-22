# comment-critic

![comment critic — an eleven line comment block cut down to two](assets/banner.svg)

A Claude Code plugin. One advisory hook: after any write, if a comment block runs longer than
8 lines, it says where and asks three questions — **is it needed, will it change what someone
does, can it be shorter?** It cannot judge. You answer.

Catches the write however it happened. `Write`, `Edit` and `MultiEdit` are read from the tool
payload; for `Bash` the hook asks `git` what actually changed, so a heredoc, `sed -i`, a `python3 -`
one-liner, a generator script and a brand-new untracked file are all caught the same way. Parsing
the command to guess which of those wrote what is unwinnable — there is always another `etc.`

Source extensions only: a markdown heredoc is nearly all `#` headings and would fire on every
document written, which is how a hook gets switched off. The `Bash` path needs a git repo and
reports each block once — it stays in the diff until fixed or committed, and a warning that
repeats on every command is noise.

## Install

```
/plugin marketplace add myxomatozis/comment-critic
/plugin install comment-critic@comment-critic
```

## Tune

| env | default | |
|---|---|---|
| `COMMENT_CRITIC_THRESHOLD` | `8` | Lines before a block is flagged. 8 is ~p80 of a real codebase's blocks. Measure your own: outliers by distribution beat outliers by taste. |
| `COMMENT_CRITIC_HOME` | `a doc` | Where rulings and measurements belong, e.g. `docs/backlog/`. Named in the message. |
| `COMMENT_CRITIC_SKILL` | unset | A skill that files them, e.g. `backlog`. Naming the destination is not the same as naming the tool that writes it there, so when this is set the message says to invoke the skill rather than hand-roll the file. Unset, the sentence is omitted entirely. |

## The policy it enforces

The hook only nags. Paste this into your `CLAUDE.md` so there's a rule to answer to:

```markdown
## Comment policy — comment as little as possible

Every comment must survive three questions: **is it needed, will it change what someone does,
can it be shorter?** Default to none.

- Comment **why**, never **what**. The code says what.
- If the explanation is longer than the code it explains, delete the explanation.
- A ruling, a measurement or a history belongs in a doc. Link to it; don't restate it.
```

## Check

`python3 test_comment_critic.py`

## Forking it

The repo is its own marketplace — `.claude-plugin/marketplace.json` lists the plugin beside it,
so one URL is both. A fork needs no extra wiring: push it, and
`/plugin marketplace add <you>/comment-critic` works against yours.

To try a change before pushing, point the same command at a path — `/plugin marketplace add
~/src/comment-critic`. Edits to the working copy are live on the next session.

Bump `version` in `.claude-plugin/plugin.json` when you change the hook; `/plugin update` reads it.
