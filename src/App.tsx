import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import './focused-workspace.css';
import './srt-voice-v1.css';
import './capcut-project-v1.css';
import './capcut-sync.css';
import './shell-v3.css';
import './sync-phase5.css';
import './phase6.css';
import { useToast } from './components/ui';
import { AudioLines, Captions, Check, ChevronDown, CircleHelp, Clapperboard, Download, FileText, FolderOpen, Moon, Pause, Play, RefreshCw, Search, Settings2, Sliders, Sparkles, Square, Sun, Trash2, UploadCloud, X, Zap } from 'lucide-react';

type Page = 'srt' | 'capcut';
type SrtVoiceRow = { id: number; start: string; end: string; text: string; status: 'pending' | 'generating' | 'completed' | 'failed'; duration?: number; file?: string; error?: string };
type SrtDraft = { name: string; path: string; rows: SrtVoiceRow[] };
type SrtQueueItem = { id: string; draft: SrtDraft; status: 'waiting'|'running'|'completed'|'failed'|'cancelled'; done: number; total: number; outputDir?: string; error?: string };
type SrtGenerationResult = { state: 'cancelled'|'completed'; completed: number; failed: number; total: number; items: SrtVoiceRow[]; outputDir: string };
type ApiVoice = { id: string; name: string; previewUrl?: string; language?: string; provider?: string; personal?: boolean };
type VoiceEngine = 'ai33' | 'aimax' | 'capcut';
type CapCutBackend = 'direct' | 'space' | 'hybrid';
type VoicePreset = {
  engine: VoiceEngine;
  apiProvider: string;
  apiModel: string;
  apiVoiceId: string;
  apiWorkers: number;
  apiRequestInterval: number;
  subtitleLanguage: string;
  speed: number;
  capcutBackend: CapCutBackend;
  autoRetry: boolean;
};

const readVoicePreset = (): Partial<VoicePreset> | null => {
  try {
    const value = JSON.parse(localStorage.getItem('hhvietsub.voicePreset') || 'null');
    return value && typeof value === 'object' ? value as Partial<VoicePreset> : null;
  } catch {
    return null;
  }
};

const liteVoiceEngine = (value: unknown): VoiceEngine =>
  value === 'ai33' || value === 'aimax' || value === 'capcut' ? value : 'capcut';

const cleanUnicode = (value: string) => new TextDecoder().decode(new TextEncoder().encode(value));
const subtitleTimeMs = (value: string) => {
  const parts = value.replace(',', '.').split(':').map(Number);
  return parts.length === 3 && parts.every(Number.isFinite) ? ((parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000) : Number.NaN;
};

const nav: { id: Page; label: string; icon: typeof Sparkles }[] = [
  { id: 'srt', label: 'Tạo voice SRT', icon: FileText },
  { id: 'capcut', label: 'Đồng bộ & CapCut', icon: Clapperboard },
];

export function App() {
  const [page, setPage] = useState<Page>('srt');
  const [online, setOnline] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('hhvietsub.theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    if (!window.desktop) return;
    window.desktop.request<{ online: boolean }>('system.ping').then((v) => setOnline(v.online)).catch(() => setOnline(false));
    return window.desktop.onBackendEvent((raw) => {
      const event = raw as { event?: string; data?: { online?: boolean } };
      if (event.event === 'backend.state') setOnline(Boolean(event.data?.online));
    });
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('hhvietsub.theme', theme);
  }, [theme]);

  return <div className="app-shell focused-workspace lite-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><AudioLines size={23} /></div><div><strong>HHVietSub Lite</strong><span>CapCut Voice & Sync</span></div></div>
      <nav className="nav-pills">{nav.map((item) => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => setPage(item.id)}><item.icon size={15} />{item.label}</button>)}</nav>
      <div className="top-actions">
        <span className={`backend-state ${online ? 'online' : ''}`}><i />{online ? 'Backend sẵn sàng' : 'Backend chưa sẵn sàng'}</span>
        <button className="theme-toggle" type="button" title={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}</button>
      </div>
    </header>

    <main className="workspace">
      <div className="workspace-view" style={{ display: page === 'srt' ? 'block' : 'none' }}>
        <SrtVoicePage />
      </div>
      <div className="workspace-view" style={{ display: page === 'capcut' ? 'block' : 'none' }}>
        <CapCutProjectPage />
      </div>
    </main>

  </div>;
}

