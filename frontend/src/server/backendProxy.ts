/** Proxy do painel para a API. O hostname é o serviço Docker, não o browser. */
export const DEFAULT_BACKEND_INTERNAL_URL = "http://backend:8000/api/v1";

const HOP_BY_HOP = new Set([
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
  "keep-alive",
]);

export function backendBaseUrl(): string {
  const raw = process.env.BACKEND_INTERNAL_URL || DEFAULT_BACKEND_INTERNAL_URL;
  return raw.replace(/\/+$/, "");
}

export async function proxyBackend(request: Request, path: string[]): Promise<Response> {
  const url = new URL(request.url);
  const target = `${backendBaseUrl()}/${path.join("/")}${url.search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const accept = request.headers.get("accept");
  if (accept) headers.set("accept", accept);

  const token = process.env.TRADER_API_TOKEN;
  if (token) {
    headers.set("authorization", `Bearer ${token}`);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const outgoing = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) outgoing.set(key, value);
  });
  return new Response(upstream.body, { status: upstream.status, headers: outgoing });
}
