import React, { useState, useRef, useEffect } from "react";
import { LogOut, Send, ShieldCheck, Dot, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const dummyChat = [
  { id: 1, role: "agent", text: "Welcome to BrainBack Secure Banking. How can I help you today?" },
  { id: 2, role: "user", text: "I'm looking to apply for a car loan." },
  { id: 3, role: "agent", text: "I can help with that. To check your eligibility, could you please confirm your monthly salary and current CIBIL score?" },
  { id: 4, role: "user", text: "My salary is 85000 and my score is 780." }
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const [chat, setChat] = useState(dummyChat);
  const [input, setInput] = useState("");
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);
  const chatEndRef = useRef(null);

  useEffect(() => {
    const fetchUserData = async () => {
      const token = localStorage.getItem("token");
      if (!token) {
        navigate("/loan-login");
        return;
      }
      try {
        const response = await axios.get(`${import.meta.env.VITE_BASE_URL}/loan/profile`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setUserData(response.data.user || response.data);
      } catch (err) {
        console.error("Invalid token or failed to fetch user data", err);
        localStorage.removeItem("token");
        navigate("/loan-login");
      } finally {
        setLoading(false);
      }
    };

    fetchUserData();
  }, [navigate]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/loan-login");
  };

  const handleSend = () => {
    if (input.trim()) {
      setChat([...chat, { id: chat.length + 1, role: "user", text: input }]);
      setInput("");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-emerald-400">
        <Loader2 className="w-12 h-12 animate-spin mb-4" />
        <p className="text-xl font-semibold">Authenticating Session...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-br from-slate-100 to-slate-200 font-sans">
      {/* Top Navigation */}
      <nav className="flex items-center justify-between h-16 px-4 md:px-8 bg-white/90 border-b border-slate-200 shadow-sm backdrop-blur-lg z-10">
        <div className="flex items-center gap-3">
          <ShieldCheck className="text-blue-700 w-8 h-8 drop-shadow-md" />
          <span className="font-extrabold text-2xl md:text-3xl tracking-tight text-slate-900 select-none">BrainBack Secure Banking</span>
        </div>
        <div className="flex items-center gap-4 md:gap-6">
          <span className="flex items-center gap-2 bg-green-100 text-green-700 px-3 py-1 rounded-full font-semibold text-sm shadow-sm">
            <Dot className="animate-pulse text-green-500 w-5 h-5" />
            Session Active
          </span>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-700 to-slate-800 text-white rounded-lg hover:from-blue-800 hover:to-slate-900 transition font-bold shadow-md focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <LogOut className="w-5 h-5" /> Logout
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden max-w-7xl mx-auto w-full shadow-xl rounded-2xl bg-white/80 mt-4 mb-4 md:mb-8 md:mt-8">
        {/* Chat Area */}
        <section className="flex flex-col w-full md:w-[70%] h-[60vh] md:h-auto bg-white border-b md:border-b-0 md:border-r border-slate-200 transition-all duration-300">
          <div className="flex-1 overflow-y-auto px-3 md:px-8 py-4 md:py-6 space-y-4 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
            {chat.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85vw] md:max-w-[70%] px-4 py-3 rounded-2xl shadow-md text-base whitespace-pre-line break-words
                    ${msg.role === "user"
                      ? "bg-gradient-to-br from-blue-600 to-blue-500 text-white rounded-br-md"
                      : "bg-slate-100 text-slate-900 rounded-bl-md border border-slate-200"}
                  `}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
          {/* Input Bar */}
          <div className="sticky bottom-0 bg-white/95 border-t border-slate-200 px-3 md:px-8 py-3 md:py-4 flex items-center gap-2 md:gap-3 z-10">
            <input
              type="text"
              className="flex-1 px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-slate-50 text-slate-900 shadow-sm placeholder-slate-400 text-base md:text-lg"
              placeholder="Type your message..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSend()}
            />
            <button
              onClick={handleSend}
              className="p-2 md:p-3 bg-gradient-to-br from-blue-600 to-blue-500 text-white rounded-full hover:from-blue-700 hover:to-blue-600 transition shadow-md focus:outline-none focus:ring-2 focus:ring-blue-400"
              aria-label="Send"
            >
              <Send className="w-5 h-5 md:w-6 md:h-6" />
            </button>
          </div>
        </section>

        {/* Vault Sidebar */}
        <aside className="w-full md:w-[30%] h-[40vh] md:h-auto bg-gradient-to-br from-slate-50 to-slate-200 flex flex-col border-t md:border-t-0 md:border-l border-slate-200 transition-all duration-300">
          <div className="flex items-center justify-between px-4 md:px-6 pt-4 md:pt-6 pb-2">
            <h2 className="flex items-center gap-2 text-lg md:text-xl font-bold text-slate-800 tracking-tight">
              <ShieldCheck className="w-5 h-5 text-blue-700" />
              Client Vault (Decrypted)
            </h2>
          </div>
          <div className="flex-1 px-4 md:px-6 py-4 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
            {userData && Object.keys(userData).length > 0 ? (
              <div className="space-y-6">
                {Object.entries(userData).map(([key, value]) => {
                  if (typeof value === 'object' || key === '_id' || key === 'password' || key === '__v') return null;
                  return (
                    <div key={key} className="flex flex-col gap-1 overflow-hidden">
                      <span className="text-xs md:text-sm text-slate-500 font-mono tracking-tight uppercase truncate">
                        {key.replace(/([A-Z])/g, ' $1').trim()}
                      </span>
                      <span className="text-xl md:text-2xl font-extrabold text-slate-900 tracking-wide truncate" title={value}>
                        {value}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center text-slate-400">
                <ShieldCheck className="w-12 h-12 mb-4 text-slate-300" />
                <span className="text-lg md:text-xl font-bold">No user data found.</span>
                <span className="text-sm md:text-base mt-2">The vault is currently empty.</span>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
