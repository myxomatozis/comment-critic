# comment-critic

![comment critic — an eleven line comment block cut down to two](assets/banner.svg)

A Claude Code plugin. One advisory hook: after any write, if a comment block runs longer than
8 lines, it says where and asks three questions — **is it needed, will it change what someone
does, can it be shorter?** It cannot judge. You answer.

Catches writes through `Write`, `Edit`, `MultiEdit`, and Bash heredocs redirected into a source
file (auto mode writes that way). Source extensions only — a markdown heredoc is nearly all `#`
headings and would fire on every document written, which is how a hook gets switched off.

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
