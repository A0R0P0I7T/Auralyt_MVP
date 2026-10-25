"""Derive brand identity (registrable domain and name) from a website hostname."""
from typing import List

SECOND_LEVEL_LABELS = {"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or", "go"}


def _host_labels(host: str) -> List[str]:
    clean = (host or "").strip().lower().rstrip(".")
    if clean.startswith("www."):
        clean = clean[4:]
    return [label for label in clean.split(".") if label]


def registrable_domain(host: str) -> str:
    """Return the root domain, e.g. 'in.louisvuitton.com' -> 'louisvuitton.com'."""
    labels = _host_labels(host)
    if len(labels) <= 2:
        return ".".join(labels)
    if labels[-2] in SECOND_LEVEL_LABELS and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def registrable_label(host: str) -> str:
    """Return the brand label of the root domain, e.g. 'in.louisvuitton.com' -> 'louisvuitton'."""
    return registrable_domain(host).split(".")[0]


def infer_business_name_from_host(host: str) -> str:
    label = registrable_label(host)
    return label.capitalize() if label else ""


def is_inferred_business_name(name: str, host: str) -> bool:
    """True when a stored business name is just the hostname-derived placeholder.

    Includes the legacy placeholder (first hostname label, e.g. 'In' for in.louisvuitton.com).
    """
    if not name:
        return True
    labels = _host_labels(host)
    legacy = labels[0].capitalize() if labels else ""
    return name in {infer_business_name_from_host(host), legacy}
