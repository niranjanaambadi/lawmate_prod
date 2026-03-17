"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, ExternalLink, FileText, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type RosterEntry = {
  label: string;
  pdfUrl: string;
  sourcePage: string;
  parsedDate: string | null;
};

type RosterApiResponse = {
  ok: boolean;
  fetchedAt?: string;
  sourcePages: string[];
  latest?: RosterEntry;
  entries: RosterEntry[];
  error?: string;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "Date not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date not available";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function RosterPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RosterApiResponse | null>(null);
  const [selectedUrl, setSelectedUrl] = useState<string>("");
  const [htmlContent, setHtmlContent] = useState<string>("");
  const [htmlLoading, setHtmlLoading] = useState(true);

  const loadRoster = async (forceRefresh = false) => {
    if (forceRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `/api/kerala-high-court/roster${forceRefresh ? "?refresh=1" : ""}`,
        { cache: "no-store" },
      );
      const body = (await res.json()) as RosterApiResponse;
      if (!res.ok || !body.ok) {
        throw new Error(body.error || "Unable to load roster");
      }
      setData(body);
      setSelectedUrl(body.latest?.pdfUrl || body.entries[0]?.pdfUrl || "");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load roster";
      setError(message);
      setData(null);
      setSelectedUrl("");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadHtml = async () => {
    setHtmlLoading(true);
    setHtmlContent("");
    try {
      const res = await fetch("/api/kerala-high-court/roster/html", { cache: "no-store" });
      if (res.ok) {
        setHtmlContent(await res.text());
      }
    } catch {
      // Silently degrade — the "Open official PDF" button remains available.
    } finally {
      setHtmlLoading(false);
    }
  };

  const handleRefresh = async () => {
    // Run sequentially: sync first (generates new HTML), then reload HTML.
    await loadRoster(true);
    await loadHtml();
  };

  useEffect(() => {
    void loadRoster();
    void loadHtml();
  }, []);

  const selectedRoster = useMemo(
    () => data?.entries.find((e) => e.pdfUrl === selectedUrl) ?? data?.latest ?? null,
    [data, selectedUrl],
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="mb-2 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white">
            <FileText className="h-5 w-5" />
          </div>
          <CardTitle>Kerala High Court Roster</CardTitle>
          <CardDescription>
            Shows the latest roster available on the High Court website.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              onClick={() => void handleRefresh()}
              disabled={refreshing || loading}
            >
              <RefreshCcw className="mr-2 h-4 w-4" />
              {refreshing ? "Refreshing..." : "Refresh"}
            </Button>
            <Button variant="outline" asChild>
              <Link href="/dashboard">Back to dashboard</Link>
            </Button>
          </div>

          {data?.fetchedAt ? (
            <p className="text-sm text-muted-foreground">
              Last checked: {new Date(data.fetchedAt).toLocaleString()}
            </p>
          ) : null}

          {data?.entries.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="roster-select" className="text-sm font-medium text-slate-700">
                  Available roster documents
                </label>
                <select
                  id="roster-select"
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                  value={selectedUrl}
                  onChange={(e) => setSelectedUrl(e.target.value)}
                >
                  {data.entries.map((entry) => (
                    <option key={entry.pdfUrl} value={entry.pdfUrl}>
                      {entry.parsedDate ? `${formatDate(entry.parsedDate)} — ` : ""}
                      {entry.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2 rounded-md border bg-slate-50 p-3">
                <p className="text-sm font-medium">Selected roster date</p>
                <p className="text-sm text-muted-foreground">
                  {formatDate(selectedRoster?.parsedDate)}
                </p>
              </div>
            </div>
          ) : null}

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <p className="flex items-center gap-2 font-medium">
                <AlertCircle className="h-4 w-4" />
                Unable to load latest roster
              </p>
              <p className="mt-1">{error}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>Roster document</CardTitle>
          <CardDescription>
            Use Ctrl+F / ⌘F inside the document to search. The original PDF is also available below.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {selectedRoster ? (
            <div className="flex flex-wrap gap-3">
              <Button asChild>
                <a href={selectedRoster.pdfUrl} target="_blank" rel="noopener noreferrer">
                  Open official PDF
                  <ExternalLink className="ml-2 h-4 w-4" />
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href={selectedRoster.sourcePage} target="_blank" rel="noopener noreferrer">
                  Open source page
                  <ExternalLink className="ml-2 h-4 w-4" />
                </a>
              </Button>
            </div>
          ) : null}

          <div className="h-[72vh] min-h-[500px] overflow-hidden rounded-md border bg-slate-100">
            {loading || htmlLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Loading roster...
              </div>
            ) : htmlContent ? (
              <iframe
                srcDoc={htmlContent}
                sandbox="allow-scripts"
                className="h-full w-full border-0"
                title="Kerala High Court Roster"
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
                <p>Roster document view not yet available.</p>
                {selectedRoster ? (
                  <Button asChild size="sm">
                    <a href={selectedRoster.pdfUrl} target="_blank" rel="noopener noreferrer">
                      Open official PDF
                      <ExternalLink className="ml-2 h-4 w-4" />
                    </a>
                  </Button>
                ) : null}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
