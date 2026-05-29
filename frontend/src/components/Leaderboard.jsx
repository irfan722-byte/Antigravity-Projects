import React, { useState, useEffect } from "react";
import { Award, Trophy, User, Calendar, Loader } from "lucide-react";
import { api } from "../api";

export default function Leaderboard() {
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await api.getLeaderboard();
        setBoard(data);
      } catch (err) {
        console.error("Error loading leaderboard:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[300px]">
        <Loader className="w-8 h-8 text-blue-500 animate-spin" />
        <span className="text-slate-400 mt-2 text-sm">Loading leaderboard rankings...</span>
      </div>
    );
  }

  // Extract top 3 for the podium
  const top1 = board.find((u) => u.rank === 1);
  const top2 = board.find((u) => u.rank === 2);
  const top3 = board.find((u) => u.rank === 3);
  
  // Remainders for list
  const runners = board.filter((u) => u.rank > 3);

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Page Title */}
      <div className="flex items-center gap-3">
        <div className="p-2.5 bg-gradient-to-tr from-yellow-500 to-amber-500 rounded-2xl glow-amber">
          <Trophy className="w-6 h-6 text-slate-950" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Training Leaderboard</h1>
          <p className="text-slate-400 text-xs">High scores of our internal finance team</p>
        </div>
      </div>

      {/* 3D-Style Premium Podium */}
      {board.length > 0 && (
        <div className="grid grid-cols-3 gap-4 items-end max-w-xl mx-auto pt-12 pb-4">
          {/* 2nd Place */}
          {top2 ? (
            <div className="flex flex-col items-center group">
              <div className="w-12 h-12 bg-slate-800 rounded-full border border-slate-700/80 flex items-center justify-center text-slate-300 font-bold shadow-lg shadow-black/20 group-hover:scale-105 transition-transform">
                <User className="w-5 h-5 text-slate-400" />
              </div>
              <span className="text-xs font-bold text-slate-300 mt-2 block w-full text-center truncate">{top2.full_name}</span>
              <span className="text-[10px] text-slate-400 font-mono mb-2">{top2.total_points} PTS</span>
              
              {/* Pillar */}
              <div className="w-full h-24 bg-gradient-to-t from-slate-900/90 to-slate-800/80 rounded-t-2xl border-t border-x border-slate-700 flex flex-col justify-end p-3 shadow-lg glow-blue">
                <span className="text-2xl font-black text-slate-400 text-center block leading-none">2</span>
                <span className="text-[8px] uppercase tracking-wider text-slate-500 text-center block mt-1">Silver</span>
              </div>
            </div>
          ) : <div />}

          {/* 1st Place */}
          {top1 ? (
            <div className="flex flex-col items-center group -translate-y-4">
              <div className="relative">
                {/* Glowing Golden Crown */}
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-yellow-500 animate-bounce">
                  👑
                </div>
                <div className="w-16 h-16 bg-gradient-to-tr from-yellow-600 to-amber-500 rounded-full border-2 border-yellow-400 flex items-center justify-center text-slate-950 font-extrabold shadow-xl shadow-yellow-500/10 group-hover:scale-105 transition-transform">
                  <Trophy className="w-7 h-7 text-yellow-100" />
                </div>
              </div>
              <span className="text-sm font-extrabold text-yellow-400 mt-2 block w-full text-center truncate">{top1.full_name}</span>
              <span className="text-xs text-yellow-300/80 font-mono mb-2">{top1.total_points} PTS</span>
              
              {/* Pillar */}
              <div className="w-full h-32 bg-gradient-to-t from-slate-900/90 to-amber-950/20 rounded-t-2xl border-t border-x border-yellow-500/50 flex flex-col justify-end p-3 shadow-xl glow-amber">
                <span className="text-4xl font-black text-yellow-400 text-center block leading-none">1</span>
                <span className="text-[8px] uppercase tracking-wider text-yellow-500 text-center block mt-1 font-bold">Champion</span>
              </div>
            </div>
          ) : <div />}

          {/* 3rd Place */}
          {top3 ? (
            <div className="flex flex-col items-center group">
              <div className="w-12 h-12 bg-slate-800 rounded-full border border-slate-700/80 flex items-center justify-center text-slate-300 font-bold shadow-lg shadow-black/20 group-hover:scale-105 transition-transform">
                <User className="w-5 h-5 text-slate-500" />
              </div>
              <span className="text-xs font-bold text-slate-300 mt-2 block w-full text-center truncate">{top3.full_name}</span>
              <span className="text-[10px] text-slate-400 font-mono mb-2">{top3.total_points} PTS</span>
              
              {/* Pillar */}
              <div className="w-full h-16 bg-gradient-to-t from-slate-900/90 to-slate-800/80 rounded-t-2xl border-t border-x border-slate-700 flex flex-col justify-end p-3 shadow-lg glow-blue">
                <span className="text-xl font-black text-amber-700 text-center block leading-none">3</span>
                <span className="text-[8px] uppercase tracking-wider text-slate-500 text-center block mt-1">Bronze</span>
              </div>
            </div>
          ) : <div />}
        </div>
      )}

      {/* Rankings List */}
      <div className="glass-panel rounded-3xl overflow-hidden p-6 max-w-xl mx-auto">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 px-2">
          Rankings Standings
        </h3>
        
        {board.length === 0 ? (
          <div className="text-center py-6 text-slate-500 text-sm">
            No training activities completed yet. Be the first to secure a spot!
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {board.map((u) => (
              <div
                key={u.user_id}
                className="py-3 px-2 flex items-center justify-between hover:bg-slate-900/20 rounded-xl transition-colors duration-200"
              >
                <div className="flex items-center gap-4">
                  {/* Rank bubble */}
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                    u.rank === 1 ? "bg-yellow-500/20 text-yellow-400" :
                    u.rank === 2 ? "bg-slate-300/25 text-slate-300" :
                    u.rank === 3 ? "bg-amber-700/20 text-amber-600" :
                    "bg-slate-900 text-slate-400"
                  }`}>
                    {u.rank}
                  </span>
                  
                  <span className="text-sm font-semibold text-slate-200">{u.full_name}</span>
                </div>
                
                <span className="text-sm font-mono font-bold text-blue-400">{u.total_points} PTS</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
