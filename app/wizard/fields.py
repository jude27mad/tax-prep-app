from __future__ import annotations

import csv
import json
import re
from typing import Any, Iterable

from .estimator import round_cents

CLI_SUBMIT_FIELDS = {"box14", "box22", "box16", "box16a", "box18", "rrsp", "province"}
CLI_NUMERIC_FIELDS = {"box14", "box22", "box16", "box16a", "box18", "rrsp"}
CLI_INT_FIELDS = {"num_dependents"}
CLI_BOOL_FIELDS = {"dependents"}
CLI_SAVE_ORDER = [
    "full_name",
    "province",
    "box14",
    "box22",
    "box16",
    "box16a",
    "box18",
    "rrsp",
    "filing_status",
    "dependents",
    "num_dependents",
]

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("full name", "name", "legal name", "taxpayer name"),
    "province": ("province", "province code", "province of residence", "prov", "residence province"),
    "box14": ("box14", "box 14", "employment income", "wages", "salary", "income", "t4 box 14"),
    "box22": ("box22", "box 22", "tax deducted", "tax withheld", "withholding", "income tax deducted", "t4 box 22"),
    "box16": ("box16", "box 16", "cpp contributions", "cpp", "t4 box 16"),
    "box16a": (
        "box16a",
        "box 16a",
        "cpp2",
        "second cpp",
        "additional cpp",
        "additional cpp contributions",
        "t4 box 16a",
    ),
    "box18": ("box18", "box 18", "ei premiums", "ei", "employment insurance"),
    "rrsp": ("rrsp", "rrsp deduction", "rrsp contributions", "rrsp claimed"),
    "filing_status": ("filing status", "status"),
    "dependents": ("dependents", "has dependents", "dependents?"),
    "num_dependents": ("dependents count", "dependents number", "number of dependents"),
}

NUM_SUFFIXES = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "b": 1_000_000_000.0,
}

_KEY_VALUE_RE = re.compile(r"^\s*([^#:=]+?)\s*(?:[:=]|->)\s*(.+)$")
_ALIAS_LOOKUP: dict[str, str] = {}
_ALIAS_MATCHERS: list[tuple[str, str]] = []


def _normalize_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def canonical_key(raw: str) -> str | None:
    normalized = _normalize_key(raw)
    return _ALIAS_LOOKUP.get(normalized)


for canonical, aliases in _FIELD_ALIASES.items():
    all_aliases = (canonical, *aliases)
    for alias in all_aliases:
        normalized = re.sub(r"[^a-z0-9]", "", alias.lower())
        if normalized and normalized not in _ALIAS_LOOKUP:
            _ALIAS_LOOKUP[normalized] = canonical
        cleaned = " ".join(alias.lower().split())
        if cleaned:
            _ALIAS_MATCHERS.append((cleaned, canonical))

# Deduplicate while keeping longest aliases first so "box 16a" matches before "box 16"
_ALIAS_MATCHERS = sorted({alias: canonical for alias, canonical in _ALIAS_MATCHERS}.items(), key=lambda item: len(item[0]), reverse=True)


def parse_number(text: str) -> float:
    cleaned = text.strip().lower()
    if not cleaned:
        raise ValueError("Please enter a number.")
    multiplier = 1.0
    suffix = cleaned[-1]
    if suffix in NUM_SUFFIXES:
        multiplier = NUM_SUFFIXES[suffix]
        cleaned = cleaned[:-1]
    cleaned = cleaned.replace("$", "").replace(",", "").replace(" ", "").replace("_", "")
    cleaned = cleaned.replace("−", "-").replace("–", "-")
    if cleaned in {"", "-", "."}:
        raise ValueError("Please enter a number.")
    try:
        return float(cleaned) * multiplier
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Could not understand number '{text}'.") from exc


def parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in {"y", "yes", "true", "1", "ok", "sure"}:
        return True
    if lowered in {"n", "no", "false", "0"}:
        return False
    raise ValueError("Enter yes or no.")


