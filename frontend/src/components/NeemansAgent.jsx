import { useState } from "react";

export default function NeemansAgent({ token }) {
  const today = new Date().toISOString().split("T")[0];

  const [date, setDate] = useState(today);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  const handleExport = async () => {
    setExporting(true);
    setError("");

    try {
      const res = await fetch(
        `http://localhost:8000/api/neemans-agent/export?date=${date}`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      if (!res.ok) {
        throw new Error("Export failed");
      }

      const blob = await res.blob();

      const url = window.URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = `Neemans_Agent_${date}.csv`;
      a.click();

      window.URL.revokeObjectURL(url);

    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <header className="dash-header">
        <div>
          <h2>Neemans Agent Report</h2>
          <p>Export Agent Time Detail Report</p>
        </div>
      </header>

      {error && (
        <div className="dash-error">
          {error}
        </div>
      )}

      <div className="filter-bar">
        <div className="filter-group">
          <label>Select Date</label>

          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>

        <button
          className="btn-export"
          onClick={handleExport}
          disabled={exporting}
        >
          {exporting ? "Exporting..." : "Export CSV"}
        </button>
      </div>
    </div>
  );
}