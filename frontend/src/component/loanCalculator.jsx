import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Calculator } from "lucide-react";

/* ── Interactive Loan Calculator Component ── */
const LoanCalculator = () => {
  const schemes = [
    { name: "Home Loan", minRate: 8.5 },
    { name: "Car Loan", minRate: 9.0 },
    { name: "Personal Loan", minRate: 11.5 },
    { name: "Education Loan", minRate: 7.5 },
  ];

  const [scheme, setScheme] = useState(schemes[0].name);
  const [amount, setAmount] = useState("50,00,000");
  const [tenure, setTenure] = useState("15");
  const [rate, setRate] = useState(String(schemes[0].minRate));

  useEffect(() => {
    const s = schemes.find(s => s.name === scheme);
    if(s) setRate(String(s.minRate));
  }, [scheme]);

  const p = parseFloat(String(amount).replace(/,/g, '')) || 0;
  const r = (parseFloat(String(rate).replace(/,/g, '')) || 0) / 12 / 100;
  const n = (parseFloat(String(tenure).replace(/,/g, '')) || 0) * 12;

  let emi = 0;
  let totalPayable = 0;
  let totalInterest = 0;

  if (p > 0 && r > 0 && n > 0) {
    emi = (p * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
    totalPayable = emi * n;
    totalInterest = totalPayable - p;
  }

  const formatInr = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Math.round(val));

  return (
    <motion.div 
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, type: "spring", bounce: 0.4 }}
      viewport={{ once: true, margin: "-100px" }}
      className="w-full max-w-4xl mx-auto my-12 mb-24 p-6 md:p-8 bg-white/[0.02] border border-emerald-500/30 rounded-[2rem] backdrop-blur-xl shadow-[0_10px_40px_rgba(52,211,153,0.15)] ring-1 ring-emerald-400/20 relative overflow-hidden font-sans"
    >
      <div className="absolute top-0 right-0 w-[400px] h-[400px] bg-emerald-500/10 blur-[80px] rounded-full pointer-events-none -z-10 translate-x-1/2 -translate-y-1/2" />
      
      <div className="flex items-center gap-3 justify-center mb-8">
        <div className="p-2 bg-[#03060a] rounded-lg shadow-inner border border-emerald-500/30">
          <Calculator className="w-4 h-4 text-emerald-400" />
        </div>
        <h2 className="text-lg md:text-xl font-bold text-white tracking-widest uppercase">Smart Rate Calculator</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8 lg:gap-10 items-center">
        <div className="flex flex-col gap-5 text-left relative z-10 lg:col-span-3">
          
          <div>
            <label className="block text-xs font-semibold text-indigo-300 mb-1.5 uppercase tracking-wider">Loan Scheme Focus</label>
            <select 
              value={scheme}
              onChange={(e) => setScheme(e.target.value)}
              className="relative z-50 w-full bg-[#03060a]/80 backdrop-blur-md border border-emerald-500/30 hover:border-emerald-400/60 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:ring-1 focus:ring-emerald-400/80 appearance-none text-sm font-medium transition-colors shadow-inner cursor-pointer"
            >
              {schemes.map(s => <option key={s.name} value={s.name}>{s.name} (from {s.minRate}%)</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-indigo-300 mb-1.5 uppercase tracking-wider">Capital Request (₹)</label>
            <input 
              type="text" 
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="relative z-50 w-full bg-[#03060a]/80 backdrop-blur-md border border-emerald-500/30 hover:border-emerald-400/60 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:ring-1 focus:ring-emerald-400/80 text-sm font-medium transition-colors shadow-inner"
              placeholder="e.g., 5000000"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-indigo-300 mb-1.5 uppercase tracking-wider whitespace-nowrap">Time Horizon (Yrs)</label>
              <input 
                type="text" 
                value={tenure}
                onChange={(e) => setTenure(e.target.value)}
                className="relative z-50 w-full bg-[#03060a]/80 backdrop-blur-md border border-emerald-500/30 hover:border-emerald-400/60 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:ring-1 focus:ring-emerald-400/80 text-sm font-medium transition-colors shadow-inner"
                placeholder="e.g., 15"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-indigo-300 mb-1.5 uppercase tracking-wider whitespace-nowrap">Calculated Rate (%)</label>
              <input 
                type="text" 
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                className="relative z-50 w-full bg-[#03060a]/80 backdrop-blur-md border border-emerald-500/30 hover:border-emerald-400/60 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:ring-1 focus:ring-emerald-400/80 text-sm font-medium transition-colors shadow-inner"
                placeholder="e.g., 8.5"
              />
            </div>
          </div>

        </div>

        {/* Results Panel */}
        <div className="bg-gradient-to-b from-[#03060a] to-[#0A0D14] border border-white/5 rounded-2xl p-6 flex flex-col justify-center relative shadow-[inset_0_0_50px_rgba(52,211,153,0.03)] lg:col-span-2">
          <div className="absolute top-0 right-0 w-full h-1 bg-gradient-to-r from-transparent via-emerald-400 to-transparent opacity-30" />
          
          <div className="mb-5 text-center">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Projected Monthly EMI</h4>
            <div className="text-3xl lg:text-4xl font-black text-transparent bg-clip-text bg-gradient-to-br from-emerald-300 to-cyan-400 tracking-tight drop-shadow-sm">
              {emi > 0 ? formatInr(emi) : '₹0'}
            </div>
          </div>

          <div className="h-px w-full bg-gradient-to-r from-transparent via-white/10 to-transparent mb-5" />

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1 items-center text-center">
              <span className="text-xs tracking-wider font-semibold uppercase text-slate-500">Interest Burden</span>
              <span className="text-base font-bold text-emerald-300 tracking-wide">{totalInterest > 0 ? formatInr(totalInterest) : '₹0'}</span>
            </div>
            
            <div className="flex flex-col gap-1 items-center justify-center text-center mt-1 p-3 bg-white/[0.02] border border-indigo-500/10 rounded-xl shadow-inner">
              <span className="text-xs tracking-wider font-semibold uppercase text-indigo-400/80">Total Lifecycle Cost</span>
              <span className="text-lg font-black text-indigo-300 tracking-wide">{totalPayable > 0 ? formatInr(totalPayable) : '₹0'}</span>
            </div>
          </div>

        </div>

      </div>
    </motion.div>
  );
};

export default LoanCalculator;