"""Pure configuration helpers for the compact Image Occlusion dialog."""

TAB_LABELS = ("1", "2")
TAB_NAMES = ("Default", "Fields")
ADD_BUTTON_LABELS = ("Hide All", "Hide One", "X")
DEFAULT_EDITOR_MAX_FRACTION = 0.30


def bounded_default_editor_height(natural_height, dialog_height):
    """Fit the native Front editor while reserving most space for the canvas."""
    natural = max(1, int(round(natural_height)))
    maximum = max(1, int(dialog_height * DEFAULT_EDITOR_MAX_FRACTION))
    return min(natural, maximum)
