const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function corsHeaders(origin, allowedOrigin) {
  const allow = !allowedOrigin || origin === allowedOrigin ? (origin || allowedOrigin || "*") : allowedOrigin;
  return {
    "access-control-allow-origin": allow,
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,authorization",
    "access-control-max-age": "86400",
    "vary": "Origin",
  };
}

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...extra },
  });
}

function backendList(env) {
  return String(env.BACKEND_URLS || "")
    .split(",")
    .map((x) => x.trim().replace(/\/$/, ""))
    .filter(Boolean);
}

async function fetchWithTimeout(request, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(request, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function checkBackend(base) {
  try {
    const response = await fetchWithTimeout(
      new Request(`${base}/ready`, { method: "GET", headers: { accept: "application/json" } }),
      3500,
    );
    return { ok: response.ok, status: response.status };
  } catch (_) {
    return { ok: false, status: 0 };
  }
}

async function proxyToBackend(request, base, index) {
  const incoming = new URL(request.url);
  const target = new URL(base);
  target.pathname = incoming.pathname;
  target.search = incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-uvt-router", "cloudflare");

  const outbound = new Request(target.toString(), {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.clone().body,
    redirect: "follow",
  });

  const response = await fetchWithTimeout(outbound, 120000);
  const responseHeaders = new Headers(response.headers);
  responseHeaders.set("x-uvt-backend", String(index + 1));

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("origin") || "";
    const cors = corsHeaders(origin, env.ALLOWED_ORIGIN);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    if (url.pathname === "/health" || url.pathname === "/") {
      return json(
        {
          status: "ok",
          service: "universal-transcriber-router",
          backends_configured: backendList(env).length,
        },
        200,
        cors,
      );
    }

    if (url.pathname === "/backends") {
      const bases = backendList(env);
      const checks = await Promise.all(bases.map(checkBackend));
      return json(
        {
          status: "ok",
          backends: checks.map((result, i) => ({ index: i + 1, ...result })),
        },
        200,
        cors,
      );
    }

    if (!url.pathname.startsWith("/api/") && url.pathname !== "/ready") {
      return json({ detail: "Not found" }, 404, cors);
    }

    const bases = backendList(env);
    if (!bases.length) {
      return json({ detail: "No transcription backend is configured yet." }, 503, cors);
    }

    let lastError = null;

    for (let i = 0; i < bases.length; i += 1) {
      try {
        const response = await proxyToBackend(request, bases[i], i);
        const headers = new Headers(response.headers);
        Object.entries(cors).forEach(([k, v]) => headers.set(k, v));

        if (response.status < 500 && response.status !== 429) {
          return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers,
          });
        }

        lastError = `backend ${i + 1} returned ${response.status}`;
      } catch (error) {
        lastError = error?.message || `backend ${i + 1} failed`;
      }
    }

    return json(
      {
        detail: "All configured transcription backends are unavailable.",
        router_error: lastError,
      },
      503,
      cors,
    );
  },
};
