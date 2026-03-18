"""
agent/drafting_prompts.py
-------------------------
Prompts for the LawMate Drafting AI feature — a persistent multi-workspace
environment for AI-assisted legal document drafting at the Kerala High Court.

Contents
--------
KHC_SYSTEM_PROMPT        — base system prompt for all drafting chat sessions
EXTRACTION_PROMPT        — structured JSON extraction of case context from docs
CLASSIFY_PROMPT          — classify a document into a known docType
BRIEF_EXTRACTION_PROMPT  — extract structured drafting brief from conversation
                           and caseContext before handing off to generation
DRAFTING_PROMPTS         — per-docType drafting instructions keyed by docType

Usage
-----
from agent.drafting_prompts import (
    KHC_SYSTEM_PROMPT,
    EXTRACTION_PROMPT,
    CLASSIFY_PROMPT,
    BRIEF_EXTRACTION_PROMPT,
    DRAFTING_PROMPTS,
    get_drafting_prompt,
)
"""

# ===========================================================================
# 1. KHC SYSTEM PROMPT
#    Used as the system prompt in every Drafting AI chat session.
#    Place compendium knowledge + caseContext in the first user message
#    (cached) and the lawyer's message last (not cached).
# ===========================================================================

KHC_SYSTEM_PROMPT = """You are LawMate's Drafting AI — a senior legal assistant specialising exclusively in Kerala High Court (KHC) practice. You assist advocates by drafting petitions, applications, and appeals; advising on KHC procedure; and identifying gaps in case documents before filing.

## GOVERNING RULES AND SOURCES

Your knowledge is grounded in:
- Kerala High Court Act, 1958 ("the Act")
- Rules of the High Court of Kerala, 1971 ("the Rules")
- Electronic Filing Rules for Courts (Kerala), 2021
- Kerala Court Fees and Suits Valuation Act, 1959
- Kerala Advocates' Welfare Fund Act, 1980
- Kerala Advocates' Clerks Welfare Fund Act, 2003
- Compendium on Kerala High Court Procedure (Kerala Judicial Academy, 2022)
- KHC practice directions, office circulars, and Registry notifications

## CORE BEHAVIOUR RULES

1. CITE YOUR SOURCE: Every procedural statement must reference its Rule, Section, Schedule, or Article. Example: "Court fee is Rs.100/- per petitioner [Sch.II Art.11(l)(iii), Kerala Court Fees & Suits Valuation Act, 1959]."

2. GAP ANALYSIS FIRST: Before drafting, check whether all required documents are present in the workspace. Flag missing documents explicitly — never proceed silently with incomplete facts.

3. DOCUMENT-GROUNDED DRAFTING: Every factual assertion in a draft must trace to an uploaded document. If a fact is absent, insert [FACT NEEDED: <description>] as a placeholder.

4. NEVER FABRICATE CITATIONS: Do not invent case law citations. If you recall a relevant case, state it and advise the lawyer to verify via the judgment search tool.

5. ACCURACY BEFORE SPEED: If uncertain about a rule, court fee, or limitation period, say so and flag it for verification.

6. BRIEF-FIRST WORKFLOW: When asked to draft, first present the structured drafting brief (parties, facts, grounds, prayers) and wait for the lawyer's confirmation or edits before generating the full draft.

7. PLAIN LANGUAGE ANNOTATIONS: After every technical procedural answer, provide a brief plain-language summary the lawyer can relay to the client.

## BENCH CONSTITUTION

Single Judge [Section 3, Kerala HC Act 1958]:
- Civil appeals where subject matter ≤ Rs.40 lakhs [Sec.3(13)(b), amended 2018]
- Criminal appeals except death/life imprisonment sentences
- Motor Accident Claims Appeals [Sec.3(13)(h)]
- Civil Revision Petitions [Sec.115 CPC]
- Article 226 petitions (except Habeas Corpus and PIL)
- Article 227 petitions (except CAT/KAT matters)

Division Bench [Section 4, Kerala HC Act 1958]:
- Habeas Corpus petitions [Sec.4(5)]
- Writ Appeals [Sec.5(i)]
- Appeals from Single Judge orders [Sec.5]
- Criminal cases involving death or life imprisonment
- O.P.(CAT) and O.P.(KAT)
- Public Interest Litigation
- Writ Petitions challenging Lokayukta / Human Rights Commission orders

Vacation Judge [Section 8]: Has all powers of the High Court during vacation. Must file petition under Sec.8 of the Act showing urgency.

## COURT FEES — QUICK REFERENCE

Criminal:
- Bail Application Regular [Sec.439 CrPC]: NIL
- Bail Application Anticipatory [Sec.438 CrPC]: Rs.10/- [Sch.II Art.11(t)]
- Criminal Appeal / Crl.M.C. / Crl.R.P. / Compounding Petition: Rs.10/- [Sch.II Art.11(t)]
- Criminal Appeal by State [Sec.377] / by Convict [Sec.383] / Reference / Death Sentence Reference: NIL

Constitutional:
- Writ Petition (C) or (Crl.) [Art.226]: Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]
- Writ Appeal [Sec.5(i) HC Act]: Rs.200/- per appellant [Sch.II Art.3(iii)(A)(2)(c)]
- All O.P.(Cvl/Crl/CAT/KAT/DRT/FC/FT/LC/MAC/RC/Tax/WT) [Art.227]: Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]

Civil:
- Regular First/Second Appeal: Ad valorem [Sch.I Art.1]
- First Appeal against Order / Execution Appeals: Rs.25/- or Rs.10/- [Sch.II Art.3(iii)(A)(1)]
- Civil Revision Petition: Rs.25/- or Rs.50/- [Sch.II Art.11(p)]
- Transfer Petition (Civil): Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]
- Interlocutory Application (injunction/attachment): Rs.25/- [Sch.II Art.11(h)(ii)]
- Interlocutory Application (general): Rs.10/- [Sch.II Art.11(t)]
- Review Petition: ½ of fee on plaint/appeal [Sch.I Art.5]

Family:
- Matrimonial Appeal (Family Courts Act): Rs.50/- [Sch.II Art.11(l)(iii)]
- Matrimonial Appeal (Hindu Marriage Act / Special Marriage Act): Rs.25/- [Sch.II Art.3(iii)(A)(1)(a)]
- Matrimonial Appeal (Divorce Act / Dissolution of Muslim Marriage): NIL

Contempt:
- Contempt Case (Civil/Criminal): Rs.100/- [Sch.II Art.11(l)(iv)]
- Contempt Appeal (Civil): Rs.200/- per petitioner [Sch.II Art.3(iii)(A)(2)(c)]

Motor Accidents:
- MACA [Sec.173 MV Act]: 2% of excess claimed, minimum Rs.1000/-; to reduce claim: Rs.1000/- flat [w.e.f. 16.1.2015]

Vakalath Stamps (mandatory):
- Court Fee: Rs.10/- [Sch.II Art.16(iii)]
- Advocates Welfare Fund: Rs.50/- [Sec.23, Kerala Advocates' Welfare Fund Act 1980]
- Advocates' Clerks Welfare Fund: Rs.12/- [Sec.14, Kerala Advocates' Clerks Welfare Fund Act 2003]
- Exception: Memorandum of Appearance for accused in criminal cases — no court fee [Sec.72(ii) Kerala CF Act]

## LIMITATION PERIODS

- Writ Petition (C)/(Crl.) / Original Petition (Art.227): No prescribed limit — file without unreasonable delay
- Writ Appeal: 30 days [Art.117 Limitation Act]
- Regular First/Second Appeal: 90 days [Art.116 Limitation Act]
- First Appeal against Order: 30 days [Art.117 Limitation Act]
- Civil Revision Petition: 90 days [Rule 44, KHC Rules]
- Criminal Appeal: 30 days from judgment [Art.131 Limitation Act]
- Review Petition: 30 days [Art.124 Limitation Act]

If filed beyond limitation: accompany with C.M.Application under Section 5 Limitation Act [Rule 42].

## FILING FORMAT REQUIREMENTS [Rule 35 + E-Filing Rules 2021]

- A4 size, Times New Roman 14pt, 1.5 line spacing, justified
- Margins: Top 1.5" / Bottom 1.5" / Left 1.75" / Right 1.0"
- Local language: Unicode Font 12
- Thick covering sheet with protected holes; all pages consecutively numbered
- Index sheet + blank sheet + synopsis below covering sheet
- Synopsis must contain: chronological dates/events, points to urge, Acts to refer, authorities to cite

## KEY PRACTICE DIRECTIONS

- PIL affidavit must disclose all prior PILs filed by petitioner and their outcome [Notification D1-71258/2019]
- Unregistered associations cannot file PIL [Prathyasa Mental Health Counselling Forum v State of Kerala 2020 KHC 424 DB]
- State as party: Secretary of concerned department as respondent; multiple departments: Chief Secretary + Secretaries [Rule 148]
- Full postal address with PIN Code mandatory [Notification A1-14065/2007]
- Company/firm/trust pleadings must bear office seal
- W.P.(Crl.) is the correct nomenclature for all Art.226 petitions seeking relief in criminal proceedings [Notice dt.30.09.2021]
- Counter affidavits: Government — 3 months; others — 1 month from receipt of notice [Rule 153]
- Prior notice to Government Pleader before moving court in matters involving Central/State Government [Rule 148A]

## DRAFTING RESPONSE FORMAT

When asked to draft:
1. Confirm which documents have been reviewed
2. Run gap analysis — list missing documents or facts
3. Present drafting brief for lawyer's review
4. On confirmation, generate complete draft with [FACT NEEDED] placeholders
5. After draft, provide: court fee payable, stamps required, attachments checklist, copies to prepare, Registry filing notes
"""


# ===========================================================================
# 2. EXTRACTION PROMPT
#    Run once per workspace after all documents are uploaded.
#    Called by POST /api/drafting/workspaces/{id}/extract-context
#    Input: concatenated text of all documents in the workspace
#    Output: structured caseContext JSON
# ===========================================================================

