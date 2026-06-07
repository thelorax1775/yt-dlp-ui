import { PageHeader } from "@/components/PageHeader";
import { SettingsForm } from "@/components/SettingsForm";
import { SharesManager } from "@/components/SharesManager";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        title="Settings"
        description="Configure download behavior, tool paths, and network shares."
      />
      <div className="flex flex-col gap-6">
        <SettingsForm />
        <SharesManager />
      </div>
    </div>
  );
}
