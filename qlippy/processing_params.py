"""Reading Processing parameters as QGIS records them in its history.

No QGIS imports here, so this can be tested on its own.

QGIS 3.44 records a run like:
    {"inputs": {"INPUT": "delimitedtext://file:///C:/data/a.csv?...", "DISTANCE": 100.0, ...},
     "distance_units": "meters", "area_units": "m2", "ellipsoid": "EPSG:7030"}
Older versions put the inputs at the top level.
"""

import re
from urllib.parse import unquote

# "delimitedtext://file:///C:/a.csv" -> provider "delimitedtext", source "file:///C:/a.csv"
PROVIDER_PREFIX_RE = re.compile(r"^([A-Za-z][\w-]*)://(.+)$")
URL_SCHEMES = {"file", "http", "https", "ftp", "s3", "vsicurl"}  # real URL schemes, not provider names


def run_inputs(parameters):
    """The algorithm's own parameters, whichever way the history stored them."""
    if not isinstance(parameters, dict):
        return {}
    inputs = parameters.get("inputs")
    return inputs if isinstance(inputs, dict) else parameters


def normalize_source(source):
    """Comparable form of a data source string (case, slashes, %20, default layer suffixes)."""
    text = unquote(str(source)).strip().replace("\\", "/")
    text = re.sub(r"\|layerid=0$", "", text)
    return text.lower()


def source_variants(value):
    """Normalized ways a recorded layer value might match a layer's source()."""
    text = str(value)
    variants = {normalize_source(text)}
    match = PROVIDER_PREFIX_RE.match(text)
    if match and match.group(1).lower() not in URL_SCHEMES:
        variants.add(normalize_source(match.group(2)))
    return variants
