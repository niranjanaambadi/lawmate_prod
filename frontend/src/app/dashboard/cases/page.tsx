"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { deleteCase, listCases, type CaseListItem } from "@/lib/api";
import { ChevronDown, ChevronUp, ChevronsUpDown, Trash2 } from "lucide-react";

function formatDate(value: string | null) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString();
}

function statusBadgeClass(status: string) {
  const v = (status || "").toLowerCase();
  if (v === "pending") return "bg-amber-100 text-amber-800 border-amber-200";
  if (v === "disposed") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (v === "failed") return "bg-rose-100 text-rose-800 border-rose-200";
  if (v === "completed") return "bg-blue-100 text-blue-800 border-blue-200";
  return "bg-slate-100 text-slate-700 border-slate-200";
}

function roleBadgeClass(role: string) {
  const v = (role || "").toLowerCase();
  if (v === "petitioner") return "bg-indigo-100 text-indigo-800 border-indigo-200";
  if (v === "respondent") return "bg-cyan-100 text-cyan-800 border-cyan-200";
  if (v === "amicus") return "bg-violet-100 text-violet-800 border-violet-200";
  return "bg-slate-100 text-slate-700 border-slate-200";
}

function SortIcon({ field, sortBy, sortDir }: { field: string; sortBy: string; sortDir: string }) {
  if (sortBy !== field) return <ChevronsUpDown className="ml-1 inline h-3.5 w-3.5 text-slate-300" />;
  return sortDir === "asc"
    ? <ChevronUp className="ml-1 inline h-3.5 w-3.5 text-indigo-500" />
    : <ChevronDown className="ml-1 inline h-3.5 w-3.5 text-indigo-500" />;
}