def coerce_for_field(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in CLI_NUMERIC_FIELDS:
        if isinstance(value, (int, float)):
            return round_cents(float(value))
        from decimal import Decimal

        if isinstance(value, Decimal):
            return round_cents(float(value))
        return round_cents(parse_number(str(value)))
    if field in CLI_INT_FIELDS:
        if isinstance(value, (int, float)):
            return int(round(float(value)))
        return int(round(parse_number(str(value))))
    if field in CLI_BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        return parse_bool(str(value))
    if field == "province":
        return str(value).strip().upper()
    return str(value).strip()


def canonicalize_with_metadata(raw: Any) -> tuple[dict[str, Any], list[tuple[str, str]], list[str]]:
    if not isinstance(raw, dict):
        return {}, [], []
    flattened = dict(raw)
    t4_block = flattened.get("t4")
    if isinstance(t4_block, dict):
        flattened = {**flattened, **t4_block}
    result: dict[str, Any] = {}
    mapping: list[tuple[str, str]] = []
    unknown: list[str] = []
    for key, value in flattened.items():
        canonical = canonical_key(str(key))
        if not canonical:
            unknown.append(str(key))
            continue
        try:
            coerced = coerce_for_field(canonical, value)
        except ValueError as exc:
            raise ValueError(f"Field '{key}': {exc}") from exc
        if coerced is not None:
            result[canonical] = coerced
            mapping.append((str(key), canonical))
    return result, mapping, unknown


def canonicalize_data(raw: Any) -> dict[str, Any]:
    data, _, _ = canonicalize_with_metadata(raw)
    return data


def parse_freeform_text(text: str) -> tuple[dict[str, Any], list[tuple[str, str]], list[str]]:
    result: dict[str, Any] = {}
    mapping: list[tuple[str, str]] = []
    unknown: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(line)
        if match:
            raw_key, raw_value = match.groups()
            canonical = canonical_key(raw_key)
            if canonical:
                result[canonical] = coerce_for_field(canonical, raw_value.strip())
                mapping.append((raw_key.strip(), canonical))
            else:
                unknown.append(raw_key.strip())
            continue
        lowered = " ".join(line.lower().split())
        matched = False
        for alias, canonical in _ALIAS_MATCHERS:
            if lowered.startswith(alias):
                remainder = line[len(alias) :].lstrip(" :=-")
                if not remainder:
                    continue
                result[canonical] = coerce_for_field(canonical, remainder.strip())
                mapping.append((alias, canonical))
                matched = True
                break
        if not matched:
            unknown.append(line)
    return result, mapping, unknown


def _load_from_csv(reader: csv.DictReader[str]) -> tuple[dict[str, Any], list[tuple[str, str]], list[str]]:
    try:
        row = next(reader)
    except StopIteration:
        return {}, [], []
    return canonicalize_with_metadata(row)


def load_data_file(path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load structured data from TOML/JSON/TXT/CSV.

    Returns a tuple of ``(data, preview)`` where the preview contains the
    mapping and unknown keys similar to the CLI wizard output.
    """

    from pathlib import Path

    path = Path(path)
    suffix = path.suffix.lower()
    preview: dict[str, Any] = {"mapping": [], "unknown": [], "source": str(path)}
    if suffix == ".toml":
        try:
            import tomllib  # Python 3.11+
        except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]

        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        data, mapping, unknown = canonicalize_with_metadata(raw)
        preview["mapping"] = mapping
        preview["unknown"] = unknown
        return data, preview
    if suffix == ".json":
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        data, mapping, unknown = canonicalize_with_metadata(raw)
        preview["mapping"] = mapping
        preview["unknown"] = unknown
        return data, preview
    if suffix == ".txt":
        text_content = path.read_text(encoding="utf-8")
        data, mapping, unknown = parse_freeform_text(text_content)
        preview["mapping"] = mapping
        preview["unknown"] = unknown
        return data, preview
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            data, mapping, unknown = _load_from_csv(reader)
        preview["mapping"] = mapping
        preview["unknown"] = unknown
        return data, preview
    raise ValueError(f"Unsupported data file: {path.name}")


def iter_save_order(fields: Iterable[str] | None = None) -> list[str]:
    if fields is None:
        return list(CLI_SAVE_ORDER)
    return [field for field in CLI_SAVE_ORDER if field in fields]


__all__ = [
    "CLI_SUBMIT_FIELDS",
    "CLI_NUMERIC_FIELDS",
    "CLI_INT_FIELDS",
    "CLI_BOOL_FIELDS",
    "CLI_SAVE_ORDER",
    "NUM_SUFFIXES",
    "canonical_key",
    "canonicalize_data",
    "canonicalize_with_metadata",
    "coerce_for_field",
    "iter_save_order",
    "load_data_file",
    "parse_bool",
    "parse_freeform_text",
    "parse_number",
]
