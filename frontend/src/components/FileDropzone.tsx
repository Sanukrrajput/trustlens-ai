import { useRef, useState, type DragEvent } from 'react';
import { FileText, UploadCloud } from 'lucide-react';
import { cx } from '../lib/utils';

export function FileDropzone({
  onFile,
  accept = '.pdf,.doc,.docx,.txt,.png,.jpg,.jpeg',
  maxSizeMB = 20,
  error,
  selected,
}: {
  onFile: (file: File) => void;
  accept?: string;
  maxSizeMB?: number;
  error?: string;
  selected?: File | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleFile = (file?: File) => {
    if (!file) return;
    if (file.size > maxSizeMB * 1024 * 1024) {
      setLocalError(`File is larger than the ${maxSizeMB} MB limit.`);
      return;
    }
    setLocalError(null);
    onFile(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    handleFile(event.dataTransfer.files?.[0]);
  };

  const shownError = error ?? localError;

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={cx(
          'flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition',
          dragging ? 'border-brand-500 bg-brand-500/10' : 'border-line bg-elevated/40 hover:border-brand-500/60',
          shownError && 'border-danger/60',
        )}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click();
        }}
        aria-label="Upload a document"
      >
        <UploadCloud className={cx('mb-3 h-8 w-8', dragging ? 'text-brand-500' : 'text-muted')} />
        <p className="text-sm font-semibold">{selected ? selected.name : 'Drop a file here or click to browse'}</p>
        <p className="mt-1 text-xs text-muted">
          PDF, DOC, DOCX, TXT or images · up to {maxSizeMB} MB · stored and processed securely
        </p>
        {selected && <p className="mt-1 text-xs text-brand-600 dark:text-brand-400">{(selected.size / 1024).toFixed(0)} KB selected</p>}
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={accept}
          onChange={(event) => handleFile(event.target.files?.[0])}
        />
      </div>
      {shownError && <p className="mt-2 text-xs font-medium text-danger" role="alert">{shownError}</p>}
      {selected && !shownError && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted"><FileText className="h-3.5 w-3.5" /> Ready for analysis.</p>
      )}
    </div>
  );
}
