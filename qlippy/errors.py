"""Recognising what kind of error QGIS (or a plugin) just reported."""

import re

# Error kinds, recognised by words in the error text (checked in this order).
ERROR_KINDS = [
    # Processing failures first: their messages often contain other trigger words.
    ("processing_source_failed", ("could not load source layer", "unable to load source", "could not load layer",
                                  "invalid source layer", "source layer is invalid", "could not open source")),
    ("processing_parameter_failed", ("incorrect parameter value", "wrong or missing parameter",
                                     "missing parameter value", "is not a valid parameter", "invalid parameter")),
    ("processing_cancelled", ("execution canceled", "execution cancelled", "was canceled", "was cancelled",
                              "canceled by user", "cancelled by user")),
    ("error_none", ("nonetype",)),
    ("error_memory", ("memoryerror", "out of memory", "bad_alloc", "cannot allocate")),
    ("error_permission", ("permission denied", "permissionerror", "read-only", "access is denied",
                          "database is locked", "locked")),
    ("error_field", ("keyerror", "no such field", "unknown field", "field not found", "field does not exist",
                     "no such column", "column not found")),
    ("error_file", ("no such file", "filenotfounderror", "does not exist", "not found", "unable to open",
                    "could not open", "failed to open", "cannot open", "is not a valid or recognized")),
    ("error_geometry", ("invalid geometr", "geos", "self-intersect", "topologyexception", "ring self")),
    ("error_crs", ("proj:", "proj error", "transform", "crs", "projection")),
    ("error_network", ("timed out", "timeout", "connection refused", "network", "ssl", "http error",
                       "host not found")),
    ("error_database", ("sql", "sqlite", "psycopg", "postgres", "ora-", "syntax error")),
]
PYTHON_ERROR_TYPE_RE = re.compile(r"\b([A-Z]\w*(?:Error|Exception))\b")


def classify_error(text):
    """(rule id or None, Python error type, one-line detail) for an error message."""
    text = str(text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # In a traceback the last line says what went wrong.
    detail = lines[-1] if lines else ""
    type_match = PYTHON_ERROR_TYPE_RE.search(detail) or PYTHON_ERROR_TYPE_RE.search(text)
    error_type = type_match.group(1) if type_match else "error"
    if "qlippy" in text.lower():
        return "error_mine", error_type, detail or error_type
    # The last line is the most specific; only fall back to the whole text if it says nothing useful.
    for haystack in (detail.lower(), text.lower()):
        for kind, words in ERROR_KINDS:
            if any(word in haystack for word in words):
                return kind, error_type, detail or error_type
    return None, error_type, detail or error_type
