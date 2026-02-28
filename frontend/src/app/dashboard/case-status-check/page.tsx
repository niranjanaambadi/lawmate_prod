"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { addCaseToDashboard, queryCaseStatus, type CaseStatusLookupResult } from "@/lib/api";
import ChatWidget from "@/components/agent/ChatWidget";

const CASE_TYPES = [
  "Adml.S.",
  "AFA",
  "AFFD",
  "APPEAL (ICA)",
  "AR",
  "Arb.A",
  "Arb.P.",
  "AS",
  "ASA",
  "Bail Appl.",
  "Bkg.P",
  "Cal. Case",
  "CC",
  "CCC",
  "CDAR",
  "CDB",
  "CDIR",
  "CDSR",
  "C.E.Appeal",
  "CE.Ref.",
  "CMA",
  "CMC",
  "CMCP",
  "CMP",
  "CMR",
  "CO",
  "CO.ADJ.APPEAL",
  "Co.Appeal",
  "Co.Appl.",
  "Co.Case",
  "Coml.A",
  "COMPLAINT NO",
  "Con.APP(C)",
  "Con.Case(C)",
  "Cont.Cas.(Crl.)",
  "Co.Pet",
  "CR",
  "CRA(V)",
  "CRL.A",
  "Crl.Compl.",
  "Crl.L.P.",
  "Crl.MC",
  "Crl.RC",
  "CRL.REF",
  "Crl.Rev.Pet",
  "CRP",
  "CRP(LR)",
  "CRP(UTY)",
  "CRP(WAKF)",
  "CS",
  "CSDA",
  "Cus.Appeal",
  "Cus.Ref.",
  "DB",
  "DBA",
  "DBAR",
  "DBC",
  "DBP",
  "DIR",
  "DSR",
  "EDA",
  "EDR",
  "EFA",
  "El.Pet.",
  "EP(ICA)",
  "ESA",
  "Ex.Appl.",
  "Ex.FA",
  "Ex.P",
  "Ex.SA",
  "FA",
  "F.A (ADMIRALTY)",
  "FAO",
  "F.A.O (ADMIRALTY)",
  "FAO (RO)",
  "Gen.Report",
  "GTA",
  "GTR",
  "Gua.P.",
  "HPCR(S)",
  "IA",
  "ICR (Crl.MC)",
  "ICR (CRP)",
  "ICR (ITA)",
  "ICR (LA.App)",
  "ICR (MACA)",
  "ICR (Mat.Appeal)",
  "ICR (MFA (FOREST))",
  "ICR (OP(ATE))",
  "ICR (OP(C))",
  "ICR (OP(KAT))",
  "ICR (OP (RC) )",
  "ICR (OT.Rev)",
  "ICR (RP)",
  "ICR (WA)",
  "ICR (WP(C))",
  "ICR (WP(Crl.))",
  "Ins.APP",
  "Intest.Cas.",
  "ITA",
  "ITR",
  "JPP",
  "LAAP",
  "LA.App.",
  "MAC",
  "MACA",
  "MA (EXE.)",
  "Mat.Appeal",
  "Mat.Cas",
  "Mat.Ref.",
  "MCA",
  "MEMO",
  "MFA",
  "MFA (ADL)",
  "MFA (ADR)",
  "MFA (CINEMATOGRAPH ACT)",
  "MFA (COPYRIGHT)",
  "MFA (ECC)",
  "MFA (ELECTION)",
  "MFA (ELECTRICITY)",
  "MFA (FCRA)",
  "MFA (FEMA)",
  "MFA (FERA)",
  "MFA (FINANCE)",
  "MFA (FOREST)",
  "MFA (GST)",
  "MFA (G & W)",
  "MFA (HRCE)",
  "MFA (IDPA)",
  "MFA (INSOLVENCY)",
  "MFA (KEA)",
  "MFA(KME)",
  "MFA (LUNACY)",
  "MFA (MHA)",
  "MFA MT (OP)",
  "MFA (PANCHAYAT)",
  "MFA (PATENTS)",
  "MFA (PROBATE)",
  "MFA (RCT)",
  "MFA (SCSTCC)",
  "MFA (SEBI)",
  "MFA (SUCCESSION)",
  "MFA (TCHRI)",
  "MFA (TCRA)",
  "MFA (TRADE MARKS)",
  "MFA (WAQF)",
  "MFCA",
  "MITA",
  "MJC",
  "MSA",
  "MSA(FS)",
  "NO",
  "OP",
  "OP(AFT)",
  "OP(ATE)",
  "OP(C)",
  "OP (CAT)",
  "OP(Crl.)",
  "OP (DRT)",
  "OP (FC)",
  "OP(FT)",
  "OP(ICA)",
  "OP(KAT)",
  "OP(LC)",
  "OP (MAC)",
  "OP(NCDRC)",
  "OP (RC)",
  "OP STAT",
  "OP (TAX)",
  "OP (WAKF)",
  "OS",
  "OT.Appeal",
  "OT.Appl.",
  "OTC",
  "OTR",
  "OT.Rev",
  "PA",
  "RC",
  "RCRev.",
  "Report",
  "RFA",
  "RFA (MISC.)",
  "RP",
  "RPAR",
  "RPFC",
  "RPJJ",
  "RRPT",
  "RSA",
  "RT",
  "SA",
  "SCA",
  "SCLP",
  "SLP",
  "SP.JC",
  "SRDB",
  "SSCR",
  "ST.Appl.",
  "ST.Ref.",
  "ST.Rev.",
  "Suo Motu Ref.",
  "TDAR",
  "TDB",
  "TDIR",
  "TDSR",
  "Test.Cas",
  "TIP",
  "Tr.Appeal(C)",
  "Tr.Appl. (CR)",
  "TRC",
  "Tr.P(C)",
  "Tr.P(Crl.)",
  "UNN.ADML.S",
  "Unn.CRP Uty",
  "UNN.FAO (RO)",
  "UNNUMB.AFA",
  "UNNUMB.AR",
  "UNNUMB.Arb.A.",
  "UNNUMB.AS",
  "UNNUMB.Bail Appl.",
  "UNNUMB.CB",
  "UNNUMB.CC",
  "UNNUMB.CCC",
  "UNNUMB.CDB",
  "UNNUMB.CEA",
  "UNNUMB.Ce.Ref",
  "UNNUMB.CMA",
  "UNNUMB.CMC",
  "UNNUMB.CMCP",
  "UNNUMB.CMP",
  "UNNUMB.CMR",
  "UNNUMB.CO",
  "UNNUMB.COA",
  "UNNUMB.Co.Appl.",
  "UNNUMB.Con.Case(C)",
  "UNNUMB.Cont.App(C)",
  "UNNUMB.Cont.Cas.(Crl",
  "UNNUMB.CP",
  "UNNUMB.CRA(V)",
  "UNNUMB.CRL.A",
  "UNNUMB.Crl.Compl.",
  "UNNUMB.Crl.L.P.",
  "UNNUMB.Crl.MC",
  "UNNUMB.Crl.RC",
  "UNNUMB.Crl.Rev.Pet",
  "UNNUMB.CRP",
  "UNNUMB.CS",
  "UNNUMB.CUA",
  "UNNUMB.Cus.Ref.",
  "UNNUMB.DBA",
  "UNNUMB.DBC",
  "UNNUMB.DBP",
  "UNNUMB.EDA",
  "UNNUMB.EDR",
  "UNNUMB.EFA",
  "UNNUMB.EP",
  "UNNUMB.EP(ICA)",
  "UNNUMB.ESA",
  "UNNUMB.Ex.FA",
  "UNNUMB Ex.P",
  "UNNUMB.ExSA",
  "UNNUMB.FA",
  "UNNUMB.FAO",
  "UNNUMB.GTA",
  "UNNUMB.GTR",
  "UNNUMB.Gua.P.",
  "UNNUMB.Ins.APP",
  "UNNUMB.Intest Cas.",
  "UNNUMB.ITA",
  "UNNUMB.ITR",
  "UNNUMB.LAA",
  "UNNUMB.LAAP",
  "UNNUMB.LC",
  "UNNUMB,MACA",
  "UNNUMB.MA (EXE.)",
  "UNNUMB.Mat.App.",
  "UNNUMB.Mat.Ref.",
  "UNNUMB.MC",
  "UNNUMB.MCA",
  "UNNUMB.MFA",
  "UNNUMB.MFA(KME)",
  "UNNUMB.MFA MT (OP)",
  "UNNUMB.MJC",
  "UNNUMB.MSA",
  "UNNUMB.MSA(FS)",
  "UNNUMB.OP",
  "UNNUMB.OP(AFT)",
  "UNNUMB.OPC",
  "UNNUMB.OPCAT",
  "UNNUMB.OP(Crl.)",
  "UNNUMB.OP DRT",
  "UNNUMB.OPFC",
  "UNNUMB.OP(ICA)",
  "UNNUMB.OP MACT",
  "UNNUMB. OP(RC)",
  "UNNUMB.OP (TAX)",
  "UNNUMB.OS",
  "UNNUMB.OTAP",
  "UNNUMB.OT.Appl",
  "UNNUMB.OTC",
  "UNNUMB.OTRV",
  "UNNUMB.RC",
  "UNNUMB.RC.Rev.",
  "UNNUMB.RFA",
  "UNNUMB.RP",
  "UNNUMB.RPAR",
  "UNNUMB.RPFC",
  "UNNUMB.RPJJ",
  "UNNUMB.RSA",
  "UNNUMB.RT",
  "UNNUMB.SA",
  "UNNUMB.SCA",
  "UNNUMB.SCLP",
  "UNNUMB.SMR",
  "UNNUMB.SP.JC.",
  "UNNUMB.ST.Appl.",
  "UNNUMB.ST.Ref.",
  "UNNUMB.ST.Rev.",
  "UNNUMB.TAC",
  "UNNUMB.TDB",
  "UNNUMB.Test.Cas.",
  "UNNUMB.Tr.Appl. (CR)",
  "UNNUMB.TRC",
  "UNNUMB.TrP(C)",
  "UNNUMB.Tr.P(Crl.)",
  "UNNUMB.UNNUMB.Co.App",
  "UNNUMB.WA",
  "UNNUMB.WAKF",
  "UNNUMB.WP(AFT)",
  "UNNUMB.WP(C)",
  "UNNUMB.WP(Crl.)",
  "UNNUMB.WTA",
  "UNNUMB.WTR",
  "WA",
  "W.C.C.Ref.",
  "WP(AFT)",
  "WP(C)",
  "WP(Crl.)",
  "WP(PIL)",
  "WTA",
  "WTR",
  "ZCOAA",
  "ZCRP(LR)",
  "ZCRP(WK)",
  "ZOP(FT)",
  "ZOP(KAT)",
  "ZOP STAT",
  "ZRFA(MISC.)",
];

