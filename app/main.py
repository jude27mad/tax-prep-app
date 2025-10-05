import argparse
import os
import re
import sys
import textwrap
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, NotRequired, Sequence, TypedDict

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI

from app.config import get_settings
from pydantic import ValidationError
from app.lifespan import build_application_lifespan

from app.wizard import (
    BASE_DIR,
    CLI_BOOL_FIELDS,
    CLI_INT_FIELDS,
    CLI_NUMERIC_FIELDS,
    CLI_SAVE_ORDER,
    CLI_SUBMIT_FIELDS,
    T4EstimateRequest,
    canonicalize_data as _canonicalize_data_impl,
    canonicalize_with_metadata as _canonicalize_with_metadata_impl,
    delete_profile as _delete_profile,
    estimate_from_t4 as _estimate_from_t4,
    get_active_profile as _get_active_profile,
    list_profiles as _list_profiles,
    load_profile as _load_profile,
    load_data_file as _load_data_file_impl,
    parse_bool,
    parse_freeform_text as _parse_freeform_text_impl,
    parse_number,
    round_cents as _round_cents,
    rename_profile as _rename_profile,
    restore_profile as _restore_profile,
    save_profile_data as _save_profile_data,
    set_active_profile as _set_active_profile,
    slugify as _slugify,
)
from app.wizard.estimator import compute_tax_summary as _compute_tax_summary
from app.wizard.profiles import INBOX_DIR
from app.ui import router as ui_router
from app.tax.dispatch import (
    list_provincial_adapters,
)


def _load_rich_modules():
    try:
        from rich.console import Console  # type: ignore[import-not-found]
        from rich.panel import Panel  # type: ignore[import-not-found]
        from rich.table import Table  # type: ignore[import-not-found]
        from rich.text import Text  # type: ignore[import-not-found]
        return Console, Panel, Table, Text
    except Exception:  # pragma: no cover - optional dependency
        return None, None, None, None


RichConsole, RichPanel, RichTable, RichText = _load_rich_modules()

app = FastAPI(
    title="Tax App",
    version="0.0.3",
    lifespan=build_application_lifespan("estimator"),
)

app.include_router(ui_router)


@app.get("/tax/estimate")
def estimate(income: float, rrsp: float = 0.0, province: str = "ON"):
    return _compute_tax_summary(income, rrsp, province)


@app.post("/tax/t4")
@app.post("/t4/estimate")
def estimate_from_t4(payload: T4EstimateRequest):
    return _estimate_from_t4(payload)


@app.get("/health")
def health():
    settings = getattr(app.state, "settings", get_settings())
    schema_versions = getattr(app.state, "schema_versions", {})
    last_sbmt_ref_id = getattr(app.state, "last_sbmt_ref_id", None)
    return {
        "ok": True,
        "build": {
            "version": settings.build_version,
            "sha": settings.build_sha,
            "feature_efile_xml": settings.feature_efile_xml,
            "sbmt_ref_id_last": last_sbmt_ref_id,
        },
        "schemas": schema_versions,
    }


class PromptStep(TypedDict):
    field: str
    required: NotRequired[bool]


class ImportPreview(TypedDict, total=False):
    mapping: list[tuple[str, str]]
    unknown: list[str]
    source: str


ColorPreference = Literal["auto", "always", "never"]


def _resolve_color_preference(pref: ColorPreference) -> ColorPreference:
    if pref == "auto" and os.getenv("NO_COLOR"):
        return "never"
    return pref


def _get_console(pref: ColorPreference):
    if RichConsole is None:
        return None
    resolved = _resolve_color_preference(pref)
    if resolved == "never":
        return None
    force_terminal = resolved == "always"
    try:
        return RichConsole(force_terminal=force_terminal)
    except Exception:  # pragma: no cover - console init failure
        return None


def _console_print(console, message: str) -> None:
    if console is not None:
        console.print(message)
    else:
        print(message)


def _build_table(title: str, columns: list[str]):
    if RichTable is None:
        return None
    table = RichTable(title=title, expand=False)
    for column in columns:
        table.add_column(column)
    return table


def _print_choices(
    choices: Sequence[tuple[str, str]] | None,
    console,
    heading: str | None = None,
) -> None:
    if not choices:
        return
    title = heading or "Available options"
    if RichTable is not None and console is not None:
        table = _build_table(title, ["#", "Code", "Description"])
        if table is not None:
            for index, (code, description) in enumerate(choices, start=1):
                table.add_row(str(index), code, description)
            console.print(table)
            return
    _console_print(console, f"  {title}:")
    for index, (code, description) in enumerate(choices, start=1):
        _console_print(console, f"    {index}. {description} ({code})")


