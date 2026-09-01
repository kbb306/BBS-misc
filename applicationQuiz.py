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

# The Flash form does not use the viewer's screen height to decide when to
# start a new choice column.  It wraps at a fixed Y coordinate.  Sixteen
# terminal rows is the closest match for Page 3 in an 80-column terminal.
CHOICE_ROWS = max(4, int(os.environ.get("APERTURE_CHOICE_ROWS", "16")))
CHOICE_COLUMN_GAP = 4
CHOICE_MIN_COLUMN_WIDTH = 20


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
                special = msvcrt.getwch()
                if special == "I":
                    return "PGUP"
                if special == "Q":
                    return "PGDN"
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

            # SyncTERM/xterm-style Page Up and Page Down keys.
            # Page Up   = ESC [ 5 ~
            # Page Down = ESC [ 6 ~
            if ch == "\x1b":
                second = sys.stdin.read(1)
                if second == "[":
                    third = sys.stdin.read(1)
                    if third in ("5", "6"):
                        fourth = sys.stdin.read(1)
                        if fourth == "~":
                            return "PGUP" if third == "5" else "PGDN"
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


def _max_choice_columns(width):
    """How many readable choice columns fit across this terminal."""
    return max(
        1,
        (width + CHOICE_COLUMN_GAP)
        // (CHOICE_MIN_COLUMN_WIDTH + CHOICE_COLUMN_GAP),
    )


def display_choices(choices, page=0):
    """
    Display choices top-to-bottom, then continue in columns to the right.

    The original Flash code wraps choice fields when their Y coordinate passes
    500 pixels; it does not use the browser/terminal window height.  For the
    terminal recreation we map that fixed cutoff to CHOICE_ROWS (16 by
    default), which gives Page 3 the original 01-16 / 17-25 layout.

    Lists too large for one terminal-width page can be browsed with Page
    Up/Page Down, mirroring the original form's PGUP/PGDN behavior.
    """
    width = terminal_width()
    digits = max(2, len(str(max(1, len(choices)))))
    max_columns = _max_choice_columns(width)
    page_capacity = CHOICE_ROWS * max_columns
    page_count = max(1, (len(choices) + page_capacity - 1) // page_capacity)
    page = max(0, min(page, page_count - 1))

    first = page * page_capacity
    last = min(first + page_capacity, len(choices))
    page_choices = choices[first:last]

    column_count = max(
        1,
        min(max_columns, (len(page_choices) + CHOICE_ROWS - 1) // CHOICE_ROWS),
    )
    column_width = (
        width - CHOICE_COLUMN_GAP * (column_count - 1)
    ) // column_count

    columns = [[] for _ in range(column_count)]

    for local_index, choice in enumerate(page_choices):
        global_number = first + local_index + 1
        column_index = local_index // CHOICE_ROWS
        lines = _choice_lines(global_number, choice, column_width, digits)

        # A wrapped answer can consume more than one physical terminal line.
        # Keep it with its numbered entry; this may make a column a little
        # taller than 16 physical rows, but never splits one answer in half.
        columns[column_index].extend(lines)

    band_height = max(len(column) for column in columns)
    for row in range(band_height):
        parts = []
        for column in columns:
            cell = column[row] if row < len(column) else ""
            parts.append(cell.ljust(column_width))
        print((" " * CHOICE_COLUMN_GAP).join(parts).rstrip())

    if page_count > 1:
        print()
        print(
            "[{} total choices : PGUP/PGDN to navigate]".format(len(choices))
        )

    return page, page_count

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

        page = 0
        while True:
            clear_screen()
            printer(QuizSource.HEADER, num=question["id"], end="")
            printer(question["question"] + "^^", end="")
            page, page_count = display_choices(question["choices"], page=page)
            print()
            answer = uppercase_input("> ").strip()

            if answer == "HELP":
                show_help()
                break

            if answer == "PGDN":
                if page + 1 < page_count:
                    page += 1
                continue

            if answer == "PGUP":
                if page > 0:
                    page -= 1
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
