import { useState, useEffect } from "react";

const API = "http://localhost:8000";

const INTENT_COLORS = {
  book_meeting:    { bg: "#EAF3DE", text: "#3B6D11", label: "Book meeting" },
  faq:             { bg: "#E6F1FB", text: "#185FA5", label: "FAQ" },
  complaint:       { bg: "#FCEBEB", text: "#A32D2D", label: "Complaint" },
  support:         { bg: "#FAEEDA", text: "#854F0B", label: "Support" },
  other:           { bg: "#F1EFE8", text: "#5F5E5A", label: "Other" },
};

const OUTCOME_COLORS = {
  meeting_booked:      { bg: "#EAF3DE", text: "#3B6D11", icon: "📅" },
  transferred:         { bg: "#E6F1FB", text: "#185FA5", icon: "👤" },
  resolved:            { bg: "#E1F5EE", text: "#0F6E56", icon: "✓" },
  callback_requested:  { bg: "#FAEEDA", text: "#854F0B", icon: "↩" },
};

function Badge({ label, bg, text }) {
  return (
    <span style={{
      background: bg, color: text,
      fontSize: 11, fontWeight: 500,
      padding: "2px 8px", borderRadius: 999,
      whiteSpace: "nowrap"
    }}>{label}</span>
  );
}