export default function CasesPage() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [rows, setRows] = useState<CaseListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(Number(searchParams.get("page") || "1"));
  const [perPage] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);

  const [qInput, setQInput] = useState(searchParams.get("q") || "");
  const [status, setStatus] = useState(searchParams.get("status") || "all");
  const [partyRole, setPartyRole] = useState(searchParams.get("party_role") || "all");
  const [sortBy, setSortBy] = useState(searchParams.get("sort_by") || "updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">(
    (searchParams.get("sort_dir") as "asc" | "desc") || "desc"
  );

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const queryString = useMemo(() => {
    const q = new URLSearchParams();
    q.set("page", String(page));
    if (qInput.trim()) q.set("q", qInput.trim());
    if (status !== "all") q.set("status", status);
    if (partyRole !== "all") q.set("party_role", partyRole);
    q.set("sort_by", sortBy);
    q.set("sort_dir", sortDir);
    return q.toString();
  }, [page, qInput, status, partyRole, sortBy, sortDir]);

  useEffect(() => {
    router.replace(`/dashboard/cases?${queryString}`);
  }, [queryString, router]);

  useEffect(() => {
    if (!token) return;

    let ignore = false;
    setLoading(true);
    setError(null);

    listCases(
      {
        page,
        perPage,
        q: qInput.trim() || undefined,
        status: status === "all" ? undefined : status,
        partyRole: partyRole === "all" ? undefined : partyRole,
        sortBy,
        sortDir,
      },
      token
    )
      .then((res) => {
        if (ignore) return;
        setRows(res.items || []);
        setTotal(res.total || 0);
      })
      .catch((e) => {
        if (ignore) return;
        setError(e instanceof Error ? e.message : "Failed to load cases");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [token, page, perPage, qInput, status, partyRole, sortBy, sortDir]);

  const onApplyFilters = () => {
    setPage(1);
  };

  const toggleSort = (field: string) => {
    if (sortBy === field) {
      setSortDir((v) => (v === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(field);
    setSortDir("asc");
  };

  const onDeleteCase = async (caseId: string, caseLabel: string) => {
    if (!token) return;
    const confirmed = window.confirm(
      `Delete case ${caseLabel}? This will remove it from your cases list.`
    );
    if (!confirmed) return;

    try {
      setDeletingCaseId(caseId);
      await deleteCase(caseId, token);
      setRows((prev) => prev.filter((row) => row.id !== caseId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete case");
    } finally {
      setDeletingCaseId(null);
    }
  };

  const selectClass =
    "h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all appearance-none";

  return (
    <div className="space-y-6">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Cases</h1>
        <p className="mt-1 text-sm text-slate-500">Synced cases from DigiCourt</p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <div className="grid gap-3 md:grid-cols-4">
            <Input
              placeholder="Search case no, e-filing, party..."
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onApplyFilters()}
            />
            <select
              className={selectClass}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="disposed">Disposed</option>
            </select>
            <select
              className={selectClass}
              value={partyRole}
              onChange={(e) => setPartyRole(e.target.value)}
            >
              <option value="all">All roles</option>
              <option value="petitioner">Petitioner</option>
              <option value="respondent">Respondent</option>
              <option value="amicus">Amicus</option>
            </select>
            <Button onClick={onApplyFilters}>Apply filters</Button>
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <div className="max-h-[70vh] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 border-b border-slate-100 bg-slate-50">
                <tr>
                  <th className="px-4 py-3 text-left">
                    <button
                      className="inline-flex items-center text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-900"
                      onClick={() => toggleSort("case_number")}
                    >
                      Case No
                      <SortIcon field="case_number" sortBy={sortBy} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Case Name
                  </th>
                  <th className="px-4 py-3 text-left">
                    <button
                      className="inline-flex items-center text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-900"
                      onClick={() => toggleSort("efiling_date")}
                    >
                      E-Filing Date
                      <SortIcon field="efiling_date" sortBy={sortBy} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-left">
                    <button
                      className="inline-flex items-center text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-900"
                      onClick={() => toggleSort("status")}
                    >
                      Status
                      <SortIcon field="status" sortBy={sortBy} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Role
                  </th>
                  <th className="px-4 py-3 text-left">
                    <button
                      className="inline-flex items-center text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-900"
                      onClick={() => toggleSort("next_hearing_date")}
                    >
                      Next Hearing
                      <SortIcon field="next_hearing_date" sortBy={sortBy} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-left">
                    <button
                      className="inline-flex items-center text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-900"
                      onClick={() => toggleSort("last_synced_at")}
                    >
                      Last Synced
                      <SortIcon field="last_synced_at" sortBy={sortBy} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {loading && (
                  <tr>
                    <td className="px-4 py-8 text-center text-slate-400" colSpan={8}>
                      <div className="flex items-center justify-center gap-2">
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                        Loading cases...
                      </div>
                    </td>
                  </tr>
                )}
                {!loading && error && (
                  <tr>
                    <td className="px-4 py-8 text-center text-rose-600" colSpan={8}>
                      {error}
                    </td>
                  </tr>
                )}
                {!loading && !error && rows.length === 0 && (
                  <tr>
                    <td className="px-4 py-8 text-center text-slate-400" colSpan={8}>
                      No cases found.
                    </td>
                  </tr>
                )}
                {!loading &&
                  !error &&
                  rows.map((c) => (
                    <tr key={c.id} className="transition-colors hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <Link
                          href={`/dashboard/cases/${c.id}`}
                          className="font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
                        >
                          {c.case_number || c.efiling_number}
                        </Link>
                      </td>
                      <td className="max-w-[200px] truncate px-4 py-3 text-slate-700">
                        <Link href={`/dashboard/cases/${c.id}`} className="hover:underline">
                          {c.petitioner_name} vs {c.respondent_name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{formatDate(c.efiling_date)}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize ${statusBadgeClass(c.status)}`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize ${roleBadgeClass(c.party_role)}`}
                        >
                          {c.party_role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{formatDate(c.next_hearing_date)}</td>
                      <td className="px-4 py-3 text-slate-600">{formatDate(c.last_synced_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => onDeleteCase(c.id, c.case_number || c.efiling_number)}
                          disabled={deletingCaseId === c.id}
                          className="inline-flex items-center justify-center rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
                          title="Delete case"
                          aria-label="Delete case"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
            <p className="text-sm text-slate-500">
              Page {page} of {totalPages} &middot; {total} total cases
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
