import React, { useState, useEffect } from "react";
import { Users, BarChart3, Bell, FileSpreadsheet, PlusCircle, AlertCircle, Eye, EyeOff, Loader, RefreshCw, CheckCircle, ShieldAlert } from "lucide-react";
import { api } from "../api";

export default function AdminPanel() {
  const [metrics, setMetrics] = useState(null);
  const [usersProgress, setUsersProgress] = useState([]);
  const [loading, setLoading] = useState(true);

  // Announcement state
  const [annContent, setAnnContent] = useState("");
  const [annLoading, setAnnLoading] = useState(false);
  const [annSuccess, setAnnSuccess] = useState(false);

  // Drawer toggling
  const [expandedUser, setExpandedUser] = useState(null);

  // New task forms state
  const [taskId, setTaskId] = useState("");
  const [taskStage, setTaskStage] = useState("beginner");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskScenario, setTaskScenario] = useState("");
  const [taskFile, setTaskFile] = useState(null);
  const [cellValidations, setCellValidations] = useState([
    { cell_reference: "", expected_value: "", required_function: "", is_financial: false, is_date: false, correct_formula_hint: "" }
  ]);
  const [taskLoading, setTaskLoading] = useState(false);
  const [taskSuccess, setTaskSuccess] = useState(false);
  const [taskError, setTaskError] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [m, u] = await Promise.all([
        api.getAdminMetrics(),
        api.getAdminUsersProgress()
      ]);
      setMetrics(m);
      setUsersProgress(u);
    } catch (err) {
      console.error("Error loading admin data:", err);
    } finally {
      setLoading(false);
    }
  }

  const handlePostAnnouncement = async (e) => {
    e.preventDefault();
    if (!annContent.trim()) return;
    setAnnLoading(true);
    setAnnSuccess(false);
    
    try {
      await api.postAnnouncement(annContent);
      setAnnSuccess(true);
      setAnnContent("");
      setTimeout(() => setAnnSuccess(false), 3000);
    } catch (err) {
      console.error("Error posting announcement:", err);
    } finally {
      setAnnLoading(false);
    }
  };

  const handleValidationChange = (index, field, value) => {
    const newVals = [...cellValidations];
    newVals[index][field] = value;
    setCellValidations(newVals);
  };

  const addValidationRow = () => {
    setCellValidations([
      ...cellValidations,
      { cell_reference: "", expected_value: "", required_function: "", is_financial: false, is_date: false, correct_formula_hint: "" }
    ]);
  };

  const removeValidationRow = (index) => {
    if (cellValidations.length === 1) return;
    setCellValidations(cellValidations.filter((_, i) => i !== index));
  };

  const handleTaskSubmit = async (e) => {
    e.preventDefault();
    setTaskLoading(true);
    setTaskSuccess(false);
    setTaskError("");

    // Validate cells
    const cleanValidations = cellValidations.filter(v => v.cell_reference.trim() !== "" && v.expected_value.trim() !== "");
    if (cleanValidations.length === 0) {
      setTaskError("Please add at least one valid cell coordinate specification.");
      setTaskLoading(false);
      return;
    }

    try {
      const taskData = {
        id: taskId,
        stage: taskStage,
        title: taskTitle,
        scenario_text: taskScenario,
        validations: cleanValidations
      };

      await api.uploadTask(taskData, taskFile);
      setTaskSuccess(true);
      // Reset form
      setTaskId("");
      setTaskTitle("");
      setTaskScenario("");
      setTaskFile(null);
      setCellValidations([
        { cell_reference: "", expected_value: "", required_function: "", is_financial: false, is_date: false, correct_formula_hint: "" }
      ]);
      setTimeout(() => setTaskSuccess(false), 3000);
      loadData(); // Reload student progress
    } catch (err) {
      setTaskError(err.message || "Failed to upload training task.");
    } finally {
      setTaskLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <Loader className="w-8 h-8 text-blue-500 animate-spin" />
        <span className="text-slate-400 mt-2 text-sm">Initializing administrative services...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Page Title */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-tr from-indigo-500 to-blue-500 rounded-2xl glow-blue">
            <BarChart3 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-100">Management Operations</h1>
            <p className="text-slate-400 text-xs">Training metrics, progress logs, and task dispatchers</p>
          </div>
        </div>
        <button
          onClick={loadData}
          className="p-2 bg-slate-900 border border-slate-800 rounded-xl hover:bg-slate-850 hover:text-white transition-colors"
          title="Refresh Ledger"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Metrics Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass-panel p-6 rounded-3xl flex items-center gap-4">
          <div className="p-4 bg-blue-900/30 text-blue-400 rounded-2xl">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider block">Registered Standard Users</span>
            <span className="text-3xl font-black text-slate-100 font-mono leading-none mt-1 block">{metrics?.total_users}</span>
          </div>
        </div>

        <div className="glass-panel p-6 rounded-3xl flex items-center gap-4">
          <div className="p-4 bg-indigo-900/30 text-indigo-400 rounded-2xl">
            <FileSpreadsheet className="w-6 h-6" />
          </div>
          <div>
            <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider block">Total Workbooks Graded</span>
            <span className="text-3xl font-black text-slate-100 font-mono leading-none mt-1 block">{metrics?.total_attempts}</span>
          </div>
        </div>

        <div className="glass-panel p-6 rounded-3xl flex items-center gap-4">
          <div className="p-4 bg-emerald-900/30 text-emerald-400 rounded-2xl">
            <CheckCircle className="w-6 h-6" />
          </div>
          <div>
            <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider block">Overall Success Rate</span>
            <span className="text-3xl font-black text-slate-100 font-mono leading-none mt-1 block">{metrics?.pass_rate}%</span>
          </div>
        </div>
      </div>

      {/* Main Admin Columns */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        
        {/* Left Side: Users Progress Lists */}
        <div className="xl:col-span-2 space-y-8">
          <div className="glass-panel p-6 rounded-3xl">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">
              Student Activity Ledger
            </h3>

            {usersProgress.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-sm">
                No standard training users found.
              </div>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {usersProgress.map((user) => (
                  <div key={user.user_id} className="py-4">
                    <div className="flex items-center justify-between flex-wrap gap-4">
                      {/* Name */}
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-slate-800 rounded-full border border-slate-700/80 flex items-center justify-center font-bold text-xs text-indigo-400">
                          {user.full_name.charAt(0)}
                        </div>
                        <div>
                          <h4 className="text-sm font-bold text-slate-200">{user.full_name}</h4>
                          <span className="text-[10px] text-slate-500 font-mono">@{user.username}</span>
                        </div>
                      </div>

                      {/* Info Pills */}
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <span className="text-[9px] uppercase font-bold tracking-wider text-slate-500 block">Total points</span>
                          <span className="text-sm font-mono font-bold text-yellow-400">{user.total_points} PTS</span>
                        </div>

                        <div className="text-right">
                          <span className="text-[9px] uppercase font-bold tracking-wider text-slate-500 block">Active Task</span>
                          <span className="text-xs font-semibold text-slate-300 truncate max-w-[120px] block" title={user.current_active_task}>
                            {user.current_active_task.replace(/_/g, " ")}
                          </span>
                        </div>

                        <button
                          onClick={() => setExpandedUser(expandedUser === user.user_id ? null : user.user_id)}
                          className="p-2 bg-slate-900/60 border border-slate-850 hover:border-slate-750 rounded-xl transition-all"
                        >
                          {expandedUser === user.user_id ? <EyeOff className="w-4 h-4 text-slate-400" /> : <Eye className="w-4 h-4 text-indigo-400" />}
                        </button>
                      </div>
                    </div>

                    {/* Detailed audits drawer */}
                    {expandedUser === user.user_id && (
                      <div className="mt-4 p-4 bg-slate-950/60 border border-slate-850 rounded-2xl grid grid-cols-1 md:grid-cols-3 gap-4 animate-slide-up">
                        {Object.entries(user.attempts_summary).map(([taskKey, stats]) => (
                          <div key={taskKey} className="p-3 bg-slate-900/40 border border-slate-800 rounded-xl flex flex-col justify-between">
                            <span className="text-[10px] font-bold text-slate-300 capitalize">
                              {taskKey.replace(/_/g, " ")}
                            </span>
                            
                            <div className="flex items-center justify-between mt-3">
                              <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase ${
                                stats.passed ? "bg-emerald-950/60 text-emerald-400 border border-emerald-900/50" : "bg-red-950/60 text-red-400 border border-red-900/50"
                              }`}>
                                {stats.passed ? "Passed" : "Locked / Active"}
                              </span>
                              
                              <span className="text-[10px] text-slate-500 font-mono">
                                Fails: <strong className="text-red-400 font-bold">{stats.failed_attempts}</strong>
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Command Center */}
        <div className="xl:col-span-1 space-y-8">
          
          {/* Section 1: Post Announcement */}
          <div className="glass-panel p-6 rounded-3xl">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
              <Bell className="w-4 h-4 text-amber-500" />
              Reward Announcement
            </h3>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Post an active training announcement or cash reward banner. Pushes instantly to the top of standard student dashboards.
            </p>

            {annSuccess && (
              <div className="mb-4 p-3 bg-emerald-950/50 border border-emerald-900/50 text-emerald-400 text-xs rounded-xl flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />
                <span>Notification posted successfully!</span>
              </div>
            )}

            <form onSubmit={handlePostAnnouncement} className="space-y-4">
              <textarea
                value={annContent}
                onChange={(e) => setAnnContent(e.target.value)}
                placeholder="e.g. 🔥 Top 3 scorers on the public leaderboard will receive AED 5,000 retail vouchers!"
                rows={3}
                className="w-full p-3.5 bg-slate-950/60 border border-slate-800 rounded-2xl text-xs text-slate-200 outline-none focus:border-blue-500 transition-colors"
                required
              />
              <button
                type="submit"
                disabled={annLoading || !annContent.trim()}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-2xl transition-all shadow-md active:scale-95 flex items-center justify-center gap-1.5"
              >
                {annLoading ? "Dispatching..." : "Post Global Banner"}
              </button>
            </form>
          </div>

          {/* Section 2: Custom Task Creator */}
          <div className="glass-panel p-6 rounded-3xl">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
              <PlusCircle className="w-4 h-4 text-indigo-400" />
              Upload Custom Exercise
            </h3>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Upload custom financial scenarios, add exercise sheets, and define coordinates expected values.
            </p>

            {taskSuccess && (
              <div className="mb-4 p-3 bg-emerald-950/50 border border-emerald-900/50 text-emerald-400 text-xs rounded-xl flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />
                <span>Task deployed successfully!</span>
              </div>
            )}

            {taskError && (
              <div className="mb-4 p-3 bg-red-950/50 border border-red-900/50 text-red-400 text-xs rounded-xl flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                <span>{taskError}</span>
              </div>
            )}

            <form onSubmit={handleTaskSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">Task ID (lowercase)</label>
                  <input
                    type="text"
                    value={taskId}
                    onChange={(e) => setTaskId(e.target.value)}
                    placeholder="e.g. inventory_valuation"
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs outline-none focus:border-blue-500"
                    required
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">Stage</label>
                  <select
                    value={taskStage}
                    onChange={(e) => setTaskStage(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs outline-none focus:border-blue-500 text-slate-300"
                  >
                    <option value="beginner">Beginner</option>
                    <option value="intermediate">Intermediate</option>
                    <option value="advanced">Advanced</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">Task Title</label>
                <input
                  type="text"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="e.g. Daily Showroom Valuation"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs outline-none focus:border-blue-500"
                  required
                />
              </div>

              <div>
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">Scenario Description</label>
                <textarea
                  value={taskScenario}
                  onChange={(e) => setTaskScenario(e.target.value)}
                  placeholder="Provide training scenarios goals and coordinates expectations detail..."
                  rows={3}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs outline-none focus:border-blue-500"
                  required
                />
              </div>

              <div>
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">Source Workbook (.xlsx)</label>
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={(e) => setTaskFile(e.target.files[0])}
                  className="w-full text-xs text-slate-400 border border-slate-800 rounded-xl bg-slate-950 p-2"
                  required
                />
              </div>

              {/* Dynamic Validations Creator */}
              <div className="pt-2 border-t border-slate-800/80">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] uppercase font-bold text-slate-300">Cell Validations Specifications</span>
                  <button
                    type="button"
                    onClick={addValidationRow}
                    className="text-[10px] font-bold text-blue-400 hover:underline"
                  >
                    + Add Cell
                  </button>
                </div>

                <div className="space-y-3 max-h-48 overflow-y-auto pr-1">
                  {cellValidations.map((val, idx) => (
                    <div key={idx} className="p-3 bg-slate-950 border border-slate-850 rounded-xl relative space-y-2">
                      <div className="grid grid-cols-3 gap-2">
                        <input
                          type="text"
                          value={val.cell_reference}
                          onChange={(e) => handleValidationChange(idx, "cell_reference", e.target.value)}
                          placeholder="e.g. B11"
                          className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[10px]"
                          required
                        />
                        <input
                          type="text"
                          value={val.expected_value}
                          onChange={(e) => handleValidationChange(idx, "expected_value", e.target.value)}
                          placeholder="Expected Val"
                          className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[10px]"
                          required
                        />
                        <input
                          type="text"
                          value={val.required_function}
                          onChange={(e) => handleValidationChange(idx, "required_function", e.target.value)}
                          placeholder="e.g. SUM"
                          className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[10px]"
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <label className="flex items-center gap-1 text-[9px] text-slate-400">
                            <input
                              type="checkbox"
                              checked={val.is_financial}
                              onChange={(e) => handleValidationChange(idx, "is_financial", e.target.checked)}
                            />
                            Financial (AED)
                          </label>
                          <label className="flex items-center gap-1 text-[9px] text-slate-400">
                            <input
                              type="checkbox"
                              checked={val.is_date}
                              onChange={(e) => handleValidationChange(idx, "is_date", e.target.checked)}
                            />
                            Date
                          </label>
                        </div>
                        {cellValidations.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeValidationRow(idx)}
                            className="text-[9px] text-red-400 hover:underline"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <input
                        type="text"
                        value={val.correct_formula_hint}
                        onChange={(e) => handleValidationChange(idx, "correct_formula_hint", e.target.value)}
                        placeholder="Formula hint e.g. =SUM(B4:B10)"
                        className="w-full px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[9px]"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                disabled={taskLoading}
                className="w-full py-2.5 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-2xl transition-all shadow-md active:scale-95 flex items-center justify-center gap-1.5"
              >
                {taskLoading ? "Deploying custom workbook..." : "Deploy Active Task"}
              </button>
            </form>
          </div>

        </div>

      </div>
    </div>
  );
}
