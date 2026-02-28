"use client";

/**
 * NotebookDrawer
 * ==============
 * A slide-in right-side drawer that lets users take notes in their case
 * notebooks without leaving Legal Insight, Case Prep, or AI Insights pages.
 *
 * Features:
 *  - Case picker when no caseId is provided (or when user wants to switch)
 *  - Chapter (note) list with add / delete
 *  - TipTap editor with auto-save (1.5 s debounce)
 *  - Unsaved-changes dot indicator
 *  - Conflict resolution (HTTP 409) via ConflictModal
 *  - Floating toggle tab on the right edge of the screen
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  BookMarked,
  BookOpen,
  Check,
  ChevronDown,
  FileText,
  Loader2,
  NotebookPen,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  type CaseOption,
  type CaseNotebook,
  type NotebookNote,
  getCases,
  openCaseNotebook,
  createNotebookNote,
  updateNotebookNote,
  deleteNotebookNote,
  ConflictError,
} from "@/lib/api";
import { NotebookEditor } from "@/components/notebooks/NotebookEditor";
import { ConflictModal, type ConflictPayload } from "@/components/ConflictModal";

// ── Props ─────────────────────────────────────────────────────────────────────

interface NotebookDrawerProps {
  /** If known up-front (e.g. from URL params), skip the case picker */
  caseId?: string;
  /** JWT token */
  token: string | null;
  /** Whether the drawer is open */
  isOpen: boolean;
  /** Called when user presses the close button */
  onClose: () => void;
}

// ── Auto-save debounce (ms) ───────────────────────────────────────────────────
const AUTOSAVE_DELAY = 1500;

// ── Component ─────────────────────────────────────────────────────────────────

