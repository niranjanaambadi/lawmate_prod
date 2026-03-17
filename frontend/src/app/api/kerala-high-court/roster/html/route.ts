import { NextResponse } from "next/server";

function getBackendBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
}

/**
 * GET /api/kerala-high-court/roster/html
 *
 * Proxies the pre-generated HTML roster from the backend.
 * Always fetches fresh from the backend (no ISR cache) so that a manual
 * Refresh on the roster page immediately reflects a newly synced PDF.
 */
export async function GET(): Promise<NextResponse> {
  const url = `${getBackendBaseUrl()}/api/v1/roster/html`;

  try {
    const res = await fetch(url, {
      headers: { Accept: "text/html" },
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Roster HTML not yet available" },
        { status: res.status },
      );
    }

    const html = await res.text();
    return new NextResponse(html, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to fetch roster HTML" },
      { status: 502 },
    );
  }
}
