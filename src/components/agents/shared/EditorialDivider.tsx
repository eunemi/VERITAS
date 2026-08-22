import React from "react";

export function EditorialDivider() {
  return (
    <div className="w-full h-px bg-ink-black/20 my-stack-lg relative">
      <div className="absolute -top-[5px] left-0 w-3 h-3 border-t border-l border-ink-black"></div>
      <div className="absolute -top-[5px] right-0 w-3 h-3 border-t border-r border-ink-black"></div>
    </div>
  );
}
