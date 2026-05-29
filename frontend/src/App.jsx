import React, { useState, useEffect } from "react";
import { Award, Trophy, LayoutDashboard, Settings, LogOut, Loader, RefreshCw, Sparkles, MessageSquare } from "lucide-react";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { auth } from "./firebase";
import { api } from "./api";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import Leaderboard from "./components/Leaderboard";
import AdminPanel from "./components/AdminPanel";

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [currentTab, setCurrentTab] = useState("dashboard"); // 'dashboard', 'leaderboard', 'admin'
  const [announcement, setAnnouncement] = useState(null);

  useEffect(() => {
    // 1. Reactive Firebase Authentication session listener
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setLoading(true);
      if (firebaseUser) {
        try {
          // Retrieve dynamic ID token and cache it in localStorage
          const token = await firebaseUser.getIdToken(true); // force refresh to get latest claims
          api.setToken(token);
          
          // Fetch student/admin profile from FastAPI SQLite database
          const userData = await api.getMe();
          setUser(userData);
          
          if (userData.role === "admin") {
            setCurrentTab("admin");
          } else {
            setCurrentTab("dashboard");
          }
          await loadAnnouncements();
        } catch (err) {
          console.error("Session sync with FastAPI failed:", err);
          if (err.message && err.message.includes("not registered")) {
            console.log("Firebase authenticated user is not registered in FastAPI backend. Redirecting to signup...");
            setUser(null);
          } else {
            handleLogout();
          }
        }
      } else {
        // No active Firebase session
        setUser(null);
        api.logout();
        setAnnouncement(null);
        setCurrentTab("dashboard");
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  async function loadAnnouncements() {
    try {
      const ann = await api.getAnnouncements();
      if (ann && ann.content) {
        setAnnouncement(ann.content);
      } else {
        setAnnouncement(null);
      }
    } catch (err) {
      console.error("Failed to load active announcements:", err);
    }
  }

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    if (userData.role === "admin") {
      setCurrentTab("admin");
    } else {
      setCurrentTab("dashboard");
    }
    loadAnnouncements();
  };

  const handleLogout = async () => {
    setLoading(true);
    try {
      await signOut(auth);
    } catch (err) {
      console.error("Firebase SignOut error:", err);
    }
    api.logout();
    setUser(null);
    setAnnouncement(null);
    setCurrentTab("dashboard");
    setLoading(false);
  };

  const refreshUserData = async () => {
    try {
      const userData = await api.getMe();
      setUser(userData);
      await loadAnnouncements();
    } catch (err) {
      console.error("Failed to refresh user progress:", err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center">
        <RefreshCw className="w-10 h-10 text-indigo-500 animate-spin mb-4" />
        <span className="text-slate-400 font-medium tracking-wide">Restoring secure session...</span>
      </div>
    );
  }

  // Not logged in -> Show Login workspace
  if (!user) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen bg-slate-950 flex">
      {/* 1. persistent Sidebar Navigation */}
      <aside className="w-64 bg-slate-900/40 border-r border-slate-900 flex flex-col justify-between p-6 shrink-0">
        <div className="space-y-8">
          {/* Logo Brand */}
          <div className="flex items-center gap-2">
            <div className="p-2 bg-gradient-to-tr from-blue-600 to-indigo-600 rounded-xl shadow-lg glow-blue">
              <Award className="w-5 h-5 text-white" />
            </div>
            <span className="font-extrabold tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-200 to-indigo-400 text-sm">
              FINANCIAL ACADEMY
            </span>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1.5">
            {user.role === "user" && (
              <button
                onClick={() => setCurrentTab("dashboard")}
                className={`w-full px-4 py-3 rounded-2xl flex items-center gap-3 text-xs font-bold transition-all duration-300 ${
                  currentTab === "dashboard"
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-500/10 glow-blue"
                    : "text-slate-400 hover:bg-slate-900/60 hover:text-slate-200"
                }`}
              >
                <LayoutDashboard className="w-4 h-4" />
                My Workspace
              </button>
            )}

            {user.role === "admin" && (
              <button
                onClick={() => setCurrentTab("admin")}
                className={`w-full px-4 py-3 rounded-2xl flex items-center gap-3 text-xs font-bold transition-all duration-300 ${
                  currentTab === "admin"
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/10 glow-blue"
                    : "text-slate-400 hover:bg-slate-900/60 hover:text-slate-200"
                }`}
              >
                <Settings className="w-4 h-4" />
                Management Desk
              </button>
            )}

            <button
              onClick={() => setCurrentTab("leaderboard")}
              className={`w-full px-4 py-3 rounded-2xl flex items-center gap-3 text-xs font-bold transition-all duration-300 ${
                currentTab === "leaderboard"
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-500/10 glow-blue"
                  : "text-slate-400 hover:bg-slate-900/60 hover:text-slate-200"
              }`}
            >
              <Trophy className="w-4 h-4" />
              Leaderboard
            </button>
          </nav>
        </div>

        {/* User Card & Logout */}
        <div className="space-y-4 pt-6 border-t border-slate-800/60">
          {/* User Details */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-slate-800 rounded-full border border-slate-700/80 flex items-center justify-center font-bold text-xs text-indigo-400">
              {user.full_name.charAt(0)}
            </div>
            <div className="truncate">
              <span className="block text-xs font-bold text-slate-200 truncate">{user.full_name}</span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold uppercase ${
                user.role === "admin" ? "bg-red-900/40 text-red-400" : "bg-emerald-900/40 text-emerald-400"
              }`}>
                {user.role === "admin" ? "Admin" : "Student"}
              </span>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="w-full py-2.5 bg-slate-950/60 hover:bg-red-950/20 text-slate-400 hover:text-red-400 border border-slate-850 hover:border-red-900/40 rounded-xl transition-all duration-300 flex items-center justify-center gap-2 text-xs font-bold active:scale-[0.98]"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* 2. Main Content Frame */}
      <main className="flex-1 flex flex-col overflow-y-auto">
        
        {/* Floating Reward Announcement Banner Overlay */}
        {user.role === "user" && announcement && (
          <div className="bg-gradient-to-r from-blue-900/80 via-indigo-950/90 to-blue-900/80 border-b border-blue-500/30 p-3.5 text-center text-xs text-slate-200 flex items-center justify-center gap-2 glow-blue animate-pulse-slow">
            <Sparkles className="w-4 h-4 text-yellow-400 shrink-0" />
            <span className="font-semibold">{announcement}</span>
          </div>
        )}

        {/* Global Progress Bar (Persistent Header for Standard Users) */}
        {user.role === "user" && user.progress && (
          <header className="bg-slate-900/20 border-b border-slate-900/60 py-4 px-8 flex items-center justify-between gap-6">
            <div className="flex-1 max-w-md">
              <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider mb-1.5 text-slate-400">
                <span>Overall Curriculum Progress</span>
                <span>
                  {user.progress.last_completed_task_id === "daily_showroom_footfall" ? "33%" :
                   user.progress.last_completed_task_id === "monthly_sales_commission" ? "66%" :
                   user.progress.last_completed_task_id === "dealership_profitability" || user.progress.current_active_task_id === "completed" ? "100%" :
                   "0%"}
                </span>
              </div>
              <div className="w-full bg-slate-950 border border-slate-850 rounded-full h-2 overflow-hidden">
                <div 
                  className="bg-gradient-to-r from-blue-500 to-indigo-500 h-full rounded-full transition-all duration-1000 glow-blue"
                  style={{
                    width: `${user.progress.last_completed_task_id === "daily_showroom_footfall" ? "33%" :
                            user.progress.last_completed_task_id === "monthly_sales_commission" ? "66%" :
                            user.progress.last_completed_task_id === "dealership_profitability" || user.progress.current_active_task_id === "completed" ? "100%" :
                            "0%"}`
                  }}
                />
              </div>
            </div>

            <div className="flex items-center gap-6">
              <div className="text-right">
                <span className="text-[9px] uppercase font-bold tracking-wider text-slate-500 block">Active Stage</span>
                <span className="text-xs font-bold text-indigo-400 capitalize">
                  {user.progress.current_active_task_id === "completed" ? "Finished" : user.progress.current_active_task_id?.replace(/_/g, " ")}
                </span>
              </div>

              <div className="text-right border-l border-slate-800 pl-6">
                <span className="text-[9px] uppercase font-bold tracking-wider text-slate-500 block">Total points</span>
                <span className="text-sm font-mono font-black text-yellow-400 leading-none block mt-0.5">{user.total_points} PTS</span>
              </div>
            </div>
          </header>
        )}

        {/* Dynamic Inner Tab View Router */}
        <div className="p-8 flex-1 max-w-6xl w-full mx-auto">
          {currentTab === "dashboard" && <Dashboard user={user} onProgressUpdate={refreshUserData} />}
          {currentTab === "leaderboard" && <Leaderboard />}
          {currentTab === "admin" && <AdminPanel />}
        </div>
      </main>
    </div>
  );
}
