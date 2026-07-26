"""MCP server exposing California ASSIST (assist.org) articulation data.

Tools mirror the flow of the assist.org UI: find institutions, pick an
academic year, list agreements between a pair, then fetch the parsed
course-to-course articulations for a specific major/department.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .client import AssistClient, AssistError

mcp = FastMCP(
    "assist",
    instructions=(
        "Query California ASSIST (assist.org) course articulation agreements "
        "between community colleges and CSU/UC campuses. Typical flow: "
        "search_institutions to get IDs, then list_agreements to get report "
        "keys for a sending/receiving pair and year, then "
        "get_articulation_agreement with a key to see which community-college "
        "courses satisfy which university courses."
    ),
)

# FastMCP takes no version argument, and the underlying server falls back to
# reporting the mcp SDK's version in the initialize response. Set ours.
mcp._mcp_server.version = __version__

client = AssistClient()


# -- helpers -----------------------------------------------------------------


def _inner_json(value: Any) -> Any:
    """assist.org double-encodes nested objects as JSON strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _current_name(institution: dict) -> str:
    return institution["names"][-1]["name"]


def _institutions() -> list[dict]:
    return client.get("institutions")


def _years_by_fall_year() -> dict[int, int]:
    return {y["fallYear"]: y["id"] for y in client.get("AcademicYears")}


def _year_id(fall_year: int) -> int:
    years = _years_by_fall_year()
    if fall_year not in years:
        span = f"{min(years)}-{max(years)}"
        raise AssistError(f"no academic year starting fall {fall_year} (valid: {span})")
    return years[fall_year]


def _attr_texts(*attribute_lists) -> list[str]:
    """Flatten assist.org attribute objects ({position, content}) to strings."""
    texts = []
    for attrs in attribute_lists:
        for attr in attrs or []:
            content = attr.get("content") if isinstance(attr, dict) else None
            if content:
                texts.append(content)
    return texts


def _render_course(course: dict, with_title: bool = False) -> str:
    text = f"{course['prefix']} {course['courseNumber']}"
    if with_title:
        text += f" — {course.get('courseTitle', '')}"
        units = course.get("minUnits"), course.get("maxUnits")
        if units[0] is not None:
            text += f" ({units[0]} units)" if units[0] == units[1] else f" ({units[0]}-{units[1]} units)"
    return text


def _render_receiving(articulation: dict) -> str:
    """The university-side requirement being satisfied."""
    kind = articulation.get("type")
    if kind == "Course":
        return _render_course(articulation["course"], with_title=True)
    if kind == "Series":
        series = articulation["series"]
        joiner = " or " if series.get("conjunction") == "Or" else " and "
        return joiner.join(_render_course(c, with_title=True) for c in series.get("courses", []))
    if kind == "Requirement":
        return articulation.get("requirement", {}).get("name", "Requirement")
    if kind == "GeneralEducation":
        return articulation.get("generalEducationArea", {}).get("name", "General Education")
    return kind or "Unknown"


def _render_sending(sending: dict | None) -> str:
    """The community-college courses that satisfy the requirement.

    Top-level items are CourseGroups. The conjunction WITHIN a group is its
    courseConjunction; conjunctions BETWEEN groups live in
    courseGroupConjunctions with begin/end positions.
    """
    if not sending:
        return "No Course Articulated"
    groups = sending.get("items") or []
    if not groups:
        return sending.get("noArticulationReason") or "No Course Articulated"

    def render_group(group: dict) -> str:
        if group.get("type") == "Series":
            series_joiner = " or " if group.get("conjunction") == "Or" else " and "
            courses = [_render_course(c) for c in group.get("courses", [])]
            text = series_joiner.join(courses)
        else:
            joiner = " or " if group.get("courseConjunction") == "Or" else " and "
            courses = [
                _render_course(c) for c in group.get("items", []) if c.get("type") == "Course"
            ]
            text = joiner.join(courses)
        return f"({text})" if len(courses) > 1 else text

    joiners = {
        gc["sendingCourseGroupBeginPosition"]: gc.get("groupConjunction", "And")
        for gc in sending.get("courseGroupConjunctions") or []
    }
    out = render_group(groups[0])
    for pos in range(1, len(groups)):
        out += (" OR " if joiners.get(pos - 1) == "Or" else " AND ") + render_group(groups[pos])
    return out


# -- tools ---------------------------------------------------------------------