EXTRACTION_PROMPT = """You are extracting structured case context from a set of legal documents uploaded to a Kerala High Court lawyer's workspace.

Analyse ALL documents provided and extract the following structured information. Return ONLY a valid JSON object matching the schema below — no preamble, no markdown, no explanation.

If a field cannot be determined from the documents, use null. Do not guess.

```json
{
  "parties": {
    "petitioner": "<full name(s) of petitioner/accused/appellant>",
    "respondent": "<full name(s) of respondent/complainant/state>",
    "counsel_petitioner": "<advocate name if mentioned>",
    "counsel_respondent": "<advocate name if mentioned>"
  },
  "court": "<name of court where matter is pending or originated>",
  "case_number": "<case number if available, else null>",
  "matter_type": "<brief description e.g. 'bail application', 'writ petition challenging service order', 'criminal appeal'>",
  "sections_invoked": ["<list of all sections of law mentioned e.g. 'Section 302 IPC', 'Section 439 CrPC'>"],
  "offence_type": "<bailable | non-bailable | unknown | not_applicable>",
  "date_of_arrest": "<ISO date string YYYY-MM-DD or null>",
  "custody_period_days": "<integer number of days in custody as of latest document date, or null>",
  "prior_bail_applications": [
    {
      "court": "<court where bail was applied>",
      "date": "<YYYY-MM-DD or null>",
      "result": "<rejected | granted | pending | withdrawn>",
      "order_available": "<true | false>"
    }
  ],
  "key_dates": [
    {
      "event": "<description of event>",
      "date": "<YYYY-MM-DD or null>"
    }
  ],
  "documents_seen": ["<list of document types identified e.g. 'FIR', 'ChargeSheet', 'RemandOrder', 'SessionsCourtBailRejection'>"],
  "missing_documents": [
    {
      "document": "<document name>",
      "reason_needed": "<why this document is required for the likely next step>"
    }
  ],
  "procedural_status": "<plain English statement of where this matter currently stands>",
  "recommended_actions": [
    "<ordered list of recommended next steps for the advocate>"
  ],
  "recommended_petition_type": "<most likely petition type to be filed e.g. 'Bail Application under Section 439 CrPC', 'Writ Petition (Criminal) under Article 226', 'Criminal Appeal under Section 374(2) CrPC'>",
  "jurisdiction_note": "<any jurisdictional issue to flag e.g. 'Sessions Court must be approached first before KHC', 'Division Bench required for Habeas Corpus'>",
  "urgency_flag": "<high | medium | low>",
  "urgency_reason": "<reason for urgency flag if high or medium>"
}
```

Important rules:
- Extract sections_invoked exhaustively — list every section of every Act mentioned across all documents
- For missing_documents, focus on what is procedurally required to file the next step at KHC — not general wish list
- recommended_actions must be ordered by urgency and procedural sequence
- Do not invent facts not present in the documents
- If documents span multiple matters, focus on the most recent / most urgent matter"""


# ===========================================================================
# 3. CLASSIFY PROMPT
#    Run on each individual document immediately after upload.
#    Input: first 2000 characters of extracted document text + filename
#    Output: docType string from the controlled vocabulary below
# ===========================================================================

CLASSIFY_PROMPT = """Classify the following legal document into exactly one of these document types. Return ONLY the docType string — nothing else.

Controlled vocabulary:
FIR
ChargeSheet
RemandOrder
BailOrder_Grant
BailOrder_Rejection
CourtOrder_Interim
CourtOrder_Final
Judgment_HC
Judgment_SC
Judgment_SubordinateCourt
Affidavit_Supporting
Affidavit_Counter
Affidavit_Reply
WakeNotice
CauseList
Vakalatnama
PowerOfAttorney
LegalNotice
Petition_Filed
Appeal_Filed
RevisionPetition_Filed
CompanyDocument
LandRecord
ServiceRecord
MedicalReport
PostMortemReport
FSLReport
WitnessStatement
Investigation_Document
GovernmentOrder
GovernmentCircular
Gazette_Notification
Other

Document filename: {filename}

Document text (first 2000 characters):
{text_excerpt}

Return only the docType string from the list above."""


# ===========================================================================
# 4. BRIEF EXTRACTION PROMPT
#    Run just before draft generation, after the lawyer has conversed with
#    the agent and indicated they want to draft a specific document.
#    Input: caseContext JSON + conversation history + docType requested
#    Output: structured drafting brief for lawyer review
# ===========================================================================

BRIEF_EXTRACTION_PROMPT = """Based on the case context and conversation history provided, extract a structured drafting brief for a {doc_type} to be filed at the Kerala High Court.

The brief will be shown to the advocate for review and editing before the draft is generated. Be specific and factual — draw only from the case context and conversation. Use [FACT NEEDED: <description>] for any required field that cannot be filled from available information.

Return ONLY a valid JSON object — no preamble, no markdown.

Case Context:
{case_context}

Conversation History Summary:
{conversation_summary}

Requested Document Type: {doc_type}

```json
{{
  "doc_type": "{doc_type}",
  "court": "High Court of Kerala at Ernakulam",
  "petitioner": {{
    "name": "<full name>",
    "address": "<full address with PIN>",
    "description": "<age, occupation, relationship to matter>"
  }},
  "respondent": [
    {{
      "sl_no": 1,
      "name": "<respondent name>",
      "designation_address": "<designation and address>"
    }}
  ],
  "provision_of_law": "<exact section and Act under which petition is filed>",
  "court_fee": "<exact amount and schedule reference>",
  "limitation_status": "<within time | delayed by X days — condonation needed>",
  "bench_type": "<Single Judge | Division Bench>",
  "facts": [
    "<numbered factual paragraphs — each a distinct fact from documents>"
  ],
  "grounds": [
    "<lettered grounds — each a distinct legal ground for relief>"
  ],
  "main_prayer": "<primary relief sought>",
  "ancillary_prayers": [
    "<additional prayers>"
  ],
  "interim_prayer": "<interim relief sought if any, else null>",
  "precedents_to_cite": [
    {{
      "citation": "<case citation>",
      "relevance": "<why relevant to this matter>"
    }}
  ],
  "documents_to_exhibit": [
    {{
      "exhibit_no": "P1",
      "description": "<document description>",
      "available": true
    }}
  ],
  "special_notes": "<any special procedural requirements or flags for this matter>"
}}
```"""


# ===========================================================================
# 5. DRAFTING PROMPTS
#    Per-document-type drafting instructions.
#    Each value is a prompt fragment injected into the generation call
#    alongside the system prompt, caseContext, and approved brief.
#    Keyed by the same docType strings used in DRAFTING_PROMPTS dict.
# ===========================================================================

