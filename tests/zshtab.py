"""Press Tab in a real zsh and return what it lists: a small pty driver for the completion tests.

complete(line, cwd, fpath_dir, path_dirs) starts `zsh -f -i` on a pseudo-terminal with only the generated `_grader` on
its fpath (no ~/.zshrc), types `line`, presses Tab, and returns the screen text: group headers come out as
`[[description]]`, candidates as zsh lists them, and the edited command line as `BUF<…>`. Nothing is executed.
Copied from exam_projects/cli/tests/zshtab.py (which drives `_exam` the same way).
"""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import time
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][A-Z0-9]|\x1b[=>]|\r")

SETUP = r"""
unsetopt prompt_cr prompt_sp; setopt no_beep auto_list no_list_ambiguous no_always_last_prompt
PS1='%% '; RPS1=''; LISTMAX=100000; COLUMNS=250
fpath=({fpath} $fpath); autoload -Uz compinit; compinit -u -D
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '[[%d]]'
zstyle ':completion:*' list-prompt ''
zstyle ':completion:*' menu no
_dumpbuf() {{ zle -M "BUF<$BUFFER>" }}; zle -N _dumpbuf; bindkey '^X^B' _dumpbuf
print RE""ADY   # the echo shows RE""ADY, only the output says READY
"""


def zsh_available() -> bool:
    return shutil.which("zsh") is not None


def _read(fd: int, until: float, stop: str | None = None) -> str:
    out = b""
    while time.time() < until:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if stop and stop.encode() in out:
                break
    return out.decode("utf-8", "replace")


def _read_until_quiet(fd: int, max_wait: float, quiet: float = 0.4) -> str:
    """Read until zsh has printed something and then stayed silent for `quiet` seconds (or max_wait passes)."""
    out, end, last = b"", time.time() + max_wait, None
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out, last = out + chunk, time.time()
        elif last and time.time() - last > quiet:
            break
    return out.decode("utf-8", "replace")


def complete(line: str, cwd: Path, fpath_dir: Path, path_dirs: list[Path], timeout: float = 6.0) -> str:
    home = fpath_dir.parent / "home"  # a throwaway HOME next to the completion dir, not inside the course
    home.mkdir(exist_ok=True)
    env = {"PATH": os.pathsep.join([*map(str, path_dirs), "/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin"]),
           "HOME": str(home), "TERM": "xterm", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "COLUMNS": "250",
           "LINES": "200"}
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.chdir(cwd)
        os.execve(shutil.which("zsh"), ["zsh", "-f", "-i"], env)
    try:
        import fcntl
        import struct
        import termios
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 200, 250, 0, 0))
        os.write(fd, SETUP.format(fpath=fpath_dir).encode())
        _read(fd, time.time() + timeout, stop="READY\r\n")
        _read_until_quiet(fd, 1.0, quiet=0.15)  # the prompt
        os.write(fd, line.encode() + b"\t")
        screen = _read_until_quiet(fd, timeout)
        os.write(fd, b"\x18\x02")  # ^X^B: show the buffer
        screen += _read_until_quiet(fd, 2.0)
        return ANSI.sub("", screen)
    finally:
        os.write(fd, b"\x03\x04exit\n")
        time.sleep(0.05)
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except OSError:
            pass
        os.close(fd)