@mcp.tool()
def search_institutions(query: str = "", community_colleges_only: bool = False) -> list[dict]:
    """Search California institutions on ASSIST by name or code.

    Returns institution IDs needed by the other tools. An empty query lists
    all ~240 institutions. Names are matched against current and historical
    names, case-insensitively.
    """
    results = []
    needle = query.lower()
    for inst in _institutions():
        if community_colleges_only and not inst.get("isCommunityCollege"):
            continue
        names = [n["name"] for n in inst["names"]]
        if needle and not any(needle in n.lower() for n in names) and needle not in inst.get("code", "").lower():
            continue
        results.append(
            {
                "id": inst["id"],
                "name": names[-1],
                "code": inst.get("code", "").strip(),
                "is_community_college": inst.get("isCommunityCollege", False),
            }
        )
    return sorted(results, key=lambda r: r["name"])


@mcp.tool()
def list_academic_years() -> list[dict]:
    """List academic years available on ASSIST (e.g. fall_year 2025 = 2025-2026)."""
    return [
        {"fall_year": y["fallYear"], "label": f"{y['fallYear']}-{y['fallYear'] + 1}"}
        for y in client.get("AcademicYears")
    ]


@mcp.tool()
def list_transfer_partners(institution_id: int) -> list[dict]:
    """List institutions that have articulation agreements with the given one.

    For each partner: years_receiving_from_partner are fall years where the
    given institution receives the partner's transfer students, and
    years_sending_to_partner are fall years where it sends students to the
    partner.
    """
    by_id = {i["id"]: i for i in _institutions()}
    id_by_year = {v: k for k, v in _years_by_fall_year().items()}
    partners = []
    for entry in client.get(f"institutions/{institution_id}/agreements"):
        partner = by_id.get(entry["institutionParentId"])
        if partner is None:
            continue
        partners.append(
            {
                "partner_id": partner["id"],
                "partner_name": _current_name(partner),
                "years_sending_to_partner": sorted(
                    id_by_year[y] for y in entry.get("receivingYearIds", []) if y in id_by_year
                ),
                "years_receiving_from_partner": sorted(
                    id_by_year[y] for y in entry.get("sendingYearIds", []) if y in id_by_year
                ),
            }
        )
    return sorted(partners, key=lambda p: p["partner_name"])


@mcp.tool()
def list_agreements(
    sending_institution_id: int,
    receiving_institution_id: int,
    academic_year: int,
    category: str = "major",
    query: str = "",
) -> dict:
    """List articulation agreement reports between two institutions for a year.

    sending = where the student takes courses now (usually a community
    college); receiving = the transfer destination; academic_year = fall year
    (2025 means 2025-2026). Category is one of: major, dept, prefix, breadth.
    Returns report labels and the keys that get_articulation_agreement needs.
    Use query to filter labels (case-insensitive substring).
    """
    year_id = _year_id(academic_year)
    data = client.get(
        "agreements",
        receivingInstitutionId=receiving_institution_id,
        sendingInstitutionId=sending_institution_id,
        academicYearId=year_id,
        categoryCode=category,
    )
    reports = data.get("reports", [])
    needle = query.lower()
    matches = [
        {"label": r["label"], "key": r["key"]}
        for r in reports
        if not needle or needle in r["label"].lower()
    ]
    result = {"total_matching": len(matches), "agreements": matches[:150]}
    if len(matches) > 150:
        result["note"] = "truncated to 150; narrow with the query parameter"
    return result


@mcp.tool()
def get_articulation_agreement(key: str) -> dict:
    """Fetch and parse one articulation agreement by its report key.

    Keys look like "76/113/to/7/Major/<uuid>" and come from list_agreements.
    Each articulation maps a university requirement ("receiving") to the
    community-college courses that satisfy it ("sending"), with And/Or logic
    already rendered into the strings.
    """
    data = client.get("articulation/Agreements", Key=key)
    if not data.get("isSuccessful"):
        raise AssistError(f"assist.org rejected key {key!r}: {data.get('validationFailure')}")
    result = data["result"]

    receiving_inst = _inner_json(result.get("receivingInstitution")) or {}
    sending_inst = _inner_json(result.get("sendingInstitution")) or {}
    academic_year = _inner_json(result.get("academicYear")) or {}
    articulations = _inner_json(result.get("articulations")) or []

    rows = []
    for cell in articulations:
        articulation = cell.get("articulation") or {}
        sending = articulation.get("sendingArticulation")
        notes = _attr_texts(
            articulation.get("attributes"),
            articulation.get("receivingAttributes"),
            articulation.get("courseAttributes"),
            (sending or {}).get("attributes"),
        )
        row = {
            "receiving": _render_receiving(articulation),
            "sending": _render_sending(sending),
        }
        if notes:
            row["notes"] = notes
        rows.append(row)

    return {
        "agreement": result.get("name"),
        "type": result.get("type"),
        "academic_year": academic_year.get("code"),
        "sending_institution": _current_name(sending_inst) if sending_inst.get("names") else None,
        "receiving_institution": _current_name(receiving_inst) if receiving_inst.get("names") else None,
        "publish_date": result.get("publishDate"),
        "articulations": rows,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
