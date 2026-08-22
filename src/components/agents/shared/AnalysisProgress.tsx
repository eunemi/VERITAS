"use client";

import React from "react";
import { motion } from "framer-motion";

interface AnalysisProgressProps {
  stages: string[];
  currentStage: number; // 0 to stages.length
  isAnalyzing: boolean;
}

export function AnalysisProgress({ stages, currentStage, isAnalyzing }: AnalysisProgressProps) {
  return (
    <div className="w-full flex flex-col gap-2">
      {stages.map((stage, i) => {
        let status = "WAITING";
        let statusColor = "text-on-surface-variant";
        let bgColor = "bg-primary/5";
        
        if (i < currentStage) {
          status = "COMPLETE";
          statusColor = "text-trust-green";
          bgColor = "bg-trust-green/10";
        } else if (i === currentStage && isAnalyzing) {
          status = "ANALYZING";
          statusColor = "text-secondary animate-pulse";
          bgColor = "bg-secondary/10";
        }

        return (
          <div key={i} className={`flex justify-between items-center px-4 py-2 border border-primary/20 ${bgColor} transition-colors duration-500`}>
            <span className={`font-mono-label text-xs tracking-widest uppercase ${i < currentStage ? "text-primary" : "text-primary/60"}`}>
              0{i + 1} {stage}
            </span>
            <span className={`font-mono-label text-[10px] tracking-widest uppercase ${statusColor}`}>
              {status}
            </span>
          </div>
        );
      })}
      
      {/* Editorial Progress Bar */}
      <div className="w-full h-[2px] bg-primary/10 mt-4 relative overflow-hidden">
         <motion.div 
            className="absolute top-0 left-0 bottom-0 bg-secondary"
            initial={{ width: "0%" }}
            animate={{ width: `${(currentStage / stages.length) * 100}%` }}
            transition={{ duration: 0.5 }}
         />
      </div>
    </div>
  );
}
