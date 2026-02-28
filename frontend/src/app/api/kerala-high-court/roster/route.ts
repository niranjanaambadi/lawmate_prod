import { NextRequest, NextResponse } from "next/server";

export const revalidate = 300;

type BackendRosterData = {
  label: string;
  effectiveDate: string | null;
  sourcePage: string;
  sourcePdfUrl: string;
  bucket: string;
  s3Key: string;
  archivalKey: string;
  checksum: string;
  fetchedAt: string;
  lastCheckedAt: string;
  signedUrl: string;
};

function getBackendBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
}

export async function GET(request: NextRequest) {
  const refresh = request.nextUrl.searchParams.get("refresh") === "1";
  const endpoint = refresh ? "/api/v1/roster/sync" : "/api/v1/roster/latest";
  const url = `${getBackendBaseUrl()}${endpoint}`;

  try {
    const res = await fetch(url, {
      method: refresh ? "POST" : "GET",
      headers: { Accept: "application/json" },
      next: { revalidate },
    });
    const body = (await res.json()) as { ok: boolean; data?: BackendRosterData; detail?: string };
    if (!res.ok || !body.ok || !body.data) {
      throw new Error(body.detail || "Backend roster API failed");
    }

    const d = body.data;
    return NextResponse.json({
      ok: true,
      fetchedAt: d.lastCheckedAt || d.fetchedAt,
      sourcePages: [d.sourcePage],
      latest: {
        label: d.label,
        parsedDate: d.effectiveDate,
        sourcePage: d.sourcePage,
        pdfUrl: d.signedUrl,
      },
      entries: [
        {
          label: d.label,
          parsedDate: d.effectiveDate,
          sourcePage: d.sourcePage,
          pdfUrl: d.signedUrl,
        },
      ],
      storage: {
        bucket: d.bucket,
        key: d.s3Key,
        archivalKey: d.archivalKey,
        checksum: d.checksum,
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        entries: [],
        sourcePages: [],
        error: error instanceof Error ? error.message : "Failed to fetch roster",
      },
      { status: 502 }
    );
  }
}
