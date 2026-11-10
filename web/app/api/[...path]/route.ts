import { NextRequest, NextResponse } from "next/server";

// Forwards /api/* to the FastAPI service. API_URL is read at runtime, so one
// container image works locally and on Cloud Run, and the browser never needs CORS.
const API_URL = (process.env.API_URL ?? "http://localhost:8080").replace(/\/$/, "");

export const dynamic = "force-dynamic";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = `${API_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const init: RequestInit = {
    method: req.method,
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
    cache: "no-store",
  };
  // Raw bytes, so image uploads (multipart) pass through untouched.
  if (req.method !== "GET" && req.method !== "HEAD") init.body = await req.arrayBuffer();

  try {
    const res = await fetch(url, init);
    if (res.status === 204) return new NextResponse(null, { status: 204 });
    return new NextResponse(await res.arrayBuffer(), {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "BrandPilot can't reach its server right now. Check that the API is running and API_URL is set." },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
