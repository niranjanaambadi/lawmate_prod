import fs from "fs";
import path from "path";
import HelpCenterClient from "./HelpCenterClient";

export default function HelpCenterPage() {
  let raw = "";
  try {
    const filePath = path.join(
      process.cwd(),
      "src",
      "docs",
      "help-center-pages.md"
    );
    raw = fs.readFileSync(filePath, "utf8");
  } catch {
    raw = "# Help Center\n\nDocumentation content is not available yet.";
  }

  return <HelpCenterClient raw={raw} />;
}

