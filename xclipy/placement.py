"""Where the overlay opens: at the bottom right of the mouse pointer.

Only when there is no pointer position does it go to the bottom right corner of
the screen. The Cinnamon helper places it the same way on Wayland.
"""

GAP = 1      # between the mouse pointer and the overlay, as for a right-click menu
MARGIN = 12  # from the edges of the screen, without a pointer


def place(size, workarea, pointer=None):
    """The top left corner for an overlay of ``size`` (width, height).

    ``workarea`` is the monitor's (x, y, width, height) without its panels and
    ``pointer`` the mouse pointer's (x, y), or None. Near the right or bottom edge
    the overlay opens to the left of or above the pointer instead, and it always
    stays inside the work area.
    """
    width, height = size
    area_x, area_y, area_width, area_height = workarea
    right, bottom = area_x + area_width, area_y + area_height
    if pointer is None:
        return right - width - MARGIN, bottom - height - MARGIN
    pointer_x, pointer_y = pointer
    x = pointer_x + GAP
    if x + width > right and pointer_x - GAP - width >= area_x:
        x = pointer_x - GAP - width
    y = pointer_y + GAP
    if y + height > bottom and pointer_y - GAP - height >= area_y:
        y = pointer_y - GAP - height
    x = min(max(x, area_x), right - width)
    y = min(max(y, area_y), bottom - height)
    return x, y
