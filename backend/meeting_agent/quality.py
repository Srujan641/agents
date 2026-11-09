import calendar
import logging
import re
from datetime import date, timedelta

from meeting_agent.schemas import ActionItem

logger = logging.getLogger(__name__)

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS |= {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_MONTH_DAY = re.compile(rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_PATTERN})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_IN_UNITS = re.compile(r"\bin\s+(\d+)\s+(day|week)s?\b")
_MAX_DAYS_AHEAD = 365
_NGRAM_SIZE = 3
_MIN_QUOTE_COVERAGE = 0.8
_MAX_CONTEXT_CHARS = 2000

_GROUP_OWNERS = {
    "all", "attendees", "everybody", "everyone", "group", "members", "participants", "staff",
    "team", "the group", "the team", "them", "they", "us", "we",
}  # fmt: skip
_STOPWORDS = {"a", "an", "and", "by", "for", "in", "of", "on", "the", "to", "with"}


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return " ".join(text.lower().split())


def resolve_deadline(text: str, meeting_date: date) -> date | None:
    """Turn spoken deadlines into dates. Returns None when the date can't be known."""
    resolved = _parse_deadline(normalize(text), meeting_date)
    if resolved is None or not 0 <= (resolved - meeting_date).days <= _MAX_DAYS_AHEAD:
        return None
    return resolved


def _parse_deadline(text: str, today: date) -> date | None:
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    try:
        if match := _ISO_DATE.search(text):
            return date(int(match[1]), int(match[2]), int(match[3]))
        if match := _MONTH_DAY.search(text):
            return _next_month_day(_MONTHS[match[1]], int(match[2]), today)
        if match := _DAY_MONTH.search(text):
            return _next_month_day(_MONTHS[match[2]], int(match[1]), today)
    except ValueError:  # an impossible date, such as February 30
        return None
    if match := _IN_UNITS.search(text):
        return today + timedelta(days=int(match[1]) * (7 if match[2] == "week" else 1))
    if "tomorrow" in text:
        return today + timedelta(days=1)
    if "today" in text or "end of day" in text or "eod" in text.split():
        return today
    if "end of the month" in text or "end of month" in text:
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])
    if "next week" in text:
        return friday + timedelta(days=7)
    if "this week" in text or "end of the week" in text or "end of week" in text:
        return friday
    for index, weekday in enumerate(_WEEKDAYS):
        if weekday in text:
            days_ahead = (index - today.weekday()) % 7 or 7
            # "Next Friday" said on a Wednesday means Friday of the following week.
            if f"next {weekday}" in text and days_ahead < 7 and index > today.weekday():
                days_ahead += 7
            return today + timedelta(days=days_ahead)
    return None


def _next_month_day(month: int, day: int, today: date) -> date:
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def apply_grounding(items: list[ActionItem], transcript: str) -> list[ActionItem]:
    """Drop items whose quote isn't in the transcript, and clear unsupported fields."""
    source = normalize(transcript)
    kept: list[ActionItem] = []
    for item in items:
        if not _quote_is_grounded(item.source_quote, source):
            logger.info("Rejected, quote not in transcript: %r", item.description)
            continue
        updates: dict[str, object] = {}
        if item.owner and not _is_real_owner(item.owner, source):
            updates["owner"] = None
        if item.deadline_text and normalize(item.deadline_text) not in source:
            updates["deadline_text"] = None
        kept.append(item.model_copy(update=updates))
    return kept


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", normalize(text))


def _quote_is_grounded(quote: str, source: str) -> bool:
    """Accept exact quotes, and near-exact ones where spoken transcripts differ slightly."""
    if normalize(quote) in source:
        return True
    quote_words = _words(quote)
    if len(quote_words) < _NGRAM_SIZE:
        return False
    # Padded so a quote can't match by joining the end of one word to the start of another.
    padded = f" {' '.join(_words(source))} "
    ngrams = [
        " ".join(quote_words[i : i + _NGRAM_SIZE])
        for i in range(len(quote_words) - _NGRAM_SIZE + 1)
    ]
    found = sum(f" {ngram} " in padded for ngram in ngrams)
    return found / len(ngrams) >= _MIN_QUOTE_COVERAGE


def find_context(quote: str, transcript: str, before: int = 3, after: int = 1) -> str:
    """Return the transcript lines around a quote, so a reviewer can see who said what."""
    lines = transcript.splitlines()
    wanted = set(_words(quote))
    best = max(range(len(lines)), key=lambda i: len(wanted & set(_words(lines[i]))), default=0)
    return "\n".join(lines[max(0, best - before) : best + after + 1])[:_MAX_CONTEXT_CHARS]


def _is_real_owner(owner: str, source: str) -> bool:
    name = normalize(owner)
    return name not in _GROUP_OWNERS and name in source


def apply_deadlines(items: list[ActionItem], meeting_date: date | None) -> list[ActionItem]:
    if meeting_date is None:
        return items
    return [
        item.model_copy(
            update={
                "deadline": resolve_deadline(item.deadline_text, meeting_date)
                if item.deadline_text
                else None
            }
        )
        for item in items
    ]


def remove_duplicates(items: list[ActionItem]) -> list[ActionItem]:
    """Keep the first of each duplicate, filling in an owner or deadline it lacks."""
    kept: list[ActionItem] = []
    for item in items:
        match = next((i for i, other in enumerate(kept) if _is_duplicate(item, other)), None)
        if match is None:
            kept.append(item)
            continue
        logger.info("Rejected, duplicate: %r", item.description)
        first = kept[match]
        kept[match] = first.model_copy(
            update={
                "owner": first.owner or item.owner,
                "deadline_text": first.deadline_text or item.deadline_text,
                "deadline": first.deadline or item.deadline,
            }
        )
    return kept


def _is_duplicate(a: ActionItem, b: ActionItem) -> bool:
    similarity = _similarity(a.description, b.description)
    same_quote = normalize(a.source_quote) == normalize(b.source_quote)
    # One quote can hold two different tasks, so a matching quote alone isn't enough.
    return similarity >= 0.7 or (same_quote and similarity >= 0.4)


def _similarity(a: str, b: str) -> float:
    first, second = _keywords(a), _keywords(b)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def _keywords(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", normalize(text))) - _STOPWORDS
