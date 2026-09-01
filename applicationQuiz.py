import os
import secrets
import shutil
import string
import sys
import textwrap

import QuizSource

# Original Aperture terminal look: green text on a black background.
SCREEN_STYLE = "\x1b[32;40m"
RESET_STYLE = "\x1b[0m"
BLINK_ON = "\x1b[5m"
BLINK_OFF = "\x1b[25m"


def ansi_supported():
    """Best-effort ANSI detection, overridable for BBS/telnet setups."""
    override = os.environ.get("APERTURE_COLOR")
    if override == "1":
        return True
    if override == "0":
        return False

    term = os.environ.get("TERM", "").lower()
    return sys.stdout.isatty() or term not in ("", "dumb")


def set_screen_style():
    if ansi_supported():
        sys.stdout.write(SCREEN_STYLE)
        sys.stdout.flush()


def reset_screen_style():
    if ansi_supported():
        sys.stdout.write(RESET_STYLE)
        sys.stdout.flush()


def generate_uin(length=64):
    """Return a case-sensitive UIN(+L) matching the site's 64-character style."""
    alphabet = string.ascii_lowercase + string.digits
    while True:
        uid = "".join(secrets.choice(alphabet) for _ in range(length))
        # UIN(+L) should actually contain both digits and letters.
        if any(ch.isdigit() for ch in uid) and any(ch.isalpha() for ch in uid):
            return uid


def terminal_size():
    """Return the live terminal size, with a classic 80x24 fallback."""
    size = shutil.get_terminal_size(fallback=(80, 24))
    return max(20, size.columns), max(10, size.lines)


def terminal_width():
    return terminal_size()[0]


def terminal_height():
    return terminal_size()[1]


def blink_supported():
    """Best-effort ANSI blink detection, overridable for BBS/telnet setups."""
    override = os.environ.get("APERTURE_BLINK")
    if override == "1":
        return True
    if override == "0":
        return False
    return ansi_supported()


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


def rendered_row_count(text, num=None):
    """Count terminal rows advanced by printer() for ordinary SWF text."""
    if num is not None:
        text = text.replace("#", str(num))

    text = text.replace("^", "\n")
    width = terminal_width()
    rendered_lines = []

    for line in text.split("\n"):
        if line == "> ":
            rendered_lines.append(line)
        else:
            rendered_lines.append(wrap_line(line, width=width))

    # printer(..., end="") advances once for every newline in the rendered text.
    return "\n".join(rendered_lines).count("\n")


def printer(text, num=None, uid=None, end="\n", blink_uid=True):
    """Render the SWF's custom formatting tokens and wrap to terminal width."""
    if num is not None:
        text = text.replace("#", str(num))

    uid_marker = None
    if uid is not None:
        uid_marker = "[{}]".format(uid)
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
            uid_marker, "{}{}{}".format(BLINK_ON, uid_marker, BLINK_OFF)
        )

    print(rendered, end=end, flush=True)


def clear_screen():
    if ansi_supported():
        # ANSI clear + home keeps the program independent of the local shell
        # and works cleanly over telnet/PTY connections.
        sys.stdout.write("\x1b[2J\x1b[H")
        set_screen_style()
    else:
        os.system("cls" if os.name == "nt" else "clear")