function SrtVoicePage() {
  const { showToast } = useToast();
  const initialVoicePreset = useMemo(() => readVoicePreset(), []);
  const [engine, setEngine] = useState<VoiceEngine>(() => liteVoiceEngine(initialVoicePreset?.engine));
  const [apiProvider, setApiProvider] = useState(() => initialVoicePreset?.apiProvider || 'minimax');
  const [apiModel, setApiModel] = useState(() => initialVoicePreset?.apiModel || 'speech-2.8-hd');
  const [apiVoiceId, setApiVoiceId] = useState(() => initialVoicePreset?.apiVoiceId || '');
  const [apiWorkers, setApiWorkers] = useState(() => initialVoicePreset?.apiWorkers || 8);
  const [apiRequestInterval, setApiRequestInterval] = useState(() => {
    const saved = Number(initialVoicePreset?.apiRequestInterval ?? localStorage.getItem('hhvietsub.apiRequestInterval') ?? 10);
    return Number.isFinite(saved) ? Math.min(60, Math.max(0, saved)) : 10;
  });
  const [subtitleLanguage, setSubtitleLanguage] = useState(() => initialVoicePreset?.subtitleLanguage || 'auto');
  const [apiVoices, setApiVoices] = useState<ApiVoice[]>([]);
  const [voiceLibraryOpen, setVoiceLibraryOpen] = useState(false);
  const [voiceLibraryLoading, setVoiceLibraryLoading] = useState(false);
  const [voiceQuery, setVoiceQuery] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [draft, setDraft] = useState<SrtDraft | null>(null);
  const [outputDir, setOutputDir] = useState('');
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn file SRT ở panel bên trái để bắt đầu.');
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [speed, setSpeed] = useState(() => initialVoicePreset?.speed || 1);
  const [audioUrl, setAudioUrl] = useState('');
  const [activeJobId, setActiveJobId] = useState('');
  const [jobState, setJobState] = useState<'idle'|'running'|'paused'|'cancelled'|'completed'>('idle');
  const [savedJobs, setSavedJobs] = useState<{jobId:string;state:string;engine:string;voiceId:string;outputDir:string;createdAt:string;total:number;completed:number;failed:number}[]>([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [jobPickerOpen, setJobPickerOpen] = useState(false);
  const [queue, setQueue] = useState<SrtQueueItem[]>([]);
  const [queueRunning, setQueueRunning] = useState(false);
  const [capcutBackend, setCapcutBackend] = useState<CapCutBackend>(() => initialVoicePreset?.capcutBackend || 'hybrid');
  const [dictionaryOpen, setDictionaryOpen] = useState(false);
  const [apiSettingsOpen, setApiSettingsOpen] = useState(false);
  const [ai33Key, setAi33Key] = useState('');
  const [aimaxKey, setAimaxKey] = useState('');
  const [apiKeyStatus, setApiKeyStatus] = useState({ ai33KeyCount: 0, aimaxKeyCount: 0 });
  const [apiKeyBusy, setApiKeyBusy] = useState(false);
  const [pronunciationDictionary, setPronunciationDictionary] = useState<{id:string;source:string;target:string}[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('hhvietsub.pronunciationDictionary') || '[]');
      return Array.isArray(saved) ? saved : [];
    } catch { return []; }
  });
  const dictionaryImportRef = useRef<HTMLInputElement>(null);
  const activeQueueId = useRef('');
  const stopQueue = useRef(false);
  const saveDictionary = (items: {id:string;source:string;target:string}[]) => {
    setPronunciationDictionary(items);
    localStorage.setItem('hhvietsub.pronunciationDictionary', JSON.stringify(items));
  };
  const loadApiKeyStatus = async () => {
    if (!window.desktop) return;
    const value = await window.desktop.request<{ai33KeyCount:number;aimaxKeyCount:number}>('settings.tts.get');
    setApiKeyStatus(value);
  };
  const saveApiKeys = async () => {
    if (!window.desktop) return;
    setApiKeyBusy(true);
    try {
      const value = await window.desktop.request<{ai33KeyCount:number;aimaxKeyCount:number}>('settings.tts.save', {
        ai33Key: ai33Key.trim(),
        aimaxKey: aimaxKey.trim(),
      });
      setApiKeyStatus(value);
      setAi33Key('');
      setAimaxKey('');
      setMessage('Đã lưu API key bằng kho mã hóa an toàn của Windows.');
    } catch (error) {
      setMessage(`Không thể lưu API key: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setApiKeyBusy(false);
    }
  };
  const testApiKey = async (provider: 'ai33'|'aimax') => {
    if (!window.desktop) return;
    setApiKeyBusy(true);
    try {
      const key = provider === 'ai33' ? ai33Key.trim() : aimaxKey.trim();
      const value = await window.desktop.request<{ok:boolean;valid:number;total:number}>('settings.tts.test', { provider, key });
      setMessage(`${provider.toUpperCase()}: ${value.valid}/${value.total} key hoạt động.`);
      await loadApiKeyStatus();
    } catch (error) {
      setMessage(`Kiểm tra ${provider.toUpperCase()} thất bại: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setApiKeyBusy(false);
    }
  };
  const replacePronunciation = (text: string) => pronunciationDictionary.reduce((current, item) => {
    const source = item.source.trim();
    if (!source || !item.target.trim()) return current;
    return current.replace(new RegExp(source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), item.target.trim());
  }, text);
  const applyDictionaryToDraft = () => {
    setDraft((current) => current ? {...current, rows: current.rows.map((row)=>({...row, text: replacePronunciation(row.text), status: row.status === 'completed' ? 'pending' : row.status}))} : current);
    setQueue((current)=>current.map((item)=>({...item,draft:{...item.draft,rows:item.draft.rows.map((row)=>({...row,text:replacePronunciation(row.text),status:row.status==='completed'?'pending':row.status}))}})));
    setMessage(`Đã áp dụng ${pronunciationDictionary.filter((item)=>item.source.trim()&&item.target.trim()).length} quy tắc phát âm vào phụ đề.`);
  };
  const exportDictionary = () => {
    const blob = new Blob([JSON.stringify(pronunciationDictionary.map(({source,target})=>({source,target})), null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
    anchor.href=url; anchor.download='tu-dien-phat-am-capcut.json'; anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const importDictionary = async (file?: File) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      if (!Array.isArray(parsed)) throw new Error('File phải là một danh sách JSON');
      const items = parsed.map((item,index)=>({id:`dict-${Date.now()}-${index}`,source:String(item.source||item.from||''),target:String(item.target||item.to||'')})).filter((item)=>item.source&&item.target);
      saveDictionary(items); setMessage(`Đã nhập ${items.length} mục từ điển phát âm.`);
    } catch(error) { setMessage(`Không thể nhập từ điển: ${error instanceof Error?error.message:String(error)}`); }
  };
  useEffect(() => { void loadApiKeyStatus().catch(() => undefined); }, []);
  useEffect(() => {
    if (!voiceLibraryOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setVoiceLibraryOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [voiceLibraryOpen]);
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const packet = raw as { event?: string; data?: { event?: string; status?: string; message?: string; device?: string; done?: number; total?: number; id?: number; attempt?: number; item?: SrtVoiceRow; jobId?: string; state?: typeof jobState } | string };
    if (packet.event === 'srt.voice.log' && typeof packet.data === 'string') {
      if (packet.data.includes('Error') || packet.data.includes('Exception') || packet.data.includes('Traceback') || packet.data.includes('RuntimeError')) {
        setMessage(`Lỗi hệ thống: ${packet.data}`);
      }
      return;
    }
    if (packet.event === 'srt.voice.job' && typeof packet.data === 'object' && packet.data) { if (packet.data.jobId) setActiveJobId(packet.data.jobId); if (packet.data.state) setJobState(packet.data.state); return; }
    if (packet.event !== 'srt.voice.progress' || !packet.data || typeof packet.data !== 'object') return;
    const data = packet.data;
    if (data.event === 'startup' || data.event === 'model' || data.event === 'prompt' || data.event === 'error') setMessage(data.message || (data.event === 'startup' ? 'Đang khởi động PyTorch…' : 'Đang nạp mô hình tạo giọng…'));
    if (data.event === 'attempt' && data.id) {
      setMessage(`Đang tạo câu ${String(data.id).padStart(4, '0')} · lần ${data.attempt}/3`);
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === data.id ? { ...row, status: 'generating' } : row) } : current);
    }
    if (data.event === 'progress' && data.item) {
      setProgress({ done: data.done || 0, total: data.total || 0 });
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === data.item!.id ? { ...row, ...data.item } : row) } : current);
      if (activeQueueId.current) {
        setQueue((current) => current.map((item) => item.id === activeQueueId.current ? {
          ...item, done: data.done || item.done, total: data.total || item.total,
          draft: { ...item.draft, rows: item.draft.rows.map((row) => row.id === data.item!.id ? { ...row, ...data.item } : row) },
        } : item));
      }
    }
  }), []);
  const refreshSavedJobs = () => window.desktop?.request<typeof savedJobs>('srt.voice.list').then((jobs)=>setSavedJobs(jobs || [])).catch(()=>undefined);
  useEffect(() => { refreshSavedJobs(); }, []);
  const loadSavedJob = async () => {
    if (!window.desktop || !selectedJobId || running) return;
    try {
      const job = await window.desktop.request<{jobId:string;state:string;engine:VoiceEngine;provider:string;model:string;voiceId:string;subtitleLanguage?:string;workers:number;outputDir:string;entries:{id:number;start:string;end:string;text:string}[];items:SrtVoiceRow[]}>('srt.voice.get',{jobId:selectedJobId});
      setActiveJobId(job.jobId); setJobState(job.state === 'running' || job.state === 'failed' ? 'cancelled' : job.state as typeof jobState); setEngine(liteVoiceEngine(job.engine)); setApiProvider(job.provider || 'minimax'); setApiModel(job.model || 'speech-2.8-hd'); setApiVoiceId(job.voiceId || ''); setSubtitleLanguage(job.subtitleLanguage || 'auto'); setApiWorkers(job.workers || 3);
      setOutputDir(job.outputDir || ''); const byId=new Map((job.items||[]).map((x)=>[x.id,x]));
      setDraft({name:`Job ${job.jobId}`,path:'',rows:(job.entries||[]).map((x)=>({...x,status:'pending',...(byId.get(x.id)||{})}))});
      setProgress({done:(job.items||[]).filter((x)=>x.status==='completed'||x.status==='failed').length,total:(job.entries||[]).length});
      setMessage(`Đã tải job ${job.jobId}. Bấm Tạo tất cả để tiếp tục các file còn thiếu hoặc tạo lại từng câu.`);
    } catch(error){setMessage(error instanceof Error?error.message:String(error));}
  };
  const parseSrtFiles = async (paths: string[], rootFolder?: string) => {
    if (!window.desktop) return [];
    const loaded: SrtQueueItem[] = [];
    for (const filePath of paths) {
      const result = await window.desktop.request<{ path: string; name: string; entries: { id: number; start: string; end: string; source: string }[]; warnings: string[] }>('subtitle.parse', { path: filePath });
      const parsed: SrtDraft = { name: result.name, path: result.path, rows: result.entries.map((row) => ({ id: row.id, start: row.start, end: row.end, text: row.source, status: 'pending' })) };
      const stem = result.name.replace(/\.srt$/i, '').replace(/[<>:"/\\|?*]+/g, '-').trim() || `subtitle-${loaded.length + 1}`;
      const separator = Math.max(result.path.lastIndexOf('\\'), result.path.lastIndexOf('/'));
      const sourceFolder = separator >= 0 ? result.path.slice(0, separator) : '.';
      loaded.push({ id: `${Date.now()}-${loaded.length}`, draft: parsed, status: 'waiting', done: 0, total: parsed.rows.length, outputDir: `${rootFolder || sourceFolder}\\${stem}` });
    }
    return loaded;
  };
  const chooseSrt = async () => {
    const path = await window.desktop?.selectFile({ title: 'Chọn một file SRT', filters: [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (!path) return;
    try {
      const [item] = await parseSrtFiles([path]);
      if (!item) return;
      setQueue([]); setDraft(item.draft); setOutputDir(item.outputDir || ''); setProgress({ done: 0, total: item.total });
      setMessage(`Đã tải ${item.draft.name} · ${item.total} câu. Kết quả tự lưu tại ${item.outputDir}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const chooseSrtFolder = async () => {
    try {
      if (!window.desktop) return;
      const folder = await window.desktop.selectFolder();
      if (!folder) return;
      const selected = await window.desktop.listSrtFiles(folder);
      if (!selected.files.length) return setMessage('Thư mục đã chọn không có file SRT.');
      const loaded = await parseSrtFiles(selected.files, selected.folder);
      setQueue(loaded); setDraft(loaded[0].draft); setOutputDir(loaded[0].outputDir || ''); setProgress({ done: 0, total: loaded[0].total });
      setMessage(`Đã quét ${loaded.length} file SRT. Kết quả sẽ lưu trong thư mục gốc, mỗi file có một thư mục cùng tên.`);
    } catch (error) { setMessage(`Không thể quét thư mục SRT: ${error instanceof Error ? error.message : String(error)}. Hãy đóng và mở lại ứng dụng nếu vừa cập nhật V2.`); }
  };
  const updateText = (id: number, text: string) => setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === id ? { ...row, text, status: row.status === 'completed' ? 'pending' : row.status } : row) } : current);
  const loadApiVoices = async () => {
    if (!window.desktop) return;
    setVoiceLibraryOpen(true); setVoiceLibraryLoading(true); setApiVoices([]);
    try {
      const result = await window.desktop.request<{ voices: ApiVoice[]; total: number }>('tts.voices.list', { engine, provider: apiProvider, language: subtitleLanguage });
      setApiVoices(result.voices);
      if (engine === 'capcut' && result.voices.length) {
        setApiVoiceId((current)=>result.voices.some((voice)=>voice.id===current)?current:result.voices[0].id);
      }
      setMessage(result.total ? `Đã tải ${result.total} giọng từ ${engine === 'ai33' ? 'AI33' : engine === 'aimax' ? 'AIMax' : 'CapCut Space'}.` : 'Không có giọng phù hợp với ngôn ngữ đang chọn.');
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setVoiceLibraryLoading(false); }
  };
  const chooseApiVoice = (voice: ApiVoice) => { setApiVoiceId(voice.id); setVoiceLibraryOpen(false); setMessage(`Đã chọn giọng ${voice.name} · ${voice.id}`); };
  const playApiVoice = async (voice: ApiVoice) => {
    if (!voice.previewUrl) return setMessage('Giọng này không có audio nghe thử.');
    try {
      const url = engine === 'aimax' ? (await window.desktop?.request<{dataUrl:string}>('tts.voice.preview', {engine, url: voice.previewUrl}))?.dataUrl : voice.previewUrl;
      if (!url) throw new Error('Không tải được audio nghe thử.');
      setPreviewUrl(url); setTimeout(() => document.querySelector<HTMLAudioElement>('.api-voice-preview-player')?.play(), 0);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const [autoRetry, setAutoRetry] = useState(() => initialVoicePreset?.autoRetry ?? true);
  const [advancedVoiceOptions, setAdvancedVoiceOptions] = useState(false);
  const saveVoicePreset = () => {
    localStorage.setItem('hhvietsub.voicePreset', JSON.stringify({engine,apiProvider,apiModel,apiVoiceId,apiWorkers,apiRequestInterval,subtitleLanguage,speed,capcutBackend,autoRetry}));
    showToast({kind:'success',title:'Đã lưu preset tạo voice',message:'Cấu hình hiện tại sẽ được dùng lại khi cần.'});
  };
  const restoreVoicePreset = () => {
    try {
      const preset = readVoicePreset();
      if (!preset) return showToast({kind:'info',title:'Chưa có preset đã lưu'});
      if (preset.engine) setEngine(preset.engine);
      if (preset.apiProvider) setApiProvider(preset.apiProvider);
      if (preset.apiModel) setApiModel(preset.apiModel);
      if (typeof preset.apiVoiceId === 'string') setApiVoiceId(preset.apiVoiceId);
      if (preset.apiWorkers) setApiWorkers(preset.apiWorkers);
      if (typeof preset.apiRequestInterval === 'number') setApiRequestInterval(preset.apiRequestInterval);
      if (preset.subtitleLanguage) setSubtitleLanguage(preset.subtitleLanguage);
      if (preset.speed) setSpeed(preset.speed);
      if (preset.capcutBackend) setCapcutBackend(preset.capcutBackend);
      if (typeof preset.autoRetry === 'boolean') setAutoRetry(preset.autoRetry);
      showToast({kind:'success',title:'Đã khôi phục preset'});
    } catch { showToast({kind:'error',title:'Preset không hợp lệ',message:'Hãy lưu lại một preset mới.'}); }
  };
  const runQueue = async () => {
    if (!window.desktop || running || !queue.some((item) => item.status !== 'completed')) return;
    if ((engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && !apiVoiceId.trim()) return setMessage('Hãy chọn giọng của dịch vụ TTS.');
    const scheduled = queue.filter((item) => item.status !== 'completed');
    const baseFolder = scheduled.some((item) => !item.outputDir) ? await window.desktop.selectFolder() : '';
    if (scheduled.some((item) => !item.outputDir) && !baseFolder) return;

    stopQueue.current = false; setQueueRunning(true); setRunning(true);
    for (let index = 0; index < scheduled.length; index += 1) {
      const item = scheduled[index];
      if (stopQueue.current) break;
      const stem = item.draft.name.replace(/\.srt$/i, '').replace(/[<>:"/\\|?*]+/g, '-').trim() || `subtitle-${index + 1}`;
      const destination = item.outputDir || `${baseFolder}\\${stem}`;
      const jobId = `srt-queue-${Date.now()}-${index + 1}`;
      activeQueueId.current = item.id;
      setDraft(item.draft); setOutputDir(destination); setProgress({ done: 0, total: item.total });
      setActiveJobId(jobId); setJobState('running');
      setQueue((current) => current.map((queued) => queued.id === item.id ? { ...queued, status: 'running', done: 0, outputDir: destination, error: undefined } : queued));
      setMessage(`Hàng chờ ${index + 1}/${scheduled.length} · đang tạo ${item.draft.name}`);
      try {
        let result: SrtGenerationResult | undefined;
        const maxPasses = autoRetry ? 3 : 1;
        for (let pass = 1; pass <= maxPasses; pass += 1) {
          result = await window.desktop.request<SrtGenerationResult>('srt.voice.generate', {
            entries: item.draft.rows.filter((row)=>row.text.trim()).map((row) => ({ id: row.id, start: row.start, end: row.end, text: replacePronunciation(row.text) })),
            outputDir: destination, jobId: `${jobId}-pass-${pass}`, engine, apiProvider, apiModel, apiVoiceId: apiVoiceId.trim(), apiWorkers, apiRequestInterval, capcutBackend,
            subtitleLanguage, language: 'vi',
            speed, postprocess: true, denoise: false, skipExisting: true,
          });
          if (result.state === 'cancelled' || result.failed === 0 || pass === maxPasses) break;
          setMessage(`Hàng chờ ${index + 1}/${scheduled.length} · ${item.draft.name} còn ${result.failed} câu lỗi · chạy lại lượt ${pass + 1}/3 sau 3 giây…`);
          await new Promise((resolve)=>setTimeout(resolve,3000));
          if (stopQueue.current) break;
        }
        if (!result) throw new Error('Không nhận được kết quả tạo voice');
        const byId = new Map(result.items.map((row)=>[row.id,row]));
        const updatedDraft = { ...item.draft, rows: item.draft.rows.map((row)=>({ ...row, ...(byId.get(row.id)||{}) })) };
        const status: SrtQueueItem['status'] = result.state === 'cancelled' ? 'cancelled' : result.failed ? 'failed' : 'completed';
        setDraft(updatedDraft); setProgress({ done: result.total, total: result.total });
        setQueue((current) => current.map((queued) => queued.id === item.id ? { ...queued, draft: updatedDraft, status, done: result.total, total: result.total, outputDir: destination, error: result.failed ? `${result.failed} câu lỗi` : undefined } : queued));
        if (result.state === 'cancelled') { stopQueue.current = true; break; }
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        setQueue((current) => current.map((queued) => queued.id === item.id ? { ...queued, status: 'failed', outputDir: destination, error: detail } : queued));
        setMessage(`File ${item.draft.name} lỗi: ${detail}. Đang chuyển file kế tiếp…`);
      }
    }
    activeQueueId.current = ''; setQueueRunning(false); setRunning(false); refreshSavedJobs();
    setMessage(stopQueue.current ? 'Đã dừng hàng chờ. Các file chưa chạy vẫn được giữ lại.' : 'Hàng chờ đã xử lý xong tất cả file.');
  };
  const run = async (only?: SrtVoiceRow, selectedRows?: SrtVoiceRow[], retryPass = 0) => {
    if (!window.desktop || !draft || running) return;
    if ((engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && !apiVoiceId.trim()) return setMessage('Hãy chọn giọng của dịch vụ TTS.');
    let destination = outputDir;
    if (!destination) {
      const stem = draft.name.replace(/\.srt$/i, '').replace(/[<>:"/\\|?*]+/g, '-').trim() || 'subtitle';
      const separator = Math.max(draft.path.lastIndexOf('\\'), draft.path.lastIndexOf('/'));
      if (separator < 0) return setMessage('Không xác định được thư mục của file SRT.');
      destination = `${draft.path.slice(0, separator)}\\${stem}`; setOutputDir(destination);
    }
    const entries = selectedRows || (only ? [only] : draft.rows.filter((row) => row.text.trim()));
    const jobId = `srt-${Date.now()}`; setActiveJobId(jobId); setJobState('running');
    setRunning(true); setProgress({ done: 0, total: entries.length });
    if (retryPass === 0) showToast({kind:'info',title:'Đã bắt đầu tạo voice',message:`${entries.length} câu · ${draft.name}`});
    setDraft((current) => current ? { ...current, rows: current.rows.map((row) => entries.some((e) => e.id === row.id) ? { ...row, status: 'pending' as const, error: undefined } : row) } : current);
    try {
      const result = await window.desktop.request<{ state: 'cancelled'|'completed'; completed: number; failed: number; total: number; items: SrtVoiceRow[]; outputDir: string }>(only ? 'srt.voice.regenerate' : 'srt.voice.generate', {
        entries: entries.map((row) => ({ id: row.id, start: row.start, end: row.end, text: replacePronunciation(row.text) })), outputDir: destination,
        jobId, engine, apiProvider, apiModel, apiVoiceId: apiVoiceId.trim(), apiWorkers, apiRequestInterval, capcutBackend, subtitleLanguage, language: 'vi', speed, postprocess: true, denoise: false, skipExisting: !only && !selectedRows,
      });
      let updatedRows = draft.rows;
      setDraft((current) => {
        if (!current) return current;
        updatedRows = current.rows.map((row) => { const matched = result.items.find((item) => item.id === row.id); return matched ? { ...row, ...matched } : row; });
        return { ...current, rows: updatedRows };
      });
      setJobState(result.state === 'cancelled' ? 'cancelled' : 'completed');
      const failedItems = updatedRows.filter((r) => r.status === 'failed');
      if (autoRetry && result.state !== 'cancelled' && failedItems.length > 0 && retryPass < 2) {
        setMessage(`Lượt ${retryPass + 1} xong. Phát hiện ${failedItems.length} câu lỗi. Đang tự động chạy lại lượt ${retryPass + 2}/3 sau 3 giây…`);
        setRunning(false);
        await new Promise((res) => setTimeout(res, 3000));
        return run(undefined, failedItems, retryPass + 1);
      }
      setMessage(`${result.state === 'cancelled' ? 'Đã huỷ' : 'Hoàn tất'} ${result.completed}/${result.total} câu${result.failed ? ` · ${result.failed} câu lỗi` : ''}.`);
      if (result.state !== 'cancelled') showToast(result.failed ? {kind:'error',title:'Job hoàn tất nhưng còn lỗi',message:`${result.failed}/${result.total} câu cần chạy lại.`} : {kind:'success',title:'Tạo voice hoàn tất',message:`Đã tạo ${result.completed}/${result.total} câu.`});
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setMessage(detail); setJobState('cancelled');
      showToast({kind:'error',title:'Tạo voice thất bại',message:detail});
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.status === 'generating' ? { ...row, status: 'failed' as const, error: detail } : row) } : current);
    }
    finally { setRunning(false); refreshSavedJobs(); }
  };
  const controlJob = async (action:'pause'|'resume'|'cancel') => { if(!activeJobId || !window.desktop) return; if(action==='cancel' && queueRunning) stopQueue.current=true; try { const r=await window.desktop.request<{state:typeof jobState}>('srt.voice.control',{jobId:activeJobId,action}); setJobState(r.state); setMessage(action==='pause'?'Đã tạm dừng gửi câu mới. Các request đang chạy vẫn hoàn tất an toàn.':action==='resume'?'Đang tiếp tục job…':'Đã yêu cầu huỷ job và dừng hàng chờ.'); } catch(error){ setMessage(error instanceof Error?error.message:String(error)); } };
  const play = async (row: SrtVoiceRow) => { if (!row.file) return; const url = await window.desktop?.readAudio(row.file); if (url) { setAudioUrl(url); setTimeout(() => document.querySelector<HTMLAudioElement>('.srt-voice-player')?.play(), 0); } };
  const completed = draft?.rows.filter((row) => row.status === 'completed').length || 0;
  const failed = draft?.rows.filter((row) => row.status === 'failed').length || 0;
  const longCueCount = draft?.rows.filter((row) => row.text.trim().length > 300).length || 0;
  const invalidTimestampCount = draft?.rows.filter((row) => {
    const start = subtitleTimeMs(row.start); const end = subtitleTimeMs(row.end);
    return !Number.isFinite(start) || !Number.isFinite(end) || end <= start;
  }).length || 0;
  return <div className="srt-voice-page">
    <div className="srt-voice-hero"><div><h1>Tạo giọng từ <span>file hoặc thư mục SRT.</span></h1><p>Chọn nguồn, giọng đọc rồi theo dõi toàn bộ hàng chờ ở một màn hình.</p></div></div>
    <section className="srt-output-bar"><div><FolderOpen size={17}/><span><small>JOB ĐÃ LƯU · KHÔNG TỰ ĐỘNG TẢI</small><select value={selectedJobId} onChange={(e)=>setSelectedJobId(e.target.value)}><option value="">Chọn job muốn mở…</option>{savedJobs.map((job)=><option key={job.jobId} value={job.jobId}>{job.createdAt || job.jobId} · {job.engine} · {job.voiceId || 'chưa chọn giọng'} · {job.completed}/{job.total}{job.failed?` · ${job.failed} lỗi`:''}</option>)}</select></span></div><button disabled={!selectedJobId||running} onClick={loadSavedJob}>Tải job</button><button disabled={running} onClick={()=>{setSelectedJobId('');setDraft(null);setOutputDir('');setProgress({done:0,total:0});setJobState('idle');setMessage('Đã tạo phiên trống. Hãy chọn file SRT mới.');}}>Job mới</button></section>
    {queue.length>0&&<section className="srt-queue-panel"><header><div><strong>HÀNG CHỜ TẠO VOICE</strong><small>{queue.filter((item)=>item.status==='completed').length}/{queue.length} file hoàn thành</small></div><button disabled={running} onClick={()=>setQueue((current)=>current.filter((item)=>item.status!=='completed'))}>Dọn file đã xong</button><button disabled={running} onClick={()=>{setQueue([]);setMessage('Đã xóa hàng chờ.');}}>Xóa hàng chờ</button></header><div className="srt-queue-list">{queue.map((item,index)=><article key={item.id} className={item.status} onClick={()=>{if(running)return;setDraft(item.draft);setOutputDir(item.outputDir||'');setProgress({done:item.done,total:item.total});}}><b>{index+1}</b><div><strong>{item.draft.name}</strong><small>{item.done}/{item.total} câu{item.error?` · ${item.error}`:''}</small></div><span>{item.status==='waiting'?'Đang chờ':item.status==='running'?'Đang tạo':item.status==='completed'?'Hoàn thành':item.status==='cancelled'?'Đã dừng':'Có lỗi'}</span><button disabled={running} title="Xóa khỏi hàng chờ" onClick={(event)=>{event.stopPropagation();setQueue((current)=>current.filter((queued)=>queued.id!==item.id));}}><X size={14}/></button></article>)}</div></section>}
    {engine==='capcut'&&<section className="capcut-voice-tools"><label><small>NGUỒN CAPCUT TTS</small><select value={capcutBackend} onChange={(e)=>setCapcutBackend(e.target.value as typeof capcutBackend)}><option value="hybrid">Kết hợp nội bộ + Space (nhanh nhất)</option><option value="direct">Chỉ backend nội bộ</option><option value="space">Chỉ Hugging Face Space</option></select><span>{capcutBackend==='hybrid'?'Chia câu chẵn/lẻ cho hai nguồn; mỗi nguồn cách request 10 giây.':capcutBackend==='direct'?'Gọi trực tiếp CapCut API.':'Dùng tony2k/ai-voice-studio như trước.'}</span></label><button type="button" onClick={()=>setDictionaryOpen(true)}><FileText size={15}/> Từ điển phát âm <b>{pronunciationDictionary.length}</b></button></section>}
    <div className="saved-job-compact"><button type="button" disabled={running} onClick={()=>setJobPickerOpen(true)}><FolderOpen size={15}/> Job đã lưu <b>{savedJobs.length}</b></button></div>
    <section className="lite-engine-switch">
      <div>
        <small>DỊCH VỤ TẠO GIỌNG</small>
        <button className={engine==='capcut'?'active':''} onClick={()=>{setEngine('capcut');setApiVoiceId('');setApiVoices([]);}}>CapCut TTS</button>
        <button className={engine==='ai33'?'active':''} onClick={()=>{setEngine('ai33');setApiVoiceId('');setApiVoices([]);}}>AI33 API</button>
        <button className={engine==='aimax'?'active':''} onClick={()=>{setEngine('aimax');setApiVoiceId('');setApiVoices([]);}}>AIMax API</button>
      </div>
      <div className="lite-engine-actions">
      <button type="button" onClick={()=>setJobPickerOpen(true)}>
        <FolderOpen size={15}/> Job đã lưu
        <b>{savedJobs.length}</b>
      </button>
      </div>
    </section>
    <section className="srt-voice-config">
      <label className={`srt-input-card ${running?'disabled':''}`} role="button" tabIndex={running?-1:0} onClick={()=>{if(!running)void chooseSrt();}} onKeyDown={(event)=>{if(!running&&(event.key==='Enter'||event.key===' ')){event.preventDefault();void chooseSrt();}}}><small>FILE ĐẦU VÀO · BẤM ĐỂ CHỌN</small><strong>{draft?.name || 'Chưa chọn SRT'}</strong><span>{draft ? `${draft.rows.length} câu phụ đề · bấm để đổi file` : 'Chọn một file SRT từ máy'}</span></label>
      <button className="srt-folder-input" type="button" disabled={running} onClick={chooseSrtFolder}><small>THƯ MỤC ĐẦU VÀO</small><strong>Chọn thư mục SRT</strong><span>Quét toàn bộ file và tạo hàng chờ</span></button>
      {engine === 'capcut' ? <><label className={!apiVoiceId?'voice-required':''}><small>GIỌNG CAPCUT SPACE</small><div className="voice-id-picker"><input value={apiVoices.find((voice)=>voice.id===apiVoiceId)?.name||''} readOnly placeholder={voiceLibraryLoading?'Đang tải thư viện giọng…':'Chưa chọn giọng'}/><button type="button" onClick={loadApiVoices}><Search size={14}/> Thư viện</button></div><span>{apiVoiceId?'Đã sẵn sàng tạo voice':'Bắt buộc chọn giọng trước khi chạy'}</span></label><label className="legacy-service-card"><small>DỊCH VỤ</small><strong>tony2k · AI Voice Studio</strong><span>CapCut TTS từ Hugging Face Space · không cần API key</span></label></> : <><label><small>VOICE ID</small><div className="voice-id-picker"><input value={apiVoiceId} onChange={(e) => setApiVoiceId(e.target.value)} placeholder="Chọn trong thư viện hoặc nhập ID"/><button type="button" onClick={loadApiVoices}><Search size={14}/> Thư viện</button></div></label><label><small>NHÀ CUNG CẤP {engine === 'aimax' ? '/ MODEL' : ''}</small><div className="inline-numbers"><select value={apiProvider} onChange={(e) => { const p=e.target.value; setApiProvider(p); setApiVoices([]); setApiModel(p === 'minimax' ? 'speech-2.8-hd' : 'eleven_multilingual_v2'); }}><option value="minimax">MiniMax</option><option value="elevenlabs">ElevenLabs</option>{engine === 'ai33' && <><option value="edge">Edge</option><option value="kokoro">Kokoro</option><option value="vbee">Vbee</option><option value="fishaudio">Fish Audio</option><option value="clone">Giọng clone</option></>}</select>{engine === 'aimax' && <select value={apiModel} onChange={(e) => setApiModel(e.target.value)}>{apiProvider === 'minimax' ? <><option value="speech-2.8-hd">2.8 HD</option><option value="speech-2.8-turbo">2.8 Turbo</option><option value="speech-2.6-hd">2.6 HD</option><option value="speech-2.6-turbo">2.6 Turbo</option><option value="speech-02-hd">02 HD</option><option value="speech-02-turbo">02 Turbo</option></> : <><option value="eleven_v3">Eleven v3</option><option value="eleven_multilingual_v2">Multilingual v2</option><option value="eleven_flash_v2_5">Flash v2.5</option><option value="eleven_turbo_v2_5">Turbo v2.5</option></>}</select>}</div></label></>}
      <label><small>TỐC ĐỘ · {speed.toFixed(2)}×</small><input type="range" min="0.6" max="1.5" step="0.05" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /></label>
      { <label><small>NGÔN NGỮ PHỤ ĐỀ</small><select value={subtitleLanguage} onChange={(e)=>{setSubtitleLanguage(e.target.value);setApiVoices([]);setApiVoiceId('');}}><option value="auto">Tự động nhận diện</option><option value="Vietnamese">Tiếng Việt</option><option value="English">Tiếng Anh</option><option value="Spanish">Tiếng Tây Ban Nha</option><option value="French">Tiếng Pháp</option><option value="German">Tiếng Đức</option><option value="Portuguese">Tiếng Bồ Đào Nha</option><option value="Italian">Tiếng Ý</option><option value="Japanese">Tiếng Nhật</option><option value="Korean">Tiếng Hàn</option><option value="Chinese">Tiếng Trung</option><option value="Thai">Tiếng Thái</option><option value="Indonesian">Tiếng Indonesia</option><option value="Russian">Tiếng Nga</option><option value="Arabic">Tiếng Ả Rập</option></select><span>Dùng để lọc giọng và tạo đúng phát âm</span></label>}
      <button className="srt-advanced-toggle" type="button" aria-expanded={advancedVoiceOptions} onClick={()=>setAdvancedVoiceOptions((current)=>!current)}><Settings2 size={15}/><span><strong>Tùy chọn nâng cao</strong><small>Luồng API, delay, retry và từ điển</small></span><ChevronDown size={16} className={advancedVoiceOptions?'rotated':''}/></button>
      {advancedVoiceOptions&&<>
      <div className="voice-preset-actions"><button type="button" onClick={saveVoicePreset}><Download size={14}/> Lưu preset</button><button type="button" onClick={restoreVoicePreset}><RefreshCw size={14}/> Khôi phục</button><button type="button" onClick={()=>{setApiSettingsOpen(true);void loadApiKeyStatus();}}><Settings2 size={14}/> API key <b>{apiKeyStatus.ai33KeyCount + apiKeyStatus.aimaxKeyCount}</b></button></div>
      {(engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && <label><small>SỐ LUỒNG API</small><input type="number" min="1" max="32" value={apiWorkers} onChange={(e)=>setApiWorkers(Math.min(32,Math.max(1,Number(e.target.value)||1)))}/><span>Tối đa request đang xử lý song song</span></label>}
      {(engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && <label><small>DELAY GỬI API · GIÂY</small><input type="number" min="0" max="60" step="0.5" value={apiRequestInterval} onChange={(e)=>{const value=Math.min(60,Math.max(0,Number(e.target.value)||0));setApiRequestInterval(value);localStorage.setItem('hhvietsub.apiRequestInterval',String(value));}}/><span>Khoảng cách giữa hai request: {apiRequestInterval}s{engine==='capcut'&&capcutBackend==='hybrid'?' trên mỗi nguồn':''}</span></label>}
      <label><small>TỰ ĐỘNG RETRY LỖI</small><button type="button" onClick={() => setAutoRetry(!autoRetry)} style={{ border: autoRetry ? '1px solid #7edab7' : '1px solid #dfe3f0', borderRadius: 8, padding: '7px 8px', fontSize: 10, fontWeight: 700, cursor: 'pointer', background: autoRetry ? '#ecfbf5' : '#f4f5fa', color: autoRetry ? '#178360' : '#778198', display: 'flex', alignItems: 'center', gap: 5 }}>{autoRetry ? <><RefreshCw size={12} /> Bật (Tối đa 3 lượt)</> : 'Tắt'}</button></label>
      {engine==='capcut'&&<label className="capcut-source-card"><small>NGUỒN CAPCUT TTS</small><select value={capcutBackend} onChange={(e)=>setCapcutBackend(e.target.value as typeof capcutBackend)}><option value="hybrid">Kết Hợp</option><option value="direct">Nội Bộ</option><option value="space">Space</option></select><span>{capcutBackend==='hybrid'?'Chia tải cho hai nguồn để tạo nhanh hơn.':capcutBackend==='direct'?'Gọi trực tiếp CapCut API nội bộ.':'Dùng tony2k/ai-voice-studio.'}</span></label>}
      {engine==='capcut'&&<label className="dictionary-config-card"><small>TỪ ĐIỂN PHÁT ÂM</small><button type="button" onClick={()=>setDictionaryOpen(true)}><FileText size={15}/><span>Mở từ điển</span><b>{pronunciationDictionary.length}</b></button><span>Tự động sửa cách đọc trước khi tạo MP3.</span></label>}
      </>}
    </section>
    <section className="srt-sticky-actions">
      {running && <>{jobState==='paused'?<button className="job-resume" onClick={()=>controlJob('resume')}><Play size={16}/> Tiếp tục</button>:<button className="job-pause" onClick={()=>controlJob('pause')}><Pause size={16}/> Tạm dừng</button>}<button className="job-cancel" onClick={()=>controlJob('cancel')}><Square size={15}/> Dừng / Huỷ</button></>}
      {!running && failed>0 && <button className="job-retry" onClick={()=>run(undefined,draft!.rows.filter((x)=>x.status==='failed'))}><RefreshCw size={15}/> Chạy lại {failed} lỗi</button>}
      {queue.length>0&&<button className="queue-run" disabled={running||!queue.some((item)=>item.status!=='completed')||(engine==='capcut'&&!apiVoiceId)} onClick={runQueue}><Play size={16}/> Hàng chờ ({queue.filter((item)=>item.status!=='completed').length})</button>}
      <button className="primary" disabled={!draft?.rows.length || running || (engine==='capcut'&&!apiVoiceId)} title={engine==='capcut'&&!apiVoiceId?'Đang chờ tải và chọn giọng CapCut':''} onClick={() => run()}>{running ? <><RefreshCw className="spin" size={17} /> {jobState==='paused'?'Đã tạm dừng':`Đang tạo ${progress.done}/${progress.total}`}</> : engine==='capcut'&&!apiVoiceId ? <><RefreshCw className={voiceLibraryLoading?'spin':''} size={17}/> {voiceLibraryLoading?'Đang tải giọng…':'Chọn giọng trước'}</> : <><Play size={17} /> {jobState==='cancelled'?'Tiếp tục phần còn lại':'Tạo voice'}</>}</button>
    </section>
    {voiceLibraryOpen && <section className="api-voice-library"><header><div><strong>Thư viện giọng {engine === 'ai33' ? 'AI33' : engine === 'aimax' ? 'AIMax' : 'CapCut Space'}</strong><small>{engine === 'capcut' ? 'tony2k/ai-voice-studio' : apiProvider} · {apiVoices.length} giọng</small></div><div className="api-voice-search"><Search size={14}/><input value={voiceQuery} onChange={(e)=>setVoiceQuery(e.target.value)} placeholder="Tìm tên hoặc Voice ID"/></div><button onClick={()=>setVoiceLibraryOpen(false)}><X size={16}/></button></header><div className="api-voice-list">{voiceLibraryLoading ? <div className="api-voice-empty"><RefreshCw className="spin"/> Đang tải thư viện…</div> : apiVoices.filter((v)=>`${v.name} ${v.id}`.toLowerCase().includes(voiceQuery.toLowerCase())).map((voice)=><article key={voice.id} className={apiVoiceId === voice.id ? 'selected' : ''}><div className="api-voice-avatar">{voice.name.slice(0,2).toUpperCase()}</div><div><strong>{voice.name}</strong><small>{voice.language || 'Không rõ ngôn ngữ'} · {voice.id}</small></div><button disabled={!voice.previewUrl} onClick={()=>playApiVoice(voice)} title="Nghe thử"><Play size={14}/></button><button className="choose" onClick={()=>chooseApiVoice(voice)}>Chọn</button></article>)}{!voiceLibraryLoading && !apiVoices.length && <div className="api-voice-empty">Không tìm thấy giọng phù hợp hoặc dịch vụ đang tạm ngủ. Hãy thử lại sau.</div>}</div></section>}
    <div className="srt-run-stats"><span>{draft?.rows.length || 0} câu</span><span className="ok">{completed} hoàn thành</span><span className={failed ? 'bad' : ''}>{failed} lỗi</span>{longCueCount>0&&<span className="warn">{longCueCount} câu quá dài</span>}{invalidTimestampCount>0&&<span className="bad">{invalidTimestampCount} timestamp lỗi</span>}<div><i style={{ width: `${progress.total ? progress.done / progress.total * 100 : 0}%` }} /></div></div>
    <section className="srt-voice-table"><header><span># / THỜI GIAN</span><span>NỘI DUNG ĐỌC</span><span>TRẠNG THÁI</span><span>THAO TÁC</span></header>{draft?.rows.length ? draft.rows.map((row) => <article key={row.id}><div><b>{String(row.id).padStart(4, '0')}</b><small>{row.start} → {row.end}</small></div><textarea value={row.text} disabled={running} onChange={(e) => updateText(row.id, e.target.value)} /><div className={`voice-row-status ${row.status}`}><strong>{row.status === 'completed' ? 'Hoàn thành' : row.status === 'failed' ? 'Lỗi' : row.status === 'generating' ? 'Đang tạo' : 'Chờ'}</strong><small>{row.duration ? `${row.duration.toFixed(2)} giây` : row.error || `${String(row.id).padStart(4, '0')}.wav`}</small></div><div className="voice-row-actions"><button disabled={!row.file} onClick={() => play(row)} title="Nghe"><Play size={15} /></button><button disabled={running || !row.text.trim()} onClick={() => run(row)} title="Tạo lại"><RefreshCw size={15} /></button></div></article>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>Chưa có dữ liệu SRT</strong><small>Chọn file SRT ở panel bên trái hoặc quét cả thư mục để tạo hàng chờ.</small></div>}</section>
    {dictionaryOpen&&<div className="dictionary-backdrop" onMouseDown={(e)=>{if(e.target===e.currentTarget)setDictionaryOpen(false)}}><section className="dictionary-modal"><header><div><strong>Từ điển phát âm CapCut</strong><small>Thay từ sai hoặc tiếng Anh bằng cách viết để TTS đọc đúng trước khi tạo MP3.</small></div><button onClick={()=>setDictionaryOpen(false)}><X size={18}/></button></header><div className="dictionary-actions"><button onClick={()=>saveDictionary([...pronunciationDictionary,{id:`dict-${Date.now()}`,source:'',target:''}])}>+ Thêm từ</button><button onClick={()=>dictionaryImportRef.current?.click()}><UploadCloud size={14}/> Nhập JSON</button><button onClick={exportDictionary}><Download size={14}/> Xuất JSON</button><button className="apply" onClick={applyDictionaryToDraft}><Check size={14}/> Áp dụng vào SRT</button><input ref={dictionaryImportRef} type="file" accept=".json,application/json" hidden onChange={(e)=>{void importDictionary(e.target.files?.[0]);e.currentTarget.value=''}}/></div><div className="dictionary-head"><span>TỪ GỐC / TIẾNG ANH</span><span>CÁCH VIẾT ĐỂ ĐỌC</span><span/></div><div className="dictionary-list">{pronunciationDictionary.map((item)=><article key={item.id}><input value={item.source} onChange={(e)=>saveDictionary(pronunciationDictionary.map((row)=>row.id===item.id?{...row,source:e.target.value}:row))} placeholder="Ví dụ: Facebook"/><input value={item.target} onChange={(e)=>saveDictionary(pronunciationDictionary.map((row)=>row.id===item.id?{...row,target:e.target.value}:row))} placeholder="Ví dụ: phây búc"/><button title="Xóa" onClick={()=>saveDictionary(pronunciationDictionary.filter((row)=>row.id!==item.id))}><Trash2 size={15}/></button></article>)}{!pronunciationDictionary.length&&<div className="dictionary-empty">Chưa có quy tắc. Bấm “Thêm từ” hoặc nhập file JSON.</div>}</div><footer><span>{pronunciationDictionary.length} quy tắc · tự động áp dụng khi tạo voice</span><button onClick={()=>setDictionaryOpen(false)}>Đóng</button></footer></section></div>}
    {jobPickerOpen&&<div className="dictionary-backdrop" onMouseDown={(e)=>{if(e.target===e.currentTarget)setJobPickerOpen(false)}}><section className="saved-job-modal"><header><div><strong>Mở job tạo voice đã lưu</strong><small>Chỉ tải job khi bạn chủ động chọn.</small></div><button onClick={()=>setJobPickerOpen(false)}><X size={18}/></button></header><div className="saved-job-picker"><select value={selectedJobId} onChange={(e)=>setSelectedJobId(e.target.value)}><option value="">Chọn job muốn mở…</option>{savedJobs.map((job)=><option key={job.jobId} value={job.jobId}>{job.createdAt||job.jobId} · {job.engine} · {job.completed}/{job.total}{job.failed?` · ${job.failed} lỗi`:''}</option>)}</select>{!savedJobs.length&&<p>Chưa có job nào được lưu.</p>}</div><footer><button onClick={()=>{setSelectedJobId('');setDraft(null);setOutputDir('');setProgress({done:0,total:0});setJobState('idle');setJobPickerOpen(false);setMessage('Đã tạo phiên trống. Hãy chọn file SRT mới.');}}>Job mới</button><button className="primary" disabled={!selectedJobId} onClick={async()=>{await loadSavedJob();setJobPickerOpen(false)}}>Tải job đã chọn</button></footer></section></div>}
    {audioUrl && <audio className="srt-voice-player" src={audioUrl} controls />}{previewUrl && <audio className="api-voice-preview-player" src={previewUrl} controls />}
    {apiSettingsOpen&&<div className="dictionary-backdrop" onMouseDown={(e)=>{if(e.target===e.currentTarget)setApiSettingsOpen(false)}}><section className="dictionary-modal api-key-modal"><header><div><strong>Cấu hình API tạo giọng</strong><small>Key được mã hóa bằng Windows Safe Storage và không ghi dạng rõ vào file cấu hình.</small></div><button onClick={()=>setApiSettingsOpen(false)}><X size={18}/></button></header><div className="lite-api-key-grid"><label><span>AI33 API key · {apiKeyStatus.ai33KeyCount} key đã lưu</span><textarea value={ai33Key} onChange={(e)=>setAi33Key(e.target.value)} placeholder="Mỗi key một dòng. Để trống nếu không thay đổi."/><button disabled={apiKeyBusy} onClick={()=>void testApiKey('ai33')}>Kiểm tra AI33</button></label><label><span>AIMax API key · {apiKeyStatus.aimaxKeyCount} key đã lưu</span><textarea value={aimaxKey} onChange={(e)=>setAimaxKey(e.target.value)} placeholder="Mỗi key một dòng. Để trống nếu không thay đổi."/><button disabled={apiKeyBusy} onClick={()=>void testApiKey('aimax')}>Kiểm tra AIMax</button></label></div><footer><button onClick={()=>setApiSettingsOpen(false)}>Đóng</button><button className="primary" disabled={apiKeyBusy||(!ai33Key.trim()&&!aimaxKey.trim())} onClick={()=>void saveApiKeys()}>{apiKeyBusy?'Đang xử lý…':'Lưu API key'}</button></footer></section></div>}
  </div>;
}

function SyncProgressBar({ progress, steps, running, complete, error }: {
  progress: number;
  steps: [string, string, string, string];
  running: boolean;
  complete: boolean;
  error: boolean;
}) {
  const safeProgress = Math.min(100, Math.max(0, progress));
  const stepIndex = safeProgress === 0 ? 0 : Math.min(3, Math.max(0, Math.ceil(safeProgress / 25) - 1));
  const label = error
    ? `Lỗi ở bước ${steps[stepIndex]}`
    : complete
      ? 'Hoàn tất'
      : running
        ? `Bước ${stepIndex + 1}/4 · ${steps[stepIndex]}`
        : 'Sẵn sàng';
  return <section className={`sync-progress ${complete ? 'complete' : ''} ${error ? 'error' : ''}`}>
    <div className="sync-progress-label"><strong>{label}</strong><span>{Math.round(safeProgress)}%</span></div>
    <div className="sync-progress-track"><i style={{ width: `${safeProgress}%` }} /></div>
  </section>;
}

function SyncInputRow({ number, icon, label, description, value, onClick, children }: {
  number: number;
  icon: ReactNode;
  label: string;
  description: string;
  value?: string;
  onClick?: () => void;
  children?: ReactNode;
}) {
  const content = <>
    <span className="sync-input-number">{number}</span>
    <span className="sync-input-icon">{icon}</span>
    <span className="sync-input-copy"><small>{label}</small>{children || <strong>{description}</strong>}<em>{value || description}</em></span>
    <span className={`sync-input-badge ${value ? 'selected' : ''}`}>{value ? fileNameFromPath(value) : 'Chưa chọn'}</span>
  </>;
  return onClick
    ? <button type="button" className="sync-input-row" onClick={onClick}>{content}</button>
    : <div className="sync-input-row">{content}</div>;
}

const fileNameFromPath = (value: string) => value.split(/[\\/]/).at(-1) || value;

function FfmpegAndCapCutTab() {
  const { showToast } = useToast();
  const [videoPath, setVideoPath] = useState('');
  const [srtPath, setSrtPath] = useState('');
  const [voiceDir, setVoiceDir] = useState('');
  const [outputDir, setOutputDir] = useState('');
  const [encoder, setEncoder] = useState('auto');
  const [renderProfile, setRenderProfile] = useState<'weak'|'balanced'|'fast'>('weak');
  const [voiceSpeed, setVoiceSpeed] = useState(1.0);
  const [changePitch, setChangePitch] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressError, setProgressError] = useState(false);
  const [jobName, setJobName] = useState(`FFmpeg Sync ${new Date().toLocaleDateString('vi-VN').replaceAll('/', '-')}`);
  const [analysis, setAnalysis] = useState<{subtitles:number;voiceFiles:number;missing:number[];ready:boolean;ffmpegReady:boolean;rawVoiceDuration?:number;totalVoiceDuration?:number}|null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn video, SRT, thư mục voice và nơi xuất kết quả.');
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<{projectName:string;projectPath:string;template:string}|null>(null);
  const fileName = (value:string) => value.split(/[\\/]/).at(-1) || '';
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const event = raw as {event?:string;data?:{message?:string}};
    if (event.event === 'ffmpeg.sync.progress' && event.data?.message) {
      const rawMsg = event.data.message;
      try {
        const parsed = JSON.parse(rawMsg);
        if (parsed.percent !== undefined) {
          setProgressPercent(parsed.percent);
          if (parsed.message) {
            setMessage(parsed.message);
            setLogs((current) => [...current.slice(-99), parsed.message]);
          }
          return;
        }
      } catch { /* text log */ }
      setLogs((current) => [...current.slice(-99), rawMsg]);
      setMessage(rawMsg);
    }
  }), []);
  useEffect(() => {
    setAnalysis(null); setResult(null); setProgressError(false);
    if (!videoPath || !srtPath || !voiceDir || !window.desktop) return;
    window.desktop.request<typeof analysis>('ffmpeg.sync.validate',{videoPath,srtPath,voiceDir,voiceSpeed}).then((value)=>{
      setAnalysis(value);
      setMessage(!value?.ffmpegReady ? 'Chưa có FFmpeg. Hãy cài Gyan.FFmpeg bằng winget.' : value.ready ? `Sẵn sàng: ${value.subtitles} phụ đề ↔ ${value.voiceFiles} voice (Tổng ${value.totalVoiceDuration?.toFixed(1)}s).` : `Thiếu ${value?.missing.length||0} file voice (câu bị thiếu: ${value?.missing.slice(0, 8).join(', ')}${(value?.missing.length||0) > 8 ? '…' : ''}). Hãy bổ sung file voice tương ứng.`);
    }).catch((error)=>setMessage(error instanceof Error?error.message:String(error)));
  },[videoPath,srtPath,voiceDir,voiceSpeed]);
  const pickFile = async (kind:'video'|'srt') => {
    const path=await window.desktop?.selectFile({filters:kind==='video'?[{name:'Video',extensions:['mp4','mov','mkv','avi','m4v','webm']}]:[{name:'SRT',extensions:['srt']}]});
    if(path) {
      if (kind==='video') {
        setVideoPath(path);
        if (!outputDir) {
          const folder = path.substring(0, Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/')));
          if (folder) setOutputDir(`${folder}\\output`);
        }
      } else {
        setSrtPath(path);
      }
    }
  };
  const pickFolder = async (kind:'voice'|'output') => {
    const path=await window.desktop?.selectFolder();
    if(path) {
      if (kind==='voice') {
        setVoiceDir(path);
        if (!outputDir) setOutputDir(`${path}_sync_output`);
      } else {
        setOutputDir(path);
      }
    }
  };
  const create = async () => {
    if(!window.desktop||!analysis?.ready||!outputDir||running)return;
    setRunning(true);setLogs([]);setResult(null);setProgressPercent(0);setProgressError(false);setMessage('Đang lập kế hoạch đồng bộ…');
    showToast({kind:'info',title:'Đã bắt đầu đồng bộ',message:'FFmpeg đang chuẩn bị và kiểm tra các đoạn video.'});
    const profileEncoder = renderProfile === 'weak' ? 'x264' : encoder;
    const chunkPieces = renderProfile === 'weak' ? 6 : renderProfile === 'balanced' ? 12 : 24;
    try { const value=await window.desktop.request<{projectName:string;projectPath:string;template:string}>('ffmpeg.sync.create',{videoPath,srtPath,voiceDir,outputDir,projectName:jobName,chunkPieces,encoder:profileEncoder,voiceSpeed,changePitch,videoVolumeDb:-35,mergeAudio:false,renderProfile}); setResult(value);setProgressPercent(100);setMessage(`Hoàn tất: ${value.projectName}`);showToast({kind:'success',title:'Đồng bộ hoàn tất',message:value.projectName}); }
    catch(error){const detail=error instanceof Error?error.message:String(error);setProgressError(true);setMessage(detail);showToast({kind:'error',title:'Đồng bộ thất bại',message:detail});} finally{setRunning(false);}
  };
  return <div className="capcut-project-page" style={{ paddingTop: '10px' }}>
    <div className="capcut-project-hero"><div><h1>Co giãn video theo <span>voice nguyên bản.</span></h1><p>Xuất video đồng bộ độc lập; không ghép audio và không cần mở CapCut.</p></div></div>
    <div className="sync-workspace-grid">
      <section className="sync-input-panel">
        <header><strong>Đầu vào</strong><small>Chọn đủ 4 mục để kiểm tra và đồng bộ.</small></header>
        <div className="sync-input-list">
          <SyncInputRow number={1} icon={<Clapperboard size={20}/>} label="VIDEO GỐC" description="Chọn video" value={videoPath} onClick={()=>pickFile('video')}/>
          <SyncInputRow number={2} icon={<Captions size={20}/>} label="PHỤ ĐỀ SRT" description="Chọn file SRT" value={srtPath} onClick={()=>pickFile('srt')}/>
          <SyncInputRow number={3} icon={<AudioLines size={20}/>} label="THƯ MỤC VOICE" description="Chọn thư mục voice" value={voiceDir} onClick={()=>pickFolder('voice')}/>
          <SyncInputRow number={4} icon={<FolderOpen size={20}/>} label="THƯ MỤC XUẤT" description="Chọn thư mục xuất" value={outputDir} onClick={()=>pickFolder('output')}/>
        </div>
      </section>
      <section className="sync-right-column">
    <div className="capcut-settings-row">
      <div className="capcut-panel-card">
        <div className="panel-card-title"><Sliders size={15}/> <span>TÙY CHỈNH ÂM THÀNH</span></div>
        <div className="panel-card-grid-3">
          <label className="speed-control-box">
            <div className="speed-header">
              <small>TỐC ĐỘ (SPEED)</small>
              <span className="speed-badge">{voiceSpeed.toFixed(2)}x</span>
            </div>
            <input type="range" min="0.5" max="2.0" step="0.05" value={voiceSpeed} onChange={(e)=>setVoiceSpeed(Number(e.target.value))} />
            <div className="duration-preview">
              <small>THỜI LƯỢNG VOICE</small>
              <span>{analysis?.rawVoiceDuration != null ? `${analysis.rawVoiceDuration.toFixed(1)}s` : '--'} → <strong>{(analysis?.totalVoiceDuration ?? (analysis?.rawVoiceDuration ? analysis.rawVoiceDuration / voiceSpeed : 0)).toFixed(1)}s</strong></span>
            </div>
          </label>

          <label className="pitch-toggle-box">
            <div className="pitch-header">
              <small>CAO ĐỘ (PITCH)</small>
            </div>
            <div className="pitch-switch-row" style={{ marginTop: '6px' }}>
              <input type="checkbox" checked={changePitch} onChange={(e)=>setChangePitch(e.target.checked)} />
            </div>
          </label>

        </div>
      </div>

      <div className="capcut-panel-card">
        <div className="panel-card-title"><Zap size={15}/> <span>CẤU HÌNH XUẤT</span></div>
        <label><small>CẤU HÌNH THEO MÁY</small><select value={renderProfile} onChange={(e)=>setRenderProfile(e.target.value as typeof renderProfile)}><option value="weak">Máy yếu · CPU 4 luồng · ít RAM</option><option value="balanced">Cân bằng · GPU tự động</option><option value="fast">Máy mạnh · GPU · cache lớn</option></select></label>
        <div className="panel-card-grid-2">
          <label><small>TÊN KẾT QUẢ</small><input value={jobName} onChange={(e)=>setJobName(e.target.value)}/></label>
          <label><small>BỘ MÃ HÓA VIDEO</small><select value={encoder} onChange={(e)=>setEncoder(e.target.value)}><option value="auto">Tự động</option><option value="nvenc">NVIDIA NVENC</option><option value="amf">AMD AMF</option><option value="qsv">Intel QSV</option><option value="x264">CPU (libx264)</option></select></label>
        </div>
      </div>
    </div>
        <SyncProgressBar progress={progressPercent} steps={['Chuẩn bị','Co giãn video','Ghép đoạn','Xuất MP4']} running={running} complete={Boolean(result)} error={progressError}/>
        <section className="sync-status-run">
          <div className={`sync-input-check ${analysis?.ready ? 'ready' : ''}`}>{analysis?.ready?<Check size={15}/>:<CircleHelp size={15}/>}<span>{analysis?.ready?'Đã kiểm tra đầu vào':'Chưa kiểm tra đầu vào'}</span></div>
          <div className="sync-status-heading"><div><strong>{analysis?.ready?'Đầu vào hợp lệ':message}</strong><small>{analysis?.ready?`${analysis.subtitles} phụ đề · ${analysis.voiceFiles} file voice`:'Chọn đủ video, SRT, voice và thư mục xuất.'}</small></div><span>{running?'ĐANG XỬ LÝ':result?'HOÀN TẤT':progressError?'LỖI':'SẴN SÀNG'}</span></div>
          <div className="capcut-log">{logs.length?logs.map((line,index)=><p key={`${index}-${line}`}>{line}</p>):<p>FFmpeg sẽ xử lý video độc lập mà không cần CapCut.</p>}</div>
          {result&&<footer><div><Check size={18}/><span><strong>{result.projectName}</strong><small>{result.template} · {result.projectPath}</small></span></div><button onClick={()=>window.desktop?.showInFolder(result.projectPath)}><FolderOpen size={15}/> Mở kết quả</button></footer>}
          <button className="primary sync-main-cta" disabled={!analysis?.ready||!outputDir||!jobName.trim()||running} onClick={create}>{running?<><RefreshCw className="spin" size={17}/> Đang render ({progressPercent}%)…</>:<><Zap size={17}/> Đồng bộ & xuất MP4</>}</button>
        </section>
      </section>
    </div>
  </div>;
}

function CapCutProjectPage() {
  const { showToast } = useToast();
  const [subtab, setSubtab] = useState<'ffmpeg' | 'capcut'>('ffmpeg');
  const [projects, setProjects] = useState<{name:string;path:string}[]>([]);
  const [projectPath, setProjectPath] = useState('');
  const [srtPath, setSrtPath] = useState('');
  const [voiceDir, setVoiceDir] = useState('');
  const [analysis, setAnalysis] = useState<{ subtitles: number; voiceFiles: number; missing: number[]; ready: boolean } | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn dự án CapCut, file SRT và thư mục voice để kiểm tra ánh xạ.');
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<{ projectName: string; projectPath: string; template: string } | null>(null);
  const [capcutProgress, setCapcutProgress] = useState(0);
  const [capcutProgressError, setCapcutProgressError] = useState(false);
  useEffect(() => { window.desktop?.request<{name:string;path:string}[]>('project.list').then((items)=>{setProjects(items || []);if(items?.length)setProjectPath((value)=>value || items[0].path);}).catch(()=>undefined); }, []);
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const event = raw as { event?: string; data?: { message?: string } };
    if (event.event === 'capcut.project.progress' && event.data?.message) {
      const progressMessage = event.data.message.toLowerCase();
      if (progressMessage.includes('sao lưu') || progressMessage.includes('khởi tạo')) setCapcutProgress((value)=>Math.max(value,25));
      else if (progressMessage.includes('phụ đề') || progressMessage.includes('voice')) setCapcutProgress((value)=>Math.max(value,50));
      else if (progressMessage.includes('cắt video') || progressMessage.includes('cắt clip')) setCapcutProgress((value)=>Math.max(value,75));
      else if (progressMessage.includes('đồng bộ') || progressMessage.includes('timeline')) setCapcutProgress((value)=>Math.max(value,75));
      setLogs((current) => [...current.slice(-99), event.data!.message!]);
      setMessage(event.data.message);
    }
  }), []);
  useEffect(() => {
    setAnalysis(null); setResult(null); setCapcutProgress(0); setCapcutProgressError(false);
    if (!projectPath || !srtPath || !voiceDir || !window.desktop) return;
    window.desktop.request<typeof analysis>('capcut.project.validate_existing', { projectPath, srtPath, voiceDir })
      .then((value) => { setAnalysis(value); setMessage(value?.ready ? `Sẵn sàng: ${value.subtitles} phụ đề ↔ ${value.voiceFiles} voice.` : `Thiếu ${value?.missing.length || 0} file voice.`); })
      .catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [projectPath, srtPath, voiceDir]);
  const pick = async (kind: 'srt' | 'voice') => {
    if (kind === 'voice') { const path = await window.desktop?.selectFolder(); if (path) setVoiceDir(path); return; }
    const path = await window.desktop?.selectFile({ filters: [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (path) setSrtPath(path);
  };
  const create = async () => {
    if (!window.desktop || !analysis?.ready || running) return;
    setRunning(true); setLogs([]); setResult(null); setCapcutProgress(0); setCapcutProgressError(false); setMessage('Đang sao lưu và đồng bộ dự án có sẵn…');
    showToast({kind:'info',title:'Đã bắt đầu cập nhật CapCut',message:'Dự án sẽ được sao lưu trước khi thay đổi.'});
    try {
      const created = await window.desktop.request<{ projectName: string; projectPath: string; template: string }>('capcut.project.sync', { projectPath, srtPath, voiceDir });
      setResult(created); setCapcutProgress(100); setMessage(`Hoàn tất project: ${created.projectName}`); showToast({kind:'success',title:'Cập nhật CapCut hoàn tất',message:created.projectName});
    } catch (error) { const detail=error instanceof Error ? error.message : String(error); setCapcutProgressError(true); setMessage(detail); showToast({kind:'error',title:'Cập nhật CapCut thất bại',message:detail}); }
    finally { setRunning(false); }
  };
  const fileName = (value: string) => value.split(/[\\/]/).at(-1) || '';
  return <div className="capcut-project-page" style={{ paddingTop: '20px' }}>
    <div className="capcut-subtab-bar">
      <button className={subtab === 'ffmpeg' ? 'active' : ''} onClick={() => setSubtab('ffmpeg')}><Zap size={15} /> Đồng bộ FFmpeg (Xuất MP4)</button>
      <button className={subtab === 'capcut' ? 'active' : ''} onClick={() => setSubtab('capcut')}><Clapperboard size={15} /> Dự án CapCut</button>
    </div>
    {subtab === 'ffmpeg' ? <FfmpegAndCapCutTab /> : <>
      <div className="capcut-project-hero"><div><h1>Thêm voice và <span>đồng bộ timeline.</span></h1><p>Chỉnh sửa dự án CapCut có sẵn và tự động sao lưu JSON trước khi ghi.</p></div></div>
      <div className="sync-workspace-grid">
        <section className="sync-input-panel">
          <header><strong>Đầu vào</strong><small>Chọn dự án, phụ đề và thư mục voice.</small></header>
          <div className="sync-input-list">
            <SyncInputRow number={1} icon={<Clapperboard size={20}/>} label="DỰ ÁN CAPCUT" description="Chọn dự án" value={projectPath}><select value={projectPath} onChange={(e)=>setProjectPath(e.target.value)}><option value="">Chọn dự án…</option>{projects.map((project)=><option key={project.path} value={project.path}>{project.name}</option>)}</select></SyncInputRow>
            <SyncInputRow number={2} icon={<Captions size={20}/>} label="PHỤ ĐỀ SRT" description="Chọn file SRT" value={srtPath} onClick={()=>pick('srt')}/>
            <SyncInputRow number={3} icon={<AudioLines size={20}/>} label="THƯ MỤC VOICE" description="Chọn thư mục voice" value={voiceDir} onClick={()=>pick('voice')}/>
          </div>
        </section>
        <section className="sync-right-column">
          <SyncProgressBar progress={capcutProgress} steps={['Sao lưu dự án','Ghép SRT + voice','Cắt video','Đồng bộ']} running={running} complete={Boolean(result)} error={capcutProgressError}/>
          <section className="sync-status-run">
            <div className={`sync-input-check ${analysis?.ready ? 'ready' : ''}`}>{analysis?.ready?<Check size={15}/>:<CircleHelp size={15}/>}<span>{analysis?.ready?'Đã kiểm tra đầu vào':'Chưa kiểm tra đầu vào'}</span></div>
            <div className="sync-status-heading"><div><strong>{analysis?.ready?'Dự án đã sẵn sàng':message}</strong><small>{analysis?.ready?`${analysis.voiceFiles}/${analysis.subtitles} voice đã khớp`:'CapCut sẽ được yêu cầu đóng trước khi cập nhật project.'}</small></div><span>{running?'ĐANG XỬ LÝ':result?'HOÀN TẤT':capcutProgressError?'LỖI':'SẴN SÀNG'}</span></div>
            <div className="capcut-log">{logs.length?logs.map((line,index)=><p key={`${index}-${line}`}>{line}</p>):<p>Chưa có tác vụ. Tool sẽ yêu cầu đóng CapCut trước khi ghi project.</p>}</div>
            {result&&<footer><div><Check size={18}/><span><strong>{result.projectName}</strong><small>{result.template} · {result.projectPath}</small></span></div><button onClick={()=>window.desktop?.showInFolder(result.projectPath)}><FolderOpen size={15}/> Mở thư mục</button><button className="open-capcut" onClick={()=>window.desktop?.request('capcut.open')}><Clapperboard size={15}/> Mở CapCut</button></footer>}
            <button className="primary sync-main-cta" disabled={!analysis?.ready||running} onClick={create}>{running?<><RefreshCw className="spin" size={17}/> Đang đồng bộ…</>:<><Sparkles size={17}/> Thêm voice & đồng bộ</>}</button>
          </section>
        </section>
      </div>
    </>}
  </div>;
}
