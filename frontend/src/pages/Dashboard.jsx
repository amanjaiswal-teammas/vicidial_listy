import { useState, useEffect } from "react";

export default function Dashboard({ username, onLogout }) {
  const today = new Date().toISOString().split("T")[0];
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);

  const token = localStorage.getItem("token");

  const fetchData = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `http://localhost:8000/api/list?from_date=${fromDate}&to_date=${toDate}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.status === 401) { onLogout(); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setRows(data.data);
      setTotal(data.total);
      setSearched(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(
        `http://localhost:8000/api/list/export?from_date=${fromDate}&to_date=${toDate}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vicidial_list_${fromDate}_to_${toDate}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  const formatDate = (val) => {
    if (!val) return "—";
    return new Date(val).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  };

  return (
    <div className="dash-root">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <svg width="28" height="28" viewBox="0 0 38 38" fill="none">
            <rect width="38" height="38" rx="10" fill="#1a2540"/>
            <path d="M10 28L19 10L28 28" stroke="#4f8ef7" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M13.5 22H24.5" stroke="#4f8ef7" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <span>ViciDial</span>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-section">REPORTS</div>
          <a href="#" className="nav-item active">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
            List
          </a>
        </nav>
        <div className="sidebar-user">
          <div className="user-avatar">{username[0].toUpperCase()}</div>
          <div className="user-info">
            <div className="user-name">{username}</div>
            <div className="user-role">Administrator</div>
          </div>
          <button className="logout-btn" onClick={onLogout} title="Logout">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="dash-main">
        <header className="dash-header">
          <div>
            <h2>Vicidial List</h2>
            <p>list_id: 33331 — entry records with date filter</p>
          </div>
        </header>

        {/* Filter Bar */}
        <div className="filter-bar">
          <div className="filter-group">
            <label>From Date</label>
            <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} />
          </div>
          <div className="filter-group">
            <label>To Date</label>
            <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} />
          </div>
          <button className="btn-search" onClick={fetchData} disabled={loading}>
            {loading
              ? <><span className="spinner sm" /> Searching...</>
              : <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Search</>
            }
          </button>
          {searched && rows.length > 0 && (
            <button className="btn-export" onClick={handleExport} disabled={exporting}>
              {exporting
                ? <><span className="spinner sm white" /> Exporting...</>
                : <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Export Excel</>
              }
            </button>
          )}
        </div>

        {error && <div className="dash-error">{error}</div>}

        {/* Table */}
        <div className="table-wrap">
          {!searched ? (
            <div className="empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
              <p>Select a date range and click <strong>Search</strong> to load data</p>
            </div>
          ) : loading ? (
            <div className="empty-state"><span className="spinner lg" /></div>
          ) : rows.length === 0 ? (
            <div className="empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <p>No records found for the selected date range.</p>
            </div>
          ) : (
            <>
              <div className="table-meta">
                <span>{total} records found</span>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Entry Date</th>
                    <th>Source ID</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i}>
                      <td className="row-num">{i + 1}</td>
                      <td>{formatDate(row.entry_date)}</td>
                      <td><span className="source-badge">{row.source_id || "—"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
