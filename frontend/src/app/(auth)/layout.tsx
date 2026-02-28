import { Scale } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 px-4">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-center mb-8">
          <div className="h-16 w-16 bg-primary rounded-lg flex items-center justify-center">
            <Scale className="h-8 w-8 text-primary-foreground" />
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
