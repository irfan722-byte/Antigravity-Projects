import React, { useState, useEffect } from "react";
import { Download, UploadCloud, CheckCircle2, Lock, PlayCircle, ShieldAlert, Award, FileSpreadsheet, RefreshCw, ChevronRight } from "lucide-react";
import { api } from "../api";

const TASK_SEQUENCE = [
  "daily_showroom_footfall",
  "weekly_sales_volume",
  "showroom_csat_score",
  "spare_parts_orders",
  "test_drive_conversion",
  "monthly_sales_commission",
  "camry_fleet_lease",
  "sales_agent_performance",
  "spare_parts_valuation",
  "opex_allocation",
  "loan_eligibility",
  "revenue_share_audit",
  "dealership_profitability",
  "holding_cost_aging",
  "capital_project_eval",
  "dynamic_commission",
  "trade_in_depreciation",
  "working_capital_aging",
  "fleet_procurement",
  "showroom_feasibility",
  "parts_forecasting",
  "service_capacity"
];

export default function Dashboard({ user, onProgressUpdate }) {
  const [task, setTask] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  
  // Grading response states
  const [graderStatus, setGraderStatus] = useState(null); // 'passed', 'failed', 'error'
  const [graderMessage, setGraderMessage] = useState("");
  const [errorsList, setErrorsList] = useState({});
  const [pointsAwarded, setPointsAwarded] = useState(0);
  const [isFirstTry, setIsFirstTry] = useState(false);

  useEffect(() => {
    loadActiveTask();
  }, []);

  async function loadActiveTask() {
    setLoading(true);
    setGraderStatus(null);
    try {
      const data = await api.getActiveTask();
      setTask(data);
    } catch (err) {
      console.error("Error loading active task:", err);
    } finally {
      setLoading(false);
    }
  }

  // Handle drag events
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = async (e) => {
    if (e.target.files && e.target.files[0]) {
      await handleFileUpload(e.target.files[0]);
    }
  };

  const handleFileUpload = async (file) => {
    setUploading(true);
    setGraderStatus(null);
    
    try {
      const result = await api.submitTask(task.task_id, file);
      setGraderStatus(result.status);
      setGraderMessage(result.message);
      
      if (result.status === "passed") {
        setPointsAwarded(result.points_awarded);
        setIsFirstTry(result.is_first_try);
        // Refresh global user state in App.jsx (points, progress)
        onProgressUpdate();
      } else {
        setErrorsList(result.errors || {});
      }
    } catch (err) {
      setGraderStatus("error");
      setGraderMessage(err.message || "An unexpected error occurred during grading.");
    } finally {
      setUploading(false);
    }
  };

  const getStageHeaderColor = (stage) => {
    switch (stage) {
      case "beginner": return "text-emerald-400 border-emerald-900/60 bg-emerald-950/20";
      case "intermediate": return "text-blue-400 border-blue-900/60 bg-blue-950/20";
      case "advanced": return "text-purple-400 border-purple-900/60 bg-purple-950/20";
      default: return "text-slate-400 border-slate-900/60 bg-slate-950/20";
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
        <span className="text-slate-400 mt-2 text-sm">Synchronizing your learning state...</span>
      </div>
    );
  }

  // Calculate overall progress percentage dynamically based on 22 tasks sequence
  let overallPercent = 0;
  if (user.progress) {
    if (user.progress.current_active_task_id === "completed") {
      overallPercent = 100;
    } else {
      const lastIdx = TASK_SEQUENCE.indexOf(user.progress.last_completed_task_id);
      if (lastIdx !== -1) {
        overallPercent = Math.round(((lastIdx + 1) / TASK_SEQUENCE.length) * 100);
      }
    }
  }

  // If curriculum is completely completed
  if (task?.status === "completed" || user.progress?.current_active_task_id === "completed") {
    return (
      <div className="max-w-2xl mx-auto text-center py-12 px-4 animate-slide-up">
        <div className="w-24 h-24 bg-gradient-to-tr from-yellow-500 to-amber-500 rounded-full flex items-center justify-center mx-auto mb-8 shadow-xl shadow-yellow-500/20 glow-amber">
          <Award className="w-12 h-12 text-slate-950" />
        </div>
        <h1 className="text-3xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-yellow-400 via-amber-200 to-yellow-400 mb-4">
          Training Complete!
        </h1>
        <p className="text-slate-300 max-w-md mx-auto mb-8 leading-relaxed">
          Amazing work, <span className="font-bold text-slate-100">{user.full_name}</span>! You have successfully completed all stages of the Automotive Retail Finance training.
        </p>

        {/* Global Progress Bar */}
        <div className="glass-panel p-6 rounded-3xl mb-8">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider mb-2">
            <span className="text-emerald-400">Curriculum Completion</span>
            <span className="text-slate-300">100%</span>
          </div>
          <div className="w-full bg-slate-950 rounded-full h-3.5 border border-slate-800 p-0.5 overflow-hidden">
            <div className="bg-gradient-to-r from-emerald-500 to-teal-500 h-full rounded-full transition-all duration-1000 glow-emerald" style={{ width: "100%" }} />
          </div>
        </div>

        <div className="flex items-center justify-center gap-4">
          <span className="text-slate-400 text-sm">Your Final Score:</span>
          <span className="text-2xl font-mono font-black text-yellow-400">{user.total_points} PTS</span>
        </div>
      </div>
    );
  }

  // Calculate dynamic stage status
  const isBeginnerCompleted = user.progress?.intermediate_unlocked || user.progress?.advanced_unlocked || user.progress?.current_active_task_id === "completed";
  
  const isIntermediateCompleted = user.progress?.advanced_unlocked || user.progress?.current_active_task_id === "completed";
  const isIntermediateActive = user.progress?.intermediate_unlocked && !isIntermediateCompleted;
  
  const isAdvancedCompleted = user.progress?.current_active_task_id === "completed";
  const isAdvancedActive = user.progress?.advanced_unlocked && !isAdvancedCompleted;

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Stages Timeline */}
      <div className="glass-panel p-6 rounded-3xl">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-6">
          Training Road Map
        </h3>
        
        <div className="grid grid-cols-3 gap-4 relative">
          {/* Connector Line */}
          <div className="absolute top-[21px] left-[16%] right-[16%] h-[2px] bg-slate-800" />
          <div 
            className="absolute top-[21px] left-[16%] h-[2px] bg-gradient-to-r from-emerald-500 to-blue-500 transition-all duration-1000" 
            style={{ width: `${isIntermediateCompleted ? "68%" : isBeginnerCompleted ? "33%" : "0%"}` }}
          />

          {/* Node 1: Beginner */}
          <div className="flex flex-col items-center z-10">
            <div className={`w-11 h-11 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
              isBeginnerCompleted 
                ? "bg-emerald-950/60 border-emerald-500 text-emerald-400 glow-emerald" 
                : "bg-blue-950/60 border-blue-500 text-blue-400 glow-blue animate-pulse"
            }`}>
              {isBeginnerCompleted ? <CheckCircle2 className="w-5 h-5" /> : <PlayCircle className="w-5 h-5" />}
            </div>
            <span className="text-[11px] font-bold mt-2 text-slate-200">Stage 1: Beginner</span>
            <span className="text-[9px] text-slate-500 mt-0.5">SUM, AVERAGE, COUNT</span>
          </div>

          {/* Node 2: Intermediate */}
          <div className="flex flex-col items-center z-10">
            <div className={`w-11 h-11 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
              isIntermediateCompleted
                ? "bg-emerald-950/60 border-emerald-500 text-emerald-400 glow-emerald" 
                : isIntermediateActive
                ? "bg-blue-950/60 border-blue-500 text-blue-400 glow-blue animate-pulse"
                : "bg-slate-900 border-slate-800 text-slate-600"
            }`}>
              {isIntermediateCompleted 
                ? <CheckCircle2 className="w-5 h-5" /> 
                : isIntermediateActive 
                ? <PlayCircle className="w-5 h-5" /> 
                : <Lock className="w-4 h-4" />}
            </div>
            <span className="text-[11px] font-bold mt-2 text-slate-200">Stage 2: Intermediate</span>
            <span className="text-[9px] text-slate-500 mt-0.5">VLOOKUP, SUMIFS, IF</span>
          </div>

          {/* Node 3: Advanced */}
          <div className="flex flex-col items-center z-10">
            <div className={`w-11 h-11 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
              isAdvancedCompleted
                ? "bg-emerald-950/60 border-emerald-500 text-emerald-400 glow-emerald" 
                : isAdvancedActive
                ? "bg-blue-950/60 border-blue-500 text-blue-400 glow-blue animate-pulse"
                : "bg-slate-900 border-slate-800 text-slate-600"
            }`}>
              {isAdvancedCompleted 
                ? <CheckCircle2 className="w-5 h-5" /> 
                : isAdvancedActive 
                ? <PlayCircle className="w-5 h-5" /> 
                : <Lock className="w-4 h-4" />}
            </div>
            <span className="text-[11px] font-bold mt-2 text-slate-200">Stage 3: Advanced</span>
            <span className="text-[9px] text-slate-500 mt-0.5">INDEX/MATCH, XNPV, XIRR</span>
          </div>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Side: Scenario Details */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-panel p-6 rounded-3xl flex flex-col justify-between h-full">
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className={`text-[10px] px-3 py-1 rounded-full border font-bold uppercase tracking-wider ${getStageHeaderColor(task.stage)}`}>
                  {task.stage} STAGE ACTIVE
                </span>
                <span className="text-xs text-slate-500 font-mono">Attempt #{task.attempt_count + 1}</span>
              </div>
              
              <h2 className="text-2xl font-extrabold text-slate-100 mb-4">{task.title}</h2>
              <div className="text-slate-300 text-sm leading-relaxed whitespace-pre-line p-4 bg-slate-950/60 border border-slate-850 rounded-2xl mb-6">
                {task.scenario_text}
              </div>
            </div>

            <div className="flex items-center gap-4">
              <a
                href={api.getDownloadUrl(task.task_id)}
                download
                className="inline-flex items-center gap-2 px-5 py-3 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-2xl transition-all duration-300 shadow-md shadow-blue-500/10 glow-blue active:scale-95"
              >
                <Download className="w-4 h-4" />
                Download Exercise Sheet (.xlsx)
              </a>
            </div>
          </div>
        </div>

        {/* Right Side: Upload Zone */}
        <div className="lg:col-span-1">
          <div className="glass-panel p-6 rounded-3xl h-full flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-200 mb-2 flex items-center gap-2">
                <UploadCloud className="w-5 h-5 text-indigo-400" />
                Submit Calculations
              </h3>
              <p className="text-xs text-slate-400 mb-6 leading-relaxed">
                Save your completed spreadsheet in Excel and drop it here. We will grade your formulas and cached values instantly.
              </p>
            </div>

            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-3xl p-8 flex flex-col items-center justify-center transition-all duration-300 ${
                dragActive
                  ? "border-blue-500 bg-blue-950/20 glow-blue"
                  : "border-slate-800 bg-slate-950/40 hover:border-slate-700/80 hover:bg-slate-950/60"
              }`}
            >
              {uploading ? (
                <div className="text-center py-4">
                  <RefreshCw className="w-10 h-10 text-indigo-400 animate-spin mx-auto mb-3" />
                  <span className="text-xs font-semibold text-slate-200">Evaluating calculations...</span>
                  <p className="text-[10px] text-slate-500 mt-1">Reading workbook and verifying cells...</p>
                </div>
              ) : (
                <div className="text-center py-2 cursor-pointer group">
                  <input
                    type="file"
                    id="excel-file"
                    accept=".xlsx"
                    onChange={handleFileInput}
                    className="hidden"
                  />
                  <label htmlFor="excel-file" className="cursor-pointer">
                    <FileSpreadsheet className="w-12 h-12 text-slate-500 group-hover:text-blue-400 transition-colors mx-auto mb-3" />
                    <span className="text-xs font-bold text-blue-400 block group-hover:underline mb-1">
                      Click to Browse File
                    </span>
                    <span className="text-[10px] text-slate-500 block">or drag and drop here</span>
                    <span className="text-[9px] text-slate-600 block mt-2">Only .xlsx supported</span>
                  </label>
                </div>
              )}
            </div>
            
            <div className="mt-4 pt-4 border-t border-slate-800/60">
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500 block mb-2">Required Functions Check:</span>
              <div className="flex flex-wrap gap-1.5">
                {task.required_functions_list.map((func) => (
                  <span key={func} className="text-[9px] bg-slate-950 border border-slate-850 px-2 py-0.5 rounded-full font-mono text-slate-400">
                    {func}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Grader Output Details (FAIL / PASS drawers) */}
      {graderStatus === "passed" && (
        <div className="glass-panel p-8 rounded-3xl border-emerald-900 bg-emerald-950/10 glow-emerald animate-pulse-slow">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-emerald-500/20 text-emerald-400 rounded-xl">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-emerald-400">Exercise Completed Successfully!</h3>
              <p className="text-xs text-emerald-300/80">Excellent modelling. You passed all target cell checks.</p>
            </div>
          </div>
          
          <div className="p-4 bg-slate-950/60 border border-slate-850 rounded-2xl flex items-center justify-between">
            <div className="flex items-center gap-4 text-sm text-slate-300">
              <span>Points Earned:</span>
              <span className="text-xl font-mono font-black text-yellow-400">+{pointsAwarded} PTS</span>
              {isFirstTry && (
                <span className="text-[9px] font-extrabold uppercase px-2 py-0.5 bg-yellow-500/20 border border-yellow-500/50 text-yellow-400 rounded-full animate-bounce">
                  ⚡ First-Try Bonus Added!
                </span>
              )}
            </div>
            <button
              onClick={loadActiveTask}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-xl transition-all flex items-center gap-1.5"
            >
              <span>Unlock Next Workspace</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {graderStatus === "failed" && (
        <div className="glass-panel p-6 rounded-3xl border-red-900/60 bg-red-950/10 glow-blue">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-red-500/20 text-red-400 rounded-xl">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-red-400">Validation Audit Failed</h3>
              <p className="text-xs text-slate-400">{graderMessage}</p>
            </div>
          </div>

          {/* Table Diff */}
          <div className="overflow-x-auto rounded-2xl border border-slate-850 bg-slate-950/60 p-2">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="p-3 font-semibold uppercase tracking-wider">Cell</th>
                  <th className="p-3 font-semibold uppercase tracking-wider">Required Function</th>
                  <th className="p-3 font-semibold uppercase tracking-wider">Your Value</th>
                  <th className="p-3 font-semibold uppercase tracking-wider">Your Formula</th>
                  <th className="p-3 font-semibold uppercase tracking-wider">Expected Value</th>
                  <th className="p-3 font-semibold uppercase tracking-wider">Expected Formula / Hint</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {Object.entries(errorsList).map(([cell, details]) => (
                  <tr key={cell} className="hover:bg-slate-900/40 transition-colors">
                    <td className="p-3 font-mono font-bold text-red-400">{cell}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-slate-400">
                        {details.required_function}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-red-300 line-through">{details.actual_value}</td>
                    <td className="p-3 font-mono text-red-300/80 truncate max-w-[150px]" title={details.actual_formula}>
                      {details.actual_formula}
                    </td>
                    <td className="p-3 font-mono font-semibold text-emerald-400">{details.expected_value}</td>
                    <td className="p-3 font-mono font-bold text-emerald-400">{details.correct_formula_hint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {graderStatus === "error" && (
        <div className="glass-panel p-6 rounded-3xl border-red-950 bg-red-950/20 text-red-200 flex items-start gap-4">
          <ShieldAlert className="w-6 h-6 text-red-400 shrink-0 mt-0.5" />
          <div>
            <h3 className="font-bold text-red-400">Workbook Read Error</h3>
            <p className="text-xs mt-1 text-red-300/80 leading-relaxed">{graderMessage}</p>
          </div>
        </div>
      )}
    </div>
  );
}
