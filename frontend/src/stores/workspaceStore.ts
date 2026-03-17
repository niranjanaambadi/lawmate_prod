/**
 * stores/workspaceStore.ts
 *
 * Zustand store for the Drafting AI feature.
 * Holds the workspace list + which workspace is currently open in the editor.
 */

import { create } from "zustand";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface WorkspaceDocument {
  id: string;
  workspaceId: string;
  filename: string;
  docType: string | null;
  s3Key: string;
  sizeBytes: number;
  pageCount: number | null;
  tokenEstimate: number;
  strategy: "full_context" | "summarized";
  uploadedAt: string;
}

export interface WorkspaceDraft {
  id: string;
  workspaceId: string;
  title: string;
  docType: string;
  content: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface CaseContext {
  parties?: { petitioner?: string; respondent?: string };
  caseType?: string;
  caseNumber?: string;
  courtNumber?: string;
  judge?: string;
  nextHearing?: string;
  status?: string;
  sectionsInvoked?: string[];
  reliefSought?: string;
  proceduralHistory?: { date: string; event: string }[];
  complianceObligations?: { party: string; obligation: string; deadline: string | null }[];
  recommendedActions?: string[];
  missingDocuments?: string[];
}

export interface Workspace {
  id: string;
  userId: string;
  label: string;
  caseContext: CaseContext | null;
  conversationHistory: { role: string; content: string }[];
  createdAt: string;
  updatedAt: string;
  documents: WorkspaceDocument[];
  drafts: WorkspaceDraft[];
}

// ── State interface ───────────────────────────────────────────────────────────

interface WorkspaceState {
  /** All workspaces loaded for this user. */
  workspaces: Workspace[];
  /** The workspace currently open in the editor (null = none). */
  activeWorkspaceId: string | null;
  /** IDs of documents that were cited in the latest AI response. */
  citedDocIds: string[];
  /** ID of the draft currently open in the DraftingStudio. */
  activeDraftId: string | null;

  // ── Workspace actions ─────────────────────────────────────────────────────
  setWorkspaces: (workspaces: Workspace[]) => void;
  addWorkspace: (workspace: Workspace) => void;
  updateWorkspace: (id: string, patch: Partial<Workspace>) => void;
  removeWorkspace: (id: string) => void;
  setActiveWorkspace: (id: string | null) => void;

  // ── Document actions ──────────────────────────────────────────────────────
  addDocument:      (workspaceId: string, doc: WorkspaceDocument) => void;
  removeDocument:   (workspaceId: string, docId: string) => void;
  /** Remove all documents and reset caseContext for the given workspace. */
  clearDocuments:   (workspaceId: string) => void;
  setCitedDocIds:   (ids: string[]) => void;

  // ── Draft actions ─────────────────────────────────────────────────────────
  addDraft: (workspaceId: string, draft: WorkspaceDraft) => void;
  updateDraft: (workspaceId: string, draftId: string, patch: Partial<WorkspaceDraft>) => void;
  removeDraft: (workspaceId: string, draftId: string) => void;
  setActiveDraftId: (id: string | null) => void;

  // ── Context ───────────────────────────────────────────────────────────────
  setCaseContext: (workspaceId: string, ctx: CaseContext) => void;

  // ── Selectors (convenience) ───────────────────────────────────────────────
  activeWorkspace: () => Workspace | null;
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces:        [],
  activeWorkspaceId: null,
  citedDocIds:       [],
  activeDraftId:     null,

  // Workspace
  setWorkspaces: (workspaces) => set({ workspaces }),

  addWorkspace: (workspace) =>
    set((s) => ({ workspaces: [workspace, ...s.workspaces] })),

  updateWorkspace: (id, patch) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === id ? { ...w, ...patch } : w
      ),
    })),

  removeWorkspace: (id) =>
    set((s) => ({
      workspaces:        s.workspaces.filter((w) => w.id !== id),
      activeWorkspaceId: s.activeWorkspaceId === id ? null : s.activeWorkspaceId,
    })),

  setActiveWorkspace: (id) => set({ activeWorkspaceId: id, activeDraftId: null }),

  // Documents
  addDocument: (workspaceId, doc) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId
          ? { ...w, documents: [...w.documents, doc] }
          : w
      ),
    })),

  removeDocument: (workspaceId, docId) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId
          ? { ...w, documents: w.documents.filter((d) => d.id !== docId) }
          : w
      ),
    })),

  clearDocuments: (workspaceId) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId
          ? { ...w, documents: [], caseContext: null, conversationHistory: [] }
          : w
      ),
    })),

  setCitedDocIds: (ids) => set({ citedDocIds: ids }),

  // Drafts
  addDraft: (workspaceId, draft) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId ? { ...w, drafts: [draft, ...w.drafts] } : w
      ),
    })),

  updateDraft: (workspaceId, draftId, patch) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId
          ? {
              ...w,
              drafts: w.drafts.map((d) =>
                d.id === draftId ? { ...d, ...patch } : d
              ),
            }
          : w
      ),
    })),

  removeDraft: (workspaceId, draftId) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId
          ? { ...w, drafts: w.drafts.filter((d) => d.id !== draftId) }
          : w
      ),
      activeDraftId: get().activeDraftId === draftId ? null : get().activeDraftId,
    })),

  setActiveDraftId: (id) => set({ activeDraftId: id }),

  // Context
  setCaseContext: (workspaceId, ctx) =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId ? { ...w, caseContext: ctx } : w
      ),
    })),

  // Selectors
  activeWorkspace: () => {
    const { workspaces, activeWorkspaceId } = get();
    return workspaces.find((w) => w.id === activeWorkspaceId) ?? null;
  },
}));
