import React from "react";

interface FindingListProps {
  findings: { text: string; status: string }[];
}

export function FindingList({ findings }: FindingListProps) {
  return (
    <div className="flex flex-col gap-4">
      {findings.map((finding, i) => {
        let statusColor = "text-secondary border-secondary/20 bg-secondary/10";
        if (finding.status === "SUPPORTED" || finding.status === "PASSED" || finding.status === "NATURAL" || finding.status === "NONE DETECTED") {
          statusColor = "text-trust-green border-trust-green/20 bg-trust-green/10";
        } else if (finding.status === "REQUIRES VERIFICATION" || finding.status === "INSUFFICIENT" || finding.status === "LOW (12%)") {
          statusColor = "text-gold-foil border-gold-foil/20 bg-gold-foil/10";
        }

        return (
          <div key={i} className="flex flex-col md:flex-row justify-between items-start md:items-center p-4 border border-primary/20 bg-primary/5">
            <span className="font-body-md text-primary pr-4">{finding.text}</span>
            <div className={`mt-4 md:mt-0 px-3 py-1 border font-mono-label text-[10px] tracking-widest uppercase ${statusColor}`}>
              {finding.status}
            </div>
          </div>
        );
      })}
    </div>
  );
}
