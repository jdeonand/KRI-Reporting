"""Pure-Python RAG logic. Mirrors the SQL in kri_status; tests assert the two agree."""
RANK = {"Green": 0, "Amber": 1, "Red": 2}


def status_for(value, amber, red, direction):
    """Return 'Green', 'Amber' or 'Red'. A value exactly on a threshold takes the worse status."""
    if value is None:
        return None
    if direction == "higher_is_worse":
        return "Red" if value >= red else "Amber" if value >= amber else "Green"
    return "Red" if value <= red else "Amber" if value <= amber else "Green"