def _print_import_preview(preview: ImportPreview | None, console) -> None:
    if not preview:
        return
    mapping = preview.get("mapping") or []
    unknown = preview.get("unknown") or []
    if not mapping and not unknown:
        return
    if RichTable is not None and console is not None:
        table = _build_table("Imported fields", ["source", "field"])
        if table is not None:
            for source, field in mapping:
                table.add_row(source, field)
            if unknown:
                table.add_section()
                for item in unknown:
                    table.add_row(item, "? (unrecognized)")
            console.print(table)
            return
    if mapping:
        print("Imported fields:")
        for source, field in mapping:
            print(f"  - {source} -> {field}")
    if unknown:
        print("Ignored entries:")
        for item in unknown:
            print(f"  - {item}")


def _print_changes_summary(before: dict[str, Any], after: dict[str, Any], console) -> None:
    keys = [key for key in CLI_SAVE_ORDER if key in before or key in after]
    changes = []
    for key in keys:
        if before.get(key) != after.get(key):
            changes.append((key, before.get(key), after.get(key)))
    if not changes:
        if before:
            _console_print(console, "\nNo changes from the saved answers.")
        return
    if RichTable is not None and console is not None:
        table = _build_table("Updated answers", ["field", "before", "after"])
        if table is not None:
            for key, old, new in changes:
                table.add_row(
                    key, _display_value(key, old) or "<empty>", _display_value(key, new) or "<empty>"
                )
            console.print(table)
            return
    _console_print(console, "\nUpdated answers:")
    for key, old, new in changes:
        before_text = _display_value(key, old) or "<empty>"
        after_text = _display_value(key, new) or "<empty>"
        _console_print(console, f"  - {key}: {before_text} -> {after_text}")


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("full name", "name", "legal name", "taxpayer name"),
    "province": ("province", "province code", "province of residence", "prov", "residence province"),
    "box14": ("box14", "box 14", "employment income", "wages", "salary", "income", "t4 box 14"),
    "box22": ("box22", "box 22", "tax deducted", "tax withheld", "withholding", "income tax deducted", "t4 box 22"),
    "box16": ("box16", "box 16", "cpp contributions", "cpp", "t4 box 16"),
    "box16a": ("box16a", "box 16a", "cpp2", "second cpp", "additional cpp", "additional cpp contributions", "t4 box 16a"),
    "box18": ("box18", "box 18", "ei premiums", "ei", "employment insurance"),
    "rrsp": ("rrsp", "rrsp deduction", "rrsp contributions", "rrsp claimed"),
    "filing_status": ("filing status", "status"),
    "dependents": ("dependents", "has dependents", "dependents?"),
    "num_dependents": ("dependents count", "dependents number", "number of dependents"),
}

_KEY_VALUE_RE = re.compile(r"^\s*([^#:=]+?)\s*(?:[:=]|->)\s*(.+)$")
_ALIAS_LOOKUP: dict[str, str] = {}
_ALIAS_MATCHERS: list[tuple[str, str]] = []

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
_ALIAS_MATCHERS = sorted(
    {alias: canonical for alias, canonical in _ALIAS_MATCHERS}.items(),
    key=lambda item: len(item[0]),
    reverse=True,
)

