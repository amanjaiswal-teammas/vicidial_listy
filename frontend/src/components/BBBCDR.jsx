import { useState } from "react";
import "./BBBCDR.css";

export default function BBBCDR({ token }) {
  const today = new Date().toISOString().split("T")[0];

  const [date, setDate] = useState(today);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);

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
      a.download = `Reginald_CDR_${date}.xlsx`;

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

  const viewRecords = async (pageNo = page) => {
      if (typeof pageNo !== "number") {
        pageNo = page;
      }

      setLoading(true);
      setError("");

      try {
        const res = await fetch(
          `http://localhost:8000/api/bbb-cdr?start_date=${date}&end_date=${date}&page=${pageNo}&limit=${limit}`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        if (!res.ok) throw new Error("Failed to fetch records");

        const data = await res.json();

        setRecords(data.data || []);
        setPage(data.page);
        setTotalPages(data.total_pages);
        setTotalRecords(data.total);
      } catch (err) {
        setError(err.message || "Failed to load records");
      } finally {
        setLoading(false);
      }
  };

  return (
    <>
      <h2>Reginald CDR</h2>

      <div className="filter-bar">
        <input
          type="date"
          value={date}
          onChange={(e) => {
              setDate(e.target.value);
              setPage(1);
          }}
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

        <button onClick={() => viewRecords(page)} disabled={loading}>
          {loading ? "Loading..." : "View Records"}
        </button>

      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <div className="cdr-card">
          <div className="cdr-header">
            <h3>Call Records</h3>

            <span>
                {totalRecords} Records | Page {page} of {totalPages}
            </span>
          </div>

          <div className="cdr-table-wrapper">
            <table className="cdr-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Agent</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Campaign</th>
                  <th>Duration</th>
                  <th>Recording</th>
                </tr>
              </thead>

              <tbody>
                {records.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: "center" }}>
                      No Records Found
                    </td>
                  </tr>
                ) : (
                  records.map((row) => (
                    <tr key={row.uniqueid}>
                      <td>{row.CallDate}</td>
                      <td>{row.Agent}</td>
                      <td>{row.PhoneNumber}</td>
                      <td>{row.CallStatus}</td>
                      <td>{row.campaign_id}</td>
                      <td>{row.LengthInMin}</td>

                      <td>
                        {row.RecordingUrl ? (
                          <audio
                            controls
                            preload="none"
                            style={{ width: 230 }}
                          >
                            <source
                              src={row.RecordingUrl}
                              type="audio/mpeg"
                            />
                          </audio>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="cdr-pagination">
            <button
              disabled={page === 1}
              onClick={() => viewRecords(page - 1)}
            >
              ◀ Previous
            </button>

            <span>
              Page {page} of {totalPages}
            </span>

            <button
              disabled={page === totalPages}
              onClick={() => viewRecords(page + 1)}
            >
              Next ▶
            </button>
          </div>
      </div>
    </>
  );
}