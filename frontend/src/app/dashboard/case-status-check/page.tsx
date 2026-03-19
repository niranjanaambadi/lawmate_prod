"use client";

import { useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { addCaseToDashboard, queryCaseStatus, type CaseStatusLookupResult } from "@/lib/api";
import ChatWidget from "@/components/agent/ChatWidget";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  Gavel,
  Loader2,
  PlusCircle,
  Scale,
  Search,
  Users,
} from "lucide-react";

// ─── Case type list ───────────────────────────────────────────────────────────

const CASE_TYPES = [
  "Adml.S.","AFA","AFFD","APPEAL (ICA)","AR","Arb.A","Arb.P.","AS","ASA",
  "Bail Appl.","Bkg.P","Cal. Case","CC","CCC","CDAR","CDB","CDIR","CDSR",
  "C.E.Appeal","CE.Ref.","CMA","CMC","CMCP","CMP","CMR","CO","CO.ADJ.APPEAL",
  "Co.Appeal","Co.Appl.","Co.Case","Coml.A","COMPLAINT NO","Con.APP(C)",
  "Con.Case(C)","Cont.Cas.(Crl.)","Co.Pet","CR","CRA(V)","CRL.A","Crl.Compl.",
  "Crl.L.P.","Crl.MC","Crl.RC","CRL.REF","Crl.Rev.Pet","CRP","CRP(LR)",
  "CRP(UTY)","CRP(WAKF)","CS","CSDA","Cus.Appeal","Cus.Ref.","DB","DBA","DBAR",
  "DBC","DBP","DIR","DSR","EDA","EDR","EFA","El.Pet.","EP(ICA)","ESA","Ex.Appl.",
  "Ex.FA","Ex.P","Ex.SA","FA","F.A (ADMIRALTY)","FAO","F.A.O (ADMIRALTY)",
  "FAO (RO)","Gen.Report","GTA","GTR","Gua.P.","HPCR(S)","IA","ICR (Crl.MC)",
  "ICR (CRP)","ICR (ITA)","ICR (LA.App)","ICR (MACA)","ICR (Mat.Appeal)",
  "ICR (MFA (FOREST))","ICR (OP(ATE))","ICR (OP(C))","ICR (OP(KAT))",
  "ICR (OP (RC) )","ICR (OT.Rev)","ICR (RP)","ICR (WA)","ICR (WP(C))",
  "ICR (WP(Crl.))","Ins.APP","Intest.Cas.","ITA","ITR","JPP","LAAP","LA.App.",
  "MAC","MACA","MA (EXE.)","Mat.Appeal","Mat.Cas","Mat.Ref.","MCA","MEMO","MFA",
  "MFA (ADL)","MFA (ADR)","MFA (CINEMATOGRAPH ACT)","MFA (COPYRIGHT)",
  "MFA (ECC)","MFA (ELECTION)","MFA (ELECTRICITY)","MFA (FCRA)","MFA (FEMA)",
  "MFA (FERA)","MFA (FINANCE)","MFA (FOREST)","MFA (GST)","MFA (G & W)",
  "MFA (HRCE)","MFA (IDPA)","MFA (INSOLVENCY)","MFA (KEA)","MFA(KME)",
  "MFA (LUNACY)","MFA (MHA)","MFA MT (OP)","MFA (PANCHAYAT)","MFA (PATENTS)",
  "MFA (PROBATE)","MFA (RCT)","MFA (SCSTCC)","MFA (SEBI)","MFA (SUCCESSION)",
  "MFA (TCHRI)","MFA (TCRA)","MFA (TRADE MARKS)","MFA (WAQF)","MFCA","MITA",
  "MJC","MSA","MSA(FS)","NO","OP","OP(AFT)","OP(ATE)","OP(C)","OP (CAT)",
  "OP(Crl.)","OP (DRT)","OP (FC)","OP(FT)","OP(ICA)","OP(KAT)","OP(LC)",
  "OP (MAC)","OP(NCDRC)","OP (RC)","OP STAT","OP (TAX)","OP (WAKF)","OS",
  "OT.Appeal","OT.Appl.","OTC","OTR","OT.Rev","PA","RC","RCRev.","Report",
  "RFA","RFA (MISC.)","RP","RPAR","RPFC","RPJJ","RRPT","RSA","RT","SA","SCA",
  "SCLP","SLP","SP.JC","SRDB","SSCR","ST.Appl.","ST.Ref.","ST.Rev.",
  "Suo Motu Ref.","TDAR","TDB","TDIR","TDSR","Test.Cas","TIP","Tr.Appeal(C)",
  "Tr.Appl. (CR)","TRC","Tr.P(C)","Tr.P(Crl.)","UNN.ADML.S","Unn.CRP Uty",
  "UNN.FAO (RO)","UNNUMB.AFA","UNNUMB.AR","UNNUMB.Arb.A.","UNNUMB.AS",
  "UNNUMB.Bail Appl.","UNNUMB.CB","UNNUMB.CC","UNNUMB.CCC","UNNUMB.CDB",
  "UNNUMB.CEA","UNNUMB.Ce.Ref","UNNUMB.CMA","UNNUMB.CMC","UNNUMB.CMCP",
  "UNNUMB.CMP","UNNUMB.CMR","UNNUMB.CO","UNNUMB.COA","UNNUMB.Co.Appl.",
  "UNNUMB.Con.Case(C)","UNNUMB.Cont.App(C)","UNNUMB.Cont.Cas.(Crl",
  "UNNUMB.CP","UNNUMB.CRA(V)","UNNUMB.CRL.A","UNNUMB.Crl.Compl.",
  "UNNUMB.Crl.L.P.","UNNUMB.Crl.MC","UNNUMB.Crl.RC","UNNUMB.Crl.Rev.Pet",
  "UNNUMB.CRP","UNNUMB.CS","UNNUMB.CUA","UNNUMB.Cus.Ref.","UNNUMB.DBA",
  "UNNUMB.DBC","UNNUMB.DBP","UNNUMB.EDA","UNNUMB.EDR","UNNUMB.EFA","UNNUMB.EP",
  "UNNUMB.EP(ICA)","UNNUMB.ESA","UNNUMB.Ex.FA","UNNUMB Ex.P","UNNUMB.ExSA",
  "UNNUMB.FA","UNNUMB.FAO","UNNUMB.GTA","UNNUMB.GTR","UNNUMB.Gua.P.",
  "UNNUMB.Ins.APP","UNNUMB.Intest Cas.","UNNUMB.ITA","UNNUMB.ITR","UNNUMB.LAA",
  "UNNUMB.LAAP","UNNUMB.LC","UNNUMB,MACA","UNNUMB.MA (EXE.)","UNNUMB.Mat.App.",
  "UNNUMB.Mat.Ref.","UNNUMB.MC","UNNUMB.MCA","UNNUMB.MFA","UNNUMB.MFA(KME)",
  "UNNUMB.MFA MT (OP)","UNNUMB.MJC","UNNUMB.MSA","UNNUMB.MSA(FS)","UNNUMB.OP",
  "UNNUMB.OP(AFT)","UNNUMB.OPC","UNNUMB.OPCAT","UNNUMB.OP(Crl.)","UNNUMB.OP DRT",
  "UNNUMB.OPFC","UNNUMB.OP(ICA)","UNNUMB.OP MACT","UNNUMB. OP(RC)",
  "UNNUMB.OP (TAX)","UNNUMB.OS","UNNUMB.OTAP","UNNUMB.OT.Appl","UNNUMB.OTC",
  "UNNUMB.OTRV","UNNUMB.RC","UNNUMB.RC.Rev.","UNNUMB.RFA","UNNUMB.RP",
  "UNNUMB.RPAR","UNNUMB.RPFC","UNNUMB.RPJJ","UNNUMB.RSA","UNNUMB.RT","UNNUMB.SA",
  "UNNUMB.SCA","UNNUMB.SCLP","UNNUMB.SMR","UNNUMB.SP.JC.","UNNUMB.ST.Appl.",
  "UNNUMB.ST.Ref.","UNNUMB.ST.Rev.","UNNUMB.TAC","UNNUMB.TDB","UNNUMB.Test.Cas.",
  "UNNUMB.Tr.Appl. (CR)","UNNUMB.TRC","UNNUMB.TrP(C)","UNNUMB.Tr.P(Crl.)",
  "UNNUMB.UNNUMB.Co.App","UNNUMB.WA","UNNUMB.WAKF","UNNUMB.WP(AFT)","UNNUMB.WP(C)",
  "UNNUMB.WP(Crl.)","UNNUMB.WTA","UNNUMB.WTR","WA","W.C.C.Ref.","WP(AFT)",
  "WP(C)","WP(Crl.)","WP(PIL)","WTA","WTR","ZCOAA","ZCRP(LR)","ZCRP(WK)",
  "ZOP(FT)","ZOP(KAT)","ZOP STAT","ZRFA(MISC.)",
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(value?: string | null) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function formatList(values?: string[] | null) {
  if (!values || values.length === 0) return null;
  return values.join(", ");
}

function InfoRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex gap-2 text-sm py-1.5 border-b border-slate-50 last:border-0">
      <span className="w-44 shrink-0 text-slate-500 font-medium">{label}</span>
      <span className="text-slate-800 break-words">{value}</span>
    </div>
  );
}

