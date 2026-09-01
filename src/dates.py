"""Turns whatever date string the extractor pulled out of free text
('October 15, 2026', '15 Oct 2026', '2026-10-15', 'within 18 months')
into an ISO date where possible. Genuinely ambiguous or relative
deadlines ('within 18 months') are left unparsed rather than guessed --
a wrong silently-parsed date is worse than an obligation with no
computed status."""
from datetime import datetime
from dateutil import parser as dateutil_parser

_SENTINEL = datetime(1, 1, 1)


def try_parse_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        dt = dateutil_parser.parse(text, fuzzy=True, default=_SENTINEL)
        # dateutil silently fills in missing components using `default`;
        # if it didn't find a real year in the text, reject the parse.
        if dt.year == 1:
            return None
        return dt.date().isoformat()
    except (ValueError, OverflowError):
        return None
