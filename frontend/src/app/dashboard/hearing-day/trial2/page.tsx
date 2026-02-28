"use client";

import { useMemo, useState } from "react";
import CaseBundleWorkspaceTrial2 from "@/components/hearing-day/CaseBundleWorkspaceTrial2";

export default function HearingDayTrial2Page() {
  const [input, setInput] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");

  const effectivePdf = useMemo(() => (pdfUrl || "").trim(), [pdfUrl]);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4">
        <h1 className="text-base font-semibold text-slate-900">Hearing Day Trial 2</h1>
        <p className="mt-1 text-sm text-slate-600">Paste a PDF URL and test the Trial 2 workspace.</p>
        <div className="mt-3 flex gap-2">
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            placeholder="https://.../document.pdf"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
            onClick={() => {
              const raw = input.trim();
              if (!raw) {
                setPdfUrl("");
                return;
              }
              setPdfUrl(`/api/pdf-proxy?url=${encodeURIComponent(raw)}`);
            }}
          >
            Load PDF
          </button>
        </div>
      </div>

      <CaseBundleWorkspaceTrial2
        pdfUrl={effectivePdf || undefined}
        caseTitle="Trial 2 Hearing Workspace"
        onSave={(payload) => {
          console.log("[hearing-day-trial2-save]", payload);
        }}
      />
    </div>
  );
}
