with open("frontend/src/components/CommissionPanel.tsx", "r") as f:
    content = f.read()

# Make inputType !== "text" also have the upload button.
import re

# Update handleFileUpload
new_handle = """  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setIsExtracting(true);
    setExtractError(null);
    try {
      if (inputType === "text") {
        const extractedText = await extractTextFromFile(file);
        setText(extractedText);
      } else {
        const { uploadMediaFile } = await import("@/lib/api/client");
        const url = await uploadMediaFile(file);
        setText(url);
      }
    } catch (e: unknown) {
      const err = e as Error;
      setExtractError(err.message || "Failed to process file.");
    } finally {
      setIsExtracting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };"""

content = re.sub(r'  const handleFileUpload = async \(file: File\) => \{.*?\n  \};\n', new_handle + '\n', content, flags=re.DOTALL)

# Update the render block
new_upload_btn = """              <>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  className="hidden" 
                  accept={inputType === "text" ? ".pdf,.docx,.md" : inputType === "image" ? "image/*" : inputType === "audio" ? "audio/*" : "video/*"}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isExtracting}
                  className="absolute bottom-4 right-4 z-20 font-mono-label text-xs uppercase tracking-wider text-ink-black/50 hover:text-ink-black transition-colors disabled:opacity-50"
                  title={`Upload ${inputType} file`}
                >
                  [ UPLOAD FILE ]
                </button>
              </>"""

content = re.sub(r'\{inputType === "text" && \(\s*<>\s*<input[^>]+>\s*<button.*?</button>\s*</>\s*\)\}', new_upload_btn, content, flags=re.DOTALL)

with open("frontend/src/components/CommissionPanel.tsx", "w") as f:
    f.write(content)
