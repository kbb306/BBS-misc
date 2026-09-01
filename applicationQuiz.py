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

# SyncTERM/CTerm can repurpose or disable the legacy blink bit:
#   ?33h = blink becomes bright background
#   ?34h = blink selects alternate character set
#   ?35h = blink disabled
# Reset all three before using SGR 5 so the UIN actually flashes.
ENABLE_REAL_BLINK = "\x1b[?33l\x1b[?34l\x1b[?35l"

# The Flash form does not use the viewer's screen height to decide when to
# start a new choice column.  It wraps at a fixed Y coordinate.  Sixteen
# terminal rows is the closest match for Page 3 in an 80-column terminal.
CHOICE_ROWS = max(4, int(os.environ.get("APERTURE_CHOICE_ROWS", "16")))
CHOICE_COLUMN_GAP = 4
CHOICE_MIN_COLUMN_WIDTH = 20

# SyncTERM and the server-side PTY do not always agree about screen height.
# Use a fixed Flash-like viewport for layout, with environment overrides.
SCREEN_ROWS = max(12, int(os.environ.get("APERTURE_SCREEN_ROWS", "25")))
QUESTION_PAGE_ROWS = max(
    4,
    int(os.environ.get("APERTURE_QUESTION_ROWS", str(SCREEN_ROWS - 7))),
)
MIN_INLINE_CHOICE_ROWS = 6
STATIC_PAGE_ROWS = max(
    4,
    int(os.environ.get("APERTURE_STATIC_ROWS", str(SCREEN_ROWS - 4))),
)


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


def enable_real_blink():
    """Put SyncTERM/CTerm back into actual-blink mode."""
    if blink_supported():
        sys.stdout.write(ENABLE_REAL_BLINK)
        sys.stdout.flush()


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
        enable_real_blink()
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

            # Page Up/Page Down sequences.
            #
            # SyncTERM:
            #   Page Up   = ESC [ V
            #   Page Down = ESC [ U
            #
            # xterm-compatible terminals:
            #   Page Up   = ESC [ 5 ~
            #   Page Down = ESC [ 6 ~
            if ch == "\x1b":
                second = sys.stdin.read(1)
                if second == "[":
                    third = sys.stdin.read(1)

                    # Native SyncTERM sequences.
                    if third == "V":
                        return "PGUP"
                    if third == "U":
                        return "PGDN"

                    # Common xterm/VT-style sequences.
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


def _wrapped_swf_lines(text):
    """Turn SWF ^ breaks and terminal wrapping into physical screen rows."""
    text = text.replace("^", "\n")
    width = terminal_width()
    lines = []

    for logical_line in text.split("\n"):
        if logical_line == "":
            lines.append("")
        else:
            lines.extend(wrap_line(logical_line, width=width).split("\n"))

    return lines


def _question_pages(question):
    """Split a question body into PGUP/PGDN-sized physical-row pages."""
    lines = _wrapped_swf_lines(question["question"])
    if not lines:
        lines = [""]

    return [
        lines[i:i + QUESTION_PAGE_ROWS]
        for i in range(0, len(lines), QUESTION_PAGE_ROWS)
    ]


def _print_question_screen(question, body_lines):
    """Clear and redraw the form header plus one page of question text."""
    clear_screen()
    printer(QuizSource.HEADER, num=question["id"], end="")

    for line in body_lines:
        print(line)

    # Original form leaves a blank row between the question and its controls.
    print()


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


def _build_choice_pages(choices, rows_per_column):
    """
    Pack numbered choices by *physical terminal rows*.

    This is important for long answer text: a wrapped answer consumes two or
    more rows instead of causing the bottom of the screen to scroll away.
    """
    width = terminal_width()
    digits = max(2, len(str(max(1, len(choices)))))
    max_columns = _max_choice_columns(width)

    # Pack conservatively using the narrowest width a full page could have.
    # When a page uses fewer columns, rendering only gets wider and therefore
    # cannot require more wrapped rows than the packing calculation.
    packing_width = (
        width - CHOICE_COLUMN_GAP * (max_columns - 1)
    ) // max_columns

    pages = []
    columns = [[]]
    used_rows = 0

    for number, choice in enumerate(choices, start=1):
        needed = len(_choice_lines(number, choice, packing_width, digits))

        if columns[-1] and used_rows + needed > rows_per_column:
            if len(columns) >= max_columns:
                pages.append(columns)
                columns = [[]]
            else:
                columns.append([])
            used_rows = 0

        columns[-1].append((number, choice))
        used_rows += needed

    if columns and any(columns):
        pages.append(columns)

    if not pages:
        pages = [[[]]]

    return pages, digits