_HELP_TOPICS: dict[str, str] = {
    "overview": textwrap.dedent(
        """
        Guided mode walks you through the T4 estimator without typing Python syntax.
        The flow is simple: we load any saved answers, ask for anything missing,
        compute the result, and save a fresh copy for next time. Type `?` during a prompt
        to open the matching help topic.
        """
    ).strip(),
    "wizard": textwrap.dedent(
        """
        The wizard asks for: your name (optional), province, and the T4 boxes (14, 22, 16, 16A, 18),
        plus RRSP deductions if you have them. Press Enter to keep the current value, or enter a new one.
        You can type amounts like 57k, $12,345.67, or 12345. The app cleans them automatically.
        """
    ).strip(),
    "box14": textwrap.dedent(
        """
        Box 14 is the employment income on your T4. Enter the number printed in box 14.
        You can paste it directly, or type shorthand such as 85k or $42,100.
        """
    ).strip(),
    "box22": textwrap.dedent(
        """
        Box 22 is the total income tax deducted at source. It is used to determine your refund or balance due.
        Enter the full amount from the slip, including cents if available.
        """
    ).strip(),
    "box16": textwrap.dedent(
        """
        Box 16 is your CPP contributions. Enter the value exactly as it appears.
        We compare it to the annual maximum to flag under- or over-contributions.
        """
    ).strip(),
    "box16a": textwrap.dedent(
        """
        Box 16A is the additional CPP (CPP2) amount. Only some employees have this.
        If your slip does not show a figure, press Enter to skip it.
        """
    ).strip(),
    "box18": textwrap.dedent(
        """
        Box 18 is Employment Insurance (EI) premiums. Enter the value from your T4 so the
        app can compare it to the EI maximum.
        """
    ).strip(),
    "rrsp": textwrap.dedent(
        """
        RRSP deductions reduce taxable income. Use the total from your official receipts (March to
        December plus the first 60 days of the next year) and stay within the deduction limit on your
        latest Notice of Assessment. You can always claim less than you contributed and carry the rest
        forward.
        """
    ).strip(),
    "province": textwrap.dedent(
        """
        Enter the two-letter province or territory code for where you live on December 31 (example: ON, BC, QC).
        It affects the provincial tax and credits that are applied in the calculation.
        """
    ).strip(),
    "full_name": textwrap.dedent(
        """
        Your name only appears on the PDF or summary output. It is optional but handy if you keep multiple runs.
        """
    ).strip(),
    "dependents": textwrap.dedent(
        """
        Dependents are family members (children, parents, others) you support. This assistant notes the count for
        checklist purposes but does not yet calculate dependent credits. Future releases can use it.
        """
    ).strip(),
    "checklist": textwrap.dedent(
        """
        The checklist lists documents that are commonly needed before filing: personal info, T4 slips, RRSP receipts,
        prior assessments, and anything related to dependents or deductions you plan to claim.
        """
    ).strip(),
    "t4_slip": textwrap.dedent(
        """
        T4 slips report employment income and payroll deductions for each employer. Collect every slip
        you received. The wizard needs boxes 14 (income), 22 (tax withheld), 16/16A (CPP amounts), and
        18 (EI premiums). Note any other boxes (union dues, taxable benefits, RPP contributions) for the
        full return even if the quick estimator ignores them today.
        """
    ).strip(),
    "t4a_slip": textwrap.dedent(
        """
        T4A slips cover other income such as pensions, self-employed commissions, scholarships, or
        research grants. Record the boxes that apply to you (commonly 020, 048, 105, 107). The estimator
        focuses on employment income now, but keep these figures ready for the complete filing or future
        updates.
        """
    ).strip(),
    "t5_slip": textwrap.dedent(
        """
        T5 slips summarize investment income from banks and brokerages. Box 10 holds interest, boxes 12 and
        13 cover eligible and other dividends, and boxes 15-18 show foreign income and taxes paid. Track
        currency codes and withholding because they matter for the foreign tax credit.
        """
    ).strip(),
    "tuition_credit": textwrap.dedent(
        """
        Tuition credits come from the T2202 or TL11 slips. Capture the eligible tuition amount, number of
        months of full-time or part-time study, and any unused credits you are carrying forward. The wizard
        does not deduct tuition yet, but the checklist will remind you to apply the credit when you file.
        """
    ).strip(),
    "canada_workers_benefit": textwrap.dedent(
        """
        The Canada Workers Benefit (CWB) is a refundable credit for low-income workers. Eligibility depends
        on earned income, family status, and residency. Keep your net income estimate, marital status, and
        spouse or partner income nearby so you can check the CRA tables or schedule when you complete the
        full return.
        """
    ).strip(),
    "topics": textwrap.dedent(
        """
        Available help topics include: overview, wizard, box14, box22, box16, box16a, box18, rrsp, province,
        full_name, dependents, checklist. Run `python -m app.main help <topic>` to open one of them.
        """
    ).strip(),
}

_HELP_TOPIC_ALIASES: dict[str, str] = {}
for key in _HELP_TOPICS:
    _HELP_TOPIC_ALIASES[re.sub(r"[^a-z0-9]", "", key.lower())] = key
_HELP_TOPIC_ALIASES[""] = "overview"
_HELP_TOPIC_ALIASES["start"] = "overview"
_HELP_TOPIC_ALIASES["help"] = "overview"
_HELP_TOPIC_ALIASES["list"] = "topics"
_HELP_TOPIC_ALIASES["topic"] = "topics"
for canonical, aliases in _FIELD_ALIASES.items():
    if canonical in _HELP_TOPICS:
        _HELP_TOPIC_ALIASES.setdefault(re.sub(r"[^a-z0-9]", "", canonical.lower()), canonical)
        for alias in aliases:
            normalized = re.sub(r"[^a-z0-9]", "", alias.lower())
            _HELP_TOPIC_ALIASES.setdefault(normalized, canonical)

