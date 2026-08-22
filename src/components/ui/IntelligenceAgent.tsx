import React from "react";
import { motion } from "framer-motion";
import Link from "next/link";

interface IntelligenceAgentProps {
  name: string;
  description: string;
  icon: string;
  status?: "WAITING" | "ANALYZING" | "COMPLETE" | "ERROR" | "ONLINE";
  delay?: number;
  route: string;
}

export function IntelligenceAgent({ name, description, icon, status = "ONLINE", delay = 0, route }: IntelligenceAgentProps) {
  return (
    <Link href={route}>
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, delay }}
        className="flex flex-col gap-3 p-6 glass-card relative group hover:-translate-y-1 hover:shadow-xl hover:border-secondary/40 transition-all duration-300 cursor-pointer h-full"
      >
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-secondary scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom duration-300"></div>
        <div className="flex justify-between items-start">
          <div className="w-12 h-12 rounded-full border border-primary/20 flex items-center justify-center bg-parchment group-hover:border-secondary transition-colors relative">
            <span className="material-symbols-outlined text-primary group-hover:text-secondary transition-colors">
              {icon}
            </span>
            {status === "ANALYZING" && (
              <motion.div 
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                className="absolute -inset-1 border border-secondary/50 border-t-transparent rounded-full"
              />
            )}
          </div>
          
          <div className="flex flex-col items-end gap-2">
            <span className={`font-mono-label text-[10px] tracking-widest px-2 py-1 border rounded-full ${
              status === "COMPLETE" ? "text-trust-green border-trust-green/30 bg-trust-green/10" :
              status === "ANALYZING" ? "text-secondary border-secondary/30 bg-secondary/10" :
              status === "ERROR" ? "text-alert-crimson border-alert-crimson/30 bg-alert-crimson/10" :
              status === "ONLINE" ? "text-trust-green border-trust-green/30 bg-trust-green/10" :
              "text-on-surface-variant border-primary/20"
            }`}>
              {status}
            </span>
            <span className="material-symbols-outlined text-sm text-primary/40 group-hover:text-secondary group-hover:translate-x-1 transition-all">
              arrow_forward
            </span>
          </div>
        </div>

        <div className="mt-2">
          <h4 className="font-mono-label text-sm font-bold text-primary mb-1">
            {name}
          </h4>
          <p className="font-body-md text-sm text-on-surface-variant">
            {description}
          </p>
        </div>
      </motion.div>
    </Link>
  );
}
