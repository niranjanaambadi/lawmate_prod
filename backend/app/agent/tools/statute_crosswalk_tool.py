"""
Statute Crosswalk Tool for LawMate Agent

This tool provides deterministic, instant lookups for section mappings
between old criminal laws (IPC, CrPC, IEA) and new laws (BNS, BNSS, BSA).

NOT a vector search — this is a JSON/DynamoDB lookup that returns exact answers.
Use this for "what is the BNS equivalent of Section 302 IPC?" type queries.
"""

import json
from pathlib import Path
from typing import Any

from app.agent.tools.registry import BaseTool


# In production, replace with DynamoDB or S3 read
# For MVP, loading from JSON is perfectly fine
_CROSSWALK_DIR = Path(__file__).parent / "data" / "crosswalk"

_CACHE: dict[str, dict] = {}


def _load_crosswalk(filename: str) -> dict:
    """Load a crosswalk JSON file with caching."""
    if filename not in _CACHE:
        filepath = _CROSSWALK_DIR / filename
        if filepath.exists():
            with open(filepath) as f:
                _CACHE[filename] = json.load(f)
        else:
            _CACHE[filename] = {}
    return _CACHE[filename]


def statute_crosswalk(
    section: str,
    from_act: str,
    to_act: str | None = None,
) -> dict[str, Any]:
    """
    Look up the corresponding section in the new/old criminal law.

    Args:
        section: Section number (e.g., "302", "438", "376(2)")
        from_act: Source act — "IPC", "CrPC", "IEA", "BNS", "BNSS", "BSA"
        to_act:   Target act (auto-inferred if not provided)

    Returns:
        Dict with mapping details, change type, and comparison summary.
    """

    # Auto-infer target act
    act_pairs = {
        "IPC": "BNS", "BNS": "IPC",
        "CrPC": "BNSS", "BNSS": "CrPC",
        "IEA": "BSA", "BSA": "IEA",
    }

    from_act = from_act.upper()
    if to_act:
        to_act = to_act.upper()
    else:
        to_act = act_pairs.get(from_act)

    if not to_act:
        return {"error": f"Unknown act: {from_act}. Supported: IPC, BNS, CrPC, BNSS, IEA, BSA"}

    section = section.strip()

    # Determine which lookup file to use
    # Files: crosswalk_bns_to_ipc.json, crosswalk_ipc_to_bns.json
    #        crosswalk_bnss_to_crpc.json, crosswalk_crpc_to_bnss.json
    #        crosswalk_bsa_to_iea.json, crosswalk_iea_to_bsa.json
    lookup_file = f"crosswalk_{from_act.lower()}_to_{to_act.lower()}.json"
    data = _load_crosswalk(lookup_file)

    if not data:
        return {
            "error": f"Crosswalk data not found for {from_act} → {to_act}. "
                     f"File {lookup_file} missing from {_CROSSWALK_DIR}",
            "section": section,
            "from_act": from_act,
            "to_act": to_act,
        }

    # Direct lookup
    result = data.get(section)

    if result:
        # Result may be a list (e.g. one IPC section maps to multiple BNS sections)
        if isinstance(result, list):
            return {
                "section": section,
                "from_act": from_act,
                "to_act": to_act,
                "mappings": result,
                "note": f"{from_act} Section {section} maps to {len(result)} {to_act} section(s).",
            }
        else:
            return {
                "section": section,
                "from_act": from_act,
                "to_act": to_act,
                **result,
            }

    # Try fuzzy match (e.g., user says "302" but data has "302(1)")
    prefix_matches = [
        (k, v) for k, v in data.items()
        if k.startswith(section) or section.startswith(k.split("(")[0])
    ]

    if prefix_matches:
        return {
            "section": section,
            "from_act": from_act,
            "to_act": to_act,
            "exact_match": False,
            "possible_matches": [
                {"section_key": k, **(v if isinstance(v, dict) else {"mappings": v})}
                for k, v in prefix_matches[:5]
            ],
            "note": f"No exact match for '{section}'. Found {len(prefix_matches)} related section(s).",
        }

    return {
        "section": section,
        "from_act": from_act,
        "to_act": to_act,
        "found": False,
        "note": f"Section {section} of {from_act} not found in crosswalk data.",
    }


