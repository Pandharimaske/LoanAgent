import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ShieldCheck, Zap, Bot, ArrowRight,
  TrendingUp, Lock
} from "lucide-react";
import { motion } from "framer-motion";
import ParticleBackground from "./ParticleBackground";

export default function Home() {
  const navigate = useNavigate();

  const features = [
    {
      icon: Bot,
      color: "text-blue-500",
      bgColor: "bg-blue-500",
      bgBase: "bg-blue-500/10",
      borderBase: "border-blue-500/20",
      hoverBorder: "hover:border-blue-500/40",
      hoverShadow: "hover:shadow-[0_20px_60px_rgba(0,0,0,0.4),0_0_40px_rgba(59,130,246,0.15)]",
      iconGlow: "shadow-[0_0_24px_rgba(59,130,246,0.15)]",
      title: "AI-Powered Chat Agent",
      desc: "Have a natural conversation with our intelligent agent. It understands your financial needs and recommends the best loan products in real-time.",
    },
    {
      icon: TrendingUp,
      color: "text-emerald-500",
      bgColor: "bg-emerald-500",
      bgBase: "bg-emerald-500/10",
      borderBase: "border-emerald-500/20",
      hoverBorder: "hover:border-emerald-500/40",
      hoverShadow: "hover:shadow-[0_20px_60px_rgba(0,0,0,0.4),0_0_40px_rgba(16,185,129,0.15)]",
      iconGlow: "shadow-[0_0_24px_rgba(16,185,129,0.15)]",
      title: "Best Rates, Instantly",
      desc: "Our AI compares rates across 50+ lenders in seconds. Get pre-approval and personalised offers without the paperwork or waiting rooms.",
    },
    {
      icon: Lock,
      color: "text-purple-500",
      bgColor: "bg-purple-500",
      bgBase: "bg-purple-500/10",
      borderBase: "border-purple-500/20",
      hoverBorder: "hover:border-purple-500/40",
      hoverShadow: "hover:shadow-[0_20px_60px_rgba(0,0,0,0.4),0_0_40px_rgba(139,92,246,0.15)]",
      iconGlow: "shadow-[0_0_24px_rgba(139,92,246,0.15)]",
      title: "Bank-Grade Security",
      desc: "End-to-end 256-bit AES encryption safeguards every message. Your financial data never leaves our secure, SOC 2-compliant servers.",
    },
  ];

  // Animation variants
  const fadeUpVariant = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 1.2, ease: "easeOut" } },
  };

  const staggerContainer = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.2, delayChildren: 0.4 } },
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#060b14] via-[#0a0f1e] to-[#0d1427] font-sans text-[#f0f4ff] relative overflow-hidden">
      <ParticleBackground />
      
      {/* Grid Overlay with subtle pulse */}
      <div 
        className="fixed inset-0 z-0 pointer-events-none bg-[length:64px_64px] bg-[linear-gradient(rgba(59,130,246,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.025)_1px,transparent_1px)] animate-pulse" 
        style={{ animationDuration: '8s' }} 
      />

      {/* ═══ NAVBAR ═══ */}
      <nav className="sticky top-0 z-[100] flex items-center justify-between px-6 md:px-10 h-16 bg-[#060b14]/85 backdrop-blur-xl border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-[0_4px_16px_rgba(59,130,246,0.4)]">
            <ShieldCheck size={20} className="text-white" />
          </div>
          <span className="font-extrabold text-lg text-[#f0f4ff]">BrainBack.AI</span>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={() => navigate("/dashboard")}
            className="bg-transparent border-none text-slate-400 text-sm font-semibold cursor-pointer px-4 py-2 rounded-xl transition-all duration-200 hover:text-[#f0f4ff] hover:bg-white/5"
          >
            Sign In
          </button>
          <button 
            onClick={() => navigate("/signup")}
            className="flex items-center gap-1.5 bg-gradient-to-br from-blue-500 to-cyan-500 text-white text-[13px] font-bold px-5 py-2.5 rounded-xl cursor-pointer shadow-[0_4px_20px_rgba(59,130,246,0.35)] transition-all duration-200 hover:-translate-y-[1px] hover:shadow-[0_6px_28px_rgba(59,130,246,0.5)]"
          >
            Get Started <ArrowRight size={14} />
          </button>
        </div>
      </nav>

      {/* ═══ HERO ═══ */}
      <section className="relative z-10 flex flex-col items-center text-center px-6 pt-[70px] pb-10 max-w-4xl mx-auto">
        <motion.div 
          animate={{ scale: [1, 1.05, 1], opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
          className="absolute -top-[100px] left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full bg-[radial-gradient(circle,rgba(59,130,246,0.1)_0%,transparent_70%)] blur-[60px] pointer-events-none" 
        />
        <motion.div 
          animate={{ scale: [1, 1.08, 1], opacity: [0.5, 0.9, 0.5] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut", delay: 2 }}
          className="absolute top-0 left-1/2 -translate-x-[60%] w-[400px] h-[300px] rounded-full bg-[radial-gradient(circle,rgba(139,92,246,0.06)_0%,transparent_70%)] blur-[60px] pointer-events-none" 
        />

        <div className="flex flex-col items-center">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, ease: "easeOut" }}
            className="relative z-10 inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-xs font-semibold text-amber-400 mb-7"
          >
            <Zap size={12} className="text-amber-500" />
            <span>Hackathon 2026 · AI-Powered Fintech</span>
          </motion.div>

          <motion.h1 
            initial="hidden"
            animate="visible"
            variants={{
              hidden: { opacity: 0 },
              visible: { opacity: 1, transition: { staggerChildren: 0.15, delayChildren: 0.3 } }
            }}
            className="relative z-10 text-[clamp(2.25rem,5vw,3.5rem)] font-black leading-[1.1] tracking-[-0.04em] mb-5 text-[#f0f4ff] text-center"
          >
            <span className="inline-block">
              {"Your AI Loan Agent.".split(" ").map((word, i) => (
                <motion.span 
                  key={i} 
                  variants={{
                    hidden: { opacity: 0, y: 20, filter: "blur(8px)" },
                    visible: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.8, ease: "easeOut" } }
                  }}
                  className="inline-block mr-[0.22em]"
                >
                  {word}
                </motion.span>
              ))}
            </span>
            <br />
            <motion.span 
              variants={{
                hidden: { opacity: 0, y: 10, filter: "blur(10px)" },
                visible: { 
                  opacity: 1, 
                  y: [0, -6, 0], 
                  filter: "blur(0px)",
                  transition: {
                    opacity: { duration: 1.2, ease: "easeOut" },
                    filter: { duration: 1.2, ease: "easeOut" },
                    y: { duration: 4, repeat: Infinity, ease: "easeInOut", delay: 1.5 }
                  }
                }
              }}
              className="inline-flex gap-[0.25em] mt-1"
            >
              {["Smarter.", "Faster.", "Secure."].map((word, i) => (
                <motion.span
                  key={i}
                  animate={{
                    filter: [
                      "drop-shadow(0px 0px 0px rgba(6,182,212,0))", 
                      "drop-shadow(0px 0px 14px rgba(6,182,212,0.85))", 
                      "drop-shadow(0px 0px 0px rgba(6,182,212,0))",
                      "drop-shadow(0px 0px 0px rgba(6,182,212,0))"
                    ],
                    opacity: [0.65, 1, 0.65, 0.65]
                  }}
                  transition={{
                    duration: 4.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                    times: [0, 0.1666, 0.3333, 1],
                    delay: i * 1.5
                  }}
                  className="bg-clip-text text-transparent bg-gradient-to-r from-blue-500 via-cyan-400 to-purple-500 animate-text-gradient bg-[length:200%_auto]"
                >
                  {word}
                </motion.span>
              ))}
            </motion.span>
          </motion.h1>
        </div>
      </section>

      {/* ═══ FEATURES ═══ */}
      <section className="relative z-10 max-w-6xl mx-auto px-6 py-10 pb-20">
        <motion.div 
          className="grid grid-cols-1 md:grid-cols-3 gap-6"
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-50px" }}
        >
          {features.map((f, i) => {
            const Icon = f.icon;
            return (
              <motion.div 
                key={i} 
                variants={fadeUpVariant}
                className={`group relative p-8 pb-7 bg-white/5 border border-white/5 rounded-2xl cursor-default transition-all duration-300 shadow-[0_8px_32px_rgba(0,0,0,0.3)] hover:scale-[1.03] hover:bg-white/10 ${f.hoverBorder} ${f.hoverShadow}`}
              >
                <div className={`w-[52px] h-[52px] rounded-xl flex items-center justify-center mb-5 ${f.bgBase} ${f.borderBase} border ${f.iconGlow}`}>
                  <Icon size={24} className={f.color} />
                </div>
                <h3 className="text-[17px] font-bold text-[#f0f4ff] mb-2.5 tracking-[-0.01em]">{f.title}</h3>
                <p className="text-[14px] text-slate-400 leading-[1.7] mb-4">{f.desc}</p>
                <div className={`w-10 h-[3px] rounded opacity-60 ${f.bgColor}`} />
              </motion.div>
            );
          })}
        </motion.div>
      </section>
    </div>
  );
}
