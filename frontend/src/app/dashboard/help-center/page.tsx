import helpCenterContent from "@/docs/help-center-content";
import HelpCenterClient from "./HelpCenterClient";

export default function HelpCenterPage() {
  return <HelpCenterClient raw={helpCenterContent} />;
}