# ── BaseTool wrapper ──────────────────────────────────────────────────────────

class StatuteCrosswalkTool(BaseTool):
    name = "statute_crosswalk"
    description = (
        "Look up the corresponding section between old and new Indian criminal laws. "
        "Maps IPC sections to BNS, CrPC sections to BNSS, and IEA sections to BSA "
        "(and vice versa). Use this when a user asks 'what is the BNS equivalent of "
        "Section X IPC' or 'what was the old CrPC section for BNSS Section Y'. "
        "This is a deterministic lookup — always prefer this over searching the knowledge base "
        "for section mapping questions. Returns the corresponding section number, "
        "change type (new/modified/consolidated/cosmetic/deleted), and a summary of what changed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": "The section number to look up, e.g. '302', '438', '376(2)', '65B'",
            },
            "from_act": {
                "type": "string",
                "description": "The source act. One of: IPC, BNS, CrPC, BNSS, IEA, BSA",
                "enum": ["IPC", "BNS", "CrPC", "BNSS", "IEA", "BSA"],
            },
            "to_act": {
                "type": "string",
                "description": "The target act (optional — auto-inferred from source). One of: IPC, BNS, CrPC, BNSS, IEA, BSA",
                "enum": ["IPC", "BNS", "CrPC", "BNSS", "IEA", "BSA"],
            },
        },
        "required": ["section", "from_act"],
    }

    async def run(self, context: Any, db: Any, **kwargs) -> dict:
        section = (kwargs.get("section") or "").strip()
        from_act = (kwargs.get("from_act") or "").strip()
        to_act = (kwargs.get("to_act") or None)

        if not section:
            return self.err("'section' is required")
        if not from_act:
            return self.err("'from_act' is required")

        result = statute_crosswalk(section=section, from_act=from_act, to_act=to_act)

        if "error" in result:
            return self.err(result["error"], data=result)

        return self.ok(result)


# ----- Quick test -----
if __name__ == "__main__":
    # Test with sample data
    sample_data = {
        "302": {
            "bns_section": "103",
            "ipc_section": "302",
            "subject": "Punishment for murder",
            "change_type": "cosmetic",
            "comparison_summary": 'No change except "Code" is replaced with "Sanhita".',
        },
        "420": {
            "bns_section": "318",
            "ipc_section": "420",
            "subject": "Cheating and dishonestly inducing delivery of property",
            "change_type": "cosmetic",
            "comparison_summary": "Phraseology changed but essence is same.",
        },
        "438": {
            "bns_section": "482",  # This is BNSS actually, but for demo
            "ipc_section": "438",
            "subject": "Direction for grant of bail to person apprehending arrest (anticipatory bail)",
            "change_type": "modified",
            "comparison_summary": "New proviso added requiring the applicant to be produced before the court within 7 days.",
        },
    }

    # Write sample for testing
    test_dir = Path("data/crosswalk")
    test_dir.mkdir(parents=True, exist_ok=True)
    with open(test_dir / "crosswalk_ipc_to_bns.json", "w") as f:
        json.dump(sample_data, f, indent=2)

    # Override module-level crosswalk dir for test
    import statute_crosswalk_tool
    statute_crosswalk_tool._CROSSWALK_DIR = test_dir
    _CACHE.clear()

    # Test lookups
    print("=== Test: IPC 302 -> BNS ===")
    print(json.dumps(statute_crosswalk("302", "IPC"), indent=2))

    print("\n=== Test: IPC 420 -> BNS ===")
    print(json.dumps(statute_crosswalk("420", "IPC"), indent=2))

    print("\n=== Test: IPC 438 -> BNS ===")
    print(json.dumps(statute_crosswalk("438", "IPC"), indent=2))

    print("\n=== Test: Unknown section ===")
    print(json.dumps(statute_crosswalk("999", "IPC"), indent=2))

    print("\n=== Test: Bad act ===")
    print(json.dumps(statute_crosswalk("302", "POCSO"), indent=2))
