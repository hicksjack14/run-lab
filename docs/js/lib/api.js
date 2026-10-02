// In the published snapshot there is no server: GET requests are answered from files in data/ and writes are refused.
export const isStatic = document.querySelector('meta[name="runlab-static"]')?.content === "1";

function staticPath(path) {
  const clean = path.split("?")[0];
  if (clean === "/api/plan.ics") return "data/plan.ics";
  const run = clean.match(/^\/api\/runs\/(.+)$/);
  if (run) return `data/runs/${run[1]}.json`;
  return `data${clean.slice(4)}.json`;          // "/api/runs" -> "data/runs.json"
}

async function request(method, path, body) {
  if (isStatic) {
    if (method !== "GET") {
      const err = new Error("This is the read-only copy. Make changes in Run Lab on your computer, then update the snapshot.");
      err.status = 405;
      throw err;
    }
    path = staticPath(path);
  }
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON response */ }
  if (!res.ok) {
    const err = new Error((data && data.error) || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body || {}),
  del: (path) => request("DELETE", path),
};
