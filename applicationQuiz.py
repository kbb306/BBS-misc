import os
import secrets
import shutil
import string
import sys
import textwrap

import QuizSource

BLINK_ON = "\x1b[5m"
BLINK_OFF = "\x1b[25m"


def generate_uin(length=64):
    """Return a case-sensitive UIN(+L) matching the site's 64-character style."""
    alphabet = string.ascii_lowercase + string.digits
    while True:
        uid = "".join(secrets.choice(alphabet) for _ in range(length))
        # UIN(+L) should actually contain both digits and letters.
        if any(ch.isdigit() for ch in uid) and any(ch.isalpha() for ch in uid):
            return uid


def terminal_width():
    """Use the live terminal width when available; fall back to classic 80 columns."""
    return max(20, shutil.get_terminal_size(fallback=(80, 24)).columns)


def blink_supported():
    """Best-effort ANSI blink detection, overridable for BBS/telnet setups."""
    override = os.environ.get("APERTURE_BLINK")
    if override == "1":
        return True
    if override == "0":
        return False

    term = os.environ.get("TERM", "").lower()
    return sys.stdout.isatty() or term not in ("", "dumb")


def wrap_line(line, width=None, initial_indent="", subsequent_indent=""):
    if width is None:
        width = terminal_width()
    if not line:
        return ""
    return textwrap.fill(
        line,
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        replace_whitespace=False,
        drop_whitespace=True,
        break_long_words=True,
        break_on_hyphens=False,
    )


def printer(text, num=None, uid=None, end="\n", blink_uid=True):
    """Render the SWF's custom formatting tokens and wrap to terminal width."""
    if num is not None:
        text = text.replace("#", str(num))

    uid_marker = None
    if uid is not None:
        uid_marker = f"[{uid}]"
        text = text.replace("@", uid_marker)

    # In the original SWF, ^ is a custom line-break token.
    text = text.replace("^", "\n")

    width = terminal_width()
    rendered_lines = []
    for line in text.split("\n"):
        # Preserve the input prompt's trailing space.
        if line == "> ":
            rendered_lines.append(line)
        # Keep the 64-character UIN intact at normal terminal widths. It is
        # intentionally difficult to memorize and should appear as one block.
        elif uid_marker is not None and line.strip() == uid_marker:
            rendered_lines.append(line)
        else:
            rendered_lines.append(wrap_line(line, width=width))
    rendered = "\n".join(rendered_lines)

    # ANSI SGR 5 is "slow blink". Terminals that do not implement blink will
    # normally just show the text steadily. Set APERTURE_BLINK=0 to disable it
    # or APERTURE_BLINK=1 to force the escape sequence under a BBS/telnet PTY.
    if uid_marker is not None and blink_uid and blink_supported():
        rendered = rendered.replace(
            uid_marker, f"{BLINK_ON}{uid_marker}{BLINK_OFF}"
        )

    print(rendered, end=end, flush=True)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def display_choices(choices):
    """Print numbered choices with hanging-indent wrapping."""
    width = terminal_width()
    digits = max(2, len(str(max(0, len(choices) - 1))))

    for i, choice in enumerate(choices):
        prefix = f"{i:0{digits}d}] "
        print(
            wrap_line(
                choice,
                width=width,
                initial_indent=prefix,
                subsequent_indent=" " * len(prefix),
            )
        )


def show_help():
    printer(QuizSource.HELP_RAW, end="")
    input()


def parser(question):
    while True:
        clear_screen()
        printer(QuizSource.HEADER, num=question["id"], end="")
        printer(question["question"] + "^^", end="")

        if question["type"] == "T":
            answer = input("> ")
            if answer.lower() == "help":
                show_help()
                continue
            return answer

        display_choices(question["choices"])
        print()
        answer = input("> ").strip()

        if answer.lower() == "help":
            show_help()
            continue

        try:
            choice = int(answer)
        except ValueError:
            continue

        if 0 <= choice < len(question["choices"]):
            return choice


def wait_for_continue(text, uid=None):
    while True:
        printer(text, uid=uid, end="")
        if input().strip() == "CONTINUE":
            return
        clear_screen()


def main():
    uid = generate_uin()

    wait_for_continue(QuizSource.INTRO_RAW)
    clear_screen()
    wait_for_continue(QuizSource.UIN_NOTICE_RAW, uid=uid)

    for question in QuizSource.QUESTIONS:
        parser(question)

    clear_screen()
    printer(QuizSource.FINISH_RAW, end="")
    input()

    # The SWF deliberately fails this final UIN entry regardless of whether
    # the player remembered the generated value correctly.
    clear_screen()
    printer(QuizSource.FAIL_RAW)


if __name__ == "__main__":
    main()
