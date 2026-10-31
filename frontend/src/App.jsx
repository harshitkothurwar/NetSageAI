import { useCallback, useEffect, useState } from "react";

const SAMPLE_OUTPUT = `Interface                  IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0         192.168.1.1     YES NVRAM  administratively down down
GigabitEthernet0/1         192.168.1.1     YES NVRAM  up                    up
GigabitEthernet0/2         10.0.0.5/32     YES NVRAM  up                    up
Loopback0                  10.255.255.1    YES NVRAM  up                    up
!
interface GigabitEthernet0/3
 ip address 172.16.0.1
`;

const FLAG_LABELS = [
  ["duplicate_ip", "Duplicate IP"],
  ["admin_down", "Administratively down"],
  ["missing_mask", "Missing subnet mask"],
  ["slash32_anomaly", "/32 anomaly"],
];

function FlagBadge({ on, label }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
        on
          ? "bg-amber-500/20 text-amber-200 ring-1 ring-amber-400/40"
          : "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-400/30"
      }`}
    >
      {on ? "FLAGGED" : "OK"} · {label}
    </span>
  );
}

export default function App() {
  const [symptom, setSymptom] = useState(
    "Users cannot reach the WAN. Gi0/0 looks down and I suspect an IP conflict."
  );
  const [showOutput, setShowOutput] = useState(SAMPLE_OUTPUT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editedFix, setEditedFix] = useState("");
  const [reviewMsg, setReviewMsg] = useState("");
  const [stats, setStats] = useState(null);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) throw new Error("stats failed");
      setStats(await res.json());
    } catch {
      /* dashboard still usable without metrics */
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  async function onDiagnose(e) {
    e.preventDefault();
    setError("");
    setReviewMsg("");
    setEditOpen(false);
    setLoading(true);
    try {
      const res = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptom, show_output: showOutput }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || res.statusText);
      }
      const data = await res.json();
      setResult(data);
      setEditedFix(data.ai?.diagnosis?.fix_steps || "");
    } catch (err) {
      setError(err.message || "Diagnosis failed");
    } finally {
      setLoading(false);
    }
  }

  async function submitReview(status, fixOverride) {
    if (!result?.case_id) return;
    const dx = result.ai?.diagnosis || {};
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: result.case_id,
          status,
          edited_fix: status === "Edit" ? fixOverride ?? editedFix : "",
          root_cause: dx.root_cause || "",
          confidence: dx.confidence || "",
          osi_layer: dx.osi_layer || "",
          next_command: dx.next_command || "",
          symptom,
        }),
      });
      if (!res.ok) throw new Error("Review could not be saved");
      setReviewMsg(`Logged as ${status}.`);
      setEditOpen(false);
      await loadStats();
    } catch (err) {
      setError(err.message || "Review failed");
    }
  }

  const rules = result?.rules;
  const dx = result?.ai?.diagnosis;
  const agreement = stats?.agreement_rate ?? 0;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-950 to-cyan-950/40">
      <header className="border-b border-cyan-500/20 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">
              Cisco troubleshooting assistant
            </p>
            <h1 className="text-2xl font-bold text-white sm:text-3xl">NetSage AI</h1>
          </div>
          <p className="font-mono text-xs text-slate-400">
            Rules + LLM · human-in-the-loop review
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-4 py-8">
        <section className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <p className="text-xs uppercase tracking-wide text-slate-400">Cases reviewed</p>
            <p className="mt-1 text-3xl font-semibold text-white">
              {stats?.total_reviewed ?? 0}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <p className="text-xs uppercase tracking-wide text-slate-400">AI agreement</p>
            <p className="mt-1 text-3xl font-semibold text-cyan-300">{agreement}%</p>
            <p className="mt-1 text-xs text-slate-500">
              Accept {stats?.accept_count ?? 0} · Edit {stats?.edit_count ?? 0} · Reject{" "}
              {stats?.reject_count ?? 0}
            </p>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-cyan-400"
                style={{ width: `${Math.min(agreement, 100)}%` }}
              />
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <p className="text-xs uppercase tracking-wide text-slate-400">Issue types (OSI)</p>
            <ul className="mt-2 space-y-1 text-sm text-slate-300">
              {stats?.issue_types && Object.keys(stats.issue_types).length > 0 ? (
                Object.entries(stats.issue_types).map(([k, v]) => (
                  <li key={k} className="flex justify-between">
                    <span>{k}</span>
                    <span className="font-mono text-cyan-200">{v}</span>
                  </li>
                ))
              ) : (
                <li className="text-slate-500">No reviews yet</li>
              )}
            </ul>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 sm:p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Case input</h2>
          <form onSubmit={onDiagnose} className="space-y-4">
            <label className="block">
              <span className="mb-1 block text-sm text-slate-300">Symptom</span>
              <textarea
                className="h-24 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none ring-cyan-500/40 focus:ring-2"
                value={symptom}
                onChange={(e) => setSymptom(e.target.value)}
                required
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm text-slate-300">Show command output</span>
              <textarea
                className="h-48 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 outline-none ring-cyan-500/40 focus:ring-2"
                value={showOutput}
                onChange={(e) => setShowOutput(e.target.value)}
                required
              />
            </label>
            <button
              type="submit"
              disabled={loading}
              className="rounded-xl bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
            >
              {loading ? "Diagnosing…" : "Diagnose"}
            </button>
          </form>
          {error && (
            <p className="mt-3 text-sm text-rose-300" role="alert">
              {error}
            </p>
          )}
        </section>

        {result && (
          <>
            <section>
              <h2 className="mb-4 text-lg font-semibold text-white">Analysis</h2>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-cyan-300">
                    Python rule checker
                  </h3>
                  <p className="mt-2 text-sm text-slate-300">{rules?.summary}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {FLAG_LABELS.map(([key, label]) => (
                      <FlagBadge key={key} on={Boolean(rules?.flags?.[key])} label={label} />
                    ))}
                  </div>
                  {rules?.messages?.length > 0 && (
                    <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-amber-100/90">
                      {rules.messages.map((m) => (
                        <li key={m}>{m}</li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-cyan-300">
                      AI diagnosis
                    </h3>
                    {result.ai?.ok === false && (
                      <span className="text-xs text-rose-300">Fallback / API error</span>
                    )}
                  </div>
                  {result.ai?.error && (
                    <p className="mt-2 font-mono text-xs text-rose-300">{result.ai.error}</p>
                  )}
                  <dl className="mt-3 space-y-3 text-sm">
                    <div>
                      <dt className="text-slate-400">Root cause</dt>
                      <dd className="text-white">{dx?.root_cause}</dd>
                    </div>
                    <div className="flex flex-wrap gap-4">
                      <div>
                        <dt className="text-slate-400">Confidence</dt>
                        <dd className="font-medium text-white">{dx?.confidence}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-400">OSI layer</dt>
                        <dd className="font-medium text-white">{dx?.osi_layer}</dd>
                      </div>
                    </div>
                    <div>
                      <dt className="text-slate-400">Evidence</dt>
                      <dd className="whitespace-pre-wrap text-slate-200">{dx?.evidence}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">Next command</dt>
                      <dd className="font-mono text-cyan-200">{dx?.next_command}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">Fix steps</dt>
                      <dd className="whitespace-pre-wrap text-slate-200">{dx?.fix_steps}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 sm:p-6">
              <h2 className="mb-3 text-lg font-semibold text-white">Human review</h2>
              <p className="mb-4 text-sm text-slate-400">
                Case ID <span className="font-mono text-cyan-200">{result.case_id}</span>
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => submitReview("Accept")}
                  className="rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
                >
                  Accept AI Fix
                </button>
                <button
                  type="button"
                  onClick={() => setEditOpen((v) => !v)}
                  className="rounded-xl bg-amber-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300"
                >
                  Edit AI Fix
                </button>
                <button
                  type="button"
                  onClick={() => submitReview("Reject")}
                  className="rounded-xl bg-rose-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-rose-400"
                >
                  Reject AI Fix
                </button>
              </div>
              {editOpen && (
                <div className="mt-4 space-y-3">
                  <textarea
                    className="h-32 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none ring-amber-400/40 focus:ring-2"
                    value={editedFix}
                    onChange={(e) => setEditedFix(e.target.value)}
                    placeholder="Corrected fix steps"
                  />
                  <button
                    type="button"
                    onClick={() => submitReview("Edit")}
                    className="rounded-xl border border-amber-400/60 px-4 py-2 text-sm font-semibold text-amber-200 hover:bg-amber-500/10"
                  >
                    Submit edited fix
                  </button>
                </div>
              )}
              {reviewMsg && <p className="mt-3 text-sm text-emerald-300">{reviewMsg}</p>}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