// ─── Searchable case type dropdown ───────────────────────────────────────────

function CaseTypeSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = CASE_TYPES.filter((t) =>
    t.toLowerCase().includes(filter.toLowerCase())
  );

  const handleSelect = (t: string) => {
    onChange(t);
    setFilter("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          setTimeout(() => inputRef.current?.focus(), 50);
        }}
        className="flex w-full items-center justify-between gap-2 h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 hover:border-slate-300 transition-colors"
      >
        <span className="truncate font-medium">{value}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-30 rounded-lg border border-slate-200 bg-white shadow-xl">
          {/* Filter input */}
          <div className="p-2 border-b border-slate-100">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                placeholder="Filter case types…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                onBlur={() => setTimeout(() => setOpen(false), 150)}
                className="w-full pl-7 pr-3 py-1.5 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-400"
              />
            </div>
          </div>
          {/* Options */}
          <ul className="max-h-52 overflow-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-sm text-slate-400 italic">No match</li>
            ) : (
              filtered.map((t) => (
                <li key={t}>
                  <button
                    type="button"
                    onMouseDown={() => handleSelect(t)}
                    className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-indigo-50 ${
                      t === value ? "bg-indigo-50 text-indigo-700 font-semibold" : "text-slate-700"
                    }`}
                  >
                    {t}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CaseStatusPage() {
  const { token } = useAuth();
  const [caseType, setCaseType] = useState("WP(C)");
  const [caseNo, setCaseNo] = useState("");
  const [caseYear, setCaseYear] = useState(new Date().getFullYear().toString());
  const [result, setResult] = useState<CaseStatusLookupResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addedOk, setAddedOk] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const formattedRef =
    caseNo.trim() && caseYear.trim()
      ? `${caseType} ${caseNo.trim()}/${caseYear.trim()}`
      : null;

  const fetchStatus = async () => {
    setValidationError(null);
    if (!caseType.trim() || !caseNo.trim() || !caseYear.trim()) {
      setValidationError("Please select a case type and enter case number and year.");
      return;
    }
    if (!/^\d+$/.test(caseNo.trim())) {
      setValidationError("Case number must be numeric.");
      return;
    }
    if (!/^\d{4}$/.test(caseYear.trim())) {
      setValidationError("Year must be 4 digits.");
      return;
    }
    if (!token) return;
    try {
      setSearching(true);
      setError(null);
      setResult(null);
      setAddedOk(false);
      const data = await queryCaseStatus(`${caseType.trim()} ${caseNo.trim()}/${caseYear.trim()}`, token);
      setResult(data);
      if (!data.found) setError("Case not found on the Kerala High Court portal.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch case status.");
    } finally {
      setSearching(false);
    }
  };

  const onAddToDashboard = async () => {
    if (!token || !result) return;
    try {
      setAdding(true);
      setError(null);
      await addCaseToDashboard(
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
      setAddedOk(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add case to dashboard.");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-50">

      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <div className="flex-none bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 shadow-sm">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Case Status Check</h1>
            <p className="text-sm text-slate-500">
              Look up the latest status of any Kerala High Court case · Add to your dashboard in one click
            </p>
          </div>
        </div>
      </div>

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-2xl mx-auto px-6 py-8 space-y-5">

          {/* ── Search card ────────────────────────────────────────────────── */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <p className="text-sm font-semibold text-slate-700">Enter case details</p>

            <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px_100px] gap-3">
              {/* Case type — searchable */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">Case Type</label>
                <CaseTypeSelect value={caseType} onChange={setCaseType} />
              </div>

              {/* Case number */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">Case No.</label>
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="e.g. 1234"
                  value={caseNo}
                  onChange={(e) => { setCaseNo(e.target.value); setValidationError(null); }}
                  onKeyDown={(e) => e.key === "Enter" && fetchStatus()}
                  className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>

              {/* Year */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">Year</label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={4}
                  placeholder="2024"
                  value={caseYear}
                  onChange={(e) => { setCaseYear(e.target.value); setValidationError(null); }}
                  onKeyDown={(e) => e.key === "Enter" && fetchStatus()}
                  className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
            </div>

            {/* Live formatted preview */}
            {formattedRef && (
              <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
                <ArrowRight className="h-3 w-3 shrink-0" />
                Will search for: <span className="font-semibold text-slate-700 ml-1">{formattedRef}</span>
              </div>
            )}

            {/* Validation error */}
            {validationError && (
              <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {validationError}
              </div>
            )}

            {/* Search button */}
            <button
              onClick={fetchStatus}
              disabled={searching}
              className="w-full flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors shadow-sm"
            >
              {searching ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Fetching status…
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  Get Case Status
                </>
              )}
            </button>
          </div>

          {/* ── Error banner ───────────────────────────────────────────────── */}
          {error && (
            <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {/* ── Result card ────────────────────────────────────────────────── */}
          {result?.found && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">

              {/* Result header */}
              <div className="bg-slate-900 px-5 py-4 flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs text-slate-400 font-medium uppercase tracking-wide">Case</p>
                  <p className="text-lg font-bold text-white mt-0.5">{result.case_number}</p>
                  {result.cnr_number && (
                    <p className="text-xs text-slate-400 mt-0.5">CNR: {result.cnr_number}</p>
                  )}
                </div>
                <div className="text-right shrink-0">
                  {result.status_text && (
                    <span className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full ${
                      result.status_text.toLowerCase().includes("disposed")
                        ? "bg-green-500/20 text-green-300"
                        : "bg-amber-500/20 text-amber-300"
                    }`}>
                      {result.status_text}
                    </span>
                  )}
                  {result.stage && (
                    <p className="text-xs text-slate-400 mt-1.5">{result.stage}</p>
                  )}
                </div>
              </div>

              {/* Next hearing — highlighted */}
              {result.next_hearing_date && (
                <div className="flex items-center gap-3 px-5 py-3 bg-indigo-50 border-b border-indigo-100">
                  <Calendar className="h-4 w-4 text-indigo-500 shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-indigo-600">Next Hearing</p>
                    <p className="text-sm font-bold text-indigo-900">{formatDate(result.next_hearing_date)}</p>
                  </div>
                </div>
              )}

              <div className="px-5 py-4 space-y-5">

                {/* Parties */}
                {(result.petitioner_name || result.respondent_name) && (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Users className="h-4 w-4 text-slate-400" />
                      <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">Parties</p>
                    </div>
                    <div className="space-y-0">
                      <InfoRow label="Petitioner" value={result.petitioner_name} />
                      <InfoRow label="Petitioner Advocates" value={formatList(result.petitioner_advocates)} />
                      <InfoRow label="Respondent" value={result.respondent_name} />
                      <InfoRow label="Respondent Advocates" value={formatList(result.respondent_advocates)} />
                    </div>
                  </div>
                )}

                {/* Case details */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="h-4 w-4 text-slate-400" />
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">Case Details</p>
                  </div>
                  <div className="space-y-0">
                    <InfoRow label="Case Type" value={result.case_type} />
                    <InfoRow label="Filing Number" value={result.filing_number} />
                    <InfoRow label="Filing Date" value={formatDate(result.filing_date)} />
                    <InfoRow label="Registration No." value={result.registration_number} />
                    <InfoRow label="Registration Date" value={formatDate(result.registration_date)} />
                    <InfoRow label="E-File No." value={result.efile_number} />
                    <InfoRow label="First Hearing" value={formatDate(result.first_hearing_date)} />
                    <InfoRow label="Last Order Date" value={formatDate(result.last_order_date)} />
                    <InfoRow label="Coram" value={result.coram} />
                    <InfoRow label="Acts" value={formatList(result.acts)} />
                    <InfoRow label="Sections" value={formatList(result.sections)} />
                  </div>
                </div>

                {/* Last listed */}
                {(result.last_listed_date || result.last_listed_bench) && (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Gavel className="h-4 w-4 text-slate-400" />
                      <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">Last Listed</p>
                    </div>
                    <div className="space-y-0">
                      <InfoRow label="Date" value={formatDate(result.last_listed_date)} />
                      <InfoRow label="Bench" value={result.last_listed_bench} />
                      <InfoRow label="List" value={result.last_listed_list} />
                      <InfoRow label="Item No." value={result.last_listed_item} />
                    </div>
                  </div>
                )}

                {/* Hearing history */}
                {result.hearing_history && result.hearing_history.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Calendar className="h-4 w-4 text-slate-400" />
                      <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                        Hearing History ({result.hearing_history.length})
                      </p>
                    </div>
                    <div className="overflow-auto rounded-lg border border-slate-100">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-50">
                          <tr>
                            {Object.keys(result.hearing_history[0]).map((k) => (
                              <th key={k} className="px-3 py-2 text-left font-semibold text-slate-500 whitespace-nowrap border-b border-slate-100">
                                {k}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.hearing_history.map((row, i) => (
                            <tr key={i} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50">
                              {Object.values(row).map((v, j) => (
                                <td key={j} className="px-3 py-2 text-slate-600 whitespace-nowrap">
                                  {String(v ?? "-")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Summary */}
                {result.summary && (
                  <div className="rounded-lg bg-slate-50 border border-slate-100 px-4 py-3 text-sm text-slate-700 leading-relaxed">
                    {result.summary}
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {result.full_details_url && (
                    <a
                      href={result.full_details_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-sm font-medium text-slate-700 border border-slate-200 bg-white hover:bg-slate-50 px-4 py-2 rounded-lg transition-colors"
                    >
                      View on KHC Portal
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}

                  {addedOk ? (
                    <div className="flex items-center gap-1.5 text-sm font-medium text-green-700 bg-green-50 border border-green-200 px-4 py-2 rounded-lg">
                      <CheckCircle2 className="h-4 w-4" />
                      Added to dashboard
                    </div>
                  ) : (
                    <button
                      onClick={onAddToDashboard}
                      disabled={adding}
                      className="flex items-center gap-1.5 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg transition-colors shadow-sm"
                    >
                      {adding ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <PlusCircle className="h-4 w-4" />
                      )}
                      Add to Dashboard
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

        </div>
      </div>

      <ChatWidget page="global" />
    </div>
  );
}
