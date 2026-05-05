import { useEffect, useState } from "react";

function studioToken() {
  return localStorage.getItem("epistoraStudioToken") || "";
}

function headers(extra = {}) {
  const token = studioToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: headers(options.headers || {}),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json();
}

export default function AIChatSettings() {
  const [form, setForm] = useState({ backend_type: "api", api_key: "", base_url: "", model_name: "" });
  const [maskedKey, setMaskedKey] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api("/studio/chat/settings")
      .then((settings) => {
        setForm({
          backend_type: settings.backend_type || "api",
          api_key: "",
          base_url: settings.base_url || "",
          model_name: settings.model_name || "",
        });
        setMaskedKey(settings.api_key || "");
      })
      .catch((err) => setStatus(err.message));
  }, []);

  async function save(event) {
    event.preventDefault();
    setStatus("Saving...");
    try {
      const settings = await api("/studio/chat/settings", {
        method: "PUT",
        body: JSON.stringify(form),
      });
      setForm((prev) => ({ ...prev, api_key: "" }));
      setMaskedKey(settings.api_key || "");
      setStatus("Chat settings saved.");
    } catch (err) {
      setStatus(err.message);
    }
  }

  return (
    <section className="card">
      <h2>AI Backend</h2>
      <form className="stack" onSubmit={save}>
        <label className="settings-label">
          Backend type
          <select value={form.backend_type} onChange={(event) => setForm({ ...form, backend_type: event.target.value })}>
            <option value="api">API</option>
            <option value="opencode">opencode</option>
            <option value="claude_code">Claude Code</option>
            <option value="codex">Codex</option>
          </select>
        </label>
        <label className="settings-label">
          API key
          <input
            type="password"
            placeholder={maskedKey || "Write-only API key"}
            value={form.api_key}
            onChange={(event) => setForm({ ...form, api_key: event.target.value })}
          />
        </label>
        <label className="settings-label">
          Base URL
          <input
            type="text"
            placeholder="OpenAI-compatible base URL"
            value={form.base_url}
            onChange={(event) => setForm({ ...form, base_url: event.target.value })}
          />
        </label>
        <label className="settings-label">
          Model name
          <input
            type="text"
            placeholder="gpt-4o-mini"
            value={form.model_name}
            onChange={(event) => setForm({ ...form, model_name: event.target.value })}
          />
        </label>
        <button type="submit">Save chat backend</button>
        <p className="caption">{status}</p>
      </form>
    </section>
  );
}