def display_choices(choices, page=0, rows_per_column=CHOICE_ROWS):
    """
    Display choices top-to-bottom, then continue in columns to the right.

    Pages are packed according to physical rows, so both very long lists and
    individually long choices remain inside the terminal viewport.
    """
    width = terminal_width()
    rows_per_column = max(4, rows_per_column)
    pages, digits = _build_choice_pages(choices, rows_per_column)
    page_count = len(pages)
    page = max(0, min(page, page_count - 1))

    entries_by_column = pages[page]
    column_count = max(1, len(entries_by_column))
    column_width = (
        width - CHOICE_COLUMN_GAP * (column_count - 1)
    ) // column_count

    columns = []
    for entries in entries_by_column:
        rendered = []
        for number, choice in entries:
            rendered.extend(
                _choice_lines(number, choice, column_width, digits)
            )
        columns.append(rendered)

    band_height = max(len(column) for column in columns)
    for row in range(band_height):
        parts = []
        for column in columns:
            cell = column[row] if row < len(column) else ""
            parts.append(cell.ljust(column_width))
        print((" " * CHOICE_COLUMN_GAP).join(parts).rstrip())

    return page, page_count


def _choice_page_count(choices, rows_per_column):
    pages, _ = _build_choice_pages(choices, rows_per_column)
    return len(pages)


def _choice_rows_for_body(body_row_count, choices):
    """
    Work out how many physical choice rows can coexist with this body page.

    Header, blank separators, navigation hint (when needed), and the input
    prompt all consume rows too.  If fewer than MIN_INLINE_CHOICE_ROWS remain,
    the choices are moved to their own PGDN screen.
    """
    # Header consumes two rows because HEADER ends in ^^.
    # Also reserve: one blank after body, one blank before prompt, prompt row.
    available = SCREEN_ROWS - 2 - body_row_count - 3
    if available < MIN_INLINE_CHOICE_ROWS:
        return 0

    rows = min(CHOICE_ROWS, available)

    # A multipage choice list needs one extra row for the navigation hint.
    if _choice_page_count(choices, rows) > 1:
        rows -= 1

    if rows < MIN_INLINE_CHOICE_ROWS:
        return 0

    return rows


def _navigation_hint(can_up, can_down):
    if can_up and can_down:
        return "[PGUP/PGDN] NAVIGATE"
    if can_down:
        return "[PGDN] MORE"
    if can_up:
        return "[PGUP] REVIEW"
    return ""

def show_help():
    printer(QuizSource.HELP_RAW, end="")
    uppercase_input()


