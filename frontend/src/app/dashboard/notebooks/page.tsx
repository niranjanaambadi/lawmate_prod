"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import ChatWidget from "@/components/agent/ChatWidget";

import {
  createNotebookNote,
  deleteNotebookNote,
  getNotebookAttachmentViewUrl,
  listCaseNotebooks,
  openCaseNotebook,
  searchNotebookNotes,
  sendNotebookToHearingDay,
  updateNotebookNote,
  uploadNotebookAttachment,
  type CaseNotebook,
  type CaseNotebookListItem,
  type NotebookNote,
  type NotebookSearchItem,
} from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NotebookEditor } from "@/components/notebooks/NotebookEditor";
import type { NotebookEditorRef } from "@/components/notebooks/NotebookEditor";

function labelForNotebook(n: CaseNotebookListItem) {
  return n.case_number || n.efiling_number;
}

export default function NotebooksPage() {
  const { token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [list, setList] = useState<CaseNotebookListItem[]>([]);
  const [current, setCurrent] = useState<CaseNotebook | null>(null);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [titleEdit, setTitleEdit] = useState("");
  const [draftJson, setDraftJson] = useState<Record<string, unknown> | null>(null);
  const [draftText, setDraftText] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<NotebookSearchItem[]>([]);
  const [sendingToHearingDay, setSendingToHearingDay] = useState<"chapter" | "selection" | null>(null);
  const editorRef = useRef<NotebookEditorRef>(null);

  const selectedCaseIdFromUrl = searchParams.get("caseId");
  const currentCaseLabel = useMemo(() => {
    if (!current) return "Notebook";
    const match = list.find((n) => n.case_id === current.case_id);
    return match ? `Notebook: ${labelForNotebook(match)}` : `Notebook: ${current.case_id}`;
  }, [current, list]);

  const activeNote: NotebookNote | null = useMemo(() => {
    if (!current || !selectedNoteId) return null;
    return current.notes.find((n) => n.id === selectedNoteId) ?? null;
  }, [current, selectedNoteId]);

  const refreshNotebooks = async () => {
    if (!token) return;
    const rows = await listCaseNotebooks(token);
    setList(rows);
    return rows;
  };

  const loadNotebookForCase = async (caseId: string) => {
    if (!token) return;
    const notebook = await openCaseNotebook(caseId, token);
    notebook.notes.sort((a, b) => a.order_index - b.order_index);
    setCurrent(notebook);
    const first = notebook.notes[0] || null;
    setSelectedNoteId(first?.id || null);
    setTitleEdit(first?.title || "");
    setDraftJson((first?.content_json as Record<string, unknown>) || null);
    setDraftText(first?.content_text || "");
    await refreshNotebooks();
    router.replace(`/dashboard/notebooks?caseId=${caseId}`);
  };

  useEffect(() => {
    if (!token) return;
    let ignore = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const rows = await refreshNotebooks();
        if (ignore) return;
        const target = selectedCaseIdFromUrl || rows?.[0]?.case_id;
        if (target) {
          await loadNotebookForCase(target);
        }
      } catch (e) {
        if (!ignore) setError(e instanceof Error ? e.message : "Failed to load notebooks");
      } finally {
        if (!ignore) setLoading(false);
      }
    })();

    return () => {
      ignore = true;
    };
  }, [token]);

  useEffect(() => {
    if (!activeNote) return;
    setTitleEdit(activeNote.title);
    setDraftJson((activeNote.content_json as Record<string, unknown>) || null);
    setDraftText(activeNote.content_text || "");
  }, [activeNote?.id]);

  const saveActiveNote = async () => {
    if (!token || !activeNote) return;
    try {
      setSaving(true);
      setError(null);
      const updated = await updateNotebookNote(
        activeNote.id,
        {
          title: titleEdit || "Untitled",
          content_json: draftJson,
          content_text: draftText,
        },
        token
      );
      setCurrent((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          notes: prev.notes
            .map((n) => (n.id === updated.id ? updated : n))
            .sort((a, b) => a.order_index - b.order_index),
        };
      });
      await refreshNotebooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save note");
    } finally {
      setSaving(false);
    }
  };

  const onAddChapter = async () => {
    if (!token || !current) return;
    try {
      const max = current.notes.reduce((m, n) => Math.max(m, n.order_index), 0);
      const created = await createNotebookNote(
        current.id,
        {
          title: `Chapter ${current.notes.length + 1}`,
          order_index: max + 1,
          content_json: { type: "doc", content: [{ type: "paragraph" }] },
          content_text: "",
        },
        token
      );
      setCurrent((prev) => (prev ? { ...prev, notes: [...prev.notes, created].sort((a, b) => a.order_index - b.order_index) } : prev));
      setSelectedNoteId(created.id);
      await refreshNotebooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create chapter");
    }
  };

  const onDeleteChapter = async () => {
    if (!token || !activeNote || !current) return;
    if (!window.confirm(`Delete chapter \"${activeNote.title}\"?`)) return;
    try {
      await deleteNotebookNote(activeNote.id, token);
      const remaining = current.notes.filter((n) => n.id !== activeNote.id);
      setCurrent({ ...current, notes: remaining });
      const next = remaining[0] || null;
      setSelectedNoteId(next?.id || null);
      await refreshNotebooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete chapter");
    }
  };

  const onUploadAttachment = async (file: File) => {
    if (!token || !activeNote) return;
    try {
      const attachment = await uploadNotebookAttachment(activeNote.id, file, token);
      setCurrent((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          notes: prev.notes.map((n) =>
            n.id === activeNote.id ? { ...n, attachments: [...n.attachments, attachment] } : n
          ),
        };
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Attachment upload failed");
    }
  };

  const onOpenAttachment = async (attachmentId: string) => {
    if (!token || !activeNote) return;
    try {
      const { url } = await getNotebookAttachmentViewUrl(activeNote.id, attachmentId, token);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to open attachment");
    }
  };

  const onSearch = async () => {
    if (!token || !search.trim()) {
      setSearchResults([]);
      return;
    }
    try {
      const rows = await searchNotebookNotes(search.trim(), token);
      setSearchResults(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    }
  };

  const onSendChapterToHearingDay = async () => {
    if (!token || !activeNote) return;
    try {
      setSendingToHearingDay("chapter");
      setError(null);
      await sendNotebookToHearingDay(activeNote.id, { mode: "chapter" }, token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send chapter to hearing day");
    } finally {
      setSendingToHearingDay(null);
    }
  };

  const onSendSelectionToHearingDay = async () => {
    if (!token || !activeNote) return;
    const selectedText = editorRef.current?.getSelectedText()?.trim() || "";
    if (!selectedText) {
      setError("Select text in the notebook editor first.");
      return;
    }
    try {
      setSendingToHearingDay("selection");
      setError(null);
      await sendNotebookToHearingDay(activeNote.id, { mode: "selection", selected_text: selectedText }, token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send selection to hearing day");
    } finally {
      setSendingToHearingDay(null);
    }
  };

  if (loading) return <div className="text-slate-600">Loading notebooks...</div>;

  return (
       <>
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-2xl font-semibold tracking-tight text-slate-900">Case Notebooks</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search notes" />
            <Button variant="outline" onClick={onSearch}>Search</Button>
          </div>

          {searchResults.length > 0 && (
            <div className="max-h-44 overflow-auto rounded border p-2 text-xs">
              {searchResults.map((r) => (
                <button
                  key={r.note_id}
                  type="button"
                  className="mb-2 w-full rounded border p-2 text-left hover:bg-slate-50"
                  onClick={() => loadNotebookForCase(r.case_id)}
                >
                  <div className="font-medium">{r.case_number || r.efiling_number}</div>
                  <div className="text-slate-500">{r.note_title}</div>
                  <div className="line-clamp-2 text-slate-600">{r.snippet}</div>
                </button>
              ))}
            </div>
          )}

          <div className="max-h-[60vh] space-y-2 overflow-auto">
            {list.length === 0 ? (
              <p className="text-sm text-slate-500">No notebooks yet. Open from a case detail page.</p>
            ) : (
              list.map((n) => {
                const selected = current?.case_id === n.case_id;
                return (
                  <button
                    key={n.notebook_id}
                    type="button"
                    onClick={() => loadNotebookForCase(n.case_id)}
                    className={`w-full rounded border p-3 text-left ${selected ? "border-blue-300 bg-blue-50" : "hover:bg-slate-50"}`}
                  >
                    <div className="font-medium">{labelForNotebook(n)}</div>
                    <div className="text-xs text-slate-500">{n.note_count} chapters</div>
                  </button>
                );
              })
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-9">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{currentCaseLabel}</CardTitle>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onAddChapter} disabled={!current}>Add Chapter</Button>
            <Button onClick={saveActiveNote} disabled={!activeNote || saving}>{saving ? "Saving..." : "Save"}</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

          {!current ? (
            <p className="text-slate-600">Select a case notebook from the left panel.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {current.notes
                  .slice()
                  .sort((a, b) => a.order_index - b.order_index)
                  .map((n) => (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => setSelectedNoteId(n.id)}
                      className={`rounded border px-3 py-1 text-sm ${selectedNoteId === n.id ? "border-blue-300 bg-blue-50" : "hover:bg-slate-50"}`}
                    >
                      {n.title}
                    </button>
                  ))}
              </div>

              {activeNote ? (
                <>
                  <div className="flex items-center gap-2">
                    <Input value={titleEdit} onChange={(e) => setTitleEdit(e.target.value)} placeholder="Chapter title" />
                    <Button
                      variant="outline"
                      onClick={onSendSelectionToHearingDay}
                      disabled={sendingToHearingDay !== null}
                    >
                      {sendingToHearingDay === "selection" ? "Sending..." : "Add Selection to Hearing Day"}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={onSendChapterToHearingDay}
                      disabled={sendingToHearingDay !== null}
                    >
                      {sendingToHearingDay === "chapter" ? "Sending..." : "Add Chapter to Hearing Day"}
                    </Button>
                    <Button variant="outline" onClick={onDeleteChapter}>Delete</Button>
                  </div>

                  <NotebookEditor
                    ref={editorRef}
                    contentJson={draftJson}
                    onChange={(json, text) => {
                      setDraftJson(json);
                      setDraftText(text);
                    }}
                  />

                  <div className="space-y-2 rounded border p-3">
                    <div className="text-sm font-medium">Attachments</div>
                    <Input
                      type="file"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        void onUploadAttachment(file);
                        e.currentTarget.value = "";
                      }}
                    />
                    {activeNote.attachments.length === 0 ? (
                      <p className="text-sm text-slate-500">No attachments for this chapter.</p>
                    ) : (
                      <div className="space-y-2">
                        {activeNote.attachments.map((a) => (
                          <div key={a.id} className="flex items-center justify-between rounded border p-2 text-sm">
                            <div>
                              <div className="font-medium">{a.file_name || a.file_url}</div>
                              <div className="text-xs text-slate-500">{a.content_type || "file"}</div>
                            </div>
                            <Button variant="outline" size="sm" onClick={() => onOpenAttachment(a.id)}>Open</Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-slate-600">Create a chapter to start writing.</p>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
    <ChatWidget page="global" /> 
</>
  );
}