def uppercase_input(prompt=""):
    """
    Read input while echoing alphabetic characters in uppercase.

    On a real TTY/PTY (including typical BBS/telnet sessions), characters are
    uppercased as the player types them. If stdin is not a TTY, the completed
    line is simply converted to uppercase.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()

    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        if line == "":
            raise EOFError
        return line.rstrip("\r\n").upper()

    if os.name == "nt":
        import msvcrt

        chars = []
        while True:
            ch = msvcrt.getwch()

            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return "".join(chars)

            if ch == "\x03":
                raise KeyboardInterrupt

            if ch in ("\x08", "\x7f"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            # Windows special keys arrive as a two-character sequence.
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue

            if ch.isprintable():
                ch = ch.upper()
                chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

    # POSIX path: use raw mode so lowercase keystrokes never get echoed before
    # we have a chance to turn them into uppercase.
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars = []

    try:
        tty.setraw(fd)

        while True:
            ch = sys.stdin.read(1)

            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return "".join(chars)

            if ch == "\x03":
                raise KeyboardInterrupt

            if ch == "\x04":
                if not chars:
                    raise EOFError
                continue

            if ch in ("\x08", "\x7f"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            if ch.isprintable():
                ch = ch.upper()
                chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _choice_lines(number, choice, column_width, digits):
    """Format one numbered choice inside a single display column."""
    prefix = "{:0{}d}] ".format(number, digits)
    wrapped = wrap_line(
        choice,
        width=column_width,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
    )
    return wrapped.split("\n")


def _pack_choice_columns(choices, column_width, rows_per_column, digits):
    """
    Fill each column top-to-bottom before moving right, like the Flash form.

    Wrapped choices consume however many physical rows they need, so a long
    choice will not collide with the next choice or the next column.
    """
    columns = [[]]

    for number, choice in enumerate(choices, start=1):
        lines = _choice_lines(number, choice, column_width, digits)

        if columns[-1] and len(columns[-1]) + len(lines) > rows_per_column:
            columns.append([])

        columns[-1].extend(lines)

    return columns


def display_choices(choices, rows_used=0):
    """
    Lay choices out in vertical columns, matching the original Flash form.

    The first column fills downward to the remaining terminal height, then the
    list continues at the top of the next column.  This is the behavior visible
    on Page 3 of the original: 01-16 on the left, then 17-25 on the right.
    """
    width, height = terminal_size()
    digits = max(2, len(str(max(1, len(choices)))))

    # Leave one row for the blank line before the prompt and one for the prompt.
    rows_per_column = max(4, height - rows_used - 2)

    # Try the smallest number of columns that lets the complete list fit in
    # the visible area.  Four spaces between columns reproduces the generous
    # separation of the original while still working on an 80-column BBS.
    gap = 4
    min_column_width = digits + 8
    max_columns = max(1, (width + gap) // (min_column_width + gap))

    chosen_columns = None
    chosen_width = None

    for column_count in range(1, max_columns + 1):
        column_width = (width - gap * (column_count - 1)) // column_count
        if column_width < min_column_width:
            break

        columns = _pack_choice_columns(
            choices, column_width, rows_per_column, digits
        )

        if len(columns) <= column_count:
            chosen_columns = columns
            chosen_width = column_width
            break

    if chosen_columns is None:
        # Some lists (especially the enormous animal list) cannot fit on one
        # terminal screen.  Use the widest practical multi-column layout and
        # allow normal terminal scrollback for the remainder.
        column_count = max_columns
        chosen_width = (width - gap * (column_count - 1)) // column_count
        chosen_columns = _pack_choice_columns(
            choices, chosen_width, rows_per_column, digits
        )

    # If more logical columns were needed than physically fit side-by-side,
    # print them in successive horizontal bands.
    for band_start in range(0, len(chosen_columns), max_columns):
        band = chosen_columns[band_start:band_start + max_columns]
        band_height = max(len(column) for column in band)

        for row in range(band_height):
            parts = []
            for column in band:
                cell = column[row] if row < len(column) else ""
                parts.append(cell.ljust(chosen_width))
            print((" " * gap).join(parts).rstrip())


def show_help():
    printer(QuizSource.HELP_RAW, end="")
    uppercase_input()


def parser(question):
    while True:
        clear_screen()
        printer(QuizSource.HEADER, num=question["id"], end="")
        printer(question["question"] + "^^", end="")

        if question["type"] == "T":
            answer = uppercase_input("> ")
            if answer == "HELP":
                show_help()
                continue
            return answer

        rows_used = (
            rendered_row_count(QuizSource.HEADER, num=question["id"])
            + rendered_row_count(question["question"] + "^^")
        )
        display_choices(question["choices"], rows_used=rows_used)
        print()
        answer = uppercase_input("> ").strip()

        if answer == "HELP":
            show_help()
            continue

        try:
            choice = int(answer)
        except ValueError:
            continue

        if 1 <= choice <= len(question["choices"]):
            return choice


def wait_for_continue(text, uid=None):
    while True:
        printer(text, uid=uid, end="")
        if uppercase_input().strip() == "CONTINUE":
            return
        clear_screen()


def main():
    uid = generate_uin()
    set_screen_style()
    clear_screen()

    try:
        wait_for_continue(QuizSource.INTRO_RAW)
        clear_screen()
        wait_for_continue(QuizSource.UIN_NOTICE_RAW, uid=uid)

        for question in QuizSource.QUESTIONS:
            parser(question)

        clear_screen()
        printer(QuizSource.FINISH_RAW, end="")
        uppercase_input()

        # The SWF deliberately fails this final UIN entry regardless of whether
        # the player remembered the generated value correctly.
        clear_screen()
        printer(QuizSource.FAIL_RAW)
    finally:
        reset_screen_style()


if __name__ == "__main__":
    main()
