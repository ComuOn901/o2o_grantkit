"""Schema for funder rule packs.

A rule pack YAML is parsed into a :class:`FunderPack`. The :func:`validate_pack`
function checks a raw dict against the documented schema and returns a list of
human-readable error strings (empty list == valid). It is used both at load time
and by the rule-pack schema tests.

Schema (top-level keys)
-----------------------
``id`` (str, required)
    Stable pack identifier, matches the YAML filename stem (e.g. ``nsf-pappg``).
``name`` (str, required)
    Human funder name (e.g. ``National Science Foundation``).
``program`` (str, optional)
    Default program/solicitation the pack targets.
``version`` (str, optional)
    Version of the underlying funder guidance (e.g. PAPPG ``24-1``).
``source_url`` (str, optional)
    Canonical solicitation / policy URL.
``locale`` (str, ``en-US`` | ``en-GB``)
    Spelling locale enforced by ``grantkit check``.
``provenance`` (str, optional)
    Free-text note on how the pack values were sourced.
``content_engine`` (str, optional)
    Named programmatic content checker to run (currently ``nsf_pappg`` or null).
``sections`` (list, optional)
    Section definitions used to scaffold a grant. Each carries
    ``id``/``title``/``word_limit``/``char_limit``/``page_limit``/``required``/
    ``description``/``file``/``stage``/``format`` (``prose`` | ``fields``;
    ``fields`` sections hold individual form values and are exempt from
    plain-text portal linting).
``formatting_rules`` (list, optional)
    Documented formatting rules. Each carries ``id``/``description``/``severity``/
    ``citation``/``url``/``quote``/``applies_to``.
``budget_rules`` (mapping, optional)
    ``total_cap``/``annual_cap``/``indirect_rate_max``/``mtdc_excludes``/
    ``currency``/``notes``.
``portal`` (mapping, optional)
    ``accepts_markdown``/``plain_text_boxes``/``url``/``notes``.
``review_rubric`` (list, optional)
    Assessment criteria used by ``grantkit review``. Each carries
    ``id``/``name``/``description``/``citation``/``url``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional, TypeGuard

VALID_SEVERITIES = {"error", "warning", "info"}
VALID_LOCALES = {"en-US", "en-GB"}
VALID_CONTENT_ENGINES = {None, "nsf_pappg"}
VALID_SECTION_FORMATS = {"prose", "fields"}


@dataclass
class PackSection:
    """A section definition contributed by a funder pack."""

    id: str
    title: str
    word_limit: Optional[int] = None
    char_limit: Optional[int] = None
    page_limit: Optional[int] = None
    required: bool = True
    description: Optional[str] = None
    file: Optional[str] = None
    stage: Optional[str] = None
    #: ``prose`` (default) is pasted as a portal text box; ``fields`` holds
    #: individual form values and is exempt from plain-text portal linting.
    format: str = "prose"


@dataclass
class FormattingRule:
    """A documented funder formatting rule with a citation."""

    id: str
    description: str
    severity: str = "error"
    citation: Optional[str] = None
    url: Optional[str] = None
    quote: Optional[str] = None
    applies_to: str = "all"


@dataclass
class BudgetRules:
    """Funder budget constraints used by the budget checks."""

    total_cap: Optional[float] = None
    annual_cap: Optional[float] = None
    indirect_rate_max: Optional[float] = None
    mtdc_excludes: list[str] = field(default_factory=list)
    currency: str = "USD"
    notes: Optional[str] = None


@dataclass
class PortalQuirks:
    """Submission-portal quirks (e.g. plain-text-only boxes)."""

    accepts_markdown: bool = True
    plain_text_boxes: bool = False
    url: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class RubricCriterion:
    """A single assessment criterion for the review packet."""

    id: str
    name: str
    description: Optional[str] = None
    citation: Optional[str] = None
    url: Optional[str] = None


@dataclass
class FunderPack:
    """A fully-parsed funder rule pack."""

    id: str
    name: str
    program: Optional[str] = None
    version: Optional[str] = None
    source_url: Optional[str] = None
    locale: str = "en-US"
    provenance: Optional[str] = None
    content_engine: Optional[str] = None
    sections: list[PackSection] = field(default_factory=list)
    formatting_rules: list[FormattingRule] = field(default_factory=list)
    budget_rules: Optional[BudgetRules] = None
    portal: PortalQuirks = field(default_factory=PortalQuirks)
    review_rubric: list[RubricCriterion] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def accepts_markdown(self) -> bool:
        """Whether the funder portal accepts markdown formatting."""
        return self.portal.accepts_markdown

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FunderPack":
        """Build a :class:`FunderPack` from a raw YAML dict.

        Assumes the dict has already passed :func:`validate_pack` (or is trusted).
        Unknown keys are ignored but preserved on ``raw``.
        """
        sections = [
            PackSection(
                id=s.get("id", ""),
                title=s.get("title", s.get("id", "")),
                word_limit=s.get("word_limit"),
                char_limit=s.get("char_limit"),
                page_limit=s.get("page_limit"),
                required=bool(s.get("required", True)),
                description=s.get("description"),
                file=s.get("file"),
                stage=s.get("stage"),
                format=(
                    s["format"]
                    if s.get("format") in VALID_SECTION_FORMATS
                    else "prose"
                ),
            )
            for s in data.get("sections", []) or []
        ]
        rules = [
            FormattingRule(
                id=r.get("id", ""),
                description=r.get("description", ""),
                severity=r.get("severity", "error"),
                citation=r.get("citation"),
                url=r.get("url"),
                quote=r.get("quote"),
                applies_to=r.get("applies_to", "all"),
            )
            for r in data.get("formatting_rules", []) or []
        ]
        budget_rules = None
        if data.get("budget_rules"):
            b = data["budget_rules"]
            budget_rules = BudgetRules(
                total_cap=b.get("total_cap"),
                annual_cap=b.get("annual_cap"),
                indirect_rate_max=b.get("indirect_rate_max"),
                mtdc_excludes=list(b.get("mtdc_excludes", []) or []),
                currency=b.get("currency", "USD"),
                notes=b.get("notes"),
            )
        portal_data = data.get("portal", {}) or {}
        portal = PortalQuirks(
            accepts_markdown=bool(portal_data.get("accepts_markdown", True)),
            plain_text_boxes=bool(portal_data.get("plain_text_boxes", False)),
            url=portal_data.get("url"),
            notes=portal_data.get("notes"),
        )
        rubric = [
            RubricCriterion(
                id=c.get("id", ""),
                name=c.get("name", c.get("id", "")),
                description=c.get("description"),
                citation=c.get("citation"),
                url=c.get("url"),
            )
            for c in data.get("review_rubric", []) or []
        ]
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            program=data.get("program"),
            version=data.get("version"),
            source_url=data.get("source_url"),
            locale=data.get("locale", "en-US"),
            provenance=data.get("provenance"),
            content_engine=data.get("content_engine"),
            sections=sections,
            formatting_rules=rules,
            budget_rules=budget_rules,
            portal=portal,
            review_rubric=rubric,
            raw=data,
        )


def _is_int_or_none(value: Any) -> bool:
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool)
    )


def _is_string(value: Any, *, nonempty: bool = False) -> TypeGuard[str]:
    if not isinstance(value, str) or (nonempty and not value):
        return False
    if any(
        (ord(char) < 32 and char not in "\t\n\r") or 0x7F <= ord(char) <= 0x9F
        for char in value
    ):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _is_string_or_none(value: Any) -> bool:
    return value is None or _is_string(value)


def _is_number_or_none(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_pack(data: Any) -> list[str]:
    """Validate a raw rule-pack dict against the schema.

    Returns a list of error strings. An empty list means the pack is valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["pack must be a mapping/dict"]

    # Required top-level keys
    for key in ("id", "name"):
        if not _is_string(data.get(key), nonempty=True):
            errors.append(f"missing required key: '{key}'")

    for key in ("program", "version", "source_url", "provenance"):
        if not _is_string_or_none(data.get(key)):
            errors.append(f"'{key}' must be a string or null")

    locale = data.get("locale", "en-US")
    if not _is_string(locale) or locale not in VALID_LOCALES:
        errors.append(
            f"invalid locale {locale!r} (allowed: {sorted(VALID_LOCALES)})"
        )

    content_engine = data.get("content_engine")
    if (
        content_engine is not None and not _is_string(content_engine)
    ) or content_engine not in VALID_CONTENT_ENGINES:
        errors.append(
            f"invalid content_engine {content_engine!r} "
            f"(allowed: {sorted(str(e) for e in VALID_CONTENT_ENGINES)})"
        )

    # Sections
    sections = data.get("sections", [])
    if sections is not None and not isinstance(sections, list):
        errors.append("'sections' must be a list")
    else:
        seen_ids: set[str] = set()
        for i, section in enumerate(sections or []):
            where = f"sections[{i}]"
            if not isinstance(section, dict):
                errors.append(f"{where} must be a mapping")
                continue
            sid = section.get("id")
            if not _is_string(sid, nonempty=True):
                errors.append(f"{where} missing 'id'")
            elif sid in seen_ids:
                errors.append(f"{where} duplicate section id '{sid}'")
            else:
                seen_ids.add(sid)
            if not _is_string(section.get("title"), nonempty=True):
                errors.append(f"{where} ('{sid}') missing 'title'")
            for key in ("description", "file", "stage"):
                if not _is_string_or_none(section.get(key)):
                    errors.append(
                        f"{where} ('{sid}') '{key}' must be a string or null"
                    )
            for limit_key in ("word_limit", "char_limit", "page_limit"):
                if not _is_int_or_none(section.get(limit_key)):
                    errors.append(
                        f"{where} ('{sid}') '{limit_key}' must be an integer or null"
                    )
            if "required" in section and not isinstance(
                section["required"], bool
            ):
                errors.append(
                    f"{where} ('{sid}') 'required' must be a boolean"
                )
            if "format" in section and (
                not _is_string(section["format"])
                or section["format"] not in VALID_SECTION_FORMATS
            ):
                errors.append(
                    f"{where} ('{sid}') invalid format "
                    f"{section['format']!r} "
                    f"(allowed: {sorted(VALID_SECTION_FORMATS)})"
                )

    # Formatting rules
    rules = data.get("formatting_rules", [])
    if rules is not None and not isinstance(rules, list):
        errors.append("'formatting_rules' must be a list")
    else:
        for i, rule in enumerate(rules or []):
            where = f"formatting_rules[{i}]"
            if not isinstance(rule, dict):
                errors.append(f"{where} must be a mapping")
                continue
            if not _is_string(rule.get("id"), nonempty=True):
                errors.append(f"{where} missing 'id'")
            if not _is_string(rule.get("description"), nonempty=True):
                errors.append(
                    f"{where} ('{rule.get('id')}') missing 'description'"
                )
            severity = rule.get("severity", "error")
            if not _is_string(severity) or severity not in VALID_SEVERITIES:
                errors.append(
                    f"{where} ('{rule.get('id')}') invalid severity "
                    f"{severity!r} "
                    f"(allowed: {sorted(VALID_SEVERITIES)})"
                )
            for key in ("citation", "url", "quote"):
                if not _is_string_or_none(rule.get(key)):
                    errors.append(
                        f"{where} ('{rule.get('id')}') '{key}' must be a "
                        "string or null"
                    )
            applies_to = rule.get("applies_to", "all")
            if not _is_string(applies_to, nonempty=True):
                errors.append(
                    f"{where} ('{rule.get('id')}') 'applies_to' must be a "
                    "non-empty string"
                )

    # Budget rules
    budget = data.get("budget_rules")
    if budget is not None:
        if not isinstance(budget, dict):
            errors.append("'budget_rules' must be a mapping")
        else:
            for key in ("total_cap", "annual_cap", "indirect_rate_max"):
                if not _is_number_or_none(budget.get(key)):
                    errors.append(
                        f"budget_rules.{key} must be a number or null"
                    )
            if budget.get("mtdc_excludes") is not None and not isinstance(
                budget.get("mtdc_excludes"), list
            ):
                errors.append("budget_rules.mtdc_excludes must be a list")
            elif not all(
                _is_string(entry, nonempty=True)
                for entry in budget.get("mtdc_excludes", []) or []
            ):
                errors.append(
                    "budget_rules.mtdc_excludes must contain non-empty strings"
                )
            if not _is_string(budget.get("currency", "USD"), nonempty=True):
                errors.append(
                    "budget_rules.currency must be a non-empty string"
                )
            if not _is_string_or_none(budget.get("notes")):
                errors.append("budget_rules.notes must be a string or null")

    # Portal
    portal = data.get("portal")
    if portal is not None:
        if not isinstance(portal, dict):
            errors.append("'portal' must be a mapping")
        else:
            for key in ("accepts_markdown", "plain_text_boxes"):
                if key in portal and not isinstance(portal[key], bool):
                    errors.append(f"portal.{key} must be a boolean")
            for key in ("url", "notes"):
                if not _is_string_or_none(portal.get(key)):
                    errors.append(f"portal.{key} must be a string or null")

    # Review rubric
    rubric = data.get("review_rubric", [])
    if rubric is not None and not isinstance(rubric, list):
        errors.append("'review_rubric' must be a list")
    else:
        for i, crit in enumerate(rubric or []):
            where = f"review_rubric[{i}]"
            if not isinstance(crit, dict):
                errors.append(f"{where} must be a mapping")
                continue
            if not _is_string(crit.get("id"), nonempty=True):
                errors.append(f"{where} missing 'id'")
            if not _is_string(crit.get("name"), nonempty=True):
                errors.append(f"{where} ('{crit.get('id')}') missing 'name'")
            for key in ("description", "citation", "url"):
                if not _is_string_or_none(crit.get(key)):
                    errors.append(
                        f"{where} ('{crit.get('id')}') '{key}' must be a "
                        "string or null"
                    )

    return errors