for alias, canonical in {
    "t4": "t4_slip",
    "t4slip": "t4_slip",
    "employmentincome": "t4_slip",
    "t4a": "t4a_slip",
    "t4aslip": "t4a_slip",
    "pensionincome": "t4a_slip",
    "t5": "t5_slip",
    "t5slip": "t5_slip",
    "investmentincome": "t5_slip",
    "tuition": "tuition_credit",
    "education": "tuition_credit",
    "cwb": "canada_workers_benefit",
    "workersbenefit": "canada_workers_benefit",
}.items():
    _HELP_TOPIC_ALIASES.setdefault(alias, canonical)

_CHECKLIST_BASE = [
    "Government-issued photo ID and your Social Insurance Number.",
    "Current address and contact information.",
    "T4 slips for each employer.",
    "Notices of Assessment from previous years (for RRSP room reference).",
]

_WIZARD_SEQUENCE: list[PromptStep] = [
    {"field": "full_name", "required": False},
    {"field": "province", "required": False},
    {"field": "box14", "required": True},
    {"field": "box22", "required": True},
    {"field": "box16", "required": True},
    {"field": "box16a", "required": False},
    {"field": "box18", "required": True},
    {"field": "rrsp", "required": False},
]

_FIELD_METADATA: dict[str, dict[str, Any]] = {
    "full_name": {
        "label": "Your full legal name",
        "hint": "Optional, used for the summary header.",
        "help_topic": "full_name",
    },
    "province": {
        "label": "Province or territory (two-letter code)",
        "hint": "Example: ON, BC, AB, QC.",
        "default": "ON",
        "help_topic": "province",
    },
    "box14": {
        "label": "Employment income — T4 box 14",
        "hint": "Type the value from the slip. Use numbers like 57000 or 57k.",
        "help_topic": "box14",
    },
    "box22": {
        "label": "Income tax deducted — T4 box 22",
        "hint": "This is the tax withheld at source.",
        "help_topic": "box22",
    },
    "box16": {
        "label": "CPP contributions — T4 box 16",
        "hint": "Used to check against the annual CPP maximum.",
        "help_topic": "box16",
    },
    "box16a": {
        "label": "Additional CPP (CPP2) — T4 box 16A",
        "hint": "Only present for some employees. Press Enter to skip if blank.",
        "default": 0.0,
        "help_topic": "box16a",
    },
    "box18": {
        "label": "EI premiums — T4 box 18",
        "hint": "Used to compare against the EI maximum.",
        "help_topic": "box18",
    },
    "rrsp": {
        "label": "RRSP deductions you plan to claim",
        "hint": "Enter zero if you are not claiming RRSP deductions.",
        "default": 0.0,
        "help_topic": "rrsp",
    },
}

# Province choices (2025)
_PROVINCE_ADAPTERS = tuple(list_provincial_adapters(2025))
_PROVINCE_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (a.code, a.name) for a in _PROVINCE_ADAPTERS
)
_FIELD_METADATA["province"]["choices"] = _PROVINCE_CHOICES
_FIELD_METADATA["province"]["choices_label"] = "Available provinces and territories"
_PROVINCE_CODES = {code for code, _ in _PROVINCE_CHOICES}

NUM_SUFFIXES = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "b": 1_000_000_000.0,
}


def _normalize_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def _friendly_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _display_value(field: str, value: Any) -> str:
    if value is None:
        return ""
    if field in CLI_NUMERIC_FIELDS:
        return _format_currency(float(value))
    if field in CLI_BOOL_FIELDS:
        return "yes" if bool(value) else "no"
    return str(value)


def _parse_number(text: str) -> float:
    return parse_number(text)


def _parse_bool(text: str) -> bool:
    return parse_bool(text)


def _match_choice(text: str, choices: Sequence[tuple[str, str]]) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        index = int(cleaned)
        if 1 <= index <= len(choices):
            return choices[index - 1][0]
    upper = cleaned.upper()
    for code, _ in choices:
        if upper == code:
            return code
    lower = cleaned.lower()
    for code, description in choices:
        if lower == description.lower():
            return code
    return None


