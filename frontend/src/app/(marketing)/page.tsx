"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import {
  Brain,
  BookOpenCheck,
  BookOpen,
  Languages,
  GitCompare,
  ListChecks,
  FileText,
  Clock3,
  Calendar,
  FolderOpen,
  ScanLine,
  NotebookPen,
  Gavel,
  Shield,
  CreditCard,
  Trash2,
  Chrome,
  Scale,
} from "lucide-react";

const CHROME_STORE_URL = "https://chromewebstore.google.com/";

export default function MarketingPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (isAuthenticated) router.replace("/dashboard");
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-amber-600 border-t-transparent" />
      </div>
    );
  }
  if (isAuthenticated) return null;

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white px-4 py-20 sm:px-6 sm:py-28">
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
            Your AI-powered practice at Kerala High Court
          </h1>
          <p className="mt-6 text-lg text-slate-600 sm:text-xl">
          The world's first AI-native workspace designed and customized for lawyers of the High Court of Kerala.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button
              asChild
              size="lg"
              className="bg-amber-600 hover:bg-amber-700 text-white px-8 text-base font-medium"
            >
              <Link href="/signup">
                Start your 3 day free trial now
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="text-base">
              <Link href="/signin">Sign in</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* AI-first features */}
      <section id="features" className="scroll-mt-20 border-b border-slate-200 bg-white px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-3xl font-bold text-slate-900 sm:text-4xl">
            AI-first workspace
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-slate-600">
            One assistant that knows your court and your case.
          </p>
          <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                icon: Brain,
                title: "LawMate AI",
                desc: "Context-aware assistant on hearing day, case prep, and cause list. Case status, roster, judgments, calendar, and drafts.",
              },
              {
                icon: BookOpenCheck,
                title: "Case Prep AI",
                desc: "Prepare for hearings with AI that knows Indian law. Conversation and precedent-finder modes; export hearing brief.",
              },
              {
                icon: Brain,
                title: "AI Insights",
                desc: "Extract and chat over documents. Turn bundles into answers.",
              },
              {
                icon: BookOpen,
                title: "Judgement Analyzer",
                desc: "Upload judgments and PDFs; summarization and extraction at scale.",
              },
              {
                icon: Languages,
                title: "Legal Translator AI",
                desc: "English ↔ Malayalam with glossary. Communicate confidently in both languages.",
              },
              {
                icon: GitCompare,
                title: "Doc Comparison AI",
                desc: "Upload two documents; get a comparison memo. Spot differences quickly.",
              },
            ].map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-xl border border-slate-200 bg-slate-50/50 p-6 transition-shadow hover:shadow-md"
              >
                <Icon className="h-10 w-10 text-amber-600" aria-hidden />
                <h3 className="mt-4 text-lg font-semibold text-slate-900">
                  {title}
                </h3>
                <p className="mt-2 text-sm text-slate-600">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Court & calendar */}
      <section className="border-b border-slate-200 bg-slate-50/50 px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-3xl font-bold text-slate-900 sm:text-4xl">
            Court & calendar
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-slate-600">
            Today&apos;s list and your matters in one place.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
            {[
              { icon: ListChecks, title: "Cause List", desc: "Daily cause list from KHC; view by date, mediation list." },
              { icon: FileText, title: "Advocate Cause List", desc: "Tomorrow's list for you, front and centre." },
              { icon: FileText, title: "Roster", desc: "Kerala HC bench roster; know the bench." },
              { icon: Clock3, title: "Case Status", desc: "Live status by case number; no court-site hunting." },
              { icon: Calendar, title: "Calendar", desc: "Hearings, deadlines, reminders; Google Calendar sync." },
            ].map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
              >
                <Icon className="h-8 w-8 text-amber-600" aria-hidden />
                <h3 className="mt-3 font-semibold text-slate-900">{title}</h3>
                <p className="mt-1 text-sm text-slate-600">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Cases, extension, docs */}
      <section className="border-b border-slate-200 bg-white px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-center text-3xl font-bold text-slate-900 sm:text-4xl">
            Cases & documents
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-slate-600">
            All cases and docs in one workspace.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { icon: FolderOpen, title: "Cases", desc: "List and detail; e-filing number, status; sync from court; recycle bin." },
              { icon: ScanLine, title: "OCR", desc: "Extract text; searchable PDFs; save to case." },
              { icon: NotebookPen, title: "Case Notebooks", desc: "Per-case notes and attachments; search; send to hearing day." },
              { icon: Gavel, title: "Hearing Day", desc: "Per-case hearing view: note, citations, AI enrichment." },
            ].map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-lg border border-slate-200 bg-slate-50/50 p-5"
              >
                <Icon className="h-8 w-8 text-amber-600" aria-hidden />
                <h3 className="mt-3 font-semibold text-slate-900">{title}</h3>
                <p className="mt-1 text-sm text-slate-600">{desc}</p>
              </div>
            ))}
          </div>
          <div className="mt-10 rounded-xl border border-slate-200 bg-slate-50/80 p-6 text-center">
            <Chrome className="mx-auto h-10 w-10 text-amber-600" aria-hidden />
            <h3 className="mt-3 font-semibold text-slate-900">Chrome Extension</h3>
            <p className="mt-2 text-sm text-slate-600">
              Tired of manual case management? Sync case bundles directly from the Kerala High Court e-filing site into LawMate.
              Install from Chrome Web Store; Sign up & Watch demo to learn more.
            </p>
          </div>
          <div className="mt-6 flex justify-center">
            <Button asChild variant="outline" size="lg" className="gap-2">
              <a href={CHROME_STORE_URL} target="_blank" rel="noopener noreferrer">
                <Chrome className="h-5 w-5" />
                Get the Chrome extension
              </a>
            </Button>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-20 border-b border-slate-200 bg-slate-50/50 px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-3xl font-bold text-slate-900 sm:text-4xl">
            Transparent pricing
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-slate-600">
            One plan. Track your usage. Pay-as-you-go top-ups when you need more.
          </p>
          <div className="mt-12 flex flex-col items-center">
            <div className="w-full max-w-md rounded-2xl border-2 border-amber-200 bg-white p-8 shadow-lg">
              <div className="text-center">
                <p className="text-sm font-medium uppercase tracking-wide text-amber-700">
                  Early bird — first 100 advocates
                </p>
                <p className="mt-2 text-4xl font-bold text-slate-900">
                  ₹1,200
                  <span className="text-lg font-normal text-slate-500">/month</span>
                </p>
                <p className="mt-2 text-sm text-slate-500 line-through">
                  Standard ₹1,500/month
                </p>
                <ul className="mt-6 space-y-2 text-left text-sm text-slate-600">
                  <li className="flex items-center gap-2">
                    <Scale className="h-4 w-4 shrink-0 text-amber-600" />
                    Full access to all features
                  </li>
                  <li className="flex items-center gap-2">
                    <Scale className="h-4 w-4 shrink-0 text-amber-600" />
                    Included usage limit per month
                  </li>
                  <li className="flex items-center gap-2">
                    <Scale className="h-4 w-4 shrink-0 text-amber-600" />
                    Track your usage anytime
                  </li>
                  <li className="flex items-center gap-2">
                    <Scale className="h-4 w-4 shrink-0 text-amber-600" />
                    ₹200 top-ups when limit exceeds — as many as you need
                  </li>
                  <li className="flex items-center gap-2">
                    <Scale className="h-4 w-4 shrink-0 text-amber-600" />
                    Cancel anytime; no long-term lock-in
                  </li>
                </ul>
                <Button
                  asChild
                  size="lg"
                  className="mt-8 w-full bg-amber-600 hover:bg-amber-700 text-white"
                >
                  <Link href="/signup">Start your 3 day free trial now</Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trust */}
      <section className="border-b border-slate-200 bg-white px-4 py-12 sm:px-6 sm:py-16">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-8 sm:grid-cols-3">
            {[
              { icon: Shield, title: "Verified identity", desc: "KHC advocate details; optional OTP verification." },
              { icon: CreditCard, title: "Clear billing", desc: "Plans, usage, invoices, payment method; cancel or pause anytime." },
              { icon: Trash2, title: "Recycle bin", desc: "Soft-delete and restore; configurable purge." },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="text-center">
                <Icon className="mx-auto h-10 w-10 text-amber-600" aria-hidden />
                <h3 className="mt-3 font-semibold text-slate-900">{title}</h3>
                <p className="mt-1 text-sm text-slate-600">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="bg-slate-900 px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-white sm:text-4xl">
            Ready to streamline your practice?
          </h2>
          <p className="mt-4 text-slate-300">
            Join advocates at Kerala High Court using LawMate. Start your free trial — no credit card required.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button
              asChild
              size="lg"
              className="bg-amber-500 hover:bg-amber-600 text-slate-900 px-8 font-medium"
            >
              <Link href="/signup">Start your 3 day free trial now</Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="border-slate-500 text-white hover:bg-slate-800">
              <Link href="/signin">Sign in</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
