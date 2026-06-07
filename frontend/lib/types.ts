export interface FormatInfo {
  format_id: string;
  ext: string;
  resolution?: string | null;
  fps?: number | null;
  vcodec?: string | null;
  acodec?: string | null;
  filesize?: number | null;
  format_note?: string | null;
}

export interface Metadata {
  title: string;
  thumbnail?: string | null;
  uploader?: string | null;
  duration?: number | null;
  url: string;
  formats: FormatInfo[];
}

export type JobStatus =
  | "queued"
  | "downloading"
  | "finished"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  url: string;
  title?: string | null;
  thumbnail?: string | null;
  status: JobStatus;
  format_id?: string | null;
  progress: number;
  speed?: string | null;
  eta?: string | null;
  file_path?: string | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface HistoryEntry {
  id: string;
  url?: string | null;
  title?: string | null;
  thumbnail?: string | null;
  file_path?: string | null;
  format_id?: string | null;
  finished_at?: string | null;
}

export interface Settings {
  download_folder: string;
  audio_format: string;
  concurrent_downloads: number;
  ytdlp_path: string;
  ffmpeg_path: string;
}

export interface DownloadRequest {
  url: string;
  format_id?: string | null;
}

export type ShareType = "smb" | "nfs";

export interface Share {
  id: number;
  name: string;
  type: ShareType;
  remote: string;
  mount_point: string;
  username?: string | null;
  domain?: string | null;
  options?: string | null;
  auto_mount: boolean;
  mounted: boolean;
}

export interface ShareCreate {
  name: string;
  type: ShareType;
  remote: string;
  mount_point: string;
  username?: string | null;
  password?: string | null;
  domain?: string | null;
  options?: string | null;
  auto_mount: boolean;
}

export interface MountResult {
  mounted: boolean;
  message?: string | null;
}
