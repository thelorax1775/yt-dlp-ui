import { FileBrowser } from "@/components/FileBrowser";
import { PageHeader } from "@/components/PageHeader";

export default function FilesPage() {
  return (
    <div>
      <PageHeader
        title="Files"
        description="Browse, rename, download, and delete files in the download folder."
      />
      <FileBrowser />
    </div>
  );
}
