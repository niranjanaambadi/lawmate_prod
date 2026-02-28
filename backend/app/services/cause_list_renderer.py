from __future__ import annotations

import html
from collections import defaultdict
from typing import Any

GREEN = {"ADMITTED", "ALLOWED", "DISPOSED"}
AMBER = {"PART_HEARD", "SERVICE_NOT_COMPLETE", "ADJOURNED"}
RED = {"NOT_ADMITTED"}

_MEDIATION_BADGE = (
    "display:inline-block;padding:2px 10px;border-radius:999px;"
    "font-size:11px;background:#ede9fe;color:#5b21b6;font-weight:600;"
)


def _status_style(status: str) -> str:
    s = (status or "UNKNOWN").upper()
    if s in GREEN:
        return "background:#dcfce7;color:#166534;"
    if s in AMBER:
        return "background:#fef3c7;color:#92400e;"
    if s in RED:
        return "background:#fee2e2;color:#991b1b;"
    return "background:#e5e7eb;color:#374151;"


def _is_mediation(row: dict[str, Any]) -> bool:
    return bool(row.get("_mediation")) or (
        str(row.get("section_type") or "").upper() == "MEDIATION_LIST"
    )


class CauseListRenderer:
    # ------------------------------------------------------------------
    # Mediation-specific rendering
    # ------------------------------------------------------------------

    def _render_mediation_section(self, rows: list[dict[str, Any]]) -> str:
        rows_html: list[str] = []
        for r in rows:
            petitioner = (
                ", ".join([str(x) for x in (r.get("petitioner_names") or []) if str(x).strip()])
                or "-"
            )
            respondent = (
                ", ".join([str(x) for x in (r.get("respondent_names") or []) if str(x).strip()])
                or "-"
            )
            pet_advs = (
                ", ".join([str(x) for x in (r.get("all_petitioner_advocates") or []) if str(x).strip()])
                or "-"
            )
            resp_advs = (
                ", ".join([str(x) for x in (r.get("all_respondent_advocates") or []) if str(x).strip()])
                or "-"
            )
            role = str(r.get("advocate_role") or "-")
            status = str(r.get("status") or "UNKNOWN").upper()
            badge_style = _status_style(status)

            rows_html.append(
                "<tr>"
                f"<td>{html.escape(str(r.get('serial_number') or '-'))}</td>"
                f"<td>{html.escape(str(r.get('case_number_raw') or '-'))}</td>"
                f"<td>"
                f"{html.escape(petitioner)} <span style='color:#6b7280'>vs</span> {html.escape(respondent)}"
                f"</td>"
                f"<td style='font-size:12px;color:#374151'>{html.escape(pet_advs)}</td>"
                f"<td style='font-size:12px;color:#374151'>{html.escape(resp_advs)}</td>"
                f"<td><span style='padding:2px 8px;border-radius:999px;font-size:12px;{badge_style}'>"
                f"{html.escape(status)}</span></td>"
                f"<td><span style='padding:2px 8px;border-radius:999px;{_MEDIATION_BADGE}'>"
                f"{html.escape(role.replace('_', ' '))}</span></td>"
                "</tr>"
            )

        table_html = (
            "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
            "<thead><tr style='background:#ede9fe;'>"
            "<th>Sr. No.</th>"
            "<th>Case Number</th>"
            "<th>Parties</th>"
            "<th>Petitioner Advocates</th>"
            "<th>Respondent Advocates</th>"
            "<th>Status</th>"
            "<th>Your Role</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody>"
            "</table>"
        )

        notice = (
            "<p style='margin:0 0 8px 0;font-size:12px;color:#6d28d9;'>"
            "&#9432;&nbsp; These cases appear in the <strong>Mediation List</strong> section of the "
            "daily cause list. Advocate details were fetched from the court&rsquo;s case detail page."
            "</p>"
        )

        return (
            "<section style='margin-bottom:16px;padding:12px;border:2px solid #c4b5fd;"
            "border-radius:10px;background:#faf5ff;'>"
            "<h4 style='margin:0 0 6px 0;font-size:15px;color:#5b21b6;'>"
            "&#9878; Mediation List</h4>"
            f"{notice}"
            f"{table_html}"
            "</section>"
        )

    # ------------------------------------------------------------------
    # Regular section rendering (existing logic)
    # ------------------------------------------------------------------

    def _render_court_section(self, court: str, rows: list[dict[str, Any]]) -> str:
        judges: list[str] = []
        for r in rows:
            values = r.get("judges") if isinstance(r.get("judges"), list) else []
            for j in values:
                jn = str(j).strip()
                if jn and jn not in judges:
                    judges.append(jn)

        rows_html: list[str] = []
        for r in rows:
            petitioner = (
                ", ".join([str(x) for x in (r.get("petitioner_names") or []) if str(x).strip()])
                or "-"
            )
            respondent = (
                ", ".join([str(x) for x in (r.get("respondent_names") or []) if str(x).strip()])
                or "-"
            )
            pending = r.get("pending_compliance") or []
            if pending:
                items = "".join([f"<li>{html.escape(str(p))}</li>" for p in pending])
                pending_html = (
                    f'<ul style="margin:0;padding-left:16px;color:#b91c1c;font-size:12px;">'
                    f"{items}</ul>"
                )
            else:
                pending_html = "-"

            status = str(r.get("status") or "UNKNOWN").upper()
            badge_style = _status_style(status)

            rows_html.append(
                "<tr>"
                f"<td>{html.escape(str(r.get('serial_number') or '-'))}</td>"
                f"<td>{html.escape(str(r.get('case_number_raw') or '-'))}</td>"
                f"<td>{html.escape(petitioner)} <span style='color:#6b7280'>vs</span> {html.escape(respondent)}</td>"
                f"<td>{html.escape(str(r.get('section_label') or '-'))}</td>"
                f"<td>{html.escape(str(r.get('advocate_role') or '-'))}</td>"
                f"<td><span style='padding:2px 8px;border-radius:999px;font-size:12px;{badge_style}'>"
                f"{html.escape(status)}</span></td>"
                f"<td>{pending_html}</td>"
                "</tr>"
            )

        judges_html = html.escape(" | ".join(judges) if judges else "-")
        table_html = (
            "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
            "<thead><tr style='background:#f3f4f6;'>"
            "<th>Sr. No.</th><th>Case Number</th><th>Parties</th>"
            "<th>Section</th><th>Your Role</th><th>Status</th><th>Pending Compliance</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table>"
        )

        return (
            "<section style='margin-bottom:16px;padding:12px;border:1px solid #e5e7eb;"
            "border-radius:10px;background:#fff;'>"
            f"<h4 style='margin:0 0 6px 0;font-size:15px;'>{html.escape(court)}</h4>"
            f"<div style='margin-bottom:10px;color:#374151;font-size:12px;'>"
            f"<strong>Judges:</strong> {judges_html}</div>"
            f"{table_html}"
            "</section>"
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def render(self, result_json: dict[str, Any]) -> str:
        listings = (
            result_json.get("listings")
            if isinstance(result_json.get("listings"), list)
            else []
        )
        if not listings:
            return (
                '<div style="padding:16px;border:1px solid #e5e7eb;border-radius:10px;background:#f8fafc;">'
                "No listings found for this date."
                "</div>"
            )

        # Split into regular and mediation rows
        regular_rows: list[dict[str, Any]] = []
        mediation_rows: list[dict[str, Any]] = []
        for row in listings:
            if _is_mediation(row):
                mediation_rows.append(row)
            else:
                regular_rows.append(row)

        chunks: list[str] = []

        # ── Regular listings grouped by court ───────────────────────────
        if regular_rows:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in regular_rows:
                court_no = str(row.get("court_number") or "UNKNOWN")
                court_code = str(row.get("court_code") or "")
                key = f"Court {court_no}{(' - ' + court_code) if court_code else ''}"
                grouped[key].append(row)

            for court, rows in grouped.items():
                chunks.append(self._render_court_section(court, rows))

        # ── Mediation listings (single combined section) ─────────────────
        if mediation_rows:
            chunks.append(self._render_mediation_section(mediation_rows))

        return "".join(chunks)

    def render_empty(self, listing_date: str) -> str:
        return (
            '<div style="padding:16px;border:1px solid #e5e7eb;border-radius:10px;background:#f8fafc;">'
            f"No cause-list data available for {html.escape(listing_date)}."
            "</div>"
        )


cause_list_renderer = CauseListRenderer()