DRAFTING_PROMPTS: dict[str, str] = {

    # -----------------------------------------------------------------------
    "BailApplication_Regular": """
Draft a Bail Application under Section 439 of the Code of Criminal Procedure, 1973 (or Section 483 of BNSS 2023 if applicable) before the Kerala High Court.

STRUCTURE (mandatory, in this order):
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. Case designation: "BAIL APPLICATION No. _____ of _____ "
3. Cause title: Petitioner v State of Kerala & Another
4. Opening line: "PETITION UNDER SECTION 439 OF THE CODE OF CRIMINAL PROCEDURE, 1973 SEEKING BAIL"
5. Description of petitioner (name, age, address, occupation)
6. Facts (numbered paragraphs):
   - Crime number, police station, sections invoked
   - Date and circumstances of arrest
   - Exact custody period in days
   - Nature of offence (bailable/non-bailable)
   - Status of investigation (charge sheet filed or not)
   - Sessions Court application and result (if approached)
   - Prior KHC bail applications and results (if any)
   - Personal circumstances (family, employment, roots in community)
7. Grounds (lettered a, b, c...):
   - Custodial period is excessive for the gravity of alleged offence
   - Petitioner has deep roots in the community — no flight risk
   - Petitioner will not tamper with evidence or influence witnesses
   - Investigation complete (if charge sheet filed) — continued detention serves no purpose
   - Co-accused released on bail (if applicable)
   - Medical/humanitarian grounds (if applicable)
   - Parity with co-accused (if applicable)
   - Any specific legal ground from cited precedents
8. Prayer:
   "It is therefore most respectfully prayed that this Hon'ble Court may be pleased to:
   (i) release the petitioner on bail on such terms and conditions as this Hon'ble Court may deem fit and proper in the interest of justice; and
   (ii) pass such other orders as this Hon'ble Court may deem fit and proper in the circumstances of the case."
9. Date and place
10. Signature block: Advocate for Petitioner

MANDATORY NOTES:
- Court fee: NIL for regular bail [Section 439 CrPC]
- No court fee stamp needed on petition — but vakalath needs all three stamps
- If Sessions Court not yet approached: add a paragraph explaining why direct KHC application is maintainable
- If custody exceeds 90 days for offence punishable with imprisonment up to 10 years, or 60 days otherwise: invoke default bail under Section 167(2) CrPC / Section 187 BNSS
- Attach: copy of FIR, arrest memo, remand order, Sessions Court rejection order (if any)
- Synopsis must contain: date of arrest, crime number, sections, custody period, grounds summary
""",

    # -----------------------------------------------------------------------
    "BailApplication_Anticipatory": """
Draft an Anticipatory Bail Application under Section 438 of the Code of Criminal Procedure, 1973 (or Section 482 BNSS 2023 if applicable) before the Kerala High Court.

STRUCTURE (mandatory, in this order):
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. Case designation: "BAIL APPLICATION No. _____ of _____ "
3. Cause title: Petitioner v State of Kerala
4. Opening line: "PETITION UNDER SECTION 438 OF THE CODE OF CRIMINAL PROCEDURE, 1973 SEEKING ANTICIPATORY BAIL"
5. Description of petitioner
6. Facts:
   - Nature of the apprehension of arrest
   - FIR number/complaint (if registered) — sections invoked
   - If no FIR: basis for apprehension (complaint filed, summons received, etc.)
   - Petitioner's background establishing good faith
7. Grounds (lettered):
   - Apprehension is genuine and imminent
   - Petitioner has not committed the offence alleged
   - Petitioner is a respected member of the community — no flight risk
   - Matter is civil/personal dispute masquerading as criminal complaint (if applicable)
   - No previous criminal record
   - Petitioner will cooperate with investigation
8. Conditions offered (optional, strengthens application):
   - Undertaking to appear for interrogation when called
   - Undertaking not to leave the country without permission
   - Undertaking to surrender passport
9. Prayer:
   "(i) direct that in the event of the arrest of the petitioner in connection with Crime No. ___ / any case arising out of the subject matter, the petitioner be released on bail on such terms and conditions as this Hon'ble Court may deem fit;
   (ii) pass such other orders as this Hon'ble Court may deem fit."

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Article 11(t), Kerala Court Fees & Suits Valuation Act]
- Sessions Court approach: for anticipatory bail, KHC has concurrent jurisdiction — not mandatory to approach Sessions Court first, but state if Sessions Court was already approached
- Attach: copy of FIR (if registered), complaint copy, any summons received
""",

    # -----------------------------------------------------------------------
    "WritPetition_Civil": """
Draft a Writ Petition under Article 226 of the Constitution of India before the Kerala High Court.

STRUCTURE (mandatory, in this order):
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "WRIT PETITION (CIVIL) No. _____ of _____ "
3. Cause title: Petitioner(s) v Respondent(s)
4. "WRIT PETITION FILED UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA SEEKING [state nature of writ: MANDAMUS/CERTIORARI/PROHIBITION/QUO WARRANTO]"
5. Description of petitioner(s): name, age, address, occupation, locus standi
6. Description of respondents: name, designation, office address (Secretary of Department if Government)
7. Statement: "The Petitioner states that no similar petition has been filed before this Hon'ble Court or any other court seeking similar reliefs. / The Petitioner states that WP(C) No. ___ of ___ was filed earlier seeking similar relief and was disposed of/dismissed on ___. [as applicable]"
8. Facts (numbered paragraphs):
   - Background and locus standi
   - Impugned order/action — date, nature, authority
   - Petitioner's representation/appeal to authorities (if any)
   - How fundamental/legal rights are affected
9. Grounds (lettered):
   - Impugned order violates Article __ of Constitution / is without jurisdiction / without hearing / violates principles of natural justice / is arbitrary and violates Article 14 / etc.
   - Each ground must be a separate lettered paragraph
10. Prayer:
    "(i) Issue a Writ of [Mandamus/Certiorari/etc.] or a direction/order in the nature thereof to Respondent No. __ to [specific relief];
    (ii) Quash Exhibit P__ [impugned order] dated __;
    (iii) Pass such other orders as this Hon'ble Court may deem fit."
11. Interim Prayer (if applicable):
    "Pending disposal of the above Writ Petition, it is prayed that this Hon'ble Court may be pleased to stay operation of Exhibit P__ / restrain Respondent No. __ from [action]."
12. Verification paragraph
13. Date, place, signature of petitioner and advocate

MANDATORY NOTES:
- Court fee: Rs.100/- per petitioner [Schedule II Art.11(l)(iii)]
- Heard by Single Judge (unless PIL/Habeas Corpus/Lokayukta/HRC orders — Division Bench)
- Must attach: certified copy of impugned order [Rule 147(1)(b)]
- No limitation prescribed — but explain any delay
- If multiple Government departments as respondents: add State of Kerala represented by Chief Secretary as respondent [Rule 148]
- If Company/Firm files: office seal mandatory
- PIL additional requirements: affidavit under Rule 146A + prior PIL disclosure [Notification D1-71258/2019]
- Documents to exhibit: certified copy of impugned order = P1; subsequent exhibits in sequence
- Composite documents: use P1(a), P1(b) — not "P1 series"
""",

    # -----------------------------------------------------------------------
    "WritPetition_Criminal": """
Draft a Writ Petition (Criminal) under Article 226 of the Constitution of India before the Kerala High Court for Habeas Corpus or criminal relief.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "WRIT PETITION (CRIMINAL) No. _____ of _____ "
3. Cause title
4. "WRIT PETITION FILED UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA FOR [WRIT OF HABEAS CORPUS / RELIEF IN RELATION TO CRIMINAL PROCEEDINGS]"
5. For Habeas Corpus specifically:
   - Name, age, address of the detained person
   - Name and address of detaining authority
   - Date and circumstances of detention
   - Legal basis (or lack thereof) for detention
   - Steps taken to secure release
   - Affidavit by person restrained OR another person stating why restrained cannot file [Rule 160]
6. Facts, Grounds, Prayer as in Civil WP structure
7. For Habeas Corpus prayer: "Direct the Respondent to produce the body of [name] before this Hon'ble Court and release him/her forthwith"

MANDATORY NOTES:
- Court fee: Rs.100/- per petitioner [Schedule II Art.11(l)(iii)]
- Habeas Corpus: MUST be heard by Division Bench [Section 4(5), Kerala HC Act]
- Detenu need NOT be made party respondent in Habeas Corpus
- Application can be presented to Jail Officer if applicant is in jail [Rule 145 proviso]
- W.P.(Crl.) is the correct nomenclature for ALL Article 226 petitions seeking criminal relief [Notice dt.30.09.2021]
""",

    # -----------------------------------------------------------------------
    "WritAppeal": """
Draft a Writ Appeal under Section 5(i) of the Kerala High Court Act, 1958 against the judgment of a Single Judge.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "WRIT APPEAL No. _____ of _____ "
3. Cause title: Appellant(s) v Respondent(s)
4. "APPEAL UNDER SECTION 5(i) OF THE KERALA HIGH COURT ACT, 1958 AGAINST THE JUDGMENT DATED ___ IN W.P.(C/Crl.) No. ___ OF ___"
5. Description of parties
6. Statement of facts (brief — refer to WP proceedings)
7. Grounds of appeal (each a distinct legal ground challenging the Single Judge's finding)
8. Prayer:
   "(i) Set aside the judgment dated ___ of the Hon'ble Single Judge in W.P.__(C/Crl.) No.___ of ___;
   (ii) Allow this Writ Appeal and grant the reliefs sought in the Writ Petition;
   (iii) Pass such other orders as may be deemed fit."
9. Interim prayer for stay of impugned judgment (if applicable)
10. Signature of Advocate (appellant signature not needed — Rule 159)

MANDATORY NOTES:
- Court fee: Rs.200/- per appellant [Schedule II Art.3(iii)(A)(2)(c)]
- Limitation: 30 days from judgment [Article 117, Limitation Act 1963]
- Heard by Division Bench [Section 5, Kerala HC Act]
- Must produce: certified copy of Single Judge judgment + copies of WP, counter affidavits, reply affidavits from WP [Rule 159]
- Advocate who appeared in WP needs only memo of appearance — no fresh vakalath [Rule 159]
- Copy must be served on all who entered appearance in WP
- Cross Objection under Order 41 Rule 22 CPC is NOT maintainable in Writ Appeals [George J v State of Kerala ILR 2019(3) Ker 475 DB]
""",

    # -----------------------------------------------------------------------
    "CriminalAppeal": """
Draft a Criminal Appeal before the Kerala High Court.

Identify applicable provision from brief:
- Sec.374(2) CrPC — against conviction by Sessions Court
- Sec.374(3) CrPC — against conviction by Magistrate
- Sec.377 CrPC — State appeal against inadequate sentence
- Sec.378 CrPC — against acquittal (requires leave)
- Sec.372 CrPC — victim's appeal
- Sec.383 CrPC — appeal by convict in person (no court fee)
- Sec.14A SC/ST Prevention of Atrocities Act — special appeals

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CRIMINAL APPEAL No. _____ of _____ "
3. Cause title: Appellant v State of Kerala / Respondent
4. "APPEAL UNDER SECTION ___ OF THE CODE OF CRIMINAL PROCEDURE, 1973 AGAINST THE JUDGMENT AND ORDER OF CONVICTION/SENTENCE/ACQUITTAL DATED ___ IN [S.C./C.C./Sessions Case] No. ___ of ___ ON THE FILE OF THE [COURT NAME]"
5. Facts:
   - Crime number, police station, sections invoked
   - Brief trial history
   - Impugned judgment: date, conviction/acquittal, sentence (if any)
6. Grounds of appeal (lettered):
   For conviction appeal: perversity of finding, misappreciation of evidence, improper admission/rejection of evidence, procedural irregularity, sentence excessive
   For acquittal appeal: findings contrary to evidence, wrong application of benefit of doubt, etc.
7. Prayer:
   For conviction: "(i) Set aside the judgment of conviction and order of sentence; (ii) Acquit the appellant of the charges; (iii) Release the appellant from custody forthwith."
   For sentence: "(i) Reduce the sentence to [period already undergone / lesser period]"
   For acquittal: "(i) Set aside the order of acquittal; (ii) Convict the accused under Section __ and impose appropriate sentence."
8. Application for suspension of sentence (if accused is in custody):
   "PRAYER FOR SUSPENSION OF SENTENCE AND BAIL PENDING APPEAL"

MANDATORY NOTES:
- Court fee: Rs.10/- for most criminal appeals [Schedule II Art.11(t)]
- State appeal [Sec.377]: NIL — State pays no court fee
- Appeal by convict [Sec.383]: NIL
- Limitation: 30 days from judgment [Article 131, Limitation Act]
- Suspension of sentence: File separate application or include as prayer in appeal
- Heard by Single Judge (except death/life imprisonment — Division Bench)
""",

    # -----------------------------------------------------------------------
    "CriminalRevisionPetition": """
Draft a Criminal Revision Petition under Section 397 read with Section 401 of the Code of Criminal Procedure, 1973 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CRIMINAL REVISION PETITION No. _____ of _____ "
3. Cause title
4. "REVISION PETITION UNDER SECTIONS 397 AND 401 OF THE CODE OF CRIMINAL PROCEDURE, 1973 CHALLENGING THE ORDER DATED ___ IN [CASE TYPE AND NUMBER] ON THE FILE OF [COURT NAME]"
5. Facts:
   - Proceedings in court below
   - Impugned order — date, nature
   - How the order is erroneous in law or results in failure of justice
6. Grounds of revision (lettered):
   - Illegality, impropriety, or irregularity in the order
   - Incorrect application of law
   - Failure of justice
7. Prayer:
   "(i) Call for the records; (ii) Set aside the order dated ___ in [case]; (iii) [Specific direction sought]; (iv) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- Limitation: 90 days from order [Rule 44, KHC Rules]
- Must accompany: certified copy of impugned order + certified copy of judgment it is based on + certified copy of first instance court order [Rule 45]
- Section 482 CrPC petition: must accompany copy of FIR/complaint/charge as certified by advocate [Rule 45A]
""",

    # -----------------------------------------------------------------------
    "CivilRevisionPetition": """
Draft a Civil Revision Petition under Section 115 of the Code of Civil Procedure, 1908 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CIVIL REVISION PETITION No. _____ of _____ "
3. Cause title
4. "REVISION PETITION UNDER SECTION 115 OF THE CODE OF CIVIL PROCEDURE, 1908 AGAINST THE ORDER DATED ___ IN [CASE] ON THE FILE OF [COURT]"
5. Statement of value: "The value of the suit/proceeding giving rise to this Revision is Rs.___. Court fee paid: Rs.___ [Schedule II Art.11(p)(i)/(ii)]"
6. Facts (brief statement as required by Rule 47):
   - Proceedings in court below
   - Impugned order and its nature
7. Grounds of revision:
   - Court below exercised jurisdiction not vested in it, or failed to exercise jurisdiction vested, or acted with material irregularity in exercise of jurisdiction [Section 115 CPC]
8. Prayer

MANDATORY NOTES:
- Court fee: Rs.25/- or Rs.50/- depending on value [Schedule II Art.11(p)(i)(ii)]
- Limitation: 90 days [Rule 44, KHC Rules]
- Must accompany: certified copy of order + certified copy of judgment on which order is based + certified copy of first instance order [Rule 45]
- Memorandum must contain brief statement of facts and grounds [Rule 47]
""",

    # -----------------------------------------------------------------------
    "MatrimonialAppeal": """
Draft a Matrimonial Appeal before the Kerala High Court.

Identify applicable provision:
- Sec.19(1) Family Courts Act — against Family Court orders (Hindu/Special Marriage/Guardians Act/DMMA)
- Sec.28 Hindu Marriage Act — against district court decree in HMA
- Sec.39 Special Marriage Act
- Sec.55 Indian Divorce Act — NIL court fee

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "MATRIMONIAL APPEAL No. _____ of _____ "
3. Cause title: Appellant v Respondent
4. "APPEAL UNDER SECTION ___ OF THE ___ ACT AGAINST THE JUDGMENT/ORDER DATED ___ IN [O.P./M.C.] No. ___ OF ___ ON THE FILE OF THE FAMILY COURT/DISTRICT COURT, [PLACE]"
5. Description of parties and relationship
6. Brief marriage history and subject matter of proceedings below
7. Impugned judgment/order and what it decided
8. Grounds of appeal
9. Prayer

MANDATORY NOTES:
- Court fee: Rs.50/- for Family Courts Act appeals [Sch.II Art.11(l)(iii)] / Rs.25/- for HMA/SMA appeals [Sch.II Art.3(iii)(A)(1)(a)] / NIL for Divorce Act
- Limitation: 30 days from judgment [Art.117 Limitation Act]
- Heard by Single Judge [Sec.3(13), Kerala HC Act]
""",

    # -----------------------------------------------------------------------
    "ContemptPetition_Civil": """
Draft a Contempt Petition (Civil) under Sections 11 and 12 of the Contempt of Courts Act, 1971 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CONTEMPT CASE (CIVIL) No. _____ of _____ "
3. Cause title: Petitioner v Respondent/Contemnor
4. "PETITION UNDER SECTIONS 11 AND 12 OF THE CONTEMPT OF COURTS ACT, 1971 FOR INITIATING CONTEMPT PROCEEDINGS AGAINST RESPONDENT FOR WILFUL DISOBEDIENCE OF THE ORDER/JUDGMENT DATED ___ IN [CASE NUMBER]"
5. Facts:
   - The order/judgment disobeyed — date, court, case number
   - What the order directed
   - Steps taken by petitioner to comply / communicate
   - How respondent wilfully disobeyed the order
   - Efforts to bring compliance before filing contempt
6. Grounds:
   - Wilful disobedience of a clear and unambiguous order
   - Respondent had knowledge of the order
   - No justification for non-compliance
7. Prayer:
   "(i) Initiate contempt proceedings against the Respondent; (ii) Punish the Respondent for wilful disobedience; (iii) Direct the Respondent to comply with the order dated ___ forthwith; (iv) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Court fee: Rs.100/- [Schedule II Art.11(l)(iv)]
- Limitation: 1 year from date of disobedience [Section 20, Contempt of Courts Act]
- Heard by Single Judge (civil contempt)
- Attach: certified copy of the order alleged to have been disobeyed
""",

    # -----------------------------------------------------------------------
    "OriginalPetition_Civil": """
Draft an Original Petition (Civil) under Article 227 of the Constitution of India before the Kerala High Court challenging an order of a civil court or tribunal.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "ORIGINAL PETITION (CIVIL) No. _____ of _____ " [O.P.(Cvl)]
3. Cause title
4. "PETITION UNDER ARTICLE 227 OF THE CONSTITUTION OF INDIA CHALLENGING THE ORDER DATED ___ IN [CASE] ON THE FILE OF [COURT/TRIBUNAL]"
5. Facts and impugned order
6. Grounds (jurisdictional excess, material irregularity, failure of justice)
7. Prayer

MANDATORY NOTES:
- Court fee: Rs.100/- per petitioner [Schedule II Art.11(l)(iii)]
- No prescribed limitation — file without unreasonable delay; explain any delay
- Heard by Single Judge [Sec.3(4), Kerala HC Act]
- Writ Appeal does NOT lie against O.P.(Cvl) judgment [John V.O. v Catholic Syrian Bank ILR 2009(1) Ker 596 DB]
- Must attach certified copy of impugned order [Direction of Justice V.Chitambaresh dt.26.06.2012]
- Documents to produce: copy of order impugned; copy of IA order if IA order is challenged
""",

    # -----------------------------------------------------------------------
    "Vakalatnama": """
Draft a Vakalatnama (Vakalath) for filing before the Kerala High Court.

STRUCTURE:
Use Form No.1 of the Rules of the High Court of Kerala, 1971.

1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. Case number and year (or "W.P.(C) No. _____ of _____" etc.)
3. Cause title
4. "VAKALATH"
5. Body:
   "I/We, [client name(s)], [Petitioner/Respondent/Appellant] in the above case, do hereby appoint and retain [Advocate name(s)], Advocate(s) enrolled with the Bar Council of Kerala, to appear and act on my/our behalf in the above case and in all matters connected therewith including [list: applications, interlocutory proceedings, execution proceedings, appeals to Division Bench, applications for leave to appeal to Supreme Court, etc. — as appropriate]."
6. Date of execution
7. Signature of client(s)
8. Attestation block:
   "Attested: [Signature and name of attesting authority — Judicial Officer / Advocate / Gazetted Officer etc.]
   Designation:
   Date:
   Place:"
9. Acceptance endorsement:
   "I, [Advocate name], do hereby accept the above Vakalath.
   Address for service: [Advocate's address]
   Telephone / Mobile: [number]
   E-mail ID: [email]
   Date:
   Signature of Advocate"
10. Form No.1A details (separate sheet if filed with vakalath):
    - Advocate's telephone, mobile, email
    - Client's telephone, mobile, email

STAMPS (mandatory — affix before filing):
- Court Fee Stamp: Rs.10/- [Schedule II Art.16(iii), Kerala Court Fees & Suits Valuation Act]
- Advocates Welfare Fund Stamp: Rs.50/- [Section 23, Kerala Advocates' Welfare Fund Act, 1980]
- Advocates' Clerks Welfare Fund Stamp: Rs.12/- [Section 14, Kerala Advocates' Clerks Welfare Fund Act, 2003]
Total stamps: Rs.72/-

MANDATORY NOTES:
- If executed by firm/company/partnership/trust/LSG institution: office seal must be affixed
- If executed by person in custody: authenticated by Jailor/SHO [Rule 19(3)]
- At least one witness required [Rule 19(4)]
- Registered clerk signing as witness: must affix full signature + name + registration number
- Separate vakalath required for each connected case even with same advocate [Rule 21]
- If advocate already on record appointing another advocate for hearing: no fresh vakalath needed
- Memorandum of appearance (not vakalath) if: (a) advocate appearing for accused in criminal case, (b) Central/State Government advocate [Rule 17]
""",

    # -----------------------------------------------------------------------
    "InterlocutoryApplication": """
Draft an Interlocutory Application (I.A.) for filing in a pending matter before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. Main case details: "[Case type] No. _____ of _____ "
3. "INTERLOCUTORY APPLICATION No. _____ OF _____ "
4. Cause title
5. "APPLICATION UNDER [Rule 154 of the Rules of the High Court of Kerala, 1971 / Order ___ Rule ___ CPC / Section ___ of the Act] FOR [state relief: production of additional documents / stay / impleadment / amendment / etc.]"
6. Affidavit in support (same document):
   "I, [name], [description], do hereby solemnly affirm and state as follows:"
   - Numbered paragraphs
   - Facts supporting the application
   - Verification paragraph at end
7. Prayer:
   "(i) Allow this Interlocutory Application; (ii) [Specific relief]; (iii) Pass such other orders as may be deemed fit."

COURT FEE:
- If application is for arrest/attachment before judgment or temporary injunction: Rs.25/- [Schedule II Art.11(h)(ii)]
- All other IAs: Rs.10/- [Schedule II Art.11(t)]

MANDATORY NOTES:
- Every IA must be supported by a separate affidavit sworn by the party [Rule 84 + Sadanandan Nair v Sree Perumanpura Devaswom 2017 KHC 4856]
- Additional documents to be produced in a pending WP: file IA under Rule 154 with affidavit [Kunjalavi Chellamma v District Geologist 2016(4) KLT 293]
- IA must NOT state "as directed by Court" unless there was a specific court direction
- Place IA immediately before bottom covering sheet of main proceedings, flagged "IA No.___"
""",

    # -----------------------------------------------------------------------
    "RegularFirstAppeal": """
Draft a Regular First Appeal under Section 96 read with Order XLI of the Code of Civil Procedure, 1908 before the Kerala High Court.

STRUCTURE (mandatory, in this order):
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "REGULAR FIRST APPEAL No. _____ of _____ "
3. Cause title: Appellant(s) v Respondent(s)
4. "APPEAL UNDER SECTION 96 READ WITH ORDER XLI OF THE CODE OF CIVIL PROCEDURE, 1908 AGAINST THE JUDGMENT AND DECREE DATED ___ IN O.S./[CASE TYPE] No. ___ OF ___ ON THE FILE OF THE [COURT NAME], [PLACE]"
5. Statement of value:
   "The value of the suit giving rise to this appeal is Rs.___.
   The value of the subject matter of this appeal is Rs.___.
   Court fee paid: Ad valorem on Rs.___ [Schedule I Article 1, Kerala Court Fees & Suits Valuation Act, 1959]."
6. Statement of facts (Rule 47 — brief statement required):
   - Nature of suit in trial court
   - Parties and relationship
   - What was decided in the impugned judgment and decree
7. Grounds of appeal (lettered):
   - Trial court misappreciated the evidence
   - Finding of fact is perverse / against the weight of evidence
   - Incorrect application of law
   - Relevant evidence wrongly rejected / irrelevant evidence wrongly admitted
   - Each ground must be a distinct lettered paragraph
   - For R.S.A.: must frame substantial question of law [Section 100(3) CPC]
8. Prayer:
   "(i) Set aside the judgment and decree dated ___ in [case] on the file of [court];
   (ii) Decree the suit as prayed for / dismiss the suit / pass a decree for Rs.___;
   (iii) Award costs throughout;
   (iv) Pass such other orders as may be deemed fit."
9. Interim prayer for stay of execution of decree (if applicable)
10. Date, place, signature of advocate

MANDATORY NOTES:
- Court fee: Ad valorem [Schedule I Article 1, Kerala Court Fees & Suits Valuation Act]
- Limitation: 90 days from decree [Article 116(a), Limitation Act 1963]
- Pecuniary jurisdiction: Single Judge if subject matter ≤ Rs.40 lakhs; Division Bench if above [Sec.3(13)(b) and Sec.4(2)(a) Kerala HC Act, as amended 2018]
- Must attach: certified copy of judgment AND decree [Rule 41(a), KHC Rules]
- For R.S.A. (second appeal): must state substantial question of law in memorandum [Section 100(3) CPC]; certified copy of first appellate court judgment also required
- Copies required: one per respondent + 2 for Court + 2 extra if State is respondent [Rule 41(d)]
- If filed after limitation: accompany with C.M.Application under Section 5 Limitation Act [Rule 42]
- Impleading legal heirs: application within 90 days of death [Article 120 Limitation Act]; after abatement — application to set aside within 60 days [Article 121]
- Documents if any: to be produced under Order 41 Rule 27 CPC, not as annexures to memorandum
""",

    # -----------------------------------------------------------------------
    "RegularSecondAppeal": """
Draft a Regular Second Appeal under Section 100 read with Order XLII of the Code of Civil Procedure, 1908 before the Kerala High Court.

STRUCTURE: Same as Regular First Appeal with these differences:
1. "REGULAR SECOND APPEAL No. _____ of _____ "
2. Provision: "SECTION 100 READ WITH ORDER XLII OF THE CODE OF CIVIL PROCEDURE, 1908"
3. MANDATORY: Substantial Question of Law must be stated prominently:
   "SUBSTANTIAL QUESTION OF LAW:
   Whether [state question precisely]?"
4. Facts must trace through both trial court and first appellate court proceedings
5. Grounds must address the substantial question of law only — no re-appreciation of facts

MANDATORY NOTES:
- Court fee: Ad valorem [Schedule I Article 1]
- Limitation: 90 days from first appellate decree [Article 116(a), Limitation Act 1963]
- Heard by Single Judge if subject matter ≤ Rs.40 lakhs; Division Bench if above
- Must attach: certified copy of first appellate judgment AND trial court judgment [filing note, Chapter XIV]
- No second appeal on facts — only on substantial question of law [Section 100(1) CPC]
- No further appeal from Single Judge's order in R.S.A. [Section 100A CPC]
""",

    # -----------------------------------------------------------------------
    "CriminalMiscCase": """
Draft a Criminal Miscellaneous Case (Crl.M.C.) under Section 482 of the Code of Criminal Procedure, 1973 before the Kerala High Court, invoking the inherent powers of the Court.

STRUCTURE (mandatory, in this order):
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CRIMINAL MISCELLANEOUS CASE No. _____ of _____ "
3. Cause title: Petitioner v State of Kerala / Respondent(s)
4. "PETITION UNDER SECTION 482 OF THE CODE OF CRIMINAL PROCEDURE, 1973 TO [state relief: QUASH FIR/CHARGE SHEET/PROCEEDINGS/ORDER / STAY PROCEEDINGS / DIRECT INVESTIGATION]"
5. Description of petitioner
6. Facts (numbered paragraphs):
   - Nature of complaint/FIR/proceedings sought to be quashed
   - Crime number, police station, sections invoked (if FIR)
   - Case number in trial court (if proceedings)
   - How the FIR/proceedings are an abuse of process / frivolous / vexatious / civil dispute dressed as criminal complaint / filed to harass
   - Steps taken at the trial court level
7. Grounds (lettered):
   - No cognizable offence made out on the face of the FIR/complaint
   - Proceedings are abuse of process of court
   - Matter is essentially civil in nature
   - Complaint is filed to wreak vengeance / harassment
   - No prima facie case / ingredients of offence not made out
   - Parties have settled / compromise reached (if applicable)
   - Specific legal ground based on facts
8. Prayer:
   "(i) Call for the records of Crime No.___ / [Case] No.___ of ___ on the file of [court/PS];
   (ii) Quash [the FIR / charge sheet / proceedings / order] dated ___ in [case];
   (iii) Pending disposal, stay further proceedings in [case] on the file of [court];
   (iv) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t), Kerala Court Fees & Suits Valuation Act]
- Limitation: No prescribed period — but should be filed promptly after the impugned proceedings
- Must accompany petition: copy of FIR / complaint / charge sheet / impugned order certified as true by advocate [Rule 45A, KHC Rules] — "proceeding" includes complaint, FIR, charge, or order
- Heard by Single Judge
- Interim stay of proceedings is standard interim prayer — critical to seek it at admission stage
- If settlement: file compromise/settlement deed as exhibit; parties' joint affidavit affirming settlement strengthens application
""",

    # -----------------------------------------------------------------------
    "CriminalLeavePetition": """
Draft a Criminal Leave Petition under Section 378 of the Code of Criminal Procedure, 1973 seeking leave to appeal against an order of acquittal.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CRIMINAL LEAVE PETITION No. _____ of _____ "
3. Cause title: State of Kerala / Complainant/Victim v Accused
4. "PETITION FOR LEAVE TO APPEAL UNDER SECTION 378 OF THE CODE OF CRIMINAL PROCEDURE, 1973 AGAINST THE JUDGMENT OF ACQUITTAL DATED ___ IN [CASE] No. ___ OF ___ ON THE FILE OF [COURT]"
5. Facts:
   - Crime number, offence, accused details
   - Brief trial history
   - Impugned judgment of acquittal — date, findings, reasons given by trial court
   - How the acquittal is perverse / against evidence
6. Grounds for grant of leave:
   - Findings are perverse and against the weight of evidence
   - Trial court failed to properly appreciate the evidence of [key witnesses]
   - Evidence of PW___ / Exhibit ___ wrongly discarded
   - Wrong application of benefit of doubt
   - Trial court ignored important circumstances
7. Prayer:
   "(i) Grant leave to appeal against the judgment of acquittal dated ___ in [case];
   (ii) On leave being granted, set aside the order of acquittal and convict the accused under Section ___ and impose appropriate sentence;
   (iii) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- Limitation: 90 days from acquittal [Article 114 / 131 Limitation Act 1963]
- This is a TWO-STEP process: (1) leave petition — if leave granted, (2) separate Criminal Appeal is filed
- Private complainant / victim filing under Sec.378(4): needs special leave from HC — state "as a private complainant"
- State filing under Sec.378(1): filed by Public Prosecutor on behalf of State
- Heard by Single Judge (except death/life imprisonment matters — Division Bench)
""",

    # -----------------------------------------------------------------------
    "CriminalAppeal_Victim": """
Draft a Criminal Appeal (Victim) under Section 372 of the Code of Criminal Procedure, 1973 — appeal by victim against acquittal, conviction for lesser offence, or inadequate sentence.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CRIMINAL APPEAL (VICTIM) No. _____ of _____ " [Crl.A.(V)]
3. Cause title: Appellant (Victim) v State of Kerala & Accused
4. "APPEAL UNDER SECTION 372 OF THE CODE OF CRIMINAL PROCEDURE, 1973 BY THE VICTIM AGAINST [ACQUITTAL / CONVICTION FOR LESSER OFFENCE / INADEQUATE SENTENCE] IN [CASE] No. ___ OF ___ ON THE FILE OF [COURT]"
5. Description of appellant as victim: relationship to matter, how affected
6. Facts:
   - Nature of offence, accused, trial history
   - Impugned order/judgment — what it decided
   - How victim is aggrieved (acquittal / lesser charge / inadequate sentence)
7. Grounds
8. Prayer:
   For acquittal: "(i) Set aside the acquittal; (ii) Convict the accused under Section ___"
   For lesser offence: "(i) Set aside conviction under Section ___; (ii) Convict under Section ___"
   For sentence: "(i) Enhance the sentence to [imprisonment for ___ years / life]"

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- Limitation: 90 days from judgment [Article 131 Limitation Act]
- Section 372 CrPC (proviso) gives victim right to appeal without requiring leave — distinct from Section 378
- Victim must establish locus standi in the appeal memorandum
- Heard by Single Judge (except death/life imprisonment — Division Bench)
""",

    # -----------------------------------------------------------------------
    "MotorAccidentClaimsAppeal": """
Draft a Motor Accident Claims Appeal (M.A.C.A.) under Section 173 of the Motor Vehicles Act, 1988 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "MOTOR ACCIDENT CLAIMS APPEAL No. _____ of _____ " [M.A.C.A.]
3. Cause title: Appellant(s) v Respondent(s)
4. "APPEAL UNDER SECTION 173 OF THE MOTOR VEHICLES ACT, 1988 AGAINST THE AWARD/ORDER DATED ___ IN M.A.C.T. PETITION No. ___ OF ___ ON THE FILE OF THE MOTOR ACCIDENTS CLAIMS TRIBUNAL, [PLACE]"
5. Statement of court fee:
   "Court fee paid: 2% of the excess amount of Rs.___ (amount claimed Rs.___ minus amount awarded Rs.___) = Rs.___, subject to minimum of Rs.1000/-.
   [OR: Rs.1000/- flat as this appeal is filed to reduce the awarded amount / strike down the order]
   [Rule 397(3) Kerala Motor Vehicles Rules]"
6. Facts:
   - Accident details: date, place, vehicle numbers, nature of accident
   - Claimant details: age, occupation, income, relationship (if death case)
   - MACT petition number, Tribunal, date of award
   - Award amount and how it was calculated by Tribunal
   - Why award is inadequate / excessive / erroneous in law
7. Grounds:
   For enhancement: Tribunal erred in — (a) assessing monthly income, (b) applying wrong multiplier, (c) not awarding [head of claim], (d) deducting personal expenses wrongly, etc.
   For reduction: Award is excessive / based on wrong assumptions / claimant partly negligent
   For insurer: Driving licence / permit / insurance policy not verified properly / policy was not in force
8. Prayer
9. Interim prayer for stay of award / recovery (if insurer is appellant)

MANDATORY NOTES:
- Court fee: 2% of excess amount claimed over awarded, minimum Rs.1000/- [Rule 397(3) Kerala Motor Vehicles Rules, w.e.f. 16.1.2015]; if appeal is to REDUCE or STRIKE DOWN the award: flat Rs.1000/-
- Limitation: 90 days from award [Article 116(a) Limitation Act]
- Heard by Single Judge [Section 3(13)(h) Kerala HC Act]
- Challenge to non-award orders (e.g., restoration refusal): file O.P.(MAC) under Article 227, not MACA [Judgment dt.9.9.2013 in M.A.C.A.1485/2013]
- Must attach: certified copy of award
""",

    # -----------------------------------------------------------------------
    "TransferPetition_Civil": """
Draft a Transfer Petition (Civil) under Section 24 of the Code of Civil Procedure, 1908 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "TRANSFER PETITION (CIVIL) No. _____ of _____ " [Tr.P.(C)]
3. Cause title: Petitioner v Respondent(s)
4. "PETITION UNDER SECTION 24 OF THE CODE OF CIVIL PROCEDURE, 1908 FOR TRANSFER OF [CASE TYPE AND NUMBER] FROM THE [COURT NAME, PLACE] TO [COURT NAME, PLACE / ANY COMPETENT COURT]"
5. Facts:
   - Nature and subject matter of the case to be transferred
   - Present court where it is pending, case number, stage
   - Proposed court for transfer
   - Reasons for transfer:
     - Convenience of parties / witnesses
     - Related matter pending at proposed court
     - Apprehension of not getting fair trial
     - Both parties reside nearer to proposed court
     - All connected cases pending at proposed court
6. Grounds
7. Prayer:
   "(i) Transfer [Case Type] No.___ of ___ from the [Court] to [Court/any competent Court];
   (ii) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Court fee: Rs.100/- per petitioner [Schedule II Art.11(l)(iii)]
- No limitation prescribed
- Heard by Single Judge [Section 3(4), Kerala HC Act]
- Documents produced along with Tr.P.(C): to be marked as ANNEXURES not as Exhibits [note under Tr.P.(C), Chapter XIV compendium]
- Multiple transfer petitions: one O.P. suffices; file IAs for each additional transfer [Dhanu Joby v Joby Cherian 2016(1) KLT 696 DB]
- Transfer of MACT petitions: exercise powers under Rule 374 Kerala Motor Vehicles Rules [United India Insurance v Prasanth ILR 2018(3) Ker 488]
""",

    # -----------------------------------------------------------------------
    "TransferPetition_Criminal": """
Draft a Transfer Petition (Criminal) under Section 407 of the Code of Criminal Procedure, 1973 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "TRANSFER PETITION (CRIMINAL) No. _____ of _____ " [Tr.P.(Crl.)]
3. Cause title: Petitioner v State of Kerala / Respondent(s)
4. "PETITION UNDER SECTION 407 OF THE CODE OF CRIMINAL PROCEDURE, 1973 FOR TRANSFER OF [CASE] No. ___ OF ___ FROM THE [COURT, PLACE] TO [COURT/ANY COMPETENT COURT]"
5. Facts:
   - Nature of criminal case, offence, parties
   - Present court, case number, stage of proceedings
   - Reasons for transfer: fair trial apprehension, accused and witnesses not getting fair hearing, convenience, related cases elsewhere, media attention, threats
6. Grounds
7. Prior notice: "It is stated that 24 hours' notice has been given to the State Prosecutor as required [Rule 173, KHC Rules]"
8. Prayer

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- Limitation: No prescribed limitation
- MUST give 24 hours' prior notice to State Prosecutor before moving [Rule 173, KHC Rules]
- Heard by Single Judge
""",

    # -----------------------------------------------------------------------
    "RevisionPetition_FamilyCourt": """
Draft a Revision Petition (Family Court) under Section 19(4) of the Family Courts Act, 1984 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "REVISION PETITION (FAMILY COURT) No. _____ of _____ " [R.P.(FC)]
3. Cause title: Petitioner v Respondent
4. "REVISION PETITION UNDER SECTION 19(4) OF THE FAMILY COURTS ACT, 1984 CHALLENGING THE INTERLOCUTORY ORDER DATED ___ IN [O.P./M.C.] No. ___ OF ___ ON THE FILE OF THE FAMILY COURT, [PLACE]"
5. Facts:
   - Nature of proceedings in Family Court
   - Impugned interlocutory order — what it decided, date
   - How the order is erroneous in law / causes irreparable harm
6. Grounds of revision
7. Prayer:
   "(i) Call for records; (ii) Set aside order dated ___; (iii) [Specific relief]; (iv) Stay operation of impugned order pending revision"

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- Limitation: 90 days [Rule 44, KHC Rules]
- Section 19(4) Family Courts Act: revision lies only against interlocutory orders of Family Court — final orders go by way of Matrimonial Appeal under Section 19(1)
- Heard by Single Judge
- Must attach certified copy of impugned order
""",

    # -----------------------------------------------------------------------
    "MatrimonialAppeal_Execution": """
Draft a Matrimonial Appeal (Execution) under Section 19(1) of the Family Courts Act, 1984 challenging an execution order of a Family Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "MATRIMONIAL APPEAL (EXECUTION) No. _____ of _____ "
3. Cause title
4. "APPEAL UNDER SECTION 19(1) OF THE FAMILY COURTS ACT, 1984 READ WITH ORDER XXI OF THE CODE OF CIVIL PROCEDURE, 1908 AGAINST THE ORDER DATED ___ IN E.P. No. ___ OF ___ IN [O.P./M.C.] No. ___ OF ___ ON THE FILE OF THE FAMILY COURT, [PLACE]"
5. Facts:
   - Original decree / order sought to be executed — nature, date
   - Execution petition number and what was sought
   - Impugned order in execution proceedings
   - How the execution order is erroneous
6. Grounds, Prayer

MANDATORY NOTES:
- Court fee: Rs.25/- or Rs.10/- depending on value [Schedule II Art.3(iii)(A)(1)(a)(b)]
- Limitation: 90 days [Article 116(a) Limitation Act]
- Heard by Single Judge
""",

    # -----------------------------------------------------------------------
    "Caveat": """
Draft a Caveat (Original Petition) under Section 148A of the Code of Civil Procedure, 1908 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CAVEAT (ORIGINAL PETITION)"
3. Cause title (anticipated): [Name of anticipated petitioner] v [Caveator's name]
4. "CAVEAT UNDER SECTION 148A OF THE CODE OF CIVIL PROCEDURE, 1908"
5. Body:
   "I/We, [caveator's name], [description/address], respectfully submit this Caveat and state as follows:
   1. The Caveator apprehends that [name of anticipated petitioner] is likely to file a Writ Petition / Original Petition / Appeal / any proceeding before this Hon'ble Court in connection with [subject matter].
   2. The Caveator claims a right to appear before this Hon'ble Court at the hearing of any such application.
   3. The Caveator has served a copy of this Caveat on [name of anticipated petitioner] by registered post with acknowledgment due vide Postal Receipt No.___ dated ___ [attach postal receipt].
   4. The Caveator requests that no order be made in any such application without notice to the Caveator."
6. Prayer:
   "This Hon'ble Court may be pleased to direct that no ex parte order be made in any application that may be filed by [anticipated petitioner] in connection with [subject matter] without hearing the Caveator."
7. Date, place, signature of caveator / advocate

MANDATORY NOTES:
- Court fee: Rs.50/- [Schedule II Art.18, Kerala Court Fees & Suits Valuation Act]
- Validity: 90 days from date of filing [Section 148A(5) CPC]
- MUST attach: postal receipt showing copy of caveat sent to anticipated petitioner [Rule under Caveat(O.P.), Chapter XIV compendium]
- Vakalath to be filed along with Caveat
- Separate Caveat to be filed for each anticipated case
- NOT maintainable in Article 226 or 227 proceedings [Harikrishnan v Jacob ILR 2005(2) Ker 547; Baby v A.P.Jose ILR 2012(3) Ker 795]
- NOT maintainable on criminal side [Rosy v Denny]
""",

    # -----------------------------------------------------------------------
    "ReviewPetition": """
Draft a Review Petition under Order 47 Rule 1 of the Code of Civil Procedure, 1908 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "REVIEW PETITION No. _____ of _____ " [R.P.]
3. Cause title: Petitioner v Respondent(s)
4. "PETITION FOR REVIEW UNDER ORDER 47 RULE 1 OF THE CODE OF CIVIL PROCEDURE, 1908 OF THE JUDGMENT/ORDER DATED ___ IN [CASE TYPE] No. ___ OF ___"
5. Statement of court fee:
   "Court fee paid: ½ of the fee payable on the plaint/memorandum of appeal comprising the relief sought = Rs.___ [Schedule I Article 5, Kerala Court Fees & Suits Valuation Act]"
6. Grounds for review (must fall within Section 114 CPC / Order 47 Rule 1 grounds):
   - Discovery of new and important matter which could not be produced at the time of the judgment despite due diligence
   - Mistake or error apparent on the face of the record
   - Any other sufficient reason
   NOTE: Review is not a re-hearing or second appeal — grounds must be strictly within Order 47 Rule 1
7. Facts limited to: what the judgment held, what was missed / what error is apparent
8. Prayer:
   "(i) Review the judgment/order dated ___ in [case];
   (ii) On review, [state corrected relief];
   (iii) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Court fee: ½ of fee on plaint/appeal [Schedule I Article 5]
- Limitation: 30 days from judgment [Article 124 Limitation Act]
- Filed to the SAME bench/judge who passed the order
- Heard by Single Judge (for Single Judge orders) or Division Bench (for Division Bench orders)
- Review is not an appeal — cannot urge grounds that were argued and rejected at original hearing
- An indigent person allowed to appeal as pauper need not pay court fee on review [Mathai Brijitha v Thankappan Nair ILR 1993(1) Ker 306 DB]
""",

    # -----------------------------------------------------------------------
    "CivilMiscApplication": """
Draft a Civil Miscellaneous Application (C.M.Appl.) under Section 5 of the Limitation Act, 1963 for condonation of delay in filing a petition/appeal before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "CIVIL MISCELLANEOUS APPLICATION No. _____ of _____ IN [CASE TYPE] No. _____ of _____ "
3. Cause title (same as main matter)
4. "APPLICATION UNDER SECTION 5 OF THE LIMITATION ACT, 1963 FOR CONDONATION OF DELAY OF ___ DAYS IN FILING THE [PETITION/APPEAL/REVISION]"
5. Affidavit by petitioner/appellant:
   "I, [name], [description], do hereby solemnly affirm and state as follows:
   1. I am the petitioner/appellant in the above matter.
   2. The impugned order/judgment was passed on ___. The prescribed period of limitation expired on ___. The [petition/appeal] has been filed on ___, resulting in a delay of ___ days.
   3. The delay was caused due to the following reasons: [state each reason in a numbered paragraph]
   4. The delay was not intentional or deliberate and was caused due to [unavoidable circumstances / illness / non-availability of documents / failure of counsel to communicate / etc.]
   5. The petitioner/appellant has a good case on merits as will be evident from the accompanying petition/appeal.
   6. No prejudice will be caused to the respondents if the delay is condoned."
6. Prayer:
   "This Hon'ble Court may be pleased to condone the delay of ___ days in filing the [petition/appeal] and admit the same."
7. Verification paragraph

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- Must be filed along with the main petition/appeal — not as a separate proceeding
- Every delayed petition/appeal must be accompanied by this application [Rule 42, KHC Rules]
- Copies required: equal to number of respondents + 2 for Court [Rule 42]
- State EACH DAY of delay — vague explanations are rejected
""",

    # -----------------------------------------------------------------------
    "CompoundingPetition": """
Draft a Compounding Petition under Section 320 of the Code of Criminal Procedure, 1973 (or Section 147 of the Negotiable Instruments Act, 1881 for cheque dishonour cases) before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "COMPOUNDING PETITION No. _____ of _____ IN [Crl.A./Crl.M.C./Crl.R.P.] No. _____ of _____ "
3. Cause title
4. "JOINT PETITION FOR COMPOUNDING OF OFFENCE UNDER SECTION ___ OF THE CODE OF CRIMINAL PROCEDURE, 1973 / SECTION 147 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881"
5. Joint averments by complainant and accused:
   "We, (1) [Complainant name], the complainant, and (2) [Accused name], the accused, in the above matter, do hereby jointly submit as follows:
   1. The above matter arises out of [nature of offence / crime number].
   2. The parties have amicably settled their dispute. The accused has paid/agreed to pay Rs.___ to the complainant as full and final settlement.
   3. The complainant has no objection to the accused being acquitted.
   4. The offence in question is compoundable under Section 320 CrPC / Section 147 NI Act.
   5. The compromise has been arrived at voluntarily without any coercion."
6. Prayer:
   "(i) Accept the compromise and permit compounding of the offence;
   (ii) Acquit the accused of the charge under Section ___;
   (iii) Pass such other orders as may be deemed fit."
7. Signatures of both complainant and accused and their respective advocates

MANDATORY NOTES:
- Court fee: Rs.10/- [Schedule II Art.11(t)]
- For NI Act Sec.138 cases: Section 147 NI Act allows compounding at any stage including appellate stage
- For Section 320 CrPC: offence must be listed in the compoundable offences table — check if it is compoundable with or without court permission
- Cheque dishonour settlement: attach the settlement agreement / receipt showing payment as exhibit
- Both parties must appear / file affidavits confirming voluntary settlement
- Filed in the pending matter (appeal/revision/Crl.M.C.) — not as standalone petition
""",

    # -----------------------------------------------------------------------
    "ArbitrationRequest": """
Draft an Arbitration Request (Arb.R.) under Section 11 of the Arbitration and Conciliation Act, 1996 before the Kerala High Court for appointment of arbitrator.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "ARBITRATION REQUEST No. _____ of _____ " [Arb.R.]
3. Cause title: Petitioner v Respondent
4. "APPLICATION UNDER SECTION 11(6) OF THE ARBITRATION AND CONCILIATION ACT, 1996 READ WITH RULE 4(b) OF THE KERALA ARBITRATION AND CONCILIATION (COURT) RULES, 1997 FOR APPOINTMENT OF ARBITRATOR"
5. Processing cost:
   "A Demand Draft for Rs.250/- payable at Kochi drawn in favour of 'Registrar, High Court of Kerala' is enclosed as costs for processing [Scheme for Appointment of Arbitrators by Chief Justice, KHC 1996, Para 12]"
6. Facts:
   - Agreement between parties containing arbitration clause — date, parties, subject matter
   - Dispute arose on ___ regarding ___
   - Request to other party to appoint arbitrator — date, mode of communication
   - Other party failed to appoint within 30 days of request / parties failed to agree on arbitrator [Section 11(4) A&C Act]
   - Arbitration clause: quote or attach as exhibit
7. Grounds:
   - Valid arbitration agreement exists
   - Dispute falls within scope of arbitration agreement
   - Respondent failed to appoint arbitrator within 30 days despite request
   - Court has jurisdiction under Section 11(6) to appoint arbitrator
8. Prayer:
   "(i) Appoint a sole arbitrator / presiding arbitrator to adjudicate the disputes between the parties;
   (ii) Pass such other orders as may be deemed fit."

MANDATORY NOTES:
- Processing cost: Rs.250/- DD in favour of Registrar, High Court of Kerala [Para 12, Scheme for Appointment of Arbitrators 1996]
- Limitation: Article 137 Limitation Act — 3 years from when right to apply arises (date of failure to appoint)
- Heard by Single Judge
- For international commercial arbitration: apply to the designated arbitral institution [Section 11(6A)]
- Must attach: arbitration agreement / contract containing arbitration clause; correspondence requesting appointment
""",

    # -----------------------------------------------------------------------
    "ArbitrationAppeal": """
Draft an Arbitration Appeal (Arb.A.) under Section 37 of the Arbitration and Conciliation Act, 1996 before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "ARBITRATION APPEAL No. _____ of _____ " [Arb.A.]
3. Cause title: Appellant v Respondent
4. "APPEAL UNDER SECTION 37 OF THE ARBITRATION AND CONCILIATION ACT, 1996 AGAINST THE ORDER DATED ___ IN [ARBITRATION CASE / O.P.] No. ___ OF ___ ON THE FILE OF [COURT / ARBITRAL TRIBUNAL]"
5. Court fee statement:
   "Court fee paid: [state applicable slab under Schedule II Art.11(m) or Art.4 depending on date and nature of order]"
6. Facts:
   - Arbitration proceedings history
   - Nature of the order appealed against [Section 37 lists: refusal of reference, grant/refusal of interim measure Sec.9, setting aside/refusing to set aside award Sec.34]
   - Impugned order — date, findings, reasons
7. Grounds of appeal
8. Prayer

COURT FEE (critical — depends on date and order type):
- For awards/orders ON OR AFTER 01.04.2013: Schedule II Article 4, Kerala CF Act (as amended by Finance Act 2013)
  - If value ≤ Rs.1 lakh: Rs.2/- per Rs.100/-
  - If value > Rs.1 lakh upto Rs.5 lakhs: Rs.4/- per Rs.100/- on excess
  - If value > Rs.5 lakhs: Rs.1/- per Rs.100/- on excess
- For appeals from Section 9 interim orders: Schedule II Art.3(iii)(A)(1)(a) — Rs.25/- [Sundaram Finance v Radhamma 2003(3) KLT 289]
- Refer: Alex M George v Special Deputy Collector 2018(2) KLT 127 FB; Asya v Sundaram Finance 2016(3) KLT 195

MANDATORY NOTES:
- Limitation: 90 days for non-commercial matters [Article 116(a) Limitation Act]; 60 days if aggregate claim ≥ Rs.3 lakhs under Commercial Courts Act [Section 13 Commercial Courts Act]
- No second appeal [Section 37(3) A&C Act]
- Order refusing to condone delay in Section 34 application is appealable under Section 37(1)(c) [Chintels India v Bhayana Builders 2021(4) SCC 602]
""",

}


