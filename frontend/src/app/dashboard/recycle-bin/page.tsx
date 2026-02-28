"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { listDeletedCases, restoreCase, type CaseListItem } from "@/lib/api";
import { RotateCcw, Trash2 } from "lucide-react";

function formatDate(value: string | null) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString();
}

export default function RecycleBinPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<CaseListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const load = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listDeletedCases({ page: 1, perPage: 100 }, token);
      setRows(res.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load recycle bin");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [token]);

  const onRestore = async (caseId: string, label: string) => {
    if (!token) return;
    const confirmed = window.confirm(`Restore case ${label}?`);
    if (!confirmed) return;

    try {
      setRestoringId(caseId);
      await restoreCase(caseId, token);
      setRows((prev) => prev.filter((r) => r.id !== caseId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to restore case");
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trash2 className="h-5 w-5" />
            Recycle Bin
          </CardTitle>
          <CardDescription>
            Deleted items are kept for 90 days, then auto-purged.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-md border bg-white max-h-[70vh]">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-left sticky top-0 z-10">
                <tr>
                  <th className="px-3 py-2 font-semibold">Case No</th>
                  <th className="px-3 py-2 font-semibold">Case Name</th>
                  <th className="px-3 py-2 font-semibold">Deleted At</th>
                  <th className="px-3 py-2 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td className="px-3 py-6 text-center text-slate-500" colSpan={4}>Loading deleted items...</td>
                  </tr>
                )}
                {!loading && error && (
                  <tr>
                    <td className="px-3 py-6 text-center text-rose-600" colSpan={4}>{error}</td>
                  </tr>
                )}
                {!loading && !error && rows.length === 0 && (
                  <tr>
                    <td className="px-3 py-6 text-center text-slate-500" colSpan={4}>Recycle bin is empty.</td>
                  </tr>
                )}
                {!loading && !error && rows.map((c) => (
                  <tr key={c.id} className="border-t hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium text-slate-900">{c.case_number || c.efiling_number}</td>
                    <td className="px-3 py-2">{c.petitioner_name} vs {c.respondent_name}</td>
                    <td className="px-3 py-2 text-slate-600">{formatDate(c.updated_at)}</td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={restoringId === c.id}
                        onClick={() => onRestore(c.id, c.case_number || c.efiling_number)}
                        className="inline-flex items-center gap-1"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Restore
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
