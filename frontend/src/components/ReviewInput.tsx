import { useState, useRef } from 'react';
import { Upload, Loader2, Plus, X } from 'lucide-react';
import { useDomains } from '../hooks/useDomains';

const ACCEPTED_EXTENSIONS = ['.csv', '.tsv', '.xlsx', '.json', '.jsonl', '.ndjson', '.txt'];

function isAccepted(name: string) {
  const lower = name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some(ext => lower.endsWith(ext));
}

interface ReviewInputProps {
  onSubmit: (file: File, domainId: string, aspects: string[], reviewColumn?: string) => void;
  isLoading: boolean;
}

function formatAspect(aspect: string) {
  return aspect.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function ReviewInput({ onSubmit, isLoading }: ReviewInputProps) {
  const { domains, isLoading: domainsLoading } = useDomains();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [reviewColumn, setReviewColumn] = useState('');
  const [selectedDomainId, setSelectedDomainId] = useState('general');
  const [selectedAspects, setSelectedAspects] = useState<string[]>([]);
  const [customAspect, setCustomAspect] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // When domain changes, reset aspects to that domain's defaults
  function handleDomainChange(domainId: string) {
    setSelectedDomainId(domainId);
    const domain = domains.find(d => d.id === domainId);
    if (domain) {
      setSelectedAspects(domain.aspects);
    }
  }

  // Initialize aspects when domains load
  if (domains.length > 0 && selectedAspects.length === 0) {
    const domain = domains.find(d => d.id === selectedDomainId);
    if (domain) {
      setSelectedAspects(domain.aspects);
    }
  }

  function toggleAspect(aspect: string) {
    setSelectedAspects(prev =>
      prev.includes(aspect)
        ? prev.filter(a => a !== aspect)
        : [...prev, aspect]
    );
  }

  function addCustomAspect() {
    const aspect = customAspect.trim().toLowerCase().replace(/\s+/g, '_');
    if (aspect && !selectedAspects.includes(aspect)) {
      setSelectedAspects(prev => [...prev, aspect]);
    }
    setCustomAspect('');
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) chooseFile(droppedFile);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) chooseFile(selected);
  }

  function chooseFile(f: File) {
    if (isAccepted(f.name)) {
      setFile(f);
      setFileError(null);
    } else {
      setFile(null);
      setFileError(`Unsupported file type. Use ${ACCEPTED_EXTENSIONS.join(', ')}`);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isLoading || selectedAspects.length === 0) return;

    if (file) {
      onSubmit(file, selectedDomainId, selectedAspects, reviewColumn);
    }
  }

  const canSubmit = file && selectedAspects.length > 0;

  const selectedDomain = domains.find(d => d.id === selectedDomainId);
  const domainAspects = selectedDomain?.aspects ?? [];
  const allAspects = [...new Set([...domainAspects, ...selectedAspects])];

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* File Drop Zone */}
      <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">
            Upload Reviews
          </label>
          <div
            onDragOver={e => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
              isDragOver
                ? 'border-blue-500 bg-blue-950/30'
                : file
                  ? 'border-green-700 bg-green-950/20'
                  : 'border-gray-700 hover:border-gray-600 bg-gray-800/50'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(',')}
              onChange={handleFileSelect}
              className="hidden"
              disabled={isLoading}
            />
            <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? 'text-green-400' : 'text-gray-500'}`} />
            {file ? (
              <div className="flex items-center justify-center gap-2">
                <p className="text-sm text-green-300">{file.name}</p>
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); setFile(null); }}
                  className="text-gray-500 hover:text-gray-300"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <p className="text-sm text-gray-400">
                  Drop a file of reviews here, or click to browse
                </p>
                <p className="text-xs text-gray-600 mt-1">
                  CSV, TSV, Excel (.xlsx), JSON / JSONL, or plain text (one review per line or paragraph)
                </p>
              </>
            )}
          </div>
          {fileError && <p className="text-xs text-red-400 mt-1.5">{fileError}</p>}
          <input
            type="text"
            value={reviewColumn}
            onChange={e => setReviewColumn(e.target.value)}
            placeholder="Review column / JSON key (optional — auto-detected)"
            disabled={isLoading}
            className="w-full mt-2 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
      </div>

      {/* Domain Selector */}
      <div>
        <label htmlFor="domain-select" className="block text-sm font-medium text-gray-300 mb-1.5">
          Industry / Domain
        </label>
        <select
          id="domain-select"
          value={selectedDomainId}
          onChange={e => handleDomainChange(e.target.value)}
          disabled={isLoading || domainsLoading}
          className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          {domains.map(d => (
            <option key={d.id} value={d.id}>
              {d.name}{d.description ? ` — ${d.description}` : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Aspect Chips */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Aspects to Analyze
        </label>
        <div className="flex flex-wrap gap-2">
          {allAspects.map(aspect => (
            <button
              key={aspect}
              type="button"
              onClick={() => toggleAspect(aspect)}
              disabled={isLoading}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                selectedAspects.includes(aspect)
                  ? 'bg-blue-900 text-blue-200 border border-blue-700'
                  : 'bg-gray-800 text-gray-400 border border-gray-700 hover:bg-gray-700'
              }`}
            >
              {formatAspect(aspect)}
            </button>
          ))}
        </div>
        {/* Custom aspect input */}
        <div className="flex gap-2 mt-2">
          <input
            type="text"
            value={customAspect}
            onChange={e => setCustomAspect(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustomAspect(); } }}
            placeholder="Add custom aspect..."
            disabled={isLoading}
            className="flex-1 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          <button
            type="button"
            onClick={addCustomAspect}
            disabled={!customAspect.trim() || isLoading}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-300 rounded-lg text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={!canSubmit || isLoading}
        className="w-full py-3 px-6 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Analyzing...
          </>
        ) : (
          'Analyze Reviews'
        )}
      </button>
    </form>
  );
}
