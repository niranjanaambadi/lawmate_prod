import type { Metadata } from "next";
import Link from "next/link";
import { Scale } from "lucide-react";

export const metadata: Metadata = {
  title: "LawMate — AI-first practice for Kerala High Court advocates",
  description:
    "Your AI-powered legal workspace: case management, cause list, hearing prep, and court sync for advocates at Kerala High Court. Start your free trial.",
};

const CHROME_STORE_URL = "https://chromewebstore.google.com/"; // Replace with your Lawmate Case Sync listing URL when published

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-slate-50/95 backdrop-blur supports-[backdrop-filter]:bg-slate-50/80">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-slate-900 hover:opacity-90"
          >
            <Scale className="h-8 w-8 text-amber-600" aria-hidden />
            <span className="text-xl font-semibold tracking-tight">
              LawMate
            </span>
          </Link>
          <nav className="flex items-center gap-6 text-sm font-medium">
            <a
              href="#features"
              className="text-slate-600 hover:text-slate-900 transition-colors"
            >
              Features
            </a>
            <a
              href="#pricing"
              className="text-slate-600 hover:text-slate-900 transition-colors"
            >
              Pricing
            </a>
            <a
              href={CHROME_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-600 hover:text-slate-900 transition-colors"
            >
              Chrome extension
            </a>
            <Link
              href="/signin"
              className="text-slate-600 hover:text-slate-900 transition-colors"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 transition-colors"
            >
              Start free trial
            </Link>
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-slate-200 bg-slate-100/50">
        <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <div className="flex items-center gap-2 text-slate-600">
              <Scale className="h-5 w-5 text-amber-600" aria-hidden />
              <span className="font-medium">LawMate</span>
            </div>
            <nav className="flex flex-wrap items-center justify-center gap-6 text-sm text-slate-600">
              <a href="#features" className="hover:text-slate-900">
                Features
              </a>
              <a href="#pricing" className="hover:text-slate-900">
                Pricing
              </a>
              <a
                href={CHROME_STORE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-slate-900"
              >
                Chrome extension
              </a>
              <Link href="/signin" className="hover:text-slate-900">
                Sign in
              </Link>
              <Link href="/signup" className="hover:text-slate-900">
                Get started
              </Link>
            </nav>
          </div>
          <p className="mt-6 text-center text-xs text-slate-500">
            For advocates at Kerala High Court. AI-first legal practice
            platform.
          </p>
        </div>
      </footer>
    </div>
  );
}
