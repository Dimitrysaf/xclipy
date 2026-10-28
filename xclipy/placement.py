"""Where the overlay opens: under the text cursor, or in the bottom right corner."""

GAP = 4      # between the text cursor and the overlay
MARGIN = 12  # from the edges of the screen, without a text cursor


def place(size, workarea, caret=None):
    """The top left corner for an overlay of ``size`` (width, height).

    ``workarea`` is the monitor's (x, y, width, height) without its panels and
    ``caret`` the text cursor's, or None. The overlay goes below the text
    cursor, above it when there is no room below, and always stays inside the
    work area.
    """
    width, height = size
    area_x, area_y, area_width, area_height = workarea
    right, bottom = area_x + area_width, area_y + area_height
    if caret is None:
        return right - width - MARGIN, bottom - height - MARGIN
    caret_x, caret_y, _caret_width, caret_height = caret
    y = caret_y + caret_height + GAP
    if y + height > bottom and caret_y - GAP - height >= area_y:
        y = caret_y - GAP - height
    x = min(max(caret_x, area_x), right - width)
    y = min(max(y, area_y), bottom - height)
    return x, y
