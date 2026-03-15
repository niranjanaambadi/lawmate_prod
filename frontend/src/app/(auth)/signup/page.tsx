"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import LegalDocumentModal from "@/components/LegalDocumentModal";
import { privacyPolicy, termsOfUse } from "@/lib/legalContent";

type Step = "form" | "privacy" | "terms";

export default function SignUpPage() {
  const { register } = useAuth();

  const [step, setStep] = useState<Step>("form");
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    khcAdvocateId: "",
    khcAdvocateName: "",
    mobile: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const validate = (): string | null => {
    if (formData.password !== formData.confirmPassword) return "Passwords do not match";
    if (formData.password.length < 8) return "Password must be at least 8 characters";
    if (!/[A-Z]/.test(formData.password)) return "Password must contain at least one uppercase letter";
    if (!/\d/.test(formData.password)) return "Password must contain at least one number";
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email.trim())) return "Please enter a valid email address";
    return null;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setStep("privacy");
  };

  const handlePrivacyAgree = () => setStep("terms");

  const handleTermsAgree = async () => {
    setStep("form");
    setLoading(true);
    try {
      await register({
        email: formData.email.trim().toLowerCase(),
        password: formData.password,
        khc_advocate_id: formData.khcAdvocateId.trim(),
        khc_advocate_name: formData.khcAdvocateName.trim(),
        mobile: formData.mobile.trim() || undefined,
      });
      // register() stores the token and redirects to /dashboard automatically
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleModalCancel = () => setStep("form");

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Create Account</CardTitle>
          <CardDescription>Register as an advocate to get started</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-2">
              <Label htmlFor="khcAdvocateName">Full Name</Label>
              <Input
                id="khcAdvocateName"
                value={formData.khcAdvocateName}
                onChange={(e) => setFormData({ ...formData, khcAdvocateName: e.target.value })}
                placeholder="Adv. Your Name"
                required
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="advocate@example.com"
                required
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="khcAdvocateId">KHC Advocate ID</Label>
              <Input
                id="khcAdvocateId"
                value={formData.khcAdvocateId}
                onChange={(e) => setFormData({ ...formData, khcAdvocateId: e.target.value })}
                placeholder="KHC/ADV/12345"
                required
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mobile">Mobile Number (Optional)</Label>
              <Input
                id="mobile"
                type="tel"
                value={formData.mobile}
                onChange={(e) => setFormData({ ...formData, mobile: e.target.value })}
                placeholder="+91 98765 43210"
                disabled={loading}
              />
              <p className="text-xs text-muted-foreground">
                Providing a mobile number lets you receive the identity OTP via SMS.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="••••••••"
                required
                disabled={loading}
                minLength={8}
              />
              <p className="text-xs text-muted-foreground">
                At least 8 characters, one number, one uppercase letter
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <Input
                id="confirmPassword"
                type="password"
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                placeholder="••••••••"
                required
                disabled={loading}
              />
            </div>
            <p className="text-xs text-muted-foreground text-center">
              By creating an account you will be asked to review and accept our{" "}
              <span className="text-foreground font-medium">Privacy Policy</span> and{" "}
              <span className="text-foreground font-medium">Terms of Use</span>.
            </p>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {loading ? "Creating account..." : "Create Account"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/signin" className="text-primary hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </CardFooter>
      </Card>

      {step === "privacy" && (
        <LegalDocumentModal
          legalDoc={privacyPolicy}
          checkboxLabel="I have read and understood the LawMate Privacy Policy and consent to the collection, use, and processing of my personal and professional data as described."
          onAgree={handlePrivacyAgree}
          onCancel={handleModalCancel}
        />
      )}

      {step === "terms" && (
        <LegalDocumentModal
          legalDoc={termsOfUse}
          checkboxLabel="I have read, understood, and agree to be bound by the LawMate Terms of Use."
          onAgree={handleTermsAgree}
          onCancel={handleModalCancel}
        />
      )}
    </>
  );
}
