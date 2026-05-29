import React, { useState } from "react";
import { LogIn, User, ShieldAlert, Award, UserPlus, Mail, Lock } from "lucide-react";
import { auth } from "../firebase";
import { signInWithEmailAndPassword, createUserWithEmailAndPassword } from "firebase/auth";
import { api } from "../api";

export default function Login({ onLoginSuccess }) {
  const [activeTab, setActiveTab] = useState("signin"); // 'signin' or 'signup'
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAuth = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    
    const emailClean = email.trim();
    
    try {
      if (activeTab === "signup") {
        if (!fullName.trim()) {
          throw new Error("Full name is required.");
        }
        
        // 1. Firebase Auth Registration
        const userCredential = await createUserWithEmailAndPassword(auth, emailClean, password);
        const idToken = await userCredential.user.getIdToken();
        
        // 2. Propagate profile card creation to FastAPI backend
        await api.signup(idToken, fullName.trim());
        
        // 3. Complete login and retrieve user progress
        const loginData = await api.login(idToken);
        onLoginSuccess(loginData.user);
      } else {
        // 1. Firebase Auth Sign-in
        const userCredential = await signInWithEmailAndPassword(auth, emailClean, password);
        const idToken = await userCredential.user.getIdToken();
        
        // 2. Retrieve user session and progress from FastAPI
        const loginData = await api.login(idToken);
        onLoginSuccess(loginData.user);
      }
    } catch (err) {
      console.error("Auth failed:", err);
      // Clean up common Firebase errors into human readable messages
      let msg = err.message || "Authentication failed.";
      if (err.code === "auth/email-already-in-use") {
        try {
          console.log("Email already in use in Firebase. Attempting automatic backend registration sync...");
          // Attempt to sign in with the provided password to authenticate
          const userCredential = await signInWithEmailAndPassword(auth, emailClean, password);
          const idToken = await userCredential.user.getIdToken();
          
          // Force FastAPI signup linking
          await api.signup(idToken, fullName.trim() || emailClean.split("@")[0]);
          
          // Complete login
          const loginData = await api.login(idToken);
          onLoginSuccess(loginData.user);
          return;
        } catch (syncErr) {
          console.error("Auto sync failed:", syncErr);
          msg = "This email is already registered, and password verification failed. Please try signing in.";
        }
      } else if (err.code === "auth/invalid-credential" || err.code === "auth/wrong-password" || err.code === "auth/user-not-found") {
        msg = "Incorrect email or password. Please verify credentials.";
      } else if (err.code === "auth/weak-password") {
        msg = "Password must be at least 6 characters long.";
      } else if (err.code === "auth/invalid-email") {
        msg = "Please enter a valid email address.";
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickSelect = (userEmail, pass, tab = "signin") => {
    setActiveTab(tab);
    setEmail(userEmail);
    setPassword(pass);
    if (tab === "signup") {
      // Find full name from template
      const item = testUsers.find(u => u.email === userEmail);
      setFullName(item ? item.name : "");
    }
    setError("");
  };

  const testUsers = [
    { email: "yousef@training.com", name: "Yousef", role: "Student" },
    { email: "mahmoud@training.com", name: "Mahmoud Ahmed", role: "Student" },
    { email: "arslan@training.com", name: "Arslan Ishaq", role: "Student" },
    { email: "admin@training.com", name: "Administrator", role: "Admin" }
  ];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      {/* Title */}
      <div className="mb-8 text-center animate-slide-up">
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="p-3 bg-gradient-to-tr from-blue-600 to-indigo-600 rounded-2xl shadow-lg glow-blue">
            <Award className="w-8 h-8 text-white" />
          </div>
          <span className="text-2xl font-extrabold tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-200 to-indigo-400">
            FINANCIAL ACADEMY
          </span>
        </div>
        <p className="text-slate-400 text-sm tracking-wide">Excel Training & Performance Auditing Portal</p>
      </div>

      {/* Main Card */}
      <div className="w-full max-w-md glass-panel rounded-3xl p-8 glow-blue animate-slide-up" style={{ animationDelay: '100ms' }}>
        {/* Signin vs Signup Tabs Toggle */}
        <div className="flex bg-slate-950 p-1.5 rounded-2xl mb-6 border border-slate-900">
          <button
            onClick={() => { setActiveTab("signin"); setError(""); }}
            className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
              activeTab === "signin"
                ? "bg-slate-900 text-white shadow"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <LogIn className="w-3.5 h-3.5" />
            Sign In
          </button>
          <button
            onClick={() => { setActiveTab("signup"); setError(""); }}
            className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
              activeTab === "signup"
                ? "bg-slate-900 text-white shadow"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            Sign Up
          </button>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-950/60 border border-red-800/80 rounded-2xl flex items-start gap-3 text-red-200 text-sm animate-pulse-slow">
            <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleAuth} className="space-y-5">
          {activeTab === "signup" && (
            <div>
              <label className="block text-slate-300 text-[10px] font-bold uppercase tracking-wider mb-2">Full Name</label>
              <div className="relative">
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Mahmoud Ahmed"
                  className="w-full pl-11 pr-4 py-3 bg-slate-950/60 border border-slate-800 rounded-2xl focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-slate-100 placeholder-slate-600 outline-none transition-all duration-300 text-sm"
                  required
                />
                <User className="absolute left-4 top-3.5 w-4 h-4 text-slate-500" />
              </div>
            </div>
          )}

          <div>
            <label className="block text-slate-300 text-[10px] font-bold uppercase tracking-wider mb-2">Email Address</label>
            <div className="relative">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@training.com"
                className="w-full pl-11 pr-4 py-3 bg-slate-950/60 border border-slate-800 rounded-2xl focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-slate-100 placeholder-slate-650 outline-none transition-all duration-300 text-sm"
                required
              />
              <Mail className="absolute left-4 top-3.5 w-4 h-4 text-slate-500" />
            </div>
          </div>

          <div>
            <label className="block text-slate-300 text-[10px] font-bold uppercase tracking-wider mb-2">Password</label>
            <div className="relative">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-11 pr-4 py-3 bg-slate-950/60 border border-slate-800 rounded-2xl focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-slate-100 placeholder-slate-650 outline-none transition-all duration-300 text-sm"
                required
              />
              <Lock className="absolute left-4 top-3.5 w-4 h-4 text-slate-500" />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-2xl transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl active:scale-[0.98] text-xs uppercase tracking-wider"
          >
            {loading 
              ? (activeTab === "signup" ? "Creating Firebase account..." : "Authenticating session...")
              : (activeTab === "signup" ? "Create Account & Workspace" : "Sign In to Workspace")
            }
          </button>
        </form>
      </div>

      {/* Quick Select Panel */}
      <div className="w-full max-w-md mt-6 glass-panel rounded-3xl p-6 animate-slide-up" style={{ animationDelay: '200ms' }}>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 text-center">
          Quick-Access Testing Desk
        </h3>
        <p className="text-[10px] text-slate-500 text-center mb-4 leading-relaxed">
          Select standard users to test profile automatic-linking. First-time registration requires selecting <strong>Sign Up</strong>.
        </p>
        
        <div className="grid grid-cols-2 gap-3">
          {testUsers.map((u) => (
            <div key={u.email} className="flex flex-col gap-1.5 p-3 rounded-2xl border bg-slate-900/40 border-slate-800/80 hover:border-slate-700/80 transition-colors">
              <span className="text-xs font-bold text-slate-300 truncate">{u.name}</span>
              <span className="text-[9px] text-slate-500 truncate font-mono">{u.email}</span>
              
              <div className="flex items-center gap-1.5 mt-2">
                <button
                  onClick={() => handleQuickSelect(u.email, "Password123", "signin")}
                  className="flex-1 py-1 text-[9px] font-extrabold uppercase bg-blue-950/60 border border-blue-900/50 hover:bg-blue-900/40 text-blue-400 rounded-lg text-center"
                >
                  In
                </button>
                <button
                  onClick={() => handleQuickSelect(u.email, "Password123", "signup")}
                  className="flex-1 py-1 text-[9px] font-extrabold uppercase bg-emerald-950/60 border border-emerald-900/50 hover:bg-emerald-900/40 text-emerald-400 rounded-lg text-center"
                >
                  Up
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
