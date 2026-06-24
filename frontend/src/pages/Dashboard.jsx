import { useState, useEffect } from "react";
import NeemansAPR from "../components/NeemansAPR";
import NeemansCDR from "../components/NeemansCDR";
import NeemansAgent from "../components/NeemansAgent";
import BBBCDR from "../components/BBBCDR";

function DBCredentials({ token }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    host: "",
    host_name: "",
    user: "",
    password: "",
    database_name: ""
  });

  const [editingId, setEditingId] = useState(null);

  const fetchCredentials = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("http://localhost:8000/api/db-credentials", {
        headers: { Authorization: `Bearer ${token}` }
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail);
      setData(json.data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCredentials();
  }, []);

  const handleSubmit = async () => {
    try {
      const url = editingId
        ? `http://localhost:8000/api/db-credentials/${editingId}`
        : `http://localhost:8000/api/db-credentials`;

      const method = editingId ? "PUT" : "POST";

      const payload = { ...form };

      // 🚀 IMPORTANT: don't send empty password on update
      if (editingId && !payload.password) {
        delete payload.password;
      }

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      const json = await res.json();
      if (!res.ok) throw new Error(json.detail);

      setForm({
        host: "",
        host_name: "",
        user: "",
        password: "",
        database_name: ""
      });
      setEditingId(null);
      fetchCredentials();

    } catch (err) {
      setError(err.message);
    }
  };

  const handleEdit = (item) => {
    setForm({
      host: item.host,
      host_name: item.host_name,
      user: item.user,
      password: "",
      database_name: item.database_name
    });
    setEditingId(item.id);
  };

  return (
    <div>
      <h2>DB Credentials</h2>

      {error && <div className="dash-error">{error}</div>}

      {/* Form */}
      <div className="form">
        <input placeholder="Host IP" value={form.host}
          onChange={e => setForm({ ...form, host: e.target.value })} />

        <input placeholder="Host Name" value={form.host_name}
          onChange={e => setForm({ ...form, host_name: e.target.value })} />

        <input placeholder="User" value={form.user}
          onChange={e => setForm({ ...form, user: e.target.value })} />

        <input placeholder="Password"
          type="password"
          value={form.password}
          onChange={e => setForm({ ...form, password: e.target.value })} />

        <input placeholder="Database Name" value={form.database_name}
          onChange={e => setForm({ ...form, database_name: e.target.value })} />

        <button onClick={handleSubmit}>
          {editingId ? "Update" : "Create"}
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <p>Loading...</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Host IP</th>
              <th>Host Name</th>
              <th>User</th>
              <th>Database</th>
              <th>Created</th>
              <th>Updated</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {data.map(item => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.host}</td>
                <td>{item.host_name}</td>
                <td>{item.user}</td>
                <td>{item.database_name}</td>
                <td>{new Date(item.created_at).toLocaleString()}</td>
                <td>{new Date(item.updated_at).toLocaleString()}</td>
                <td>
                  <button onClick={() => handleEdit(item)}>Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}



function DynamicReport({ token, onLogout }) {
  const today = new Date().toISOString().split("T")[0];
  const [exporting, setExporting] = useState(false);

  const [credentials, setCredentials] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Fetch DB credentials for dropdown
  useEffect(() => {
    fetch("http://localhost:8000/api/db-credentials", {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setCredentials(data.data || []))
      .catch(() => setCredentials([]));
  }, []);

  const fetchReport = async () => {
    if (!selectedId) {
      setError("Please select a DB");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await fetch(
        `http://localhost:8000/api/dynamic-report?credential_id=${selectedId}&start_date=${startDate}&end_date=${endDate}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.status === 401) {
        onLogout();
        return;
      }

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);

      setRows(data.data || []);

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDynamicExport = async () => {
      if (!selectedId) {
        setError("Please select a DB");
        return;
      }

      setExporting(true);

      try {
        const res = await fetch(
          `http://localhost:8000/api/dynamic-report/export?credential_id=${selectedId}&start_date=${startDate}&end_date=${endDate}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );

        if (!res.ok) throw new Error("Export failed");

        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = `dynamic_report_${startDate}_${endDate}.xlsx`;
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
      <h2>Dynamic Report</h2>

      {error && <div className="dash-error">{error}</div>}

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-group">
          <label>Select DB</label>
          <select value={selectedId} onChange={e => setSelectedId(e.target.value)}>
            <option value="">-- Select Database --</option>
            {credentials.map(c => (
              <option key={c.id} value={c.id}>
                {c.host_name} ({c.database_name})
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Start Date</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
        </div>

        <div className="filter-group">
          <label>End Date</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
        </div>

        <button className="btn-search" onClick={fetchReport} disabled={loading}>
          {loading ? "Loading..." : "Search"}
        </button>

        <button
          className="btn-export"
          onClick={handleDynamicExport}
          disabled={exporting}
        >
          {exporting ? "Exporting..." : "Export Excel"}
        </button>
      </div>

      {/* Table */}
      <div className="table-wrap" style={{ overflowX: "auto" }}>
        {loading ? (
          <p>Loading...</p>
        ) : rows.length === 0 ? (
          <p>No data found</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Call Date</th>
                <th>Start Time</th>
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
                <th>Wrap Time</th>
                <th>Call ≤20s</th>
                <th>Transfer Status</th>
                <th>Feedback</th>
                <th>Transfer Time</th>
                <th>Transfer End</th>
                <th>CSAT IVR Duration</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td>{r.CallDate}</td>
                  <td>{r.StartTime}</td>
                  <td>{r.Endtime}</td>
                  <td>{r.Agent}</td>
                  <td>{r.campaign_id}</td>
                  <td>{r.PhoneNumber}</td>
                  <td>{r.status}</td>
                  <td>{r.term_reason}</td>
                  <td>{r.CallDuration}</td>
                  <td>{r.Queuetime}</td>
                  <td>{r.ParkedTime}</td>
                  <td>{r.dispo_sec ?? 0}</td>
                  <td>{r.WrapTime}</td>
                  <td>{r.Call20}</td>
                  <td>{r.CallTransferStatus}</td>
                  <td>{r.FeedbackOption}</td>
                  <td>{r.CallTransferTime}</td>
                  <td>{r.CallTransferEndTime}</td>
                  <td>{r.CSATIVRDuration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}


export default function Dashboard({ username, onLogout }) {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
//   const [activeTab, setActiveTab] = useState("list");
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);

  const [sourceId, setSourceId] = useState("");
  const [sourceRows, setSourceRows] = useState([]);
  const [sourceLoading, setSourceLoading] = useState(false);

  const token = localStorage.getItem("token");
  const role = localStorage.getItem("role");

  const getDefaultTab = (role) => {
      switch (role) {
        case "admin":
          return "list";

        case "finnable":
          return "list";

        case "gnc":
          return "dynamic";

        case "neemans":
          return "neemans-apr";

        case "bbb":
            return "bbb-cdr";

        default:
          return "list";
      }
  };

  const [activeTab, setActiveTab] = useState(getDefaultTab(role));

  const fetchData = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `http://localhost:8000/api/list?date=${date}`,
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


  const fetchSourceDetails = async () => {

      if (!sourceId) {
        setError("Please enter FN ID");
        return;
      }

      setSourceLoading(true);
      setError("");

      try {

        const res = await fetch(
          `http://localhost:8000/api/source-details?source_id=${sourceId}`,
          {
            headers: {
              Authorization: `Bearer ${token}`
            }
          }
        );

        if (res.status === 401) {
          onLogout();
          return;
        }

        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail);
        }

        setSourceRows(data.data || []);

      } catch (err) {
        setError(err.message);
      } finally {
        setSourceLoading(false);
      }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(
        `http://localhost:8000/api/list/export?date=${date}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vicidial_list_${date}.xlsx`;
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
          {(role === "admin" || role === "gnc") && (
          <a href="#" className={`nav-item ${activeTab === "credentials" ? "active" : ""}`}
               onClick={(e) => { e.preventDefault(); setActiveTab("credentials"); }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <ellipse cx="12" cy="5" rx="9" ry="3"/>
                <path d="M3 5v6c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                <path d="M3 11v6c0 1.66 4 3 9 3s9-1.34 9-3v-6"/>
              </svg>
              DB Credentials
          </a>
          )}

          {(role === "admin" || role === "finnable") && (
          <a href="#" className={`nav-item ${activeTab === "list" ? "active" : ""}`}
              onClick={(e) => { e.preventDefault(); setActiveTab("list"); }}
            >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
            List
          </a>
          )}

          {(role === "admin" || role === "gnc") && (
          <a
              href="#"
              className={`nav-item ${activeTab === "dynamic" ? "active" : ""}`}
              onClick={(e) => { e.preventDefault(); setActiveTab("dynamic"); }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2">
                <path d="M3 3v18h18"/>
                <path d="M7 14l3-3 3 3 5-5"/>
              </svg>
              Dynamic Report
          </a>
          )}

          {(role === "admin" || role === "finnable") && (
              <a
                href="#"
                className={`nav-item ${activeTab === "source-search" ? "active" : ""}`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveTab("source-search");
                }}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="11" cy="11" r="8"/>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>

                FN ID Search
              </a>
          )}

          {(role === "admin" || role === "neemans") && (
          <>

              <a
                  href="#"
                  className={`nav-item ${activeTab === "neemans-agent" ? "active" : ""}`}
                  onClick={(e) => {
                    e.preventDefault();
                    setActiveTab("neemans-agent");
                  }}
              >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>

                  Neemans Agent
              </a>

              <a
                  href="#"
                  className={`nav-item ${activeTab === "neemans-apr" ? "active" : ""}`}
                  onClick={(e)=>{
                    e.preventDefault();
                    setActiveTab("neemans-apr");
                  }}
              >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M3 3v18h18" />
                    <path d="M7 15l3-3 3 2 4-5" />
                  </svg>

                  Neemans APR
              </a>

              <a
                  href="#"
                  className={`nav-item ${activeTab === "neemans-cdr" ? "active" : ""}`}
                  onClick={(e)=>{
                    e.preventDefault();
                    setActiveTab("neemans-cdr");
                  }}
              >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <path d="M8 8h8" />
                    <path d="M8 12h8" />
                    <path d="M8 16h5" />
                  </svg>

                  Neemans CDR
              </a>
          </>
          )}

          {(role === "admin" || role === "bbb") && (
          <>
                <a
                    href="#"
                    className={`nav-item ${activeTab === "bbb-cdr" ? "active" : ""}`}
                    onClick={(e)=>{
                      e.preventDefault();
                      setActiveTab("bbb-cdr");
                    }}
                >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <path d="M8 8h8" />
                      <path d="M8 12h8" />
                      <path d="M8 16h5" />
                    </svg>

                    BBB CDR
                </a>
          </>
          )}

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
          {activeTab === "list" && (
            <>
                <header className="dash-header">
                  <div>
                    <h2>Vicidial List</h2>
                    <p>list_id: 33331 — entry records with date filter</p>
                  </div>
                </header>

                {/* Filter Bar */}
                <div className="filter-bar">
                  <div className="filter-group">
                      <label>Select Date</label>
                      <input
                        type="date"
                        value={date}
                        onChange={e => setDate(e.target.value)}
                      />
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
                            <th>List ID</th>
                            <th>Entry Date</th>
                            <th>Source ID</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row, i) => (
                            <tr key={i}>
                              <td className="row-num">{i + 1}</td>
                              <td>{row.list_id}</td>
                              <td>{formatDate(row.entry_date)}</td>
                              <td><span className="source-badge">{row.source_id || "—"}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  )}
                </div>
            </>
          )}

          {activeTab === "source-search" && (
              <>
                <header className="dash-header">
                  <div>
                    <h2>FN ID Search</h2>
                    <p>Search vicidial records using FN ID</p>
                  </div>
                </header>

                {error && <div className="dash-error">{error}</div>}

                <div className="filter-bar">

                  <div className="filter-group">
                    <label>Enter FN ID</label>

                    <input
                      type="text"
                      value={sourceId}
                      onChange={(e) => setSourceId(e.target.value)}
                    />
                  </div>

                  <button
                    className="btn-search"
                    onClick={fetchSourceDetails}
                    disabled={sourceLoading}
                  >
                    {sourceLoading ? "Searching..." : "Search"}
                  </button>

                </div>

                <div className="table-wrap">

                  {sourceLoading ? (
                    <div className="empty-state">
                      <span className="spinner lg" />
                    </div>
                  ) : sourceRows.length === 0 ? (
                    <div className="empty-state">
                      <p>No source records found</p>
                    </div>
                  ) : (

                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Lead Entry Date</th>
                          <th>Dispo Code</th>
                          <th>FN ID</th>
                          <th>List ID</th>
                          <th>Called Count</th>
                          <th>Last Call Time</th>
                        </tr>
                      </thead>

                      <tbody>
                        {sourceRows.map((row, i) => (
                          <tr key={i}>
                            <td>{i + 1}</td>
                            <td>{formatDate(row.entry_date)}</td>
                            <td>{row.status}</td>
                            <td>{row.source_id}</td>
                            <td>{row.list_id}</td>
                            <td>{row.called_count}</td>
                            <td>{formatDate(row.last_local_call_time)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                  )}

                </div>
              </>
          )}


          {activeTab === "credentials" && (
            <DBCredentials token={token} />
          )}

          {activeTab === "dynamic" && (
              <DynamicReport token={token} onLogout={onLogout} />
          )}

          {activeTab === "neemans-agent" && (
                <NeemansAgent token={token} />
          )}

          {activeTab === "neemans-apr" && (
              <NeemansAPR token={token} />
          )}

          {activeTab === "neemans-cdr" && (
              <NeemansCDR token={token} />
          )}

          {activeTab === "bbb-cdr" && (
                <BBBCDR token={token} />
          )}

      </main>

    </div>
  );
}
