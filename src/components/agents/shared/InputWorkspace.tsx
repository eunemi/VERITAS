"use client";

import React, { useState, useEffect } from "react";

interface InputWorkspaceProps {
  type: "text" | "upload" | "claim";
  placeholder?: string;
  buttonText: string;
  onAnalyze: (content: any) => void;
  isAnalyzing: boolean;
  accept?: string;
}

export function InputWorkspace({ type, placeholder, buttonText, onAnalyze, isAnalyzing, accept }: InputWorkspaceProps) {
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (file) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setPreviewUrl(null);
    }
  }, [file]);

  const handleAction = () => {
    if (type === "upload") {
      onAnalyze(file);
    } else {
      onAnalyze(content);
    }
  };

  const handleClear = () => {
    setContent("");
    setFile(null);
  };

  const getFilePreview = () => {
    if (!file || !previewUrl) return null;
    if (file.type.startsWith("image/")) {
      return <img src={previewUrl} alt="Preview" className="h-full object-contain p-2" />;
    } else if (file.type.startsWith("video/")) {
      return <video src={previewUrl} controls className="h-full object-contain p-2 w-full" />;
    } else if (file.type.startsWith("audio/")) {
      return (
        <div className="w-full flex flex-col items-center justify-center p-8 gap-4">
           <span className="material-symbols-outlined text-4xl text-primary mb-2">audio_file</span>
           <audio src={previewUrl} controls className="w-full max-w-md" />
           <span className="font-mono-label text-sm text-secondary uppercase text-center truncate w-full">{file.name}</span>
        </div>
      );
    }
    return <span className="font-mono-label text-sm text-secondary uppercase text-center truncate w-full px-4">{file.name}</span>;
  };

  return (
    <div className="w-full flex flex-col">
      <div className="font-mono-label text-xs tracking-widest uppercase text-primary/60 mb-2">
        {type === "upload" ? "FILE UPLOAD" : type === "claim" ? "ENTER CLAIM" : "SOURCE TEXT"}
      </div>
      
      {type === "upload" ? (
        <div className="w-full h-64 border-2 border-dashed border-primary/20 bg-primary/5 flex flex-col items-center justify-center cursor-pointer hover:border-secondary/50 hover:bg-secondary/5 transition-colors relative overflow-hidden">
          <input 
            type="file" 
            accept={accept}
            className="absolute inset-0 z-10 w-full h-full opacity-0 cursor-pointer"
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                setFile(e.target.files[0]);
              }
            }}
          />
          
          {file ? (
            <div className="w-full h-full flex items-center justify-center z-0 relative pointer-events-none">
              {getFilePreview()}
            </div>
          ) : (
            <div className="flex flex-col items-center pointer-events-none">
              <span className="material-symbols-outlined text-4xl text-primary/40 mb-4">cloud_upload</span>
              <span className="font-headline-md text-xl text-primary mb-2">{placeholder || "DROP FILE HERE"}</span>
              <span className="font-mono-label text-xs text-primary/40 uppercase">or click to browse</span>
            </div>
          )}
        </div>
      ) : (
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={placeholder || "Paste content here..."}
          className="w-full h-64 p-6 bg-parchment border border-primary/20 text-primary font-body-md focus:outline-none focus:border-secondary resize-none placeholder:italic placeholder:text-primary/30"
        />
      )}

      {/* Action Bar */}
      <div className="flex justify-between items-center mt-6">
        <button
          onClick={handleClear}
          disabled={isAnalyzing}
          className="font-mono-label text-xs tracking-widest uppercase text-primary/60 hover:text-secondary disabled:opacity-50 transition-colors"
        >
          CLEAR
        </button>
        <button
          onClick={handleAction}
          disabled={isAnalyzing || (type === "upload" ? !file : content.length === 0)}
          className="px-8 py-3 bg-ink-black text-parchment font-mono-label text-xs tracking-widest uppercase hover:bg-secondary transition-colors disabled:opacity-50 disabled:hover:bg-ink-black flex items-center gap-2"
        >
          {isAnalyzing ? "ANALYZING..." : buttonText}
          {!isAnalyzing && <span className="material-symbols-outlined text-sm leading-none">arrow_forward</span>}
        </button>
      </div>
    </div>
  );
}