function formatDate(value?: string | null) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString();
}

function formatList(values?: string[] | null) {
  if (!values || values.length === 0) return "-";
  return values.join(", ");
}

function formatObject(obj?: Record<string, unknown> | null) {
  if (!obj || Object.keys(obj).length === 0) return "-";
  return Object.entries(obj)
    .map(([k, v]) => `${k}: ${String(v ?? "")}`)
    .join(" | ");
}

function formatObjectList(values?: Record<string, unknown>[] | null) {
  if (!values || values.length === 0) return "-";
  return values.map((v, i) => `${i + 1}. ${formatObject(v)}`).join("\n");
}

export default function PendingCasesPage() {
  const { token } = useAuth();
  const [caseType, setCaseType] = useState("WP(C)");
  const [caseNo, setCaseNo] = useState("");
  const [caseYear, setCaseYear] = useState(new Date().getFullYear().toString());
  const [result, setResult] = useState<CaseStatusLookupResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const fetchStatus = async () => {
    if (!caseType.trim() || !caseNo.trim() || !caseYear.trim()) {
      setMessage("Please select case type and enter case number + year");
      return;
    }
    if (!/^\d+$/.test(caseNo.trim()) || !/^\d{4}$/.test(caseYear.trim())) {
      setMessage("Case number must be numeric and year must be 4 digits");
      return;
    }
    if (!token) return;
    try {
      setSearching(true);
      setMessage(null);
      const formattedCaseNumber = `${caseType.trim()} ${caseNo.trim()}/${caseYear.trim()}`;
      const data = await queryCaseStatus(formattedCaseNumber, token);
      setResult(data);
      if (!data.found) {
        setMessage("Case not found on portal");
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to fetch case status");
    } finally {
      setSearching(false);
    }
  };

  const onAddToDashboard = async () => {
    if (!token || !result) return;
    try {
      setAdding(true);
      setMessage(null);
      const res = await addCaseToDashboard(
        {
          case_number: result.case_number,
          petitioner_name: result.petitioner_name || undefined,
          respondent_name: result.respondent_name || undefined,
          status_text: result.status_text || undefined,
          stage: result.stage || undefined,
          last_order_date: result.last_order_date || undefined,
          next_hearing_date: result.next_hearing_date || undefined,
          source_url: result.source_url || undefined,
          full_details_url: result.full_details_url || undefined,
        },
        token
      );
      setMessage(res.message);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to add case to dashboard");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl font-semibold tracking-tight text-slate-900">Case Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-slate-600">
            Enter case type, case number and year to fetch latest status from the Kerala High Court portal.
          </p>
          {message && <p className="text-sm text-slate-700">{message}</p>}
          <div className="grid gap-2 md:grid-cols-4">
            <select
              className="h-9 rounded border px-3 text-sm"
              value={caseType}
              onChange={(e) => setCaseType(e.target.value)}
            >
              {CASE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              className="h-9 rounded border px-3 text-sm"
              placeholder="Case Number"
              value={caseNo}
              onChange={(e) => setCaseNo(e.target.value)}
            />
            <input
              className="h-9 rounded border px-3 text-sm"
              placeholder="Year"
              value={caseYear}
              onChange={(e) => setCaseYear(e.target.value)}
            />
            <Button onClick={fetchStatus} disabled={searching}>
              {searching ? "Fetching..." : "Get Status"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Structured Result</CardTitle>
        </CardHeader>
        <CardContent>
          {!result ? (
            <p className="text-sm text-slate-500">No case looked up yet.</p>
          ) : (
            <div className="space-y-2 text-sm">
              <p><strong>Case Number:</strong> {result.case_number}</p>
              <p><strong>Case Type:</strong> {result.case_type || "-"}</p>
              <p><strong>Filing Number:</strong> {result.filing_number || "-"}</p>
              <p><strong>Filing Date:</strong> {formatDate(result.filing_date)}</p>
              <p><strong>Registration Number:</strong> {result.registration_number || "-"}</p>
              <p><strong>Registration Date:</strong> {formatDate(result.registration_date)}</p>
              <p><strong>CNR Number:</strong> {result.cnr_number || "-"}</p>
              <p><strong>E-File No:</strong> {result.efile_number || "-"}</p>
              <p><strong>First Hearing Date:</strong> {formatDate(result.first_hearing_date)}</p>
              <p><strong>Status:</strong> {result.status_text || "-"}</p>
              <p><strong>Coram:</strong> {result.coram || "-"}</p>
              <p><strong>Stage:</strong> {result.stage || "-"}</p>
              <p><strong>Petitioner:</strong> {result.petitioner_name || "-"}</p>
              <p><strong>Petitioner Advocates:</strong> {formatList(result.petitioner_advocates)}</p>
              <p><strong>Respondent:</strong> {result.respondent_name || "-"}</p>
              <p><strong>Respondent Advocates:</strong> {formatList(result.respondent_advocates)}</p>
              <p><strong>Served On:</strong> {formatList(result.served_on)}</p>
              <p><strong>Acts:</strong> {formatList(result.acts)}</p>
              <p><strong>Sections:</strong> {formatList(result.sections)}</p>
              <p><strong>Last Order Date:</strong> {formatDate(result.last_order_date)}</p>
              <p><strong>Next Hearing:</strong> {formatDate(result.next_hearing_date)}</p>
              <p><strong>Last Listed Date:</strong> {formatDate(result.last_listed_date)}</p>
              <p><strong>Last Listed Bench:</strong> {result.last_listed_bench || "-"}</p>
              <p><strong>Last Listed List:</strong> {result.last_listed_list || "-"}</p>
              <p><strong>Last Listed Item:</strong> {result.last_listed_item || "-"}</p>
              <p><strong>History of Case Hearing:</strong></p>
              <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs">
                {formatObjectList(result.hearing_history)}
              </pre>
              <p><strong>Interim Orders:</strong></p>
              <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs">
                {formatObjectList(result.interim_orders)}
              </pre>
              <p><strong>Category Details:</strong> {formatObject(result.category_details)}</p>
              <p><strong>Objection:</strong></p>
              <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs">
                {formatObjectList(result.objections)}
              </pre>
              <p><strong>Summary:</strong> {result.summary || "-"}</p>
              <p><strong>Fetched At:</strong> {formatDate(result.fetched_at)}</p>
              <div className="pt-2">
                {result.full_details_url ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="mr-2"
                    onClick={() => window.open(result.full_details_url || "", "_blank", "noopener,noreferrer")}
                  >
                    View Full Details
                  </Button>
                ) : null}
                <Button onClick={onAddToDashboard} disabled={adding || !result.found}>
                  {adding ? "Adding..." : "Add to Dashboard"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <ChatWidget page="global" />
    </div>
  );
}
