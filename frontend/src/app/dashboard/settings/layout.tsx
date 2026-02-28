"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isProfile = pathname.startsWith("/dashboard/settings/profile");
  const isUsage = pathname.startsWith("/dashboard/settings/usage");
  const isSubscription = pathname.startsWith("/dashboard/settings/subscription");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-600">Manage your profile, usage, and subscription.</p>
      </div>

      <div className="flex gap-2">
        <Button asChild variant={isProfile ? "default" : "outline"}>
          <Link href="/dashboard/settings/profile">Profile</Link>
        </Button>
        <Button asChild variant={isUsage ? "default" : "outline"}>
          <Link href="/dashboard/settings/usage">Usage Tracker</Link>
        </Button>
        <Button asChild variant={isSubscription ? "default" : "outline"}>
          <Link href="/dashboard/settings/subscription">Subscription</Link>
        </Button>
      </div>

      {children}
    </div>
  );
}
