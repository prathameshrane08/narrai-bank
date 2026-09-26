import { type NextRequest, NextResponse } from "next/server";

import { API_URL, checkWriteRequest, readSession } from "../../lib/server/session";

/**
 * Forwards the customer app's calls to the NarrAI API with the session from the httpOnly cookie.
 * Only the customer-facing endpoints are reachable this way; everything else is refused.
 */
const ALLOWED: Record<string, RegExp[]> = {
  GET: [/^months$/, /^dashboard$/, /^story$/, /^budgets$/, /^chat\/suggestions$/, /^me\/export$/],
  POST: [/^chat$/],
  PUT: [/^budgets\/[^/]{1,60}$/],
  DELETE: [/^budgets\/[^/]{1,60}$/],
};

// Response headers worth passing through to the page.
const PASS_THROUGH = ["content-type", "content-disposition", "retry-after", "x-request-id"];

async function forward(request: NextRequest, ctx: RouteContext<"/bff/[...path]">) {
  const path = (await ctx.params).path.map(encodeURIComponent).join("/");
  if (!(ALLOWED[request.method] ?? []).some((pattern) => pattern.test(path))) {
    return NextResponse.json({ detail: "Not found." }, { status: 404 });
  }
  if (request.method !== "GET") {
    const refused = checkWriteRequest(request);
    if (refused) return NextResponse.json({ detail: refused }, { status: 403 });
  }

  const session = await readSession();
  if (!session) {
    return NextResponse.json({ detail: "Sign in required." }, { status: 401 });
  }

  const upstream = await fetch(`${API_URL}/api/${path}${request.nextUrl.search}`, {
    method: request.method,
    headers: {
      Authorization: `Bearer ${session.token}`,
      "X-NarrAI-Tenant": session.tenant,
      ...(request.method === "GET" ? {} : { "Content-Type": "application/json" }),
      ...(request.headers.get("x-request-id") ? { "X-Request-ID": request.headers.get("x-request-id")! } : {}),
    },
    body: request.method === "GET" ? undefined : await request.text(),
    cache: "no-store",
  });

  const headers = new Headers({ "Cache-Control": "no-store" });
  for (const name of PASS_THROUGH) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers });
}

export { forward as DELETE, forward as GET, forward as POST, forward as PUT };
