import { useState } from "react";

export default function NeemansCDR({ token }) {

  const today = new Date().toISOString().split("T")[0];

//   const [startDate,setStartDate] = useState(today);
//   const [endDate,setEndDate] = useState(today);

  const [date, setDate] = useState(today);

  const [rows,setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const fetchReportcdr = async () => {
    setLoading(true);

    try {
        const res = await fetch(
          `http://localhost:8000/api/neemans-cdr?start_date=${date}&end_date=${date}`,
          {
            headers:{
              Authorization:`Bearer ${token}`
            }
          }
        );

        const data = await res.json();

        setRows(data.data || []);

    } finally {
      setLoading(false);
    }
  };

  const exportExcelcdr = async () => {
    setExporting(true);

    try {
        const res = await fetch(
          `http://localhost:8000/api/neemans-cdr/export?start_date=${date}&end_date=${date}`,
          {
            headers:{
              Authorization:`Bearer ${token}`
            }
          }
        );

        const blob = await res.blob();

        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = url;
        a.download = `Neemans_CDR_${date}.xlsx`;

        a.click();

        URL.revokeObjectURL(url);

    } finally {
      setExporting(false);
    }

  };

  return (
    <>
      <h2>Neemans CDR</h2>

      <div className="filter-bar">

        <input
          type="date"
          value={date}
          onChange={(e)=>setDate(e.target.value)}
        />

        <button
          onClick={fetchReportcdr}
          disabled={loading}
        >
          {loading ? (
            <>
              <span className="spinner sm" /> Loading...
            </>
          ) : (
            "Search"
          )}
        </button>

        <button onClick={exportExcelcdr}>
          {exporting ? "Exporting..." : "Export"}
        </button>

      </div>

      <div className="table-wrap">

          {loading ? (
            <div className="empty-state">
              <span className="spinner lg" />
              <p>Loading report...</p>
            </div>
          ) : rows.length === 0 ? (
            <div className="empty-state">
              <p>No records found</p>
            </div>
          ) : (
            <table className="data-table">

              <thead>
                <tr>
                  <th>#</th>
                  <th>Lead ID</th>
                  <th>Agent</th>
                  <th>Phone</th>
                  <th>Call Date</th>
                  <th>Start Time</th>
                  <th>End Time</th>
                  <th>Call Duration</th>
                  <th>Status</th>
                  <th>Campaign</th>
                  <th>Comments</th>
                  <th>Term Reason</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{r.lead_id}</td>
                    <td>{r.Agent}</td>
                    <td>{r.PhoneNumber}</td>
                    <td>{r.CallDate}</td>
                    <td>{r.StartTime}</td>
                    <td>{r.EndTime}</td>
                    <td>{r.CallDuration}</td>
                    <td>{r.CallStatus}</td>
                    <td>{r.campaign_id}</td>
                    <td>{r.comments}</td>
                    <td>{r.term_reason}</td>
                  </tr>
                ))}
              </tbody>

            </table>
          )}

      </div>
    </>
  );
}