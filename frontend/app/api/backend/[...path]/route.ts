import { NextRequest } from "next/server";

const BACKEND_API_BASE_URL = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000/api";

let cachedToken: string | null = null;
let cachedTokenExpiresAt = 0;
let pendingToken: Promise<string | null> | null = null;

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function getAccessToken(): Promise<string | null> {
  const staticToken = process.env.API_BEARER_TOKEN;
  if (staticToken) {
    return staticToken;
  }
  if (cachedToken && cachedTokenExpiresAt - Date.now() > 60_000) {
    return cachedToken;
  }
  if (pendingToken) {
    return pendingToken;
  }

  pendingToken = (async () => {
    const email = process.env.DEMO_USER_EMAIL ?? "demo@3x.local";
    const password =
      process.env.DEMO_USER_PASSWORD ?? (process.env.NODE_ENV === "production" ? "" : "demo-password");
    if (!password) {
      return null;
    }

    try {
      const response = await fetch(`${BACKEND_API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        cache: "no-store",
      });
      if (!response.ok) {
        return null;
      }
      const body = (await response.json()) as { access_token: string };
      cachedToken = body.access_token;
      cachedTokenExpiresAt = Date.now() + 10 * 60 * 1000;
      return cachedToken;
    } finally {
      pendingToken = null;
    }
  })();

  return pendingToken;
}

function filteredResponseHeaders(source: Headers): Headers {
  const headers = new Headers(source);
  for (const key of ["content-encoding", "content-length", "transfer-encoding"]) {
    headers.delete(key);
  }
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  const targetUrl = new URL(`${BACKEND_API_BASE_URL}/${path.join("/")}`);
  targetUrl.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  if (!headers.has("authorization")) {
    const token = await getAccessToken();
    if (token) {
      headers.set("authorization", `Bearer ${token}`);
    }
  }

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();

  let response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });

  if (response.status === 401) {
    cachedToken = null;
    cachedTokenExpiresAt = 0;
    const token = await getAccessToken();
    if (token) {
      headers.set("authorization", `Bearer ${token}`);
      response = await fetch(targetUrl, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
      });
    }
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: filteredResponseHeaders(response.headers),
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
