export default function StatusBadge({ status }) {
  const map = {
    pending: { label: "Pending", color: "#f0a500" },
    running: { label: "Running", color: "#3b82f6" },
    completed: { label: "Done", color: "#22c55e" },
    failed: { label: "Failed", color: "#ef4444" },
  };
  const { label, color } = map[status] || { label: status, color: "#6b7280" };

  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "9999px",
        fontSize: "11px",
        fontWeight: 600,
        color: "#fff",
        backgroundColor: color,
        letterSpacing: "0.02em",
      }}
    >
      {status === "running" && "⟳ "}
      {label}
    </span>
  );
}
