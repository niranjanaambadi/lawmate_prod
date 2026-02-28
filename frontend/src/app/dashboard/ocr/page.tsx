"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { createSearchablePdf, extractOcrText } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Download, FileText, Info, Loader2, ScanLine } from "lucide-react";

type GeneratedFile = {
  id: string;
  name: string;
  url: string;
  format: "pdf" | "pdfa";
  selected: boolean;
};

export default function OCRPage() {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("mal+eng");
  const [languagePreset, setLanguagePreset] = useState("mal+eng");
  const [showCustomLanguage, setShowCustomLanguage] = useState(false);
  const [forceOcr, setForceOcr] = useState(true);
  const [outputFormat, setOutputFormat] = useState<"pdf" | "pdfa">("pdfa");

  const [extracting, setExtracting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [text, setText] = useState("");
  const [pages, setPages] = useState<number>(0);
  const [engine, setEngine] = useState<string>("");
  const [generatedFormat, setGeneratedFormat] = useState<"pdf" | "pdfa">("pdf");
  const [generatedEngine, setGeneratedEngine] = useState<string>("unknown");
  const [generatedSearchable, setGeneratedSearchable] = useState<boolean>(false);
  const [generatedTextPages, setGeneratedTextPages] = useState<number>(0);
  const [generatedTotalPages, setGeneratedTotalPages] = useState<number>(0);
  const [generatedImageDpi, setGeneratedImageDpi] = useState<string>("");
  const [generatedFiles, setGeneratedFiles] = useState<GeneratedFile[]>([]);
  const [previewFileId, setPreviewFileId] = useState<string | null>(null);
  const generatedFilesRef = useRef<GeneratedFile[]>([]);

  useEffect(() => {
    generatedFilesRef.current = generatedFiles;
  }, [generatedFiles]);

  useEffect(() => {
    return () => {
      generatedFilesRef.current.forEach((f) => URL.revokeObjectURL(f.url));
    };
  }, []);

  const canProcess = useMemo(() => Boolean(file && token), [file, token]);

  const onLanguagePresetChange = (value: string) => {
    setLanguagePreset(value);
    if (value !== "custom") {
      setLanguage(value);
      setShowCustomLanguage(false);
    } else {
      setShowCustomLanguage(true);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setText("");
    setPages(0);
    setEngine("");
    setGeneratedEngine("unknown");
    setGeneratedSearchable(false);
    setGeneratedTextPages(0);
    setGeneratedTotalPages(0);
    setGeneratedImageDpi("");
    setError(null);
    // Keep generated PDFs across multiple source files until user downloads or leaves page.
  };

  const handleExtract = async () => {
    if (!file || !token) return;
    setExtracting(true);
    setError(null);
    try {
      const data = await extractOcrText(file, token, {
        language,
        forceOcr,
      });
      setText(data.text || "");
      setPages(data.pages || 0);
      setEngine(data.ocrEngine || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "OCR extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  const handleGenerate = async () => {
    if (!file || !token) return;
    if (!text.trim()) {
      setError("Extract text first, or paste corrected OCR text before generating PDF.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const { blob, pdfFormat, ocrEngine, searchable, textPages, totalPages, imageDpi } = await createSearchablePdf(file, token, {
        text,
        language,
        outputFormat,
        forceOcr,
      });
      const url = URL.createObjectURL(blob);
      setGeneratedFormat(pdfFormat === "pdfa" ? "pdfa" : "pdf");
      setGeneratedEngine(ocrEngine);
      setGeneratedSearchable(searchable);
      setGeneratedTextPages(textPages);
      setGeneratedTotalPages(totalPages);
      setGeneratedImageDpi(imageDpi);
      const now = new Date();
      const ext = pdfFormat === "pdfa" ? "pdf" : "pdf";
      const defaultName = `searchable_${now.getHours()}${now.getMinutes()}${now.getSeconds()}.${ext}`;
      const fileId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setGeneratedFiles((prev) => [
        ...prev,
        {
          id: fileId,
          name: defaultName,
          url,
          format: pdfFormat === "pdfa" ? "pdfa" : "pdf",
          selected: true,
        },
      ]);
      setPreviewFileId(fileId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate searchable PDF");
    } finally {
      setGenerating(false);
    }
  };

  const toggleFileSelection = (id: string) => {
    setGeneratedFiles((prev) =>
      prev.map((f) => (f.id === id ? { ...f, selected: !f.selected } : f))
    );
  };

  const renameFile = (id: string, name: string) => {
    setGeneratedFiles((prev) =>
      prev.map((f) => (f.id === id ? { ...f, name } : f))
    );
  };

  const downloadSelected = () => {
    const selected = generatedFiles.filter((f) => f.selected);
    selected.forEach((file) => {
      const a = document.createElement("a");
      a.href = file.url;
      a.download = file.name.trim() || `searchable.${file.format === "pdfa" ? "pdf" : "pdf"}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    });
    if (selected.length > 0) {
      const selectedIds = new Set(selected.map((f) => f.id));
      setGeneratedFiles((prev) => {
        prev
          .filter((f) => selectedIds.has(f.id))
          .forEach((f) => URL.revokeObjectURL(f.url));
        return prev.filter((f) => !selectedIds.has(f.id));
      });
      setPreviewFileId((current) => (current && selectedIds.has(current) ? null : current));
    }
  };

  const previewFile = generatedFiles.find((f) => f.id === previewFileId) || generatedFiles[generatedFiles.length - 1] || null;
  const selectedCount = generatedFiles.filter((f) => f.selected).length;
  const hasGenerated = generatedFiles.length > 0;

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-800 p-6 text-slate-100 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">OCR Workspace</h1>
            <p className="mt-1 text-sm text-slate-300">
              Extract multilingual text, generate searchable PDF/PDF-A, preview results, and batch-download selected outputs.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <div className="rounded-lg bg-white/10 px-3 py-2">
              <p className="text-slate-300">File</p>
              <p className="font-medium text-white">{file ? "Loaded" : "Not loaded"}</p>
            </div>
            <div className="rounded-lg bg-white/10 px-3 py-2">
              <p className="text-slate-300">Pages</p>
              <p className="font-medium text-white">{pages || 0}</p>
            </div>
            <div className="rounded-lg bg-white/10 px-3 py-2">
              <p className="text-slate-300">Generated</p>
              <p className="font-medium text-white">{generatedFiles.length}</p>
            </div>
            <div className="rounded-lg bg-white/10 px-3 py-2">
              <p className="text-slate-300">Selected</p>
              <p className="font-medium text-white">{selectedCount}</p>
            </div>
          </div>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ScanLine className="h-5 w-5" />
            OCR Processing Control
          </CardTitle>
          <CardDescription>
            Configure OCR, process documents, and manage generated output files.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-5">
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                  <Label htmlFor="ocr-file">Document</Label>
                  <Input id="ocr-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,image/*,application/pdf" onChange={onFileChange} />
                  {file && (
                    <p className="text-xs text-slate-600">
                      {file.name} | {(file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  )}
                </div>
                <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                  <div className="inline-flex items-center gap-2">
                    <Label htmlFor="ocr-lang">OCR languages</Label>
                    <span className="group relative inline-flex cursor-help items-center">
                      <Info className="h-3.5 w-3.5 text-slate-500" />
                      <span className="pointer-events-none absolute left-5 top-1/2 z-10 hidden w-72 -translate-y-1/2 rounded-md border bg-white px-2 py-1 text-xs text-slate-700 shadow group-hover:block">
                        Use Tesseract codes, e.g. `mal+eng` for Malayalam + English.
                      </span>
                    </span>
                  </div>
                  <div className="mt-2">
                    <select
                      id="ocr-lang"
                      value={languagePreset}
                      onChange={(e) => onLanguagePresetChange(e.target.value)}
                      className="h-10 w-full max-w-[260px] rounded-md border border-slate-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                    >
                      <option value="mal+eng">Malayalam + English</option>
                      <option value="mal">Malayalam only</option>
                      <option value="eng">English only</option>
                      <option value="hin+eng">Hindi + English</option>
                      <option value="custom">Custom codes...</option>
                    </select>
                  </div>
                  {showCustomLanguage && (
                    <Input
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                      placeholder="mal+eng"
                      className="mt-2 w-full max-w-[220px]"
                    />
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-6 rounded-xl border border-slate-200 bg-white p-4">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <input className="h-4 w-4" type="checkbox" checked={forceOcr} onChange={(e) => setForceOcr(e.target.checked)} />
                  Force OCR (recommended for scanned court PDFs)
                </label>

                <div className="flex items-center gap-3 text-sm">
                  <span className="font-medium text-slate-700">Output:</span>
                  <label className="flex items-center gap-1">
                    <input
                      type="radio"
                      name="output-format"
                      checked={outputFormat === "pdfa"}
                      onChange={() => setOutputFormat("pdfa")}
                    />
                    PDF/A
                  </label>
                  <label className="flex items-center gap-1">
                    <input
                      type="radio"
                      name="output-format"
                      checked={outputFormat === "pdf"}
                      onChange={() => setOutputFormat("pdf")}
                    />
                    PDF
                  </label>
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button disabled={!canProcess || extracting} onClick={handleExtract}>
                  {extracting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Extracting
                    </>
                  ) : (
                    <>
                      <FileText className="mr-2 h-4 w-4" />
                      Extract OCR Text
                    </>
                  )}
                </Button>
                <Button disabled={!canProcess || generating || !text.trim()} onClick={handleGenerate}>
                  {generating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Generating
                    </>
                  ) : (
                    <>Generate Searchable PDF</>
                  )}
                </Button>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border bg-slate-50 px-3 py-2 text-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Extraction Status</p>
                  <p className="mt-1 text-slate-700">Pages: {pages || 0} | Engine: {engine || "n/a"}</p>
                </div>
                <div className="rounded-lg border bg-slate-50 px-3 py-2 text-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Generation Status</p>
                  <p className="mt-1 text-slate-700">
                    {hasGenerated
                      ? `Engine: ${generatedEngine} | Searchable: ${generatedSearchable ? "yes" : "no"} | Text pages: ${generatedTextPages}/${generatedTotalPages}${generatedImageDpi ? ` | DPI: ${generatedImageDpi}` : ""}`
                      : "No generated files yet"}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex h-[460px] flex-col rounded-xl border border-slate-200 bg-white">
              <div className="border-b px-4 py-3 text-sm font-semibold text-slate-800">Generated PDFs</div>
              <div className="flex-1 space-y-2 overflow-y-auto p-3">
                {generatedFiles.length === 0 ? (
                  <p className="text-xs text-slate-500">No generated files yet.</p>
                ) : (
                  generatedFiles.map((file) => (
                    <div key={file.id} className="rounded-lg border p-2">
                      <label className="mb-2 flex items-center gap-2 text-xs text-slate-700">
                        <input
                          type="checkbox"
                          checked={file.selected}
                          onChange={() => toggleFileSelection(file.id)}
                        />
                        <span>{file.format.toUpperCase()}</span>
                        <button
                          type="button"
                          className={`ml-auto underline ${previewFileId === file.id ? "text-slate-900" : "text-slate-500"}`}
                          onClick={() => setPreviewFileId(file.id)}
                        >
                          Preview
                        </button>
                      </label>
                      <Input
                        value={file.name}
                        onChange={(e) => renameFile(file.id, e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  ))
                )}
              </div>
              <div className="border-t p-3">
                <Button
                  className="w-full"
                  onClick={downloadSelected}
                  disabled={generatedFiles.length === 0 || !generatedFiles.some((f) => f.selected)}
                >
                  <Download className="mr-2 h-4 w-4" />
                  Download Selected
                </Button>
                <p className="mt-2 text-center text-xs text-slate-500">{selectedCount} selected</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6 text-sm text-red-700">{error}</CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Document Workspace</CardTitle>
          <CardDescription>
            Edit extracted text on the left and verify generated searchable PDF on the right.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="min-h-[560px] w-full rounded-xl border border-slate-200 bg-slate-50/30 p-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
              placeholder="Extracted OCR text will appear here..."
              spellCheck={false}
            />

            <div className="flex h-[560px] flex-col rounded-xl border border-slate-200 bg-white">
              <div className="border-b px-4 py-3 text-sm font-semibold text-slate-800">PDF Preview</div>
              <div className="flex-1 overflow-hidden p-2">
                {!previewFile ? (
                  <p className="text-xs text-slate-500">Generate a searchable PDF and select Preview to view it here.</p>
                ) : (
                  <iframe
                    title="Searchable PDF Preview"
                    src={previewFile.url}
                    className="h-full w-full rounded border"
                  />
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
