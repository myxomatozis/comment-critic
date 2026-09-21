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
/plugin marketplace add oleh-smirnov/comment-critic   # or a local path
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

## Sharing

The repo is both the plugin and its marketplace, so one URL does everything.

```
cd ~/Scripts/comment-critic
gh repo create comment-critic --public --source=. --push
```

Anyone then installs with:

```
/plugin marketplace add <you>/comment-critic
/plugin install comment-critic@comment-critic
```

Bump `version` in `.claude-plugin/plugin.json` when you change the hook; `/plugin update` reads it.

## Installing locally, no GitHub

```
/plugin marketplace add ~/Scripts/comment-critic
/plugin install comment-critic@comment-critic
```

Same two commands against a path. Edits to the working copy are live on the next session, which
makes this the way to try a change before pushing it.
