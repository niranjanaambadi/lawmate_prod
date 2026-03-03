"use client";

import { useEffect, useRef, useState } from "react";
import { X, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { LegalDocument } from "@/lib/legalContent";

type Props = {
  legalDoc: LegalDocument;
  checkboxLabel: string;
  onAgree: () => void;
  onCancel: () => void;
};

export default function LegalDocumentModal({ legalDoc, checkboxLabel, onAgree, onCancel }: Props) {
  const [agreed, setAgreed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Trap focus inside the modal
  useEffect(() => {
    const el = scrollRef.current?.closest("[role=dialog]") as HTMLElement | null;
    el?.focus();
  }, []);

  // Prevent body scroll while modal is open
  useEffect(() => {
    const prev = window.document.body.style.overflow;
    window.document.body.style.overflow = "hidden";
    return () => {
      window.document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="legal-modal-title"
        tabIndex={-1}
        className="relative flex flex-col w-full max-w-2xl bg-white rounded-xl shadow-2xl outline-none"
        style={{ maxHeight: "90vh" }}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-gray-200 shrink-0">
          <div>
            <h2 id="legal-modal-title" className="text-lg font-semibold text-gray-900 leading-tight">
              {legalDoc.title}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">{legalDoc.subtitle}</p>
          </div>
          <button
            onClick={onCancel}
            className="shrink-0 p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable document body */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-6 py-5 text-sm text-gray-700 space-y-5"
          style={{ minHeight: 0 }}
        >
          {/* Intro paragraphs */}
          {legalDoc.intro.map((para, i) => (
            <p key={i} className="leading-relaxed">
              {para}
            </p>
          ))}

          {/* Sections */}
          {legalDoc.sections.map((section, si) => (
            <div key={si} className="space-y-3">
              {section.heading && (
                <h3 className="font-semibold text-gray-900 text-sm uppercase tracking-wide">
                  {section.heading}
                </h3>
              )}

              {section.body.map((para, pi) => (
                <p key={pi} className="leading-relaxed">
                  {para}
                </p>
              ))}

              {section.bullets && section.bullets.length > 0 && (
                <ul className="list-disc list-outside pl-5 space-y-1">
                  {section.bullets.map((b, bi) => (
                    <li key={bi} className="leading-relaxed">
                      {b}
                    </li>
                  ))}
                </ul>
              )}

              {section.subsections?.map((sub, ssi) => (
                <div key={ssi} className="space-y-2 pl-1">
                  <h4 className="font-medium text-gray-800">{sub.heading}</h4>
                  {sub.body.map((para, pi) => (
                    <p key={pi} className="leading-relaxed">
                      {para}
                    </p>
                  ))}
                  {sub.bullets && sub.bullets.length > 0 && (
                    <ul className="list-disc list-outside pl-5 space-y-1">
                      {sub.bullets.map((b, bi) => (
                        <li key={bi} className="leading-relaxed">
                          {b}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          ))}

          {/* Acknowledgment block */}
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-amber-900 text-xs leading-relaxed font-medium">
            {legalDoc.acknowledgment}
          </div>
        </div>

        {/* Footer: checkbox + buttons */}
        <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl shrink-0 space-y-4">
          <label className="flex items-start gap-3 cursor-pointer group">
            <div className="relative mt-0.5 shrink-0">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                className="sr-only"
              />
              <div
                className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                  agreed
                    ? "bg-blue-600 border-blue-600"
                    : "border-gray-300 bg-white group-hover:border-blue-400"
                }`}
              >
                {agreed && (
                  <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
            </div>
            <span className="text-sm text-gray-700 leading-snug select-none">
              {checkboxLabel}
            </span>
          </label>

          <div className="flex gap-3 justify-end">
            <Button variant="outline" onClick={onCancel} className="min-w-[90px]">
              Cancel
            </Button>
            <Button
              onClick={onAgree}
              disabled={!agreed}
              className="min-w-[160px] gap-2"
            >
              {agreed && <CheckCircle2 className="w-4 h-4" />}
              I Agree &amp; Continue
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
