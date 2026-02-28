"use client";

import "@/styles/cause-list.css";

interface CauseListContentProps {
  html: string;
}

export function CauseListContent({ html }: CauseListContentProps) {
  return <div className="cause-list-wrapper" dangerouslySetInnerHTML={{ __html: html }} />;
}