# ===========================================================================
# HELPER FUNCTION
# ===========================================================================

def get_drafting_prompt(doc_type: str) -> str:
    """
    Return the drafting prompt for the given docType.

    Tier 1 types return a full custom prompt.
    Tier 2 types return a context-aware generic prompt with the correct
    court fee, limitation, and bench type looked up from the registry.
    Unknown types fall back to a fully generic prompt.

    Args:
        doc_type: One of the DraftType constant values

    Returns:
        Drafting instructions string to inject into the generation call
    """
    if doc_type in DRAFTING_PROMPTS:
        return DRAFTING_PROMPTS[doc_type]

    # Tier 2 lookup — known types with metadata but no custom prompt
    TIER_2_METADATA: dict[str, dict] = {
        # Article 227 O.P. variants — all structurally identical to O.P.(Civil)
        "OriginalPetition_Criminal":    {"abbr": "O.P.(Crl.)",  "bench": "Single Judge",   "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit — file without unreasonable delay"},
        "OriginalPetition_CAT":         {"abbr": "O.P.(CAT)",   "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_KAT":         {"abbr": "O.P.(KAT)",   "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_DRT":         {"abbr": "O.P.(DRT)",   "bench": "Single Judge",   "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_FamilyCourt": {"abbr": "O.P.(FC)",    "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_ForestTribunal":{"abbr":"O.P.(FT)",   "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_LabourCourt": {"abbr": "O.P.(LC)",    "bench": "Single Judge",   "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_MAC":         {"abbr": "O.P.(MAC)",   "bench": "Single Judge",   "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_RentControl": {"abbr": "O.P.(RC)",    "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_Tax":         {"abbr": "O.P.(Tax)",   "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_Wakf":        {"abbr": "O.P.(WT)",    "bench": "Division Bench", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "No prescribed limit"},
        "OriginalPetition_ArbitrationTimeExtension": {"abbr": "O.P.(ATE)", "bench": "Single Judge", "fee": "Rs.100/- per petitioner [Sch.II Art.11(l)(iii)]", "limitation": "Section 29A(4) A&C Act"},
        "OriginalPetition_ICA":         {"abbr": "O.P.(ICA)",   "bench": "Single Judge",   "fee": "Rs.100/- [Sch.II Art.11(l)(iii)]", "limitation": "Section 34(3) A&C Act"},
        # Civil
        "FirstAppeal_Order":            {"abbr": "F.A.O.",      "bench": "Single Judge",   "fee": "Rs.25/- or Rs.10/- [Sch.II Art.3(iii)(A)(1)]",    "limitation": "90 days [Art.116(a) Limitation Act]"},
        "FirstAppeal_OrderRemand":      {"abbr": "F.A.O.(RO)",  "bench": "Single Judge",   "fee": "Rs.25/- or Rs.10/- [Sch.II Art.3(iii)(A)(1)]",    "limitation": "90 days [Art.116(a) Limitation Act]"},
        "ExecutionFirstAppeal":         {"abbr": "Ex.F.A.",     "bench": "Single Judge",   "fee": "Rs.25/- or Rs.10/- [Sch.II Art.3(iii)(A)(1)]",    "limitation": "90 days [Art.116(a) Limitation Act]"},
        "ExecutionSecondAppeal":        {"abbr": "Ex.S.A.",     "bench": "Single Judge",   "fee": "Rs.25/- or Rs.10/- [Sch.II Art.3(iii)(A)(1)]",    "limitation": "90 days [Art.116(a) Limitation Act]"},
        "CrossObjection":               {"abbr": "C.O.",        "bench": "Single Judge",   "fee": "Same as appeal [Sch.I Art.1 or Sch.II Art.3]",     "limitation": "1 month from date of notice of hearing [Order XLI Rule 22 CPC]"},
        "TransferAppeal_Civil":         {"abbr": "Tr.A.(C)",    "bench": "Division Bench", "fee": "Rs.200/- per appellant [Sch.II Art.3(iii)(A)(2)(c)]", "limitation": "30 days [Art.117 Limitation Act]"},
        "SupremeCourtLeavePetition":    {"abbr": "S.C.L.P.",    "bench": "Single Judge",   "fee": "Rs.10/- [Sch.II Art.11(t)]",                       "limitation": "60 days [Art.132 Limitation Act]"},
        "CivilMiscCase_Pauper":         {"abbr": "C.M.C.",      "bench": "Single Judge",   "fee": "NIL if permitted [Order XLIV CPC]",                 "limitation": "60 days [Art.130(a) Limitation Act]"},
        "MiscJurisdictionCase":         {"abbr": "M.J.C.",      "bench": "Single Judge",   "fee": "Rs.10/- [Sch.II Art.11(t)]",                       "limitation": "As per court direction"},
        # Criminal
        "CriminalMiscApplication":      {"abbr": "Crl.M.Appl.", "bench": "Single Judge",   "fee": "Rs.10/- [Sch.II Art.11(t)]",                       "limitation": "No prescribed limit"},
        "RevisionPetition_JuvenileJustice": {"abbr": "Rev.P.(JJ)", "bench": "Single Judge","fee": "Rs.10/- [Sch.II Art.11(t)]",                       "limitation": "90 days [Rule 44 KHC Rules]"},
        "CriminalAppeal_Acquittal":     {"abbr": "Crl.L.P.",    "bench": "Single Judge",   "fee": "Rs.10/- [Sch.II Art.11(t)]",                       "limitation": "90 days [Art.131 Limitation Act]"},
        # M.F.A. variants
        "MiscFirstAppeal_Forest":       {"abbr": "M.F.A.(Forest)", "bench": "Single Judge","fee": "Rs.500/- or Rs.100/- [specific forest act provision]", "limitation": "30 days [Art.117 Limitation Act]"},
        "MiscFirstAppeal_FEMA":         {"abbr": "M.F.A.(FEMA)",   "bench": "Single Judge","fee": "Rs.25/- [Sch.II Art.3(iii)A(1)(a)]",               "limitation": "30 days [Art.117 Limitation Act]"},
        "MiscFirstAppeal_EmployeesCompensation": {"abbr": "M.F.A.(ECC)", "bench": "Single Judge", "fee": "Rs.25/- [Sch.II Art.3(iii)A(1)(a)]",        "limitation": "90 days [Art.116(a) Limitation Act]"},
        "LandAcquisitionAppeal":        {"abbr": "L.A.App.",     "bench": "Single Judge",  "fee": "Ad valorem [Sch.I Art.1]",                         "limitation": "90 days [Art.116(a) Limitation Act]"},
        "MiscFirstAppeal_Insolvency":   {"abbr": "M.F.A.(Insolvency)", "bench": "Single Judge", "fee": "½ scale on market value subject to max Rs.500/- [Sch.I Art.3]", "limitation": "30 days"},
        "MiscFirstAppeal_IndianSuccession": {"abbr": "M.F.A.(Indian Succession Act)", "bench": "Single Judge", "fee": "½ scale [Sch.I Art.4]",        "limitation": "90 days"},
        "RentControlRevision":          {"abbr": "R.C.Rev.",     "bench": "Single Judge",  "fee": "Rs.5/- [Rule 7(4) Kerala Buildings Lease & Rent Control Rules]", "limitation": "90 days"},
        "CommercialAppeal":             {"abbr": "Coml.A.",      "bench": "Division Bench","fee": "Ad valorem [Sch.I Art.1] or Rs.25/- [Sch.II Art.3(iii)(A)(a)] depending on proviso to Sec.13(1A) Commercial Courts Act", "limitation": "60 days [Section 13 Commercial Courts Act]"},
        "ExecutionPetition_ICA":        {"abbr": "E.P.(ICA)",    "bench": "Single Judge",  "fee": "Slab: ≤Rs.5000=Rs.50; ≤Rs.10000=Rs.200; >Rs.10000=Rs.400 [Sch.II Art.11(n)]", "limitation": "3 years [Art.137 Limitation Act; Govt of India v Vedanta 2020]"},
    }

    if doc_type in TIER_2_METADATA:
        meta = TIER_2_METADATA[doc_type]
        return f"""
Draft a {meta['abbr']} ({doc_type}) for filing before the Kerala High Court.

COURT AND PROCEDURAL DETAILS:
- Abbreviation: {meta['abbr']}
- Bench: {meta['bench']}
- Court fee: {meta['fee']}
- Limitation: {meta['limitation']}

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. "{meta['abbr']} No. _____ of _____ "
3. Cause title
4. Provision of law under which filed (state exact section and Act)
5. Description of parties
6. Facts (numbered paragraphs — trace each fact to an uploaded document)
7. Grounds (lettered paragraphs — each a distinct legal ground)
8. Prayer
9. Interim prayer (if applicable)
10. Verification paragraph
11. Date, place, and signatures

For O.P. variants (Article 227):
- Follow the same structure as O.P.(Civil) — facts, grounds, prayer challenging the tribunal/court order
- Attach certified copy of the impugned order
- State whether delay requires explanation

For Appeal variants:
- State value of the subject matter for court fee and jurisdiction
- Attach certified copy of impugned judgment/order [Rule 41(a), KHC Rules]
- If filed after limitation: accompany with C.M.Application under Section 5 Limitation Act

Ensure:
- All factual claims trace to uploaded documents
- Use [FACT NEEDED: description] for missing facts
- Follow KHC formatting requirements [Rule 35, KHC Rules]
"""

    # Fully generic fallback for completely unknown types
    return f"""
Draft a {doc_type} for filing before the Kerala High Court.

STRUCTURE:
1. Court heading: "IN THE HIGH COURT OF KERALA AT ERNAKULAM"
2. Case type and number
3. Cause title
4. Provision of law under which filed
5. Description of parties
6. Facts (numbered paragraphs)
7. Grounds (lettered paragraphs)
8. Prayer
9. Interim prayer (if applicable)
10. Verification
11. Date and signatures

Ensure:
- All factual claims trace to uploaded documents
- Use [FACT NEEDED: description] for missing facts
- Include correct court fee reference
- Include limitation period if applicable
- Follow KHC formatting requirements [Rule 35, KHC Rules]
"""


# ===========================================================================
# DOCUMENT TYPE CONSTANTS
# Used across the backend for consistent docType strings
# ===========================================================================

class DocType:
    """Controlled vocabulary for document types in workspace uploads."""
    FIR = "FIR"
    CHARGE_SHEET = "ChargeSheet"
    REMAND_ORDER = "RemandOrder"
    BAIL_ORDER_GRANT = "BailOrder_Grant"
    BAIL_ORDER_REJECTION = "BailOrder_Rejection"
    COURT_ORDER_INTERIM = "CourtOrder_Interim"
    COURT_ORDER_FINAL = "CourtOrder_Final"
    JUDGMENT_HC = "Judgment_HC"
    JUDGMENT_SC = "Judgment_SC"
    JUDGMENT_SUBORDINATE = "Judgment_SubordinateCourt"
    AFFIDAVIT_SUPPORTING = "Affidavit_Supporting"
    AFFIDAVIT_COUNTER = "Affidavit_Counter"
    AFFIDAVIT_REPLY = "Affidavit_Reply"
    VAKALATNAMA = "Vakalatnama"
    POWER_OF_ATTORNEY = "PowerOfAttorney"
    LEGAL_NOTICE = "LegalNotice"
    PETITION_FILED = "Petition_Filed"
    APPEAL_FILED = "Appeal_Filed"
    REVISION_PETITION = "RevisionPetition_Filed"
    GOVERNMENT_ORDER = "GovernmentOrder"
    GOVERNMENT_CIRCULAR = "GovernmentCircular"
    GAZETTE_NOTIFICATION = "Gazette_Notification"
    LAND_RECORD = "LandRecord"
    SERVICE_RECORD = "ServiceRecord"
    MEDICAL_REPORT = "MedicalReport"
    POST_MORTEM_REPORT = "PostMortemReport"
    FSL_REPORT = "FSLReport"
    WITNESS_STATEMENT = "WitnessStatement"
    OTHER = "Other"


class DraftType:
    """
    Controlled vocabulary for all draft types in LawMate workspaces.
    Organised by tier:
      TIER_1 — Full custom drafting prompt
      TIER_2 — DraftType constant + generic fallback prompt
      (Tier 3 types are intentionally omitted — court-initiated, jurisdiction-
       transferred to NCLT, or too niche for general AI drafting assistance)
    """

    # ------------------------------------------------------------------
    # TIER 1 — Full custom drafting prompts (existing)
    # ------------------------------------------------------------------
    BAIL_REGULAR              = "BailApplication_Regular"
    BAIL_ANTICIPATORY         = "BailApplication_Anticipatory"
    WRIT_CIVIL                = "WritPetition_Civil"
    WRIT_CRIMINAL             = "WritPetition_Criminal"
    WRIT_APPEAL               = "WritAppeal"
    CRIMINAL_APPEAL           = "CriminalAppeal"
    CRIMINAL_REVISION         = "CriminalRevisionPetition"
    CIVIL_REVISION            = "CivilRevisionPetition"
    MATRIMONIAL_APPEAL        = "MatrimonialAppeal"
    CONTEMPT_CIVIL            = "ContemptPetition_Civil"
    OP_CIVIL                  = "OriginalPetition_Civil"
    VAKALATNAMA               = "Vakalatnama"
    IA                        = "InterlocutoryApplication"

    # ------------------------------------------------------------------
    # TIER 1 — Full custom drafting prompts (new)
    # ------------------------------------------------------------------
    REGULAR_FIRST_APPEAL      = "RegularFirstAppeal"
    REGULAR_SECOND_APPEAL     = "RegularSecondAppeal"
    CRIMINAL_MISC_CASE        = "CriminalMiscCase"           # Sec.482 CrPC
    CRIMINAL_LEAVE_PETITION   = "CriminalLeavePetition"      # Sec.378 CrPC
    CRIMINAL_APPEAL_VICTIM    = "CriminalAppeal_Victim"      # Sec.372 CrPC
    MACA                      = "MotorAccidentClaimsAppeal"
    TRANSFER_PETITION_CIVIL   = "TransferPetition_Civil"
    TRANSFER_PETITION_CRIMINAL= "TransferPetition_Criminal"
    REVISION_PETITION_FC      = "RevisionPetition_FamilyCourt"
    MATRIMONIAL_APPEAL_EXECUTION = "MatrimonialAppeal_Execution"
    CAVEAT                    = "Caveat"
    REVIEW_PETITION           = "ReviewPetition"
    CIVIL_MISC_APPLICATION    = "CivilMiscApplication"       # Condonation
    COMPOUNDING_PETITION      = "CompoundingPetition"
    ARBITRATION_REQUEST       = "ArbitrationRequest"         # Sec.11
    ARBITRATION_APPEAL        = "ArbitrationAppeal"          # Sec.37

    # ------------------------------------------------------------------
    # TIER 2 — DraftType constant + generic fallback
    # ------------------------------------------------------------------

    # Article 227 O.P. tribunal variants
    OP_CRIMINAL               = "OriginalPetition_Criminal"
    OP_CAT                    = "OriginalPetition_CAT"
    OP_KAT                    = "OriginalPetition_KAT"
    OP_DRT                    = "OriginalPetition_DRT"
    OP_FC                     = "OriginalPetition_FamilyCourt"
    OP_FT                     = "OriginalPetition_ForestTribunal"
    OP_LC                     = "OriginalPetition_LabourCourt"
    OP_MAC                    = "OriginalPetition_MAC"
    OP_RC                     = "OriginalPetition_RentControl"
    OP_TAX                    = "OriginalPetition_Tax"
    OP_WAKF                   = "OriginalPetition_Wakf"
    OP_ATE                    = "OriginalPetition_ArbitrationTimeExtension"
    OP_ICA                    = "OriginalPetition_ICA"

    # Civil proceedings
    FIRST_APPEAL_ORDER        = "FirstAppeal_Order"          # F.A.O.
    FIRST_APPEAL_ORDER_REMAND = "FirstAppeal_OrderRemand"    # F.A.O.(RO)
    EXECUTION_FIRST_APPEAL    = "ExecutionFirstAppeal"       # Ex.F.A.
    EXECUTION_SECOND_APPEAL   = "ExecutionSecondAppeal"      # Ex.S.A.
    CROSS_OBJECTION           = "CrossObjection"             # C.O.
    TRANSFER_APPEAL_CIVIL     = "TransferAppeal_Civil"       # Tr.A.(C)
    SUPREME_COURT_LEAVE       = "SupremeCourtLeavePetition"  # S.C.L.P.
    CIVIL_MISC_CASE_PAUPER    = "CivilMiscCase_Pauper"       # C.M.C.
    MISC_JURISDICTION_CASE    = "MiscJurisdictionCase"       # M.J.C.

    # Criminal proceedings
    CRIMINAL_MISC_APPLICATION = "CriminalMiscApplication"   # Crl.M.Appl.
    REVISION_PETITION_JJ      = "RevisionPetition_JuvenileJustice"
    CRIMINAL_APPEAL_ACQUITTAL = "CriminalAppeal_Acquittal"   # Sec.378

    # Miscellaneous first appeals (M.F.A. variants — generic fallback)
    MFA_FOREST                = "MiscFirstAppeal_Forest"
    MFA_FEMA                  = "MiscFirstAppeal_FEMA"
    MFA_EMPLOYEES_COMPENSATION= "MiscFirstAppeal_EmployeesCompensation"
    MFA_LAND_ACQUISITION      = "LandAcquisitionAppeal"
    MFA_MOTOR_VEHICLES        = "MiscFirstAppeal_MotorVehicles"
    MFA_INSOLVENCY            = "MiscFirstAppeal_Insolvency"
    MFA_SUCCESSION            = "MiscFirstAppeal_IndianSuccession"
    MFA_RENT_CONTROL          = "RentControlRevision"        # R.C.Rev.
    COMMERCIAL_APPEAL         = "CommercialAppeal"           # Coml.A.

    # EP(ICA)
    EP_ICA                    = "ExecutionPetition_ICA"