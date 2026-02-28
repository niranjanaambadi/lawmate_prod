import { NextRequest, NextResponse } from "next/server";

const EXACT_ALLOWED_HOSTS = new Set([
  "hckinfo.keralacourts.in",
  "ecourts.kerala.gov.in",
]);

function isAllowedHost(hostname: string): boolean {
  if (EXACT_ALLOWED_HOSTS.has(hostname)) return true;
  // S3 presigned URLs (virtual host and regional endpoints).
  if (hostname.endsWith(".amazonaws.com")) return true;
  return false;
}

export async function GET(request: NextRequest) {
  const target = request.nextUrl.searchParams.get("url")?.trim();
  if (!target) {
    return NextResponse.json({ detail: "Missing url query param" }, { status: 400 });
  }

  let parsed: URL;
  try {
    parsed = new URL(target);
  } catch {
    return NextResponse.json({ detail: "Invalid url" }, { status: 400 });
  }

  if (parsed.protocol !== "https:") {
    return NextResponse.json({ detail: "Only https URLs are allowed" }, { status: 400 });
  }

  if (!isAllowedHost(parsed.hostname)) {
    return NextResponse.json({ detail: "Host not allowed for proxy" }, { status: 403 });
  }

  try {
    const res = await fetch(parsed.toString(), {
      method: "GET",
      cache: "no-store",
      headers: {
        Accept: "application/pdf,*/*",
        "User-Agent": "Lawmate-PDF-Proxy/1.0",
      },
    });

    if (!res.ok) {
      return NextResponse.json({ detail: `Upstream responded ${res.status}` }, { status: 502 });
    }

    const contentType = res.headers.get("content-type") || "application/pdf";
    const body = await res.arrayBuffer();

    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed fetching upstream PDF";
    return NextResponse.json({ detail: message }, { status: 502 });
  }
}
