// Mock backend services for AI Agent Workspaces

export async function analyzeText(content: string) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        claims: [
          { text: "Example claim extracted from the submitted article.", status: "REQUIRES VERIFICATION" },
          { text: "Another significant assertion found in the text.", status: "SUPPORTED" },
          { text: "A questionable statement contradicting established facts.", status: "CONTESTED" }
        ],
        signals: [
          { label: "EMOTIONAL LANGUAGE", level: "HIGH" },
          { label: "UNVERIFIED ASSERTIONS", level: "03" },
          { label: "SOURCE ATTRIBUTION", level: "LOW" },
          { label: "NARRATIVE SHIFT", level: "02" }
        ],
        metrics: {
          claimsDetected: "04",
          entities: "12",
          suspiciousSignals: "07",
          language: "ENGLISH",
          confidence: "92%"
        }
      });
    }, 4500); // Simulate network and processing delay
  });
}

export async function analyzeImage(file: File | null) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        findings: [
          { text: "Potential visual inconsistency in region 01", status: "FLAGGED" },
          { text: "Lighting mismatch in shadows", status: "ANOMALY" },
          { text: "Synthetic texture signal detected", status: "SYNTHETIC" }
        ],
        metrics: {
          aiGenerationSignal: "87%",
          manipulationSignals: "03",
          ocrText: "14 LINES",
          metadata: "AVAILABLE",
          visualAnomalies: "02"
        }
      });
    }, 4000);
  });
}

export async function analyzeAudio(file: File | null) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        findings: [
          { text: "Voice consistency check", status: "PASSED" },
          { text: "Background noise profile", status: "NATURAL" },
          { text: "Editing splicing signals", status: "NONE DETECTED" },
          { text: "Synthetic speech signal", status: "LOW (12%)" }
        ],
        metrics: {
          duration: "02:48",
          words: "421",
          speakers: "02",
          audioSignals: "05",
          confidence: "91%"
        }
      });
    }, 4500);
  });
}

export async function analyzeVideo(file: File | null) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        findings: [
          { text: "Frame consistency across scenes", status: "PASSED" },
          { text: "Audio / Video synchronization", status: "VERIFIED" },
          { text: "Scene transitions analysis", status: "NATURAL" },
          { text: "Deepfake spatial anomalies", status: "DETECTED" }
        ],
        metrics: {
          framesAnalyzed: "128",
          scenes: "12",
          audioSegments: "08",
          visualSignals: "04",
          confidence: "88%"
        }
      });
    }, 5000);
  });
}

export async function factCheckClaim(claim: string) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        evidence: [
          { sourceName: "Global Ledger DB", date: "2024-05-12", relevance: "HIGH", reliability: "VERIFIED", status: "CONTRADICTED" },
          { sourceName: "Primary Source Archives", date: "2024-05-10", relevance: "MEDIUM", reliability: "HIGH", status: "INSUFFICIENT" },
          { sourceName: "Historical Event Record", date: "2023-11-20", relevance: "HIGH", reliability: "VERIFIED", status: "CONTESTED" },
          { sourceName: "Verified Witness Statements", date: "2024-05-14", relevance: "LOW", reliability: "MEDIUM", status: "SUPPORTED" }
        ],
        metrics: {
          claims: "08",
          sources: "17",
          supporting: "05",
          contesting: "03",
          evidenceStrength: "94%"
        }
      });
    }, 4500);
  });
}

export async function runDecision(inputs: any[]) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        breakdown: [
          { agent: "TEXT SIGNALS", contribution: "35%" },
          { agent: "IMAGE SIGNALS", contribution: "15%" },
          { agent: "AUDIO SIGNALS", contribution: "10%" },
          { agent: "VIDEO SIGNALS", contribution: "20%" },
          { agent: "FACT-CHECK EVIDENCE", contribution: "20%" }
        ],
        metrics: {
          agentAgreement: "94%",
          evidenceStrength: "91%",
          signalConsistency: "89%",
          modelConfidence: "94%"
        }
      });
    }, 6000);
  });
}
