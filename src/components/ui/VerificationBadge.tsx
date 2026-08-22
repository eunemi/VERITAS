import React from "react";

export type VerificationStatus = "VERIFIED" | "UNDER REVIEW" | "CONTESTED" | string;

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  let bgColor = "bg-primary/10";
  let textColor = "text-on-surface-variant";
  let borderColor = "border-primary/20";
  let icon = "pending";

  if (status.toUpperCase() === "VERIFIED") {
    bgColor = "bg-trust-green/10";
    textColor = "text-trust-green";
    borderColor = "border-trust-green/30";
    icon = "check_circle";
  } else if (status.toUpperCase() === "CONTESTED") {
    bgColor = "bg-alert-crimson/10";
    textColor = "text-alert-crimson";
    borderColor = "border-alert-crimson/30";
    icon = "warning";
  } else if (status.toUpperCase() === "ERROR") {
    bgColor = "bg-alert-crimson/10";
    textColor = "text-alert-crimson";
    borderColor = "border-alert-crimson/30";
    icon = "error";
  }

  return (
    <div className={`inline-flex items-center gap-1.5 px-3 py-1 border rounded-full ${bgColor} ${borderColor}`}>
      <span className={`material-symbols-outlined text-[14px] ${textColor}`}>{icon}</span>
      <span className={`font-mono-label text-[10px] tracking-wider uppercase ${textColor}`}>
        {status}
      </span>
    </div>
  );
}
