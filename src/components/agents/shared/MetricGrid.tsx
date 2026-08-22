import React from "react";

interface MetricGridProps {
  metrics: { label: string; value: string }[];
}

export function MetricGrid({ metrics }: MetricGridProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
      {metrics.map((metric, i) => (
        <div key={i} className="flex flex-col border-l-2 border-primary/20 pl-4 py-2">
          <span className="font-mono-label text-[10px] text-on-surface-variant uppercase tracking-widest mb-2">
            {metric.label}
          </span>
          <span className="font-masthead text-3xl font-bold text-primary">
            {metric.value}
          </span>
        </div>
      ))}
    </div>
  );
}
