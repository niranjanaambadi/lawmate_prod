"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Info, Wand2 } from "lucide-react";
import {
  getMyProfile,
  type AuthUser,
  type ProfileUpdatePayload,
  updateMyProfile,
  apiRequest,
} from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString();
}

export default function SettingsProfilePage() {
  const { token, refreshUser } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [profile, setProfile] = useState<AuthUser | null>(null);
  const [form, setForm] = useState<ProfileUpdatePayload>({
    email: "",
    mobile: "",
    khc_enrollment_number: "",
    khc_advocate_code: "",
  });

  useEffect(() => {
    if (!token) return;
    let ignore = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getMyProfile(token);
        if (ignore) return;
        setProfile(data);
        setForm({
          email: data.email || "",
          mobile: data.mobile || "",
          khc_enrollment_number: data.khc_enrollment_number || "",
          khc_advocate_code: data.khc_advocate_code || "",
          preferences: data.preferences,
        });
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : "Failed to load profile");
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => { ignore = true; };
  }, [token]);

  const onAutoDetect = async () => {
    if (!token || detecting) return;
    setDetecting(true);
    setError(null);
    setMessage(null);
    try {
      const res = await apiRequest<{ adv_cd: string; saved: boolean }>(
        "/api/v1/advocate-cause-list/lookup-code",
        { method: "POST", token },
      );
      setForm((prev) => ({ ...prev, khc_advocate_code: res.adv_cd }));
      setMessage(`Advocate code auto-detected: ${res.adv_cd}`);
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auto-detect failed");
    } finally {
      setDetecting(false);
    }
  };

  const onSave = async () => {
    if (!token) return;
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload: ProfileUpdatePayload = {
        email: form.email,
        mobile: form.mobile ? form.mobile : null,
        khc_enrollment_number: form.khc_enrollment_number ? form.khc_enrollment_number : null,
        khc_advocate_code: form.khc_advocate_code ? form.khc_advocate_code.trim() : null,
      };
      const updated = await updateMyProfile(payload, token);
      setProfile(updated);
      setMessage("Profile updated successfully.");
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Update your contact and enrollment details.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {loading ? <p className="text-sm text-slate-500">Loading profile...</p> : null}
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}

        {profile && !loading ? (
          <>
            {/* ── KHC Identity (read-only) ─────────────────────────────── */}
            <div>
              <h3 className="mb-3 text-sm font-semibold text-slate-700">KHC Identity</h3>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>KHC Advocate ID</Label>
                  <Input value={profile.khc_advocate_id || ""} disabled className="bg-slate-50" />
                </div>
                <div>
                  <Label>Advocate Name</Label>
                  <Input value={profile.khc_advocate_name || ""} disabled className="bg-slate-50" />
                </div>
                <div>
                  <Label>Verified</Label>
                  <Input value={profile.is_verified ? "Yes" : "No"} disabled className="bg-slate-50" />
                </div>
              </div>
            </div>

            {/* ── Contact details ──────────────────────────────────────── */}
            <div>
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Contact</h3>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>Email</Label>
                  <Input
                    value={form.email || ""}
                    onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                  />
                </div>
                <div>
                  <Label>Mobile</Label>
                  <Input
                    value={form.mobile || ""}
                    onChange={(e) => setForm((prev) => ({ ...prev, mobile: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            {/* ── Digicourt credentials ────────────────────────────────── */}
            <div>
              <h3 className="mb-1 text-sm font-semibold text-slate-700">
                Kerala HC Digicourt
              </h3>
              <p className="mb-3 text-xs text-slate-500">
                Required to fetch your advocate cause list from{" "}
                <span className="font-medium">hckinfo.keralacourts.in/digicourt</span>.
                Without these, the Tomorrow&apos;s Cause List on your dashboard will not populate.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>
                    Enrollment Number
                    <span className="ml-1 text-slate-400 font-normal">(e.g. K/000671/2018)</span>
                  </Label>
                  <Input
                    placeholder="K/000671/2018"
                    value={form.khc_enrollment_number || ""}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, khc_enrollment_number: e.target.value }))
                    }
                  />
                </div>
                <div>
                  <Label>
                    Advocate Code
                    <span className="ml-1 text-slate-400 font-normal">(adv_cd · e.g. 25126)</span>
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      placeholder="25126"
                      value={form.khc_advocate_code || ""}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, khc_advocate_code: e.target.value }))
                      }
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={onAutoDetect}
                      disabled={detecting || !form.khc_enrollment_number}
                      title={
                        !form.khc_enrollment_number
                          ? "Set enrollment number first"
                          : "Auto-detect from hckinfo digicourt"
                      }
                      className="shrink-0 gap-1.5"
                    >
                      <Wand2 className={`h-3.5 w-3.5 ${detecting ? "animate-pulse" : ""}`} />
                      {detecting ? "Detecting…" : "Auto-detect"}
                    </Button>
                  </div>
                  <p className="mt-1 flex items-start gap-1 text-xs text-slate-400">
                    <Info className="mt-0.5 h-3 w-3 shrink-0" />
                    Click Auto-detect to fetch automatically, or find it manually in the
                    network tab when searching on hckinfo digicourt
                    (the <span className="font-mono">adv_cd</span> POST parameter).
                  </p>
                </div>
              </div>
            </div>

            {/* ── Account timestamps ───────────────────────────────────── */}
            <div>
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Account</h3>
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <Label>Created</Label>
                  <Input value={formatDate(profile.created_at)} disabled className="bg-slate-50" />
                </div>
                <div>
                  <Label>Last Login</Label>
                  <Input value={formatDate(profile.last_login_at)} disabled className="bg-slate-50" />
                </div>
                <div>
                  <Label>Last Sync</Label>
                  <Input value={formatDate(profile.last_sync_at)} disabled className="bg-slate-50" />
                </div>
              </div>
            </div>

            <Button onClick={onSave} disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </Button>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
