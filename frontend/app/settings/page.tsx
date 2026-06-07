import { SettingsForm } from "@/components/SettingsForm";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Configure download behavior and tool paths.
        </p>
      </div>
      <SettingsForm />
    </div>
  );
}