def parser(question):
    body_pages = _question_pages(question)
    body_page = 0

    # Free-text questions can page through a long body before accepting input.
    if question["type"] == "T":
        while True:
            body_lines = body_pages[body_page]
            _print_question_screen(question, body_lines)

            can_up = body_page > 0
            can_down = body_page + 1 < len(body_pages)
            hint = _navigation_hint(can_up, can_down)
            if hint:
                print(hint)

            answer = uppercase_input("> ").strip()

            if answer == "HELP":
                show_help()
                continue

            if answer == "PGDN" and can_down:
                body_page += 1
                continue

            if answer == "PGUP" and can_up:
                body_page -= 1
                continue

            # Do not accept an answer until the player has reached the last
            # page of a paged question body.
            if can_down:
                continue

            return answer

    choice_page = 0
    choices_only = False

    while True:
        body_lines = body_pages[body_page]

        # All non-final body pages are reading-only pages.
        if body_page + 1 < len(body_pages):
            _print_question_screen(question, body_lines)
            print(_navigation_hint(body_page > 0, True))
            command = uppercase_input("> ").strip()

            if command == "HELP":
                show_help()
                continue
            if command == "PGDN":
                body_page += 1
            elif command == "PGUP" and body_page > 0:
                body_page -= 1
            continue

        # On the final body page, show choices inline if enough physical rows
        # remain.  Otherwise PGDN advances to a choices-only screen.
        inline_rows = _choice_rows_for_body(
            len(body_lines), question["choices"]
        )

        if not choices_only and inline_rows == 0:
            _print_question_screen(question, body_lines)
            print(_navigation_hint(body_page > 0, True))
            command = uppercase_input("> ").strip()

            if command == "HELP":
                show_help()
                continue
            if command == "PGUP" and body_page > 0:
                body_page -= 1
            elif command == "PGDN":
                choices_only = True
                choice_page = 0
            continue

        if choices_only:
            clear_screen()
            printer(QuizSource.HEADER, num=question["id"], end="")
            rows_per_column = CHOICE_ROWS
        else:
            _print_question_screen(question, body_lines)
            rows_per_column = inline_rows

        # Reserve a row for the navigation hint if this choice set pages.
        if _choice_page_count(question["choices"], rows_per_column) > 1:
            rows_per_column = max(4, rows_per_column - 1)

        choice_page, choice_page_count = display_choices(
            question["choices"],
            page=choice_page,
            rows_per_column=rows_per_column,
        )

        can_up = choice_page > 0 or choices_only or body_page > 0
        can_down = choice_page + 1 < choice_page_count
        hint = _navigation_hint(can_up, can_down)
        if hint:
            print(hint)

        print()
        answer = uppercase_input("> ").strip()

        if answer == "HELP":
            show_help()
            continue

        if answer == "PGDN":
            if choice_page + 1 < choice_page_count:
                choice_page += 1
            continue

        if answer == "PGUP":
            if choice_page > 0:
                choice_page -= 1
            elif choices_only:
                choices_only = False
            elif body_page > 0:
                body_page -= 1
            continue

        try:
            choice = int(answer)
        except ValueError:
            continue

        if 1 <= choice <= len(question["choices"]):
            return choice

def _static_pages(text, uid=None):
    """
    Split long non-question screens (intro/UIN notice) into terminal pages.

    The SWF strings include their own final "> " prompt.  Strip that prompt
    from the pageable body and draw a fresh prompt on every page so PGUP/PGDN
    can be handled without letting the terminal scroll the beginning away.
    """
    uid_marker = None
    if uid is not None:
        uid_marker = "[{}]".format(uid)
        text = text.replace("@", uid_marker)

    lines = _wrapped_swf_lines(text)

    # INTRO_RAW and UIN_NOTICE_RAW both end with a literal "> " line.
    if lines and lines[-1].strip() == ">":
        lines.pop()

    # Trim only surplus blank rows at the very end; preserve internal spacing.
    while lines and lines[-1] == "":
        lines.pop()

    if not lines:
        lines = [""]

    pages = [
        lines[i:i + STATIC_PAGE_ROWS]
        for i in range(0, len(lines), STATIC_PAGE_ROWS)
    ]

    return pages, uid_marker


def _print_static_page(lines, uid_marker=None):
    clear_screen()

    for line in lines:
        if (
            uid_marker is not None
            and uid_marker in line
            and blink_supported()
        ):
            enable_real_blink()
            line = line.replace(
                uid_marker,
                "{}{}{}".format(BLINK_ON, uid_marker, BLINK_OFF),
            )
        print(line)


def wait_for_continue(text, uid=None):
    pages, uid_marker = _static_pages(text, uid=uid)
    page = 0

    while True:
        _print_static_page(pages[page], uid_marker=uid_marker)

        can_up = page > 0
        can_down = page + 1 < len(pages)
        hint = _navigation_hint(can_up, can_down)
        if hint:
            print(hint)

        answer = uppercase_input("> ").strip()

        if answer == "PGDN" and can_down:
            page += 1
            continue

        if answer == "PGUP" and can_up:
            page -= 1
            continue

        # Force the user to reach the final page before CONTINUE is accepted.
        # This also keeps the first half of the disclaimer reviewable with PGUP.
        if answer == "CONTINUE" and not can_down:
            return


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
