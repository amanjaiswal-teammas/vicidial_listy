import { useState } from "react";

export default function NeemansAPR({ token }) {
  const today = new Date().toISOString().split("T")[0];

//   const [startDate, setStartDate] = useState(today);
//   const [endDate, setEndDate] = useState(today);

  const [date, setDate] = useState(today);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const fetchReportapr = async () => {
    setLoading(true);

    try {
      const res = await fetch(
        `http://localhost:8000/api/neemans-apr?start_date=${date}&end_date=${date}`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      const data = await res.json();

      setRows(data.data || []);

    } finally {
      setLoading(false);
    }
  };

  const exportExcelapr = async () => {
    setExporting(true);

    try {
      const res = await fetch(
        `http://localhost:8000/api/neemans-apr/export?start_date=${date}&end_date=${date}`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      const blob = await res.blob();

      const url = URL.createObjectURL(blob);

      const a = document.createElement("a");

      a.href = url;
      a.download = `Neemans_APR_${date}.xlsx`;

      a.click();

      URL.revokeObjectURL(url);

    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <h2>Neemans APR</h2>

      <div className="filter-bar">

        <input
          type="date"
          value={date}
          onChange={(e)=>setDate(e.target.value)}
        />

        <button
          onClick={fetchReportapr}
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

        <button onClick={exportExcelapr}>
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
                  <th>Call Date</th>
                  <th>Start Time</th>
                  <th>Call Time</th>
                  <th>End Time</th>
                  <th>Agent</th>
                  <th>Campaign</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Term Reason</th>
                  <th>Call Duration</th>
                  <th>Queue Time</th>
                  <th>Parked Time</th>
                  <th>Dispo Sec</th>
                  <th>Wrap</th>
                  <th>Call ≤ 30s</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{r.CallDate}</td>
                    <td>{r.StartTime}</td>
                    <td>{r.CallTime}</td>
                    <td>{r.Endtime}</td>
                    <td>{r.Agent}</td>
                    <td>{r.campaign_id}</td>
                    <td>{r.PhoneNumber}</td>
                    <td>{r.status}</td>
                    <td>{r.term_reason}</td>
                    <td>{r.CallDuration}</td>
                    <td>{r.Queuetime}</td>
                    <td>{r.ParkedTime}</td>
                    <td>{r.dispo_sec}</td>
                    <td>{r.WrapTime}</td>
                    <td>{r.Call20 === 1 ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

      </div>
    </>
  );
}