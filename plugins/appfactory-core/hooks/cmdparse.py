#!/usr/bin/env python3
"""Decide whether a shell command actually INVOKES something, or merely mentions it.

WHY THIS EXISTS
---------------
The guards used substring matching: `if "gh run list" in cmd`. That is the same class of
mistake the preflight corpus was built to catch, pointed the other way. A line-oriented
grep against a multi-line block saw too little; a substring match against a whole shell
command sees too much.

On 2026-09-13 the run-list guard blocked three consecutive legitimate commands: a `sed`
rewriting the guard's own message, a `grep` for that message, and a heredoc writing a
receipt that quoted it. Nothing was being invoked in any of them.

A guard that fires when nothing is wrong costs exactly what a guard that stays silent
costs: it stops being believed. The first one gets suppressed, the second gets trusted.

THE RULE
--------
A phrase is an invocation only when its words appear as CONSECUTIVE TOKENS at a command
position. Quoting collapses a phrase into a single token, so `sed 's/gh run list/x/'`
yields one token containing the phrase rather than three tokens that are it.

QUOTING IS NOT PROOF OF INERTNESS, though. `bash -c "gh run list"` is quoted and still
runs. So the wrapper forms -- bash/sh/zsh -c, eval, xargs -- are re-entered rather than
trusted, to a bounded depth.

WHAT THIS STILL CANNOT SEE, stated rather than implied:
  * a phrase assembled at runtime: `c="gh run"; $c list`
  * a shell alias or function defined elsewhere
  * a command read from a file or a heredoc and piped into a shell
  * `$(...)` substitution contents, which are left to the caller to judge
Each of those is a real hole. None is closed by pretending otherwise.
"""
import shlex

# Separators that end one command and begin another. Order matters: two-character
# operators must be tried before their single-character prefixes.
_SEPARATORS = ("&&", "||", ";;", ";", "|", "&", "\n")

# Prefixes that precede the real command without being it.
_PREFIX_WORDS = {"sudo", "env", "time", "nohup", "command", "exec", "builtin", "nice", "doas"}

# Wrappers whose STRING ARGUMENT is executed as shell, so it must be re-entered.
_SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash", "ksh", "eval"}

_MAX_DEPTH = 3


def split_segments(command: str) -> list[str]:
    """Split a compound command on shell separators, respecting quotes.

    `echo "a && b"` is ONE segment; `echo a && echo b` is two. A naive
    `re.split(r"[;&|]{1,2}")` gets that backwards, which is how a quoted phrase
    became a separate "command" in the first place.
    """
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0
    while i < len(command):
        ch = command[i]
        if escaped:
            buf.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            buf.append(ch)
            escaped = True
            i += 1
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        for sep in _SEPARATORS:
            if command.startswith(sep, i):
                segments.append("".join(buf))
                buf = []
                i += len(sep)
                break
        else:
            buf.append(ch)
            i += 1
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def tokenize(segment: str) -> list[str]:
    """shlex tokens, or [] when the segment cannot be parsed.

    Returning [] on a parse failure means the caller sees no invocation and allows.
    That is deliberate: these are guards, and a guard that cannot read a command must
    not block it. Every guard here already fails open on an unparseable payload.
    """
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return []


def _strip_prefixes(tokens: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and wrapper words like sudo/env/time."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _PREFIX_WORDS:
            i += 1
            continue
        # A leading assignment: FOO=bar cmd ...
        if "=" in tok and not tok.startswith("-") and tok.split("=", 1)[0].isidentifier():
            i += 1
            continue
        break
    return tokens[i:]


def _wrapper_payloads(tokens: list[str]) -> list[str]:
    """Strings a wrapper will execute as shell: the argument after -c, or eval's args."""
    if not tokens:
        return []
    head = tokens[0].rsplit("/", 1)[-1]
    if head == "eval":
        return [" ".join(tokens[1:])] if len(tokens) > 1 else []
    if head in _SHELL_WRAPPERS:
        for i, tok in enumerate(tokens[1:], start=1):
            if tok == "-c" and i + 1 < len(tokens):
                return [tokens[i + 1]]
    return []


def invocations(command: str, words: list[str], _depth: int = 0) -> list[list[str]]:
    """Every segment that actually invokes `words`, returned as its token list.

    `words` are matched as consecutive tokens at the command position, after leading
    assignments and wrapper words are stripped.
    """
    found: list[list[str]] = []
    if _depth > _MAX_DEPTH:
        return found
    for segment in split_segments(command):
        tokens = tokenize(segment)
        if not tokens:
            continue
        head = _strip_prefixes(tokens)
        if head[: len(words)] == words:
            found.append(head)
        for payload in _wrapper_payloads(head):
            found.extend(invocations(payload, words, _depth + 1))
    return found


def git_subcommand(tokens: list[str]) -> str | None:
    """The git subcommand in a token list, skipping git's own global options.

    `git -C /x push` -> "push".  `git commit -m "fix: git push"` -> "commit", which is
    why a commit message mentioning a push no longer trips the push guard.
    """
    if not tokens or tokens[0].rsplit("/", 1)[-1] != "git":
        return None
    takes_value = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in takes_value:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        return tok
    return None


def git_invocations(command: str, subcommand: str, _depth: int = 0) -> list[list[str]]:
    """Every segment invoking `git <subcommand>`, as token lists."""
    found: list[list[str]] = []
    if _depth > _MAX_DEPTH:
        return found
    for segment in split_segments(command):
        tokens = _strip_prefixes(tokenize(segment))
        if not tokens:
            continue
        if git_subcommand(tokens) == subcommand:
            found.append(tokens)
        for payload in _wrapper_payloads(tokens):
            found.extend(git_invocations(payload, subcommand, _depth + 1))
    return found


NOTHING_RAN = (
    "Nothing in this command ran. A blocked command is refused whole, so anything "
    "earlier in it -- a cd, a backup copy -- did not happen either."
)
