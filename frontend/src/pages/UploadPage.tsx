/**
 * UploadPage.tsx
 *
 * Two upload paths — both send data to the real backend:
 *
 * 1. DIRECT BACKEND UPLOAD (primary, recommended):
 *    POST /api/reports/upload — file sent to FastAPI, analyzed, and persisted to the safety database.
 *    Redirects to /dashboard after success.
 *
 * 2. PREVIEW WIZARD (for users who want to inspect before committing):
 *    Parse file client-side → preview table → column mapping → quality check
 *    → POST /api/reports/upload via the same backend call.
 *
 * NO demo data. NO mock data.
 * Clean modern light theme.
 */
import { useState, useRef, useCallback } from 'react';
import {
  Upload, X, CheckCircle, AlertCircle, Eye,
  ChevronLeft, ChevronRight, Search, ArrowUpDown,
  Server, Languages, Shield,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { detectColumnMapping, analyzeDatasetQuality, formatFileSize } from '../utils/datasetUtils';
import { processDataset } from '../utils/multilingualUtils';
import { ColumnMapping, MultilingualStats } from '../types';
import { MultilingualStatsBanner, LanguageBadge } from '../components/MultilingualBadge';
import { uploadReportsCSV, UploadResult } from '../services/api';

type Step = 'upload' | 'preview' | 'mapping' | 'quality';

const PAGE_SIZE = 10;

const MAPPING_FIELDS: Array<{ key: keyof ColumnMapping; label: string; required?: boolean }> = [
  { key: 'report_text',        label: 'Report Text Column',        required: true },
  { key: 'report_type',        label: 'Report Type Column' },
  { key: 'sif_label',          label: 'SIF Label Column' },
  { key: 'severity',           label: 'Severity Column' },
  { key: 'site',               label: 'Site Column' },
  { key: 'unit',               label: 'Operating Unit Column' },
  { key: 'area',               label: 'Work Area Column' },
  { key: 'location',           label: 'Location Column' },
  { key: 'activity',           label: 'Activity Column' },
  { key: 'date',               label: 'Date Column' },
  { key: 'barrier_failure',    label: 'Barrier Failure Column' },
  { key: 'recommended_action', label: 'Recommended Action Column' },
  { key: 'life_saving_rule',   label: 'Life-Saving Rule Column' },
];

export default function UploadPage() {
  const navigate = useNavigate();
  const fileRef  = useRef<HTMLInputElement>(null);

  // ── Wizard state ──────────────────────────────────────────────────────────
  const [step,        setStep]        = useState<Step>('upload');
  const [dragging,    setDragging]    = useState(false);
  const [parsing,     setParsing]     = useState(false);
  const [parseError,  setParseError]  = useState('');
  const [rawRows,     setRawRows]     = useState<Record<string, unknown>[]>([]);
  const [columns,     setColumns]     = useState<string[]>([]);
  const [filename,    setFilename]    = useState('');
  const [filesize,    setFilesize]    = useState(0);
  const [rawFile,     setRawFile]     = useState<File | null>(null);
  const [mapping,     setMapping]     = useState<ColumnMapping>({});
  const [quality,     setQuality]     = useState<ReturnType<typeof analyzeDatasetQuality> | null>(null);
  const [previewPage, setPreviewPage] = useState(0);
  const [search,      setSearch]      = useState('');
  const [sortCol,     setSortCol]     = useState('');
  const [sortDir,     setSortDir]     = useState<'asc' | 'desc'>('asc');
  const [translateEnabled, setTranslateEnabled] = useState(true);
  const [mlStats,     setMlStats]     = useState<MultilingualStats | null>(null);

  // ── Backend upload state ──────────────────────────────────────────────────
  const [uploading,   setUploading]   = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState('');

  // ── Backend upload ────────────────────────────────────────────────────────
  async function uploadToBackend(file: File) {
    setUploading(true);
    setUploadError('');
    setUploadResult(null);
    try {
      const result = await uploadReportsCSV(file);
      setUploadResult(result);
      window.dispatchEvent(new CustomEvent('safesense:data-updated'));
      setTimeout(() => navigate('/app/dashboard'), 2500);
    } catch (err) {
      setUploadError(
        err instanceof Error
          ? err.message
          : 'Upload failed. Make sure the backend is running on port 8000.'
      );
    }
    setUploading(false);
  }

  // ── Client-side file parse (wizard preview only) ──────────────────────────
  async function parseFile(file: File) {
    setParsing(true);
    setParseError('');
    try {
      let rows: Record<string, unknown>[] = [];
      let cols: string[] = [];
      const ext = file.name.split('.').pop()?.toLowerCase();

      if (ext === 'csv') {
        const Papa = await import('papaparse');
        const text = await file.text();
        const result = Papa.default.parse(text, { header: true, skipEmptyLines: true, dynamicTyping: false });
        rows = result.data as Record<string, unknown>[];
        cols = result.meta.fields || [];
      } else if (ext === 'xlsx' || ext === 'xls') {
        const XLSX = await import('xlsx');
        const buf  = await file.arrayBuffer();
        const wb   = XLSX.read(buf, { type: 'array' });
        const ws   = wb.Sheets[wb.SheetNames[0]];
        const data = XLSX.utils.sheet_to_json(ws, { header: 1 }) as unknown[][];
        if (data.length > 0) {
          cols = (data[0] as string[]).map(String);
          rows = data.slice(1).map(row => {
            const obj: Record<string, unknown> = {};
            cols.forEach((c, i) => { obj[c] = (row as unknown[])[i] ?? ''; });
            return obj;
          });
        }
      } else {
        throw new Error('Unsupported file type. Upload a .csv, .xlsx, or .xls file.');
      }

      if (rows.length === 0) throw new Error('File appears to be empty.');

      setRawRows(rows);
      setColumns(cols);
      setFilename(file.name);
      setFilesize(file.size);
      setRawFile(file);
      setMapping(detectColumnMapping(cols));
      setStep('preview');
    } catch (err) {
      setParseError(err instanceof Error ? err.message : 'Failed to parse file.');
    }
    setParsing(false);
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) parseFile(file);
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) parseFile(file);
    e.target.value = '';
  }

  function proceedToQuality() {
    const q = analyzeDatasetQuality(rawRows, columns, mapping as never);
    if (mapping.report_text) {
      const texts = rawRows.map(r => String(r[mapping.report_text!] || ''));
      const langColName = columns.find(c => ['language', 'lang', 'detected_language'].includes(c.toLowerCase()));
      const hints = langColName ? rawRows.map(r => String(r[langColName] || '') || undefined) : undefined;
      const { stats } = processDataset(texts, hints, translateEnabled);
      setMlStats({ ...stats, translate_enabled: translateEnabled });
    }
    setQuality(q);
    setStep('quality');
  }

  // Preview table helpers
  const filteredRows = rawRows.filter(row =>
    !search || columns.some(c => String(row[c] || '').toLowerCase().includes(search.toLowerCase()))
  );
  const sortedRows = sortCol
    ? [...filteredRows].sort((a, b) => {
        const av = String(a[sortCol] || '');
        const bv = String(b[sortCol] || '');
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      })
    : filteredRows;
  const paginated  = sortedRows.slice(previewPage * PAGE_SIZE, (previewPage + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sortedRows.length / PAGE_SIZE);

  // Step indicator labels
  const STEPS: Step[] = ['upload', 'preview', 'mapping', 'quality'];

  return (
    <div className="space-y-8 animate-in">
      <div>
        <h1 className="section-title">Upload Safety Reports</h1>
        <p className="section-sub">Upload a CSV or Excel file — data is sent to the backend, analyzed, and saved to the database.</p>
      </div>

      {/* Step indicators */}
      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
              step === s                    ? 'bg-blue-600 text-white' :
              STEPS.indexOf(step) > i      ? 'bg-green-600 text-white' :
                                             'bg-slate-200 text-slate-600'
            }`}>{i + 1}</div>
            <span className={`text-xs font-medium hidden sm:block capitalize ${step === s ? 'text-blue-600 font-bold' : 'text-slate-500'}`}>{s}</span>
            {i < STEPS.length - 1 && <div className="w-8 h-px bg-slate-200" />}
          </div>
        ))}
      </div>

      {/* ─── STEP: UPLOAD ─────────────────────────────────────────────────── */}
      {step === 'upload' && (
        <div className="space-y-6">

          {/* Primary: Direct backend upload */}
          <div className="card border-blue-200 bg-blue-50/40">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Server className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-bold text-slate-900 text-base">
                    Direct Backend Upload
                  </h3>
                  <span className="text-xs bg-blue-100 text-blue-700 font-semibold px-2.5 py-0.5 rounded-full border border-blue-200">RECOMMENDED</span>
                </div>
                <p className="text-slate-600 text-sm mb-1.5">
                  File is sent directly to the FastAPI backend. Every row is analyzed and saved to the safety database. Dashboard reflects the new data immediately.
                </p>
                <p className="text-slate-500 text-xs mb-4">
                  File must contain a <code className="bg-slate-200 text-slate-800 px-1 py-0.5 rounded text-xs">description</code> column (or alias: <code className="text-slate-600">report_text</code>, <code className="text-slate-600">observation</code>, <code className="text-slate-600">text</code>).
                </p>

                <label className={`inline-block ${uploading ? 'cursor-not-allowed pointer-events-none opacity-60' : 'cursor-pointer'}`}>
                  <input
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    className="hidden"
                    disabled={uploading}
                    onChange={e => {
                      const f = e.target.files?.[0];
                      if (f) uploadToBackend(f);
                      e.target.value = '';
                    }}
                  />
                  <span className={`btn-primary text-sm inline-flex items-center gap-2 ${uploading ? 'opacity-60 cursor-not-allowed pointer-events-none' : ''}`}>
                    {uploading ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Uploading…
                      </>
                    ) : (
                      <>
                        <Server className="w-4 h-4" />
                        Choose File &amp; Upload to Backend
                      </>
                    )}
                  </span>
                </label>

                {uploadError && (
                  <div className="mt-4 flex items-start gap-2.5 text-red-900 bg-red-50 border border-red-200 rounded-lg p-3.5 text-sm">
                    <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-red-900">Upload failed</p>
                      <p className="text-xs text-red-700 mt-0.5">{uploadError}</p>
                    </div>
                  </div>
                )}

                {uploadResult && (
                  uploadResult.file_duplicate ? (
                    <div className="mt-4 p-4 bg-amber-50 border border-amber-300 rounded-lg text-amber-900 animate-in fade-in">
                      <div className="flex items-start gap-2.5 mb-2">
                        <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="text-sm font-bold text-amber-900">
                            ⚠️ This dataset was already uploaded. No new data added.
                          </p>
                          <p className="text-xs text-amber-700 mt-1">
                            File <span className="font-semibold">{uploadResult.filename}</span> matches an existing MD5 checksum. All records are already present in the database.
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 pt-3 border-t border-amber-200 flex items-center justify-between text-xs text-amber-800">
                        <span>Database remains idempotent (0 records added).</span>
                        <span className="font-medium text-amber-700">Redirecting to dashboard…</span>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-900 animate-in fade-in">
                      <div className="flex items-center gap-2 mb-2">
                        <CheckCircle className="w-5 h-5 text-green-600" />
                        <span className="text-sm font-bold text-green-800">
                          ✔ {uploadResult.inserted ?? uploadResult.processed} new reports added
                          {(uploadResult.duplicates_skipped ?? 0) > 0 ? `, ${uploadResult.duplicates_skipped} duplicate(s) skipped` : ''}
                        </span>
                      </div>
                      <div className="grid grid-cols-4 gap-2 text-center my-3">
                        <div className="bg-white p-2.5 rounded-lg border border-green-100 shadow-xs">
                          <p className="text-xl font-bold text-slate-900">{uploadResult.total_rows}</p>
                          <p className="text-xs text-slate-500 font-medium">Total Rows</p>
                        </div>
                        <div className="bg-white p-2.5 rounded-lg border border-green-100 shadow-xs">
                          <p className="text-xl font-bold text-green-600">{uploadResult.inserted ?? uploadResult.processed}</p>
                          <p className="text-xs text-slate-500 font-medium">New Inserted</p>
                        </div>
                        <div className="bg-white p-2.5 rounded-lg border border-green-100 shadow-xs">
                          <p className="text-xl font-bold text-amber-600">{uploadResult.duplicates_skipped ?? 0}</p>
                          <p className="text-xs text-slate-500 font-medium">Duplicates</p>
                        </div>
                        <div className="bg-white p-2.5 rounded-lg border border-green-100 shadow-xs">
                          <p className="text-xl font-bold text-red-600">{uploadResult.sif_count}</p>
                          <p className="text-xs text-slate-500 font-medium">SIF Potential</p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {Object.entries(uploadResult.risk_summary || {})
                          .filter(([, v]) => v > 0)
                          .map(([level, count]) => (
                            <span key={level} className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-white text-slate-700 border border-green-200">
                              {level}: {count}
                            </span>
                          ))}
                      </div>
                      {((uploadResult.pii_detected_count ?? 0) > 0) && (
                        <div className="my-2 p-2.5 bg-indigo-50 border border-indigo-200 rounded-lg flex items-center gap-2 text-xs text-indigo-900">
                          <Shield className="w-4 h-4 text-indigo-600 shrink-0" />
                          <span>
                            <strong>Privacy Protection:</strong> {uploadResult.pii_detected_count} report(s) contained personal identifiers (names, IDs, phones) and were automatically sanitized before database storage.
                          </span>
                        </div>
                      )}
                      <p className="text-xs text-green-700 font-medium mt-1">Redirecting to dashboard…</p>
                    </div>
                  )
                )}
              </div>
            </div>
          </div>

          {/* Secondary: Preview wizard drop zone */}
          <div className="card">
            <h3 className="font-semibold text-slate-900 mb-1 text-sm">Preview before uploading</h3>
            <p className="text-slate-500 text-xs mb-4">
              Drop a file below to inspect the data, map columns, and check quality — then send it to the backend.
            </p>
            <div
              className={`border-2 border-dashed rounded-xl p-10 text-center transition-all cursor-pointer ${
                dragging ? 'border-blue-500 bg-blue-50' : 'border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50'
              }`}
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFileChange} className="hidden" />
              <Upload className="w-10 h-10 text-slate-400 mx-auto mb-3" />
              <p className="text-slate-800 font-medium mb-1">Drop file here or click to browse</p>
              <p className="text-slate-400 text-xs">CSV · Excel (.xlsx, .xls)</p>
              {parsing && (
                <div className="mt-3 flex items-center justify-center gap-2 text-blue-600 text-sm font-medium">
                  <span className="w-4 h-4 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
                  Parsing file…
                </div>
              )}
            </div>
            {parseError && (
              <div className="mt-4 flex items-center gap-2 text-red-900 bg-red-50 border border-red-200 rounded-lg p-3.5 text-sm">
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                {parseError}
              </div>
            )}
          </div>

        </div>
      )}

      {/* ─── STEP: PREVIEW ────────────────────────────────────────────────── */}
      {step === 'preview' && (
        <div className="space-y-6">
          <div className="card border-green-200 bg-green-50/50 flex items-center gap-4">
            <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
            <div className="flex-1">
              <div className="font-bold text-slate-900">{filename}</div>
              <div className="text-sm text-slate-500">{formatFileSize(filesize)} · {rawRows.length} rows · {columns.length} columns</div>
            </div>
            <button onClick={() => setStep('upload')} className="text-slate-400 hover:text-slate-700 p-1">
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="card p-0 overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50/50">
              <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                <Eye className="w-4 h-4 text-blue-600" />Data Preview
              </h3>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  value={search}
                  onChange={e => { setSearch(e.target.value); setPreviewPage(0); }}
                  className="input-field pl-8 py-1.5 text-sm w-52"
                  placeholder="Search…"
                />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    {columns.map(col => (
                      <th
                        key={col}
                        className="py-3 px-3.5 text-slate-600 font-semibold whitespace-nowrap cursor-pointer hover:text-slate-900 select-none"
                        onClick={() => { setSortCol(col); setSortDir(sd => sd === 'asc' ? 'desc' : 'asc'); }}
                      >
                        <span className="flex items-center gap-1">{col} <ArrowUpDown className="w-3 h-3 text-slate-400" /></span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {paginated.map((row, i) => (
                    <tr key={i} className="hover:bg-slate-50/70 transition-colors">
                      {columns.map(col => (
                        <td key={col} className="px-3.5 py-2.5 text-slate-700 max-w-xs truncate whitespace-nowrap">
                          {String(row[col] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between p-3.5 border-t border-slate-200 bg-slate-50/50">
              <span className="text-xs text-slate-500 font-medium">
                Showing {previewPage * PAGE_SIZE + 1}–{Math.min((previewPage + 1) * PAGE_SIZE, sortedRows.length)} of {sortedRows.length}
              </span>
              <div className="flex items-center gap-1.5">
                <button onClick={() => setPreviewPage(p => Math.max(0, p - 1))} disabled={previewPage === 0} className="p-1 rounded-md border border-slate-200 hover:bg-white text-slate-600 disabled:opacity-30">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs font-semibold text-slate-700 px-2">{previewPage + 1}/{totalPages}</span>
                <button onClick={() => setPreviewPage(p => Math.min(totalPages - 1, p + 1))} disabled={previewPage >= totalPages - 1} className="p-1 rounded-md border border-slate-200 hover:bg-white text-slate-600 disabled:opacity-30">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <div className="flex justify-between">
            <button onClick={() => setStep('upload')} className="btn-secondary">← Back</button>
            <button onClick={() => setStep('mapping')} className="btn-primary">Continue to Column Mapping →</button>
          </div>
        </div>
      )}

      {/* ─── STEP: MAPPING ────────────────────────────────────────────────── */}
      {step === 'mapping' && (
        <div className="space-y-6">
          <div className="card">
            <h3 className="font-bold text-slate-900 mb-1">Column Mapping</h3>
            <p className="text-slate-500 text-sm mb-6">Map your dataset columns to expected fields. Columns were auto-detected — adjust if needed.</p>
            <div className="grid sm:grid-cols-2 gap-5">
              {MAPPING_FIELDS.map(field => (
                <div key={field.key}>
                  <label className="text-xs font-semibold text-slate-700 mb-1.5 block">
                    {field.label} {field.required && <span className="text-red-500">*</span>}
                  </label>
                  <select
                    value={(mapping as Record<string, string>)[field.key] || ''}
                    onChange={e => setMapping(prev => ({ ...prev, [field.key]: e.target.value || undefined }))}
                    className="input-field text-sm"
                  >
                    <option value="">— Not mapped —</option>
                    {columns.map(col => <option key={col} value={col}>{col}</option>)}
                  </select>
                </div>
              ))}
            </div>
          </div>

          <div className="card border-indigo-200 bg-indigo-50/40">
            <div className="flex items-center gap-2 mb-3">
              <Languages className="w-4 h-4 text-indigo-600" />
              <h3 className="font-bold text-slate-900 text-sm">Language Processing</h3>
            </div>
            <label className="flex items-center gap-3 cursor-pointer">
              <div className="relative">
                <input type="checkbox" checked={translateEnabled} onChange={e => setTranslateEnabled(e.target.checked)} className="sr-only" />
                <div className={`w-10 h-5 rounded-full transition-colors ${translateEnabled ? 'bg-indigo-600' : 'bg-slate-300'}`} />
                <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ${translateEnabled ? 'translate-x-5' : ''}`} />
              </div>
              <div>
                <p className="text-sm text-slate-800 font-medium">Detect and translate non-English reports</p>
                <p className="text-xs text-slate-500">Supports English, Kannada, Hindi</p>
              </div>
            </label>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
              <span>Supported:</span>
              <LanguageBadge language="en" size="sm" />
              <LanguageBadge language="kn" size="sm" />
              <LanguageBadge language="hi" size="sm" />
            </div>
          </div>

          <div className="flex justify-between">
            <button onClick={() => setStep('preview')} className="btn-secondary">← Back</button>
            <button onClick={proceedToQuality} className="btn-primary">Check Quality →</button>
          </div>
        </div>
      )}

      {/* ─── STEP: QUALITY ────────────────────────────────────────────────── */}
      {step === 'quality' && quality && (
        <div className="space-y-6">
          <div className="card border-blue-200 bg-blue-50/40">
            <div className="flex items-center gap-6">
              <div className="text-center bg-white p-4 rounded-xl border border-blue-100 shadow-xs min-w-[100px]">
                <div className={`text-4xl font-extrabold ${quality.health_score >= 80 ? 'text-green-600' : quality.health_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                  {quality.health_score}
                </div>
                <div className="text-slate-400 text-xs font-semibold">/ 100</div>
              </div>
              <div>
                <h3 className="font-bold text-slate-900 text-lg">Dataset Health Score</h3>
                <p className="text-slate-600 text-sm">
                  {quality.health_score >= 80 ? 'Good quality — ready for upload.' :
                   quality.health_score >= 60 ? 'Moderate quality — some data gaps detected.' :
                                                'Low quality — review warnings before uploading.'}
                </p>
              </div>
            </div>
          </div>

          {mlStats && <MultilingualStatsBanner stats={mlStats} />}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Total Records',     value: quality.total_records },
              { label: 'Columns',           value: quality.total_columns },
              { label: 'Empty Reports',     value: quality.empty_reports },
              { label: 'Duplicates',        value: quality.duplicate_records },
              { label: 'Avg Report Length', value: `${quality.avg_report_length} chars` },
              { label: 'Report Types',      value: quality.unique_report_types },
              { label: 'Sites',             value: quality.unique_sites  || 'N/A' },
              { label: 'Activities',        value: quality.unique_activities || 'N/A' },
            ].map(m => (
              <div key={m.label} className="card text-center py-4">
                <div className="text-xl font-bold text-slate-900">{m.value}</div>
                <div className="text-xs text-slate-500 font-medium mt-0.5">{m.label}</div>
              </div>
            ))}
          </div>

          {quality.warnings.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-amber-900">
              <h4 className="font-bold text-amber-900 mb-2.5 text-sm flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-amber-600" />
                Warnings
              </h4>
              <ul className="space-y-1.5">
                {quality.warnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-amber-800">
                    <span className="text-amber-500 font-bold">•</span>
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Upload error from this step */}
          {uploadError && (
            <div className="flex items-start gap-2.5 text-red-900 bg-red-50 border border-red-200 rounded-lg p-4 text-sm">
              <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-900">Upload failed</p>
                <p className="text-xs text-red-700 mt-0.5">{uploadError}</p>
              </div>
            </div>
          )}

          {/* Upload result feedback in Step 4 */}
          {uploadResult && (
            uploadResult.file_duplicate ? (
              <div className="p-4 bg-amber-50 border border-amber-300 rounded-lg text-amber-900 animate-in fade-in">
                <div className="flex items-start gap-2.5">
                  <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-bold text-amber-900">
                      ⚠️ This dataset was already uploaded. No new data added.
                    </p>
                    <p className="text-xs text-amber-700 mt-1">
                      File <span className="font-semibold">{uploadResult.filename}</span> matches an existing MD5 checksum. All records are already present in the database.
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-900 animate-in fade-in">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <span className="text-sm font-bold text-green-800">
                    ✔ {uploadResult.inserted ?? uploadResult.processed} new reports added
                    {(uploadResult.duplicates_skipped ?? 0) > 0 ? `, ${uploadResult.duplicates_skipped} duplicate(s) skipped` : ''}
                  </span>
                </div>
                {((uploadResult.pii_detected_count ?? 0) > 0) && (
                  <div className="mb-2 p-2.5 bg-indigo-50 border border-indigo-200 rounded-lg flex items-center gap-2 text-xs text-indigo-900">
                    <Shield className="w-4 h-4 text-indigo-600 shrink-0" />
                    <span>
                      <strong>Privacy Protection:</strong> {uploadResult.pii_detected_count} report(s) had sensitive personal identifiers sanitized.
                    </span>
                  </div>
                )}
                <p className="text-xs text-green-700 font-medium">Redirecting to dashboard…</p>
              </div>
            )
          )}

          <div className="flex justify-between">
            <button onClick={() => setStep('mapping')} className="btn-secondary">← Back</button>
            <button
              onClick={() => rawFile && uploadToBackend(rawFile)}
              disabled={uploading || !rawFile}
              className="btn-primary"
            >
              {uploading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Uploading to backend…
                </>
              ) : (
                <>
                  <Server className="w-4 h-4" />
                  Upload to Backend
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
