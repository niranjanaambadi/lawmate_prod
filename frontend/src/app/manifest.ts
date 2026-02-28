import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "LawMate Legal Intelligence",
    short_name: "LawMate",
    description:
      "AI-powered legal research and drafting for elite practitioners.",
    start_url: "/",
    display: "standalone",
    background_color: "#4F46E5",
    theme_color: "#4F46E5",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