def _coerce_for_field(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in CLI_NUMERIC_FIELDS:
        if isinstance(value, (int, float)):
            return _round_cents(float(value))
        if isinstance(value, Decimal):
            return _round_cents(float(value))
        return _round_cents(_parse_number(str(value)))
    if field in CLI_INT_FIELDS:
        if isinstance(value, (int, float)):
            return int(round(float(value)))
        return int(round(_parse_number(str(value))))
    if field in CLI_BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        return _parse_bool(str(value))
    if field == "province":
        cleaned = str(value).strip().upper()
        if cleaned and _PROVINCE_CODES and cleaned not in _PROVINCE_CODES:
            allowed = ", ".join(sorted(_PROVINCE_CODES))
            raise ValueError(f"Province must be one of: {allowed}.")
        return cleaned
    return str(value).strip()


def _canonical_key(raw: str) -> str | None:
    normalized = _normalize_key(raw)
    return _ALIAS_LOOKUP.get(normalized)


def _canonicalize_with_metadata(raw: Any) -> tuple[dict[str, Any], list[tuple[str, str]], list[str]]:
    return _canonicalize_with_metadata_impl(raw)


def _canonicalize_data(raw: Any) -> dict[str, Any]:
    return _canonicalize_data_impl(raw)


def _parse_freeform_text(text: str) -> tuple[dict[str, Any], list[tuple[str, str]], list[str]]:
    return _parse_freeform_text_impl(text)


def _read_data_file(path: Path) -> tuple[dict[str, Any], ImportPreview]:
    try:
        data, preview = _load_data_file_impl(path)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive catch for file decoding issues
        raise ValueError(f"{path.name}: {exc}") from exc
    normalized: ImportPreview = {
        "mapping": preview.get("mapping", []),
        "unknown": preview.get("unknown", []),
        "source": _friendly_path(path),
    }
    return data, normalized


def _default_candidate_paths() -> tuple[list[Path], list[Path]]:
    supported: list[Path] = []
    for name in ("user_data.toml", "user_data.json", "user_data.txt"):
        candidate = BASE_DIR / name
        if candidate.exists():
            supported.append(candidate)
    unsupported: list[Path] = []
    if INBOX_DIR.exists() and INBOX_DIR.is_dir():
        for item in sorted(INBOX_DIR.iterdir()):
            if not item.is_file():
                continue
            suffix = item.suffix.lower()
            if suffix in {".toml", ".json", ".txt", ".csv"}:
                supported.append(item)
            elif suffix in {".xlsx", ".pdf"}:
                unsupported.append(item)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_supported: list[Path] = []
    for path in supported:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique_supported.append(path)
    return unique_supported, unsupported


def _load_inputs(
    path_value: str | None,
) -> tuple[dict[str, Any], Path | None, list[Path], list[str], ImportPreview | None]:
    errors: list[str] = []
    unsupported: list[Path] = []
    candidates: list[Path] = []
    if path_value:
        candidate = Path(path_value).expanduser()
        if candidate.exists():
            candidates.append(candidate)
        else:
            errors.append(f"Could not find {candidate}.")
    else:
        candidates, unsupported = _default_candidate_paths()
    for candidate in candidates:
        try:
            data, preview = _read_data_file(candidate)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if data:
            return data, candidate, unsupported, errors, preview
    return {}, None, unsupported, errors, None


def _prompt_for_missing_fields(
    data: dict[str, Any], *, quick: bool = False, console=None
) -> dict[str, Any]:
    working = {key: _coerce_for_field(key, value) for key, value in data.items()}
    steps = [meta for meta in _WIZARD_SEQUENCE if meta["field"] in _FIELD_METADATA]
    if quick:
        steps = [meta for meta in steps if meta.get("required", False)]
    else:
        steps = [
            meta
            for meta in steps
            if meta.get("required", False) or not _has_value(working.get(meta["field"]))
        ]
    if not steps:
        return working
    index = 0
    total = len(steps)
    while index < total:
        meta = steps[index]
        field = meta["field"]
        required = bool(meta.get("required", False))
        current = working.get(field)
        action, value = _ask_field(field, current, index + 1, total, required, console)
        if action == "back":
            if index > 0:
                index -= 1
            else:
                _console_print(console, "Already at the first question; cannot go back.")
            continue
        if action == "skip":
            index += 1
            continue
        if action == "repeat":
            continue
        working[field] = value
        index += 1
    return working


def _review_answers(
    starting: dict[str, Any], answers: dict[str, Any], console
) -> tuple[dict[str, Any] | None, bool]:
    """Return (final_answers, restart_requested)."""
    while True:
        if RichTable is not None and console is not None:
            table = _build_table("Review answers", ["field", "value"])
            if table is not None:
                for key in CLI_SAVE_ORDER:
                    if key in answers:
                        table.add_row(key, _display_value(key, answers.get(key)))
                console.print(table)
        else:
            _console_print(console, "\nReview your answers:")
            for key in CLI_SAVE_ORDER:
                if key in answers:
                    _console_print(console, f"  - {key}: {_display_value(key, answers.get(key))}")
        cmd = input("Review command ([Enter]=accept, field name to edit, 'restart'): ").strip()
        lowered = cmd.lower()
        if lowered in {"", "accept", "done"}:
            return answers, False
        if lowered == "restart":
            return None, True
        canonical = _canonical_key(lowered) if lowered else None
        field = canonical or lowered
        if field in _FIELD_METADATA:
            meta = _FIELD_METADATA[field]
            required = bool(meta.get("required", False))
            current = answers.get(field)
            action, value = _ask_field(field, current, 1, 1, required, console)
            if action == "set":
                answers[field] = value
            elif action == "skip":
                answers.pop(field, None)
            continue
        _console_print(
            console, "  Command not recognized. Try a field name, 'restart', or Enter to accept."
        )


def _ask_field(
    field: str, current: Any, step: int, total: int, required: bool, console
) -> tuple[str, Any]:
    meta = _FIELD_METADATA[field]
    label = meta["label"]
    hint = meta.get("hint")
    default = meta.get("default")
    choices: Sequence[tuple[str, str]] | None = meta.get("choices")
    _console_print(console, f"\n[{step}/{total}] {label}")
    if hint:
        _console_print(console, f"  {hint}")
    if choices:
        _print_choices(choices, console, meta.get("choices_label"))
    if _has_value(current):
        _console_print(console, f"  Current value: {_display_value(field, current)}")
    if default is not None and not _has_value(current):
        _console_print(console, f"  Default: {_display_value(field, default)}")
    prompt = "  -> "
    while True:
        raw = input(prompt).strip()
        lowered = raw.lower()
        if lowered in {"?", "help"}:
            _print_help_topic(meta.get("help_topic", field))
            continue
        if lowered in {"back", "<"}:
            return "back", current
        if lowered in {"skip", "s"} and not required:
            return "skip", current
        if not raw:
            if _has_value(current):
                return "set", current
            if default is not None:
                return "set", _coerce_for_field(field, default)
            if not required:
                return "set", None
            _console_print(
                console, "  This field is required. Please enter a value or type ? for help."
            )
            continue
        if choices:
            matched = _match_choice(raw, choices)
            if matched is not None:
                return "set", _coerce_for_field(field, matched)
        try:
            return "set", _coerce_for_field(field, raw)
        except ValueError as exc:
            _console_print(console, f"  {exc}")
            return "repeat", current


def _print_help_topic(topic: str | None) -> None:
    key = _normalize_key(topic or "")
    resolved = _HELP_TOPIC_ALIASES.get(key)
    if resolved is None:
        print("\nNo help topic found. Try one of:")
        _print_help_index()
        return
    if resolved == "topics":
        _print_help_index()
        return
    message = _HELP_TOPICS.get(resolved)
    if not message:
        print("\nHelp topic not available yet.")
        return
    print("\n" + message + "\n")


def _print_help_index() -> None:
    print("\nAvailable help topics:")
    for key in sorted(_HELP_TOPICS):
        if key == "topics":
            continue
        print(f"  - {key}")
    print("Use `python -m app.main help <topic>` to open one.\n")


def _print_checklist(data: dict[str, Any] | None = None) -> None:
    data = data or {}
    items = list(_CHECKLIST_BASE)
    if _has_value(data.get("rrsp")) and float(data.get("rrsp", 0.0)) > 0.0:
        items.append("RRSP contribution receipts.")
    if _has_value(data.get("dependents")) or int(data.get("num_dependents") or 0) > 0:
        items.append("Information for dependents (birthdates, childcare or disability receipts).")
    items.append("A folder to store the generated PDF/summary for your records.")
    print("\nFiling checklist:")
    for item in items:
        print(f"  - {item}")
    print()


def _format_currency(value: float | Decimal) -> str:
    return f"${_round_cents(value):,.2f}"


def _summarize_changes(before: dict[str, Any], after: dict[str, Any], console) -> None:
    _print_changes_summary(before, after, console)


def _save_user_data(data: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    for key in CLI_SAVE_ORDER:
        value = data.get(key)
        if value is None:
            continue
        if key in CLI_NUMERIC_FIELDS:
            lines.append(f"{key} = {_round_cents(float(value)):.2f}")
        elif key in CLI_BOOL_FIELDS:
            lines.append(f"{key} = {'true' if bool(value) else 'false'}")
        elif key in CLI_INT_FIELDS:
            lines.append(f"{key} = {int(value)}")
        else:
            escaped = str(value).replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSaved your answers to {_friendly_path(path)}")


def _handle_profiles(subargs: list[str], explicit_profile: str | None, console) -> None:
    action = (subargs[0].lower() if subargs else "list")
    args = subargs[1:] if subargs else []
    active = _get_active_profile()
    if action == "list":
        profiles = _list_profiles()
        if not profiles:
            _console_print(console, "No profiles found. Run the wizard with --profile to create one.")
            return
        _console_print(console, "Profiles:")
        for slug in profiles:
            marker = "*" if slug == active else "-"
            _console_print(console, f"  {marker} {slug}")
        return
    if action == "show":
        target = args[0] if args else explicit_profile or active
        if not target:
            _console_print(console, "Specify a profile name to show.")
            return
        slug = _slugify(target)
        data, _, errors = _load_profile(slug)
        if errors:
            for message in errors:
                _console_print(console, f"ERROR: {message}")
            return
        if not data:
            _console_print(console, "Profile is empty or not found.")
            return
        if RichTable is not None and console is not None:
            table = _build_table(f"Profile {slug}", ["field", "value"])
            if table is not None:
                for key in CLI_SAVE_ORDER:
                    if key in data:
                        table.add_row(key, _display_value(key, data[key]))
                console.print(table)
                return
        for key in CLI_SAVE_ORDER:
            if key in data:
                print(f"{key}: {_display_value(key, data[key])}")
        return
    if action in {"switch", "set"}:
        if not args:
            _console_print(console, "Provide a profile name to switch to.")
            return
        slug = _slugify(args[0])
        data, path_obj, errors = _load_profile(slug)
        if errors:
            for message in errors:
                _console_print(console, f"ERROR: {message}")
            return
        if not path_obj:
            _console_print(
                console,
                f"Profile '{slug}' does not exist yet. Run the wizard with --profile {slug} to create it.",
            )
            return
        _set_active_profile(slug)
        _console_print(console, f"Active profile set to '{slug}'.")
        return
    if action == "delete":
        if not args:
            _console_print(console, "Provide a profile name to delete.")
            return
        slug = _slugify(args[0])
        trashed = _delete_profile(slug)
        if trashed:
            _console_print(console, f"Moved profile '{slug}' to trash: {_friendly_path(trashed)}")
        else:
            _console_print(console, f"Profile '{slug}' not found.")
        return
    if action == "restore":
        if not args:
            _console_print(console, "Provide a profile name to restore.")
            return
        slug = _slugify(args[0])
        restored = _restore_profile(slug)
        if restored:
            _console_print(console, f"Restored profile '{slug}' from trash.")
        else:
            _console_print(console, f"No trashed profile found for '{slug}'.")
        return
    if action == "rename":
        if len(args) < 2:
            _console_print(console, "Usage: profiles rename <old> <new>.")
            return
        old_slug = _slugify(args[0])
        new_slug = _slugify(args[1])
        try:
            _rename_profile(old_slug, new_slug)
        except ValueError as exc:
            _console_print(console, f"ERROR: {exc}")
            return
        _console_print(console, f"Renamed profile '{old_slug}' to '{new_slug}'.")
        return
    _console_print(console, "Unknown profiles command. Available: list, show, switch, delete, restore, rename.")


def _print_summary(payload: T4EstimateRequest, outcome: dict[str, Any], console) -> None:
    provincial = outcome["tax"]["provincial"]
    provincial_name = provincial["province_name"]
    additions = provincial.get("additions", {})

    rows = [
        ("Employment income (box 14)", _format_currency(payload.box14), ""),
        ("Tax withheld (box 22)", _format_currency(payload.box22), ""),
        ("CPP reported (box 16)", _format_currency(payload.box16), outcome["cpp"]["status"]),
        ("CPP2 reported (box 16A)", _format_currency(payload.box16a), outcome["cpp2"]["status"]),
        ("EI premiums (box 18)", _format_currency(payload.box18), outcome["ei"]["status"]),
        ("RRSP deduction", _format_currency(payload.rrsp), ""),
        ("Province", provincial_name, ""),
        (
            "Federal tax after credits",
            _format_currency(outcome["tax"]["federal"]["after_credits"]),
            "",
        ),
        (
            f"{provincial_name} tax after credits",
            _format_currency(provincial["after_credits"]),
            "",
        ),
    ]

    for key, value in additions.items():
        rows.append((f"{provincial_name} {key.replace('_', ' ')}", _format_currency(value), ""))

    rows.append((f"{provincial_name} net tax", _format_currency(provincial["net_provincial"]), ""))
    rows.append(("Total tax owing", _format_currency(outcome["total_net_tax"]), ""))
    rows.append(("Withholding applied", _format_currency(outcome["withholding"]), ""))

    balance = outcome["balance"]
    if outcome.get("is_refund"):
        rows.append(("Expected refund", _format_currency(abs(balance)), ""))
    elif balance > 0:
        rows.append(("Balance owing", _format_currency(balance), ""))
    else:
        rows.append(("Balance status", "No balance owing or refund detected.", ""))

    if RichTable is not None and console is not None:
        table = _build_table("Summary", ["Metric", "Value", "Status"])
        if table is not None:
            for metric, value, status in rows:
                table.add_row(metric, value, status)
            console.print(table)
            return
    _console_print(console, "\nSummary:")
    _console_print(console, "--------")
    for metric, value, status in rows:
        line = f"{metric}: {value}"
        if status:
            line += f" - status: {status}"
        _console_print(console, line)


def _run_wizard(
    data_path: str | None,
    *,
    allow_save: bool,
    profile_slug: str | None,
    profile_data: dict[str, Any],
    profile_errors: list[str],
    quick: bool,
    console,
) -> None:
    if profile_errors:
        for message in profile_errors:
            _console_print(console, f"NOTE: {message}")
    file_data, source, unsupported, errors, preview = _load_inputs(data_path)
    _console_print(console, "Tax App guided mode")
    _console_print(console, "===================")
    if errors:
        for message in errors:
            _console_print(console, f"NOTE: {message}")
    if profile_slug:
        _console_print(console, f"Using profile: {profile_slug}")
    if source:
        _console_print(console, f"Loaded saved answers from {_friendly_path(source)}")
    elif not profile_data:
        _console_print(console, "No saved answers found; we will collect everything now.")
    if preview:
        _print_import_preview(preview, console)
    if unsupported:
        _console_print(
            console,
            "Files in inbox/ that could not be imported automatically (open them and type the values):",
        )
        for item in unsupported:
            _console_print(console, f"  - {_friendly_path(item)}")
    combined = {**profile_data, **file_data}
    starting = combined.copy()
    while True:
        answers = _prompt_for_missing_fields(starting.copy(), quick=quick, console=console)
        reviewed, restart = _review_answers(starting, answers, console)
        if restart:
            quick = False
            continue
        if reviewed is not None:
            answers = reviewed
            break
    payload_data = {
        key: value for key, value in answers.items() if key in CLI_SUBMIT_FIELDS and value is not None
    }
    try:
        payload = T4EstimateRequest.model_validate(payload_data)
    except ValidationError as exc:
        _console_print(console, "There was a problem with the answers provided:")
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error.get("loc", ("value",)))
            _console_print(console, f"  - {location}: {error.get('msg')}")
        sys.exit(1)
    result = estimate_from_t4(payload)
    _print_summary(payload, result, console)
    _print_changes_summary(starting, answers, console)
    if not allow_save:
        _console_print(console, "Skipped saving because --no-save was used.")
        return
    if profile_slug:
        _save_profile_data(profile_slug, answers)
        _console_print(console, f"Saved answers to profile '{profile_slug}'.")
    else:
        path = BASE_DIR / "user_data.toml"
        _save_user_data(answers, path)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tax-app",
        description="Guided assistant for the Tax App T4 estimator.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="wizard",
        choices=["wizard", "help", "checklist", "profiles"],
        help="Action to perform.",
    )
    parser.add_argument("subargs", nargs="*", help="Additional arguments for the chosen command.")
    parser.add_argument("--data", help="Path to a TOML/JSON/CSV/TXT file with answers.")
    parser.add_argument("--profile", help="Profile name to load/save answers for.")
    parser.add_argument("--quick", action="store_true", help="Prompt only for required fields when possible.")
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Color output preference (default: auto).",
    )
    parser.add_argument(
        "--no-color",
        dest="color",
        action="store_const",
        const="never",
        help="Alias for --color never.",
    )
    parser.add_argument("--no-save", action="store_true", help="Do not persist answers after running.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    console = _get_console(args.color)
    if args.command == "help":
        topic = args.subargs[0] if args.subargs else None
        _print_help_topic(topic)
        return
    if args.command == "checklist":
        data, _, _, _, _ = _load_inputs(args.data)
        _print_checklist(data)
        return
    if args.command == "profiles":
        _handle_profiles(args.subargs, args.profile, console)
        return
    profile_slug = _slugify(args.profile) if args.profile else _get_active_profile()
    profile_data, _, profile_errors = _load_profile(profile_slug)
    if profile_slug and not profile_data and not profile_errors:
        _console_print(
            console,
            f"Profile '{profile_slug}' does not exist yet; it will be created when you save.",
        )
    _run_wizard(
        args.data,
        allow_save=not args.no_save,
        profile_slug=profile_slug,
        profile_data=profile_data,
        profile_errors=profile_errors,
        quick=args.quick,
        console=console,
    )


if __name__ == "__main__":
    main()
