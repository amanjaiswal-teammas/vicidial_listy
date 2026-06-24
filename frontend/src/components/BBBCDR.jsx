import { useState } from "react";

export default function BBBCDR({ token }) {
  const today = new Date().toISOString().split("T")[0];

  const [date, setDate] = useState(today);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  const exportExcel = async () => {
    setExporting(true);
    setError("");

    try {
      const res = await fetch(
        `http://localhost:8000/api/bbb-cdr/export?start_date=${date}&end_date=${date}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!res.ok) {
        throw new Error("Failed to export report");
      }

      const blob = await res.blob();

      const url = window.URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = `BBB_CDR_${date}.xlsx`;

      document.body.appendChild(a);
      a.click();

      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <h2>BBB CDR Export</h2>

      <div className="filter-bar">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />

        <button
          onClick={exportExcel}
          disabled={exporting}
        >
          {exporting ? (
            <>
              <span className="spinner sm" /> Exporting...
            </>
          ) : (
            "Export Excel"
          )}
        </button>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}
    </>
  );
}