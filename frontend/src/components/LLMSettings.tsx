/* ── LLM Settings Dialog ──────────────── */
import { useState, useEffect } from "react";

export default function LLMSettings({ onClose }: { onClose: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/v1/champion/llm-settings")
      .then((r) => r.json())
      .then((d) => {
        setBaseUrl(d.base_url || "https://api.deepseek.com");
        setModel(d.model || "deepseek-v4-flash");
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      const r = await fetch("/api/v1/champion/llm-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model }),
      });
      if (r.ok) { setMsg("✅ 已保存"); setTimeout(onClose, 1200); }
      else { setMsg("❌ 保存失败"); }
    } catch { setMsg("❌ 保存失败"); }
    setSaving(false);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>🤖 AI 设置</h3>
        <div className="edit-row">
          <span className="edit-label">API Key</span>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            placeholder="输入你的 API Key" />
        </div>
        <div className="edit-row">
          <span className="edit-label">Base URL</span>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com" />
        </div>
        <div className="edit-row">
          <span className="edit-label">模型</span>
          <input value={model} onChange={(e) => setModel(e.target.value)}
            placeholder="deepseek-v4-flash" />
        </div>
        {msg && <p style={{ fontSize: "0.75rem", marginBottom: "0.3rem" }}>{msg}</p>}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="action-btn" onClick={save} disabled={saving}>
            {saving ? "保存中..." : "保存"}
          </button>
          <button className="action-btn" onClick={onClose}>取消</button>
        </div>
      </div>
    </div>
  );
}
