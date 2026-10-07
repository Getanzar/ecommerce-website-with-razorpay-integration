def matching_age_groups(selected, choices):
    """Match overlapping ranges, without treating adjacent boundaries as overlap."""
    valid = dict(choices)
    if selected not in valid:
        return []
    low, high = map(int, selected.split("-"))
    return [value for value in valid
            if max(low, int(value.split("-")[0])) < min(high, int(value.split("-")[1]))]