export function NotebookDrawer({
  caseId: propCaseId,
  token,
  isOpen,
  onClose,
}: NotebookDrawerProps) {
  // ── State ─────────────────────────────────────────────────────────────────

  const [cases, setCases]             = useState<CaseOption[]>([]);
  const [casePickerOpen, setCasePickerOpen] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(propCaseId ?? "");

  const [notebook, setNotebook]       = useState<CaseNotebook | null>(null);
  const [activeNote, setActiveNote]   = useState<NotebookNote | null>(null);

  const [loadingNotebook, setLoadingNotebook] = useState(false);
  const [saving, setSaving]           = useState(false);
  const [isDirty, setIsDirty]         = useState(false);
  const [savingNoteId, setSavingNoteId] = useState<string | null>(null);

  // Draft held in ref so the debounce callback closes over the latest value
  const draftRef = useRef<{
    json: Record<string, unknown>;
    text: string;
  } | null>(null);

  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Adding / deleting notes
  const [addingNote,      setAddingNote]      = useState(false);
  const [deletingNoteId,  setDeletingNoteId]  = useState<string | null>(null);
  const [addMenuOpen,     setAddMenuOpen]     = useState(false);
  const [creatingChapter, setCreatingChapter] = useState(false); // inline input visible
  const addMenuRef = useRef<HTMLDivElement>(null);

  // Conflict resolution
  const [conflict, setConflict]       = useState<ConflictPayload | null>(null);

  const [error, setError]             = useState<string | null>(null);

  // ── Sync propCaseId → local selectedCaseId ───────────────────────────────

  useEffect(() => {
    if (propCaseId) setSelectedCaseId(propCaseId);
  }, [propCaseId]);

  // ── Load case list for picker (only when no caseId is known) ─────────────

  useEffect(() => {
    if (!token || propCaseId) return;
    getCases(token)
      .then((list) => setCases(Array.isArray(list) ? list : []))
      .catch(() => setCases([]));
  }, [token, propCaseId]);

  // ── Load / open notebook when caseId is known ────────────────────────────

  useEffect(() => {
    if (!selectedCaseId || !token) return;

    let cancelled = false;
    setLoadingNotebook(true);
    setNotebook(null);
    setActiveNote(null);
    setError(null);

    openCaseNotebook(selectedCaseId, token)
      .then((nb) => {
        if (cancelled) return;
        setNotebook(nb);
        // Auto-select the first note if any
        if (nb.notes.length > 0) {
          setActiveNote(nb.notes[0]);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message ?? "Failed to open notebook.");
      })
      .finally(() => {
        if (!cancelled) setLoadingNotebook(false);
      });

    return () => { cancelled = true; };
  }, [selectedCaseId, token]);

  // ── Flush autosave on unmount / close ────────────────────────────────────

  useEffect(() => {
    if (!isOpen && isDirty) {
      flushSave();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // ── Editor change handler ─────────────────────────────────────────────────

  const handleEditorChange = useCallback(
    (json: Record<string, unknown>, text: string) => {
      draftRef.current = { json, text };
      setIsDirty(true);

      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = setTimeout(() => {
        flushSave();
      }, AUTOSAVE_DELAY);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeNote, token]
  );

  // ── Save draft to server ──────────────────────────────────────────────────

  const flushSave = useCallback(async () => {
    if (!draftRef.current || !activeNote || !token) return;
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }

    const { json, text } = draftRef.current;
    setSavingNoteId(activeNote.id);
    setSaving(true);

    try {
      const updated = await updateNotebookNote(
        activeNote.id,
        { content_json: json, content_text: text, version: activeNote.version },
        token
      );
      // Update note in list with new version
      setNotebook((prev) =>
        prev
          ? {
              ...prev,
              notes: prev.notes.map((n) => (n.id === updated.id ? updated : n)),
            }
          : prev
      );
      setActiveNote(updated);
      draftRef.current = null;
      setIsDirty(false);
    } catch (err) {
      if (err instanceof ConflictError) {
        setConflict(err.payload as ConflictPayload);
      } else {
        setError((err as Error)?.message ?? "Save failed.");
      }
    } finally {
      setSaving(false);
      setSavingNoteId(null);
    }
  }, [activeNote, token]);

  // ── Close add-menu on outside click ──────────────────────────────────────

  useEffect(() => {
    if (!addMenuOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (addMenuRef.current && !addMenuRef.current.contains(e.target as Node)) {
        setAddMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [addMenuOpen]);

  // ── Add new note (quick, auto-titled) ────────────────────────────────────

  const handleAddNote = useCallback(async () => {
    if (!notebook || !token) return;
    setAddMenuOpen(false);
    setAddingNote(true);
    try {
      const newNote = await createNotebookNote(
        notebook.id,
        {
          title: `Note ${notebook.notes.length + 1}`,
          order_index: notebook.notes.length,
        },
        token
      );
      setNotebook((prev) =>
        prev ? { ...prev, notes: [...prev.notes, newNote] } : prev
      );
      setActiveNote(newNote);
      draftRef.current = null;
      setIsDirty(false);
    } catch (err) {
      setError((err as Error)?.message ?? "Could not create note.");
    } finally {
      setAddingNote(false);
    }
  }, [notebook, token]);

  // ── Confirm chapter creation (called from inline input) ──────────────────

  const handleConfirmChapter = useCallback(
    async (title: string) => {
      if (!notebook || !token || !title.trim()) {
        setCreatingChapter(false);
        return;
      }
      setCreatingChapter(false);
      setAddingNote(true);
      try {
        const chapterCount = notebook.notes.filter((n) =>
          n.title.startsWith("Chapter ")
        ).length;
        const newNote = await createNotebookNote(
          notebook.id,
          {
            title: title.trim(),
            order_index: notebook.notes.length,
          },
          token
        );
        void chapterCount; // suppress unused warning
        setNotebook((prev) =>
          prev ? { ...prev, notes: [...prev.notes, newNote] } : prev
        );
        setActiveNote(newNote);
        draftRef.current = null;
        setIsDirty(false);
      } catch (err) {
        setError((err as Error)?.message ?? "Could not create chapter.");
      } finally {
        setAddingNote(false);
      }
    },
    [notebook, token]
  );

  // ── Delete note ───────────────────────────────────────────────────────────

  const handleDeleteNote = useCallback(
    async (noteId: string) => {
      if (!token) return;
      setDeletingNoteId(noteId);
      try {
        await deleteNotebookNote(noteId, token);
        let newActive: NotebookNote | null = null;
        setNotebook((prev) => {
          if (!prev) return prev;
          const remaining = prev.notes.filter((n) => n.id !== noteId);
          newActive = remaining.length > 0 ? remaining[0] : null;
          return { ...prev, notes: remaining };
        });
        if (activeNote?.id === noteId) {
          setActiveNote(newActive);
          draftRef.current = null;
          setIsDirty(false);
        }
      } catch (err) {
        setError((err as Error)?.message ?? "Could not delete note.");
      } finally {
        setDeletingNoteId(null);
      }
    },
    [activeNote, token]
  );

  // ── Rename note title (inline) ────────────────────────────────────────────

  const handleRenameNote = useCallback(
    async (noteId: string, newTitle: string) => {
      if (!token) return;
      try {
        const updated = await updateNotebookNote(noteId, { title: newTitle }, token);
        setNotebook((prev) =>
          prev
            ? {
                ...prev,
                notes: prev.notes.map((n) => (n.id === updated.id ? updated : n)),
              }
            : prev
        );
        if (activeNote?.id === noteId) setActiveNote(updated);
      } catch {
        /* non-fatal */
      }
    },
    [activeNote, token]
  );

  // ── Conflict resolution ───────────────────────────────────────────────────

  const handleConflictReload = useCallback(
    (serverRecord: NonNullable<ConflictPayload["current_record"]>) => {
      // Adopt server version
      const serverNote = serverRecord as unknown as NotebookNote;
      setActiveNote(serverNote);
      setNotebook((prev) =>
        prev
          ? {
              ...prev,
              notes: prev.notes.map((n) =>
                n.id === serverNote.id ? serverNote : n
              ),
            }
          : prev
      );
      draftRef.current = null;
      setIsDirty(false);
      setConflict(null);
    },
    []
  );

  const handleConflictKeepMine = useCallback(() => {
    setConflict(null);
    // Force-save without version check
    if (!draftRef.current || !activeNote || !token) return;
    const { json, text } = draftRef.current;
    setSaving(true);
    updateNotebookNote(
      activeNote.id,
      { content_json: json, content_text: text }, // omit version → bypass check
      token
    )
      .then((updated) => {
        setNotebook((prev) =>
          prev
            ? {
                ...prev,
                notes: prev.notes.map((n) => (n.id === updated.id ? updated : n)),
              }
            : prev
        );
        setActiveNote(updated);
        draftRef.current = null;
        setIsDirty(false);
      })
      .catch(() => setError("Force-save failed."))
      .finally(() => setSaving(false));
  }, [activeNote, token]);

  // ── Derived helpers ───────────────────────────────────────────────────────

  const selectedCaseName = cases.find((c) => c.id === selectedCaseId)
    ?.case_number || selectedCaseId.slice(0, 8) || "Select case";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Backdrop (mobile / narrow) ─────────────────────────────────── */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/20 backdrop-blur-[1px] lg:hidden"
          onClick={onClose}
        />
      )}

      {/* ── Drawer panel ──────────────────────────────────────────────── */}
      <aside
        className={cn(
          "fixed right-0 top-0 z-40 flex h-full w-80 flex-col border-l border-slate-200",
          "bg-white shadow-2xl transition-transform duration-300 ease-in-out",
          isOpen ? "translate-x-0" : "translate-x-full"
        )}
        aria-label="Case Notebook"
      >
        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-indigo-600 px-4 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <BookOpen className="h-4 w-4 shrink-0 text-indigo-200" />
            <span className="text-sm font-semibold text-white truncate">
              Case Notebook
            </span>
            {isDirty && (
              <span className="h-2 w-2 rounded-full bg-amber-400 shrink-0" title="Unsaved changes" />
            )}
            {saving && (
              <Loader2 className="h-3 w-3 animate-spin text-indigo-200 shrink-0" />
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-indigo-200 hover:bg-indigo-700 hover:text-white transition-colors"
            aria-label="Close notebook"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Case picker (only shown when no propCaseId) ───────────── */}
        {!propCaseId && (
          <div className="relative shrink-0 border-b border-slate-200 px-3 py-2">
            <button
              onClick={() => setCasePickerOpen((v) => !v)}
              className="flex w-full items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-medium text-slate-700 hover:border-indigo-300 hover:bg-white transition-colors"
            >
              <span className="truncate">{selectedCaseName}</span>
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform",
                  casePickerOpen && "rotate-180"
                )}
              />
            </button>

            {casePickerOpen && cases.length > 0 && (
              <div className="absolute left-3 right-3 top-full z-50 mt-0.5 max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
                {cases.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      setSelectedCaseId(c.id);
                      setCasePickerOpen(false);
                    }}
                    className={cn(
                      "w-full px-3 py-2 text-left text-xs hover:bg-indigo-50 transition-colors",
                      c.id === selectedCaseId && "bg-indigo-50 font-semibold text-indigo-700"
                    )}
                  >
                    <div className="font-medium text-slate-800 truncate">
                      {c.case_number || c.efiling_number || c.id.slice(0, 8)}
                    </div>
                    {c.petitioner_name && (
                      <div className="text-slate-400 truncate">{c.petitioner_name}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Loading / error states ────────────────────────────────── */}
        {!selectedCaseId && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <BookOpen className="h-8 w-8 text-slate-300" />
            <p className="text-sm font-medium text-slate-500">Select a case</p>
            <p className="text-xs text-slate-400">
              Choose a case above to open its notebook.
            </p>
          </div>
        )}

        {selectedCaseId && loadingNotebook && (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
          </div>
        )}

        {selectedCaseId && !loadingNotebook && error && (
          <div className="m-3 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
            {error}
          </div>
        )}

        {/* ── Main notebook content ─────────────────────────────────── */}
        {selectedCaseId && !loadingNotebook && notebook && (
          <div className="flex flex-1 flex-col overflow-hidden">

            {/* Chapter / Note list */}
            <div className="shrink-0 border-b border-slate-200 bg-slate-50">

              {/* Toolbar row */}
              <div className="flex items-center justify-between px-3 py-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Contents ({notebook.notes.length})
                </span>

                {/* ── Add dropdown ── */}
                <div className="relative" ref={addMenuRef}>
                  <button
                    onClick={() => setAddMenuOpen((v) => !v)}
                    disabled={addingNote}
                    className="flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 transition-colors"
                    title="Add note or chapter"
                  >
                    {addingNote ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Plus className="h-3 w-3" />
                    )}
                    Add
                    <ChevronDown
                      className={cn(
                        "h-2.5 w-2.5 text-indigo-400 transition-transform",
                        addMenuOpen && "rotate-180"
                      )}
                    />
                  </button>

                  {/* Dropdown menu */}
                  {addMenuOpen && (
                    <div className="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                      {/* Add Note */}
                      <button
                        onClick={handleAddNote}
                        className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50 transition-colors"
                      >
                        <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                        <div>
                          <div className="font-medium">Add Note</div>
                          <div className="text-[11px] text-slate-400">Quick auto-named note</div>
                        </div>
                      </button>

                      <div className="mx-2 my-0.5 border-t border-slate-100" />

                      {/* Add Chapter */}
                      <button
                        onClick={() => {
                          setAddMenuOpen(false);
                          setCreatingChapter(true);
                        }}
                        className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-slate-700 hover:bg-indigo-50 transition-colors"
                      >
                        <BookMarked className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                        <div>
                          <div className="font-medium text-indigo-700">Add Chapter</div>
                          <div className="text-[11px] text-slate-400">Named section heading</div>
                        </div>
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Note / Chapter tabs */}
              <div className="flex flex-col max-h-40 overflow-y-auto divide-y divide-slate-100">
                {notebook.notes.length === 0 && !creatingChapter ? (
                  <p className="px-3 py-3 text-xs text-slate-400 text-center">
                    No entries yet — use Add to create a note or chapter.
                  </p>
                ) : (
                  <>
                    {notebook.notes.map((note) => (
                      <NoteTab
                        key={note.id}
                        note={note}
                        isActive={activeNote?.id === note.id}
                        isDirty={isDirty && activeNote?.id === note.id}
                        isSaving={savingNoteId === note.id}
                        isDeleting={deletingNoteId === note.id}
                        onClick={() => {
                          if (isDirty) flushSave();
                          setActiveNote(note);
                          draftRef.current = null;
                          setIsDirty(false);
                        }}
                        onRename={(title) => handleRenameNote(note.id, title)}
                        onDelete={() => handleDeleteNote(note.id)}
                      />
                    ))}

                    {/* Inline chapter-name input */}
                    {creatingChapter && (
                      <ChapterCreateRow
                        defaultValue={`Chapter ${notebook.notes.filter((n) => n.title.startsWith("Chapter ")).length + 1}`}
                        onConfirm={handleConfirmChapter}
                        onCancel={() => setCreatingChapter(false)}
                      />
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Editor */}
            <div className="flex-1 overflow-y-auto">
              {activeNote ? (
                <div className="flex flex-col h-full">
                  {/* Note / Chapter header */}
                  <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      {isChapter(activeNote.title) && (
                        <BookMarked className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                      )}
                      <NoteTitle
                        title={activeNote.title}
                        onCommit={(t) => handleRenameNote(activeNote.id, t)}
                      />
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {isDirty && !saving && (
                        <button
                          onClick={flushSave}
                          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-amber-600 hover:bg-amber-50 transition-colors"
                          title="Save now"
                        >
                          <Save className="h-3 w-3" />
                          Save
                        </button>
                      )}
                      {saving && (
                        <span className="flex items-center gap-1 text-[11px] text-slate-400">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Saving…
                        </span>
                      )}
                      {!isDirty && !saving && (
                        <span className="text-[11px] text-slate-300">Saved</span>
                      )}
                    </div>
                  </div>

                  {/* TipTap editor */}
                  <div className="flex-1 overflow-y-auto px-2 pb-4 pt-2 [&_.ProseMirror]:min-h-[200px] [&_.ProseMirror]:text-sm [&_.ProseMirror]:leading-relaxed">
                    <NotebookEditor
                      key={activeNote.id}
                      contentJson={activeNote.content_json ?? null}
                      onChange={handleEditorChange}
                      placeholder={
                        isChapter(activeNote.title)
                          ? "Write chapter content, arguments, citations…"
                          : "Write your notes here…"
                      }
                    />
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-4">
                  <NotebookPen className="h-8 w-8 text-slate-200" />
                  <p className="text-xs text-slate-400">
                    Select an entry or use <span className="font-medium text-slate-500">Add</span> to create a note or chapter.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </aside>

      {/* ── Conflict modal ─────────────────────────────────────────────── */}
      <ConflictModal
        conflict={conflict}
        entityLabel="note"
        onReload={(rec) => handleConflictReload(rec)}
        onKeepMine={handleConflictKeepMine}
        onCancel={() => setConflict(null)}
      />
    </>
  );
}

// ── NoteTab ───────────────────────────────────────────────────────────────────

interface NoteTabProps {
  note: NotebookNote;
  isActive: boolean;
  isDirty: boolean;
  isSaving: boolean;
  isDeleting: boolean;
  onClick: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}

/** Chapters are identified by their title starting with "Chapter " */
function isChapter(title: string) {
  return /^chapter\s/i.test(title);
}

function NoteTab({
  note,
  isActive,
  isDirty,
  isSaving,
  isDeleting,
  onClick,
  onDelete,
}: NoteTabProps) {
  const chapter = isChapter(note.title);

  return (
    <div
      className={cn(
        "group flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors text-xs",
        isActive
          ? chapter
            ? "bg-indigo-50 border-l-2 border-l-indigo-500 text-indigo-700"
            : "bg-slate-100 border-l-2 border-l-slate-400 text-slate-800"
          : chapter
          ? "text-indigo-600 hover:bg-indigo-50 border-l-2 border-l-transparent"
          : "text-slate-600 hover:bg-slate-100 border-l-2 border-l-transparent"
      )}
      onClick={onClick}
    >
      {/* Icon: chapter vs note */}
      {chapter ? (
        <BookMarked className="h-3 w-3 shrink-0 text-indigo-400" />
      ) : (
        <FileText className="h-3 w-3 shrink-0 text-slate-300" />
      )}

      <span
        className={cn(
          "flex-1 truncate",
          chapter ? "font-semibold" : "font-medium"
        )}
      >
        {note.title}
      </span>

      {/* Indicators */}
      {isDirty && !isSaving && (
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
      )}
      {isSaving && <Loader2 className="h-3 w-3 animate-spin text-slate-400 shrink-0" />}

      {/* Delete button (hover-reveal) */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        disabled={isDeleting}
        className={cn(
          "rounded p-0.5 text-slate-300 transition-colors",
          "opacity-0 group-hover:opacity-100",
          isActive && "opacity-60",
          "hover:bg-red-50 hover:text-red-500"
        )}
        title={`Delete ${chapter ? "chapter" : "note"}`}
      >
        {isDeleting ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Trash2 className="h-3 w-3" />
        )}
      </button>
    </div>
  );
}

// ── ChapterCreateRow ──────────────────────────────────────────────────────────

interface ChapterCreateRowProps {
  defaultValue: string;
  onConfirm: (title: string) => void;
  onCancel: () => void;
}

function ChapterCreateRow({ defaultValue, onConfirm, onCancel }: ChapterCreateRowProps) {
  const [value, setValue] = useState(defaultValue);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-select default text so user can immediately overwrite
  useEffect(() => {
    inputRef.current?.select();
  }, []);

  const confirm = () => {
    const trimmed = value.trim();
    if (trimmed) onConfirm(trimmed);
    else onCancel();
  };

  return (
    <div className="flex items-center gap-1.5 border-l-2 border-l-indigo-400 bg-indigo-50 px-2 py-1.5">
      <BookMarked className="h-3 w-3 shrink-0 text-indigo-400" />
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter")  { e.preventDefault(); confirm(); }
          if (e.key === "Escape") { e.preventDefault(); onCancel(); }
        }}
        placeholder="Chapter name…"
        className="flex-1 min-w-0 bg-transparent text-xs font-semibold text-indigo-700 placeholder-indigo-300 focus:outline-none"
        autoFocus
      />
      {/* Confirm */}
      <button
        onClick={confirm}
        className="rounded p-0.5 text-indigo-500 hover:bg-indigo-100 transition-colors"
        title="Confirm (Enter)"
      >
        <Check className="h-3 w-3" />
      </button>
      {/* Cancel */}
      <button
        onClick={onCancel}
        className="rounded p-0.5 text-slate-400 hover:bg-slate-200 transition-colors"
        title="Cancel (Escape)"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

// ── NoteTitle (inline editable) ───────────────────────────────────────────────

function NoteTitle({
  title,
  onCommit,
}: {
  title: string;
  onCommit: (t: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setValue(title); }, [title]);

  const commit = () => {
    const trimmed = value.trim();
    if (trimmed && trimmed !== title) onCommit(trimmed);
    else setValue(title);
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setValue(title); setEditing(false); }
        }}
        className="flex-1 min-w-0 rounded border border-indigo-300 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        autoFocus
      />
    );
  }

  return (
    <span
      className="flex-1 min-w-0 truncate text-xs font-semibold text-slate-700 cursor-text hover:text-indigo-600 transition-colors"
      onDoubleClick={() => setEditing(true)}
      title="Double-click to rename"
    >
      {title}
    </span>
  );
}

// ── Toggle button (exported for use in pages) ─────────────────────────────────

interface NotebookToggleButtonProps {
  isOpen: boolean;
  onClick: () => void;
  /** Vertical offset class (default: "top-1/2 -translate-y-1/2") */
  className?: string;
}

export function NotebookToggleButton({
  isOpen,
  onClick,
  className,
}: NotebookToggleButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "fixed right-0 z-50 flex items-center gap-1.5",
        "rounded-l-xl border border-r-0 border-indigo-200",
        "bg-indigo-600 px-2 py-3 shadow-lg transition-all duration-300",
        "hover:bg-indigo-700 hover:shadow-xl",
        isOpen ? "translate-x-80" : "translate-x-0",
        className ?? "top-1/2 -translate-y-1/2"
      )}
      aria-label={isOpen ? "Close notebook" : "Open notebook"}
      title={isOpen ? "Close notebook" : "Open case notebook"}
    >
      <span
        className="text-[11px] font-bold uppercase tracking-widest text-white"
        style={{ writingMode: "vertical-rl", textOrientation: "mixed", transform: "rotate(180deg)" }}
      >
        Notes
      </span>
      <NotebookPen className="h-3.5 w-3.5 text-indigo-200" />
    </button>
  );
}