function StatCard({ label, value, sub, color }) {
  return (
    <div style={{
      background: "var(--color-background-secondary)",
      borderRadius: 10, padding: "14px 18px", flex: 1, minWidth: 120
    }}>
      <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 500, color: color || "var(--color-text-primary)", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--color-text-tertiary)", marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

function CallRow({ call, onClick, selected }) {
  const intent  = INTENT_COLORS[call.intent]  || INTENT_COLORS.other;
  const outcome = OUTCOME_COLORS[call.outcome] || { bg: "#F1EFE8", text: "#5F5E5A", icon: "·" };
  const time    = call.created_at ? new Date(call.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
  const date    = call.created_at ? new Date(call.created_at).toLocaleDateString([], { month: "short", day: "numeric" }) : "—";

  return (
    <div
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: "44px 130px 1fr 100px 110px 64px",
        alignItems: "center",
        gap: 12,
        padding: "10px 16px",
        cursor: "pointer",
        borderBottom: "0.5px solid var(--color-border-tertiary)",
        background: selected ? "var(--color-background-secondary)" : "transparent",
        transition: "background 0.1s"
      }}
    >
      {/* Urgent dot */}
      <div style={{ display: "flex", justifyContent: "center" }}>
        {call.urgent
          ? <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#E24B4A" }} />
          : <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--color-border-tertiary)" }} />}
      </div>

      {/* Number + time */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-primary)" }}>
          {call.caller_number || "Unknown"}
        </div>
        <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{date} · {time}</div>
      </div>

      {/* Summary */}
      <div style={{ fontSize: 13, color: "var(--color-text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {call.summary || "No summary"}
      </div>

      {/* Intent */}
      <Badge label={intent.label} bg={intent.bg} text={intent.text} />

      {/* Outcome */}
      <Badge
        label={`${outcome.icon} ${(call.outcome || "—").replace(/_/g, " ")}`}
        bg={outcome.bg}
        text={outcome.text}
      />

      {/* Duration */}
      <div style={{ fontSize: 12, color: "var(--color-text-tertiary)", textAlign: "right" }}>
        {call.duration ? `${call.duration}s` : "—"}
      </div>
    </div>
  );
}

function TranscriptPanel({ callSid, onClose }) {
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!callSid) return;
    fetch(`${API}/calls/${callSid}`)
      .then(r => r.json())
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [callSid]);

  if (!detail) return (
    <div style={{ padding: 24, color: "var(--color-text-secondary)", fontSize: 14 }}>
      Loading transcript…
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{
        padding: "14px 20px",
        borderBottom: "0.5px solid var(--color-border-tertiary)",
        display: "flex", justifyContent: "space-between", alignItems: "center"
      }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{detail.caller_number}</div>
          <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>
            {detail.created_at ? new Date(detail.created_at).toLocaleString() : ""}
          </div>
        </div>
        <button onClick={onClose} style={{
          background: "none", border: "none", cursor: "pointer",
          fontSize: 18, color: "var(--color-text-secondary)", padding: "0 4px"
        }}>✕</button>
      </div>

      {/* Meta */}
      <div style={{ padding: "12px 20px", borderBottom: "0.5px solid var(--color-border-tertiary)", display: "flex", gap: 8, flexWrap: "wrap" }}>
        {detail.intent  && <Badge label={(INTENT_COLORS[detail.intent] || INTENT_COLORS.other).label}
                                  bg={(INTENT_COLORS[detail.intent] || INTENT_COLORS.other).bg}
                                  text={(INTENT_COLORS[detail.intent] || INTENT_COLORS.other).text} />}
        {detail.outcome && <Badge label={`${(OUTCOME_COLORS[detail.outcome] || {icon:""}).icon} ${detail.outcome.replace(/_/g," ")}`}
                                  bg={(OUTCOME_COLORS[detail.outcome] || {bg:"#F1EFE8"}).bg}
                                  text={(OUTCOME_COLORS[detail.outcome] || {text:"#5F5E5A"}).text} />}
        {detail.urgent  && <Badge label="Urgent" bg="#FCEBEB" text="#A32D2D" />}
        {detail.meeting_id && <Badge label="📅 Meeting booked" bg="#EAF3DE" text="#3B6D11" />}
      </div>

      {/* Summary */}
      {detail.summary && (
        <div style={{ padding: "12px 20px", borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
          <div style={{ fontSize: 11, color: "var(--color-text-tertiary)", marginBottom: 4 }}>Summary</div>
          <div style={{ fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>{detail.summary}</div>
        </div>
      )}

      {/* Transcript */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
        {(detail.transcript || []).map((turn, i) => (
          <div key={i} style={{
            display: "flex",
            justifyContent: turn.role === "user" ? "flex-start" : "flex-end"
          }}>
            <div style={{
              maxWidth: "82%",
              background: turn.role === "user"
                ? "var(--color-background-secondary)"
                : "var(--color-background-info)",
              color: turn.role === "user"
                ? "var(--color-text-primary)"
                : "var(--color-text-info)",
              borderRadius: turn.role === "user" ? "4px 14px 14px 14px" : "14px 4px 14px 14px",
              padding: "8px 12px",
              fontSize: 13,
              lineHeight: 1.5
            }}>
              <div style={{ fontSize: 10, opacity: 0.6, marginBottom: 2, fontWeight: 500 }}>
                {turn.role === "user" ? "Caller" : "Alex (AI)"}
              </div>
              {turn.content}
            </div>
          </div>
        ))}
        {(!detail.transcript || detail.transcript.length === 0) && (
          <div style={{ fontSize: 13, color: "var(--color-text-tertiary)", textAlign: "center", paddingTop: 24 }}>
            No transcript available
          </div>
        )}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [calls,  setCalls]  = useState([]);
  const [stats,  setStats]  = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const refresh = async () => {
    try {
      const [callsRes, statsRes] = await Promise.all([
        fetch(`${API}/calls?limit=100`).then(r => r.json()),
        fetch(`${API}/stats`).then(r => r.json())
      ]);
      setCalls(callsRes.calls || []);
      setStats(statsRes);
      setLastRefresh(new Date());
    } catch {
      // backend not running — use demo data
      setCalls(DEMO_CALLS);
      setStats(DEMO_STATS);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, []);

  const meetings = calls.filter(c => c.outcome === "meeting_booked").length;
  const urgent   = calls.filter(c => c.urgent).length;

  return (
    <div style={{ fontFamily: "var(--font-sans)", background: "transparent", minHeight: "100vh" }}>

      {/* Top bar */}
      <div style={{
        padding: "14px 20px",
        borderBottom: "0.5px solid var(--color-border-tertiary)",
        display: "flex", justifyContent: "space-between", alignItems: "center"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: "50%",
            background: "var(--color-background-info)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, color: "var(--color-text-info)", fontWeight: 500
          }}>AI</div>
          <span style={{ fontSize: 15, fontWeight: 500 }}>Receptionist</span>
          {stats?.active_calls > 0 && (
            <Badge label={`${stats.active_calls} live`} bg="#E1F5EE" text="#0F6E56" />
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>
            {lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}` : ""}
          </span>
          <button onClick={refresh} style={{
            fontSize: 12, padding: "5px 12px",
            border: "0.5px solid var(--color-border-secondary)",
            borderRadius: 6, cursor: "pointer",
            background: "var(--color-background-primary)",
            color: "var(--color-text-primary)"
          }}>Refresh</button>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ padding: "16px 20px", display: "flex", gap: 10, flexWrap: "wrap" }}>
        <StatCard label="Total calls"     value={calls.length}   />
        <StatCard label="Meetings booked" value={meetings}        color="#3B6D11" />
        <StatCard label="Urgent"          value={urgent}          color={urgent > 0 ? "#A32D2D" : undefined} />
        <StatCard label="Active now"      value={stats?.active_calls || 0} color="#185FA5" />
        <StatCard
          label="Resolution rate"
          value={calls.length ? `${Math.round((calls.filter(c=>c.outcome==="resolved"||c.outcome==="meeting_booked").length / calls.length) * 100)}%` : "—"}
          color="#0F6E56"
        />
      </div>

      {/* Main content */}
      <div style={{ display: "flex", borderTop: "0.5px solid var(--color-border-tertiary)" }}>

        {/* Call list */}
        <div style={{ flex: selected ? "0 0 55%" : "1 1 100%", borderRight: selected ? "0.5px solid var(--color-border-tertiary)" : "none" }}>
          {/* Column headers */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "44px 130px 1fr 100px 110px 64px",
            gap: 12, padding: "8px 16px",
            borderBottom: "0.5px solid var(--color-border-tertiary)",
            fontSize: 11, color: "var(--color-text-tertiary)", fontWeight: 500
          }}>
            <div></div>
            <div>Caller</div>
            <div>Summary</div>
            <div>Intent</div>
            <div>Outcome</div>
            <div style={{ textAlign: "right" }}>Duration</div>
          </div>

          {loading && (
            <div style={{ padding: 32, textAlign: "center", color: "var(--color-text-tertiary)", fontSize: 13 }}>
              Loading calls…
            </div>
          )}

          {!loading && calls.length === 0 && (
            <div style={{ padding: 48, textAlign: "center", color: "var(--color-text-tertiary)", fontSize: 13 }}>
              No calls yet. When someone dials your Twilio number, calls will appear here.
            </div>
          )}

          {calls.map(call => (
            <CallRow
              key={call.call_sid || call.id}
              call={call}
              selected={selected === call.call_sid}
              onClick={() => setSelected(selected === call.call_sid ? null : call.call_sid)}
            />
          ))}
        </div>

        {/* Transcript panel */}
        {selected && (
          <div style={{ flex: "0 0 45%", height: "calc(100vh - 160px)", overflowY: "hidden", display: "flex", flexDirection: "column" }}>
            <TranscriptPanel callSid={selected} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Demo data (shown when backend isn't running) ──────────────────────────

const DEMO_CALLS = [
  { call_sid: "CA001", caller_number: "+14155550101", summary: "Called to book a product demo for next Tuesday at 2 PM.", intent: "book_meeting", outcome: "meeting_booked", duration: 142, urgent: false, meeting_id: "evt_1", created_at: new Date(Date.now() - 1800000).toISOString() },
  { call_sid: "CA002", caller_number: "+14155550202", summary: "Asked about pricing and enterprise plan options.", intent: "faq", outcome: "resolved", duration: 87, urgent: false, created_at: new Date(Date.now() - 3600000).toISOString() },
  { call_sid: "CA003", caller_number: "+14155550303", summary: "Reported a critical billing issue — transferred to support.", intent: "complaint", outcome: "transferred", duration: 63, urgent: true, created_at: new Date(Date.now() - 7200000).toISOString() },
  { call_sid: "CA004", caller_number: "+14155550404", summary: "Requested a callback to discuss a partnership opportunity.", intent: "other", outcome: "callback_requested", duration: 55, urgent: false, created_at: new Date(Date.now() - 86400000).toISOString() },
  { call_sid: "CA005", caller_number: "+14155550505", summary: "Integration question about Slack connector — resolved.", intent: "support", outcome: "resolved", duration: 210, urgent: false, created_at: new Date(Date.now() - 90000000).toISOString() },
];

const DEMO_STATS = {
  total_calls: 5,
  urgent_calls: 1,
  active_calls: 0,
  intents: { book_meeting: 1, faq: 1, complaint: 1, support: 1, other: 1 },
  outcomes: { meeting_booked: 1, resolved: 2, transferred: 1, callback_requested: 1 }
};
