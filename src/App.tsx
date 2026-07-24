import { useEffect, useMemo, useRef, useState } from 'react';
import './studio-v2.css';
import './voice-modal.css';
import './studio-layout.css';
import './generation-side.css';
import './focused-workspace.css';
import './translate-complete.css';
import './translate-toolbar-v2.css';
import './srt-voice-v1.css';
import './capcut-project-v1.css';
import './capcut-sync.css';
import './voice-backend-settings.css';
import './shell-v3.css';
import './sync-phase5.css';
import { AudioLines, Captions, Check, ChevronDown, CircleHelp, Clapperboard, Download, DownloadCloud, FileText, FolderOpen, Languages, Loader2, Mic2, Moon, MoreHorizontal, Pause, Play, RefreshCw, Search, Settings2, Sliders, Sparkles, Square, Sun, Trash2, UploadCloud, Volume2, X, Zap } from 'lucide-react';

type Page = 'studio' | 'translate' | 'srt' | 'capcut' | 'settings';
type Voice = { id: string; name: string; language: string; ready: boolean; source: string };
type StudioResult = { id: string; path: string; name: string; bytes: number; duration: number; generationTime: number; seed: number; format: string; voiceId: string; voiceName: string; language: string; text: string; createdAt: string; srtPath?: string };
type SrtVoiceRow = { id: number; start: string; end: string; text: string; status: 'pending' | 'generating' | 'completed' | 'failed'; duration?: number; file?: string; error?: string };
type SrtDraft = { name: string; path: string; rows: SrtVoiceRow[] };
type SrtQueueItem = { id: string; draft: SrtDraft; status: 'waiting'|'running'|'completed'|'failed'|'cancelled'; done: number; total: number; outputDir?: string; error?: string };
type SrtGenerationResult = { state: 'cancelled'|'completed'; completed: number; failed: number; total: number; items: SrtVoiceRow[]; outputDir: string };
type ApiVoice = { id: string; name: string; previewUrl?: string; language?: string; provider?: string; personal?: boolean };

const cleanUnicode = (value: string) => new TextDecoder().decode(new TextEncoder().encode(value));

const nav: { id: Page; label: string; icon: typeof Sparkles }[] = [
  { id: 'srt', label: 'Tạo voice SRT', icon: FileText },
  { id: 'capcut', label: 'Đồng bộ & CapCut', icon: Clapperboard },
];

const sampleVoices: Voice[] = [
  { id: 'ban-mai', name: 'Ban Mai', language: 'Tiếng Việt', ready: true, source: 'OmniVoice' },
  { id: 'lan-trinh', name: 'Lan Trinh', language: 'Tiếng Việt', ready: true, source: 'OmniVoice' },
  { id: 'story', name: 'Story', language: 'English', ready: true, source: 'OmniVoice' },
];

export function App() {
  const [page, setPage] = useState<Page>('srt');
  const [online, setOnline] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('hhvietsub.theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  const [uiLanguage, setUiLanguage] = useState('vi');
  const [voices] = useState<Voice[]>([]);
  const [query, setQuery] = useState('');
  const [selectedVoice, setSelectedVoice] = useState('ban-mai');
  const [text, setText] = useState('Dich CapCut Studio giúp bạn biến phụ đề thành giọng nói và đồng bộ trực tiếp với dự án CapCut.');
  const [voiceModal, setVoiceModal] = useState(false);
  const [studioHistory, setStudioHistory] = useState<StudioResult[]>([]);
  const [srtDraft, setSrtDraft] = useState<SrtDraft | null>(null);
  const loadVoices = () => Promise.resolve();
  const loadStudioHistory = () => window.desktop?.request<StudioResult[]>('studio.history').then(setStudioHistory).catch(() => undefined);

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

  const filteredVoices = useMemo(() => voices.filter((voice) => voice.name.toLowerCase().includes(query.toLowerCase())), [voices, query]);
  const focusedWorkspace = true;
  return <div className="app-shell focused-workspace lite-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><AudioLines size={23} /></div><div><strong>HHVietSub Lite</strong><span>CapCut Voice & Sync</span></div></div>
      <nav className="nav-pills">{nav.map((item) => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => setPage(item.id)}><item.icon size={15} />{item.label}</button>)}</nav>
      <div className="top-actions">
        <span className={`backend-state ${online ? 'online' : ''}`}><i />{online ? 'Backend sẵn sàng' : 'Backend chưa sẵn sàng'}</span>
        <label className="ui-language-picker" title="Ngôn ngữ giao diện"><Languages size={16}/><select aria-label="Ngôn ngữ giao diện" value={uiLanguage} onChange={(event) => setUiLanguage(event.target.value)}><option value="vi">VI</option></select></label>
        <button className="theme-toggle" type="button" title={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}</button>
      </div>
    </header>

    {false && <aside className="sidebar">
      <div className="eyebrow">THƯ VIỆN GIỌNG</div><div className="side-title"><h2>Giọng của bạn</h2><button title="Thêm giọng" onClick={() => setVoiceModal(true)}>+</button></div>
      <label className="search"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm kiếm giọng" /></label>
      <div className="section-caption">GIỌNG OMNIVOICE</div>
      <div className="project-list">{filteredVoices.length ? filteredVoices.map((voice, i) => <button className={`project-card ${voice.id === selectedVoice ? 'selected' : ''}`} key={voice.id} onClick={() => setSelectedVoice(voice.id)}><span className={`project-icon tone-${i % 4}`}>{voice.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase()}</span><span><strong>{voice.name}</strong><small>{voice.language}</small></span><Volume2 size={15} /></button>) : <div className="empty-small"><AudioLines size={25} /><span>Chưa tìm thấy giọng</span><small>Thêm audio mẫu để tạo hồ sơ giọng mới.</small></div>}</div>
      <div className="privacy"><span>✓</span><div><strong>Riêng tư ngay từ thiết kế</strong><small>Audio và dự án chỉ lưu trên thiết bị này.</small></div></div>
    </aside>}

    <main className="workspace">
      <div className="workspace-view" style={{ display: page === 'srt' ? 'block' : 'none' }}>
        <SrtVoicePage voices={voices} initialDraft={srtDraft} />
      </div>
      <div className="workspace-view" style={{ display: page === 'capcut' ? 'block' : 'none' }}>
        <CapCutProjectPage />
      </div>
    </main>

    {false && <GenerationHistoryPanel history={studioHistory} refresh={loadStudioHistory} />}
  </div>;
}

function VoiceModal({ onClose, onCreated }: { onClose: () => void; onCreated: (voice: Voice) => void }) {
  const [name, setName] = useState('');
  const [audioPath, setAudioPath] = useState('');
  const [language, setLanguage] = useState('auto');
  const [refText, setRefText] = useState('');
  const [notes, setNotes] = useState('');
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [languageOptions, setLanguageOptions] = useState<{id:string;name:string}[]>([
    {id:'auto',name:'Tự động nhận diện'}, {id:'vi',name:'Vietnamese'}, {id:'en',name:'English'}
  ]);
  useEffect(() => { window.desktop?.request<{id:string;name:string}[]>('voice.languages').then((items)=>{if(items?.length)setLanguageOptions(items);}).catch(()=>undefined); }, []);
  const chooseAudio = async () => {
    const path = await window.desktop?.selectFile({ filters: [{ name: 'Audio tham chiếu', extensions: ['wav', 'mp3', 'flac', 'm4a', 'ogg', 'webm'] }] });
    if (path) setAudioPath(path);
  };
  const create = async () => {
    if (!window.desktop || !name.trim() || !audioPath || !consent) return setError('Hãy nhập tên, chọn audio và xác nhận quyền sử dụng.');
    setSaving(true); setError('');
    try { await onCreated(await window.desktop.request<Voice>('voice.create', { name, audioPath, language, refText, notes, consentConfirmed: consent })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  };
  const fileName = audioPath.split(/[\\/]/).pop();
  return <div className="voice-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section className="voice-modal"><button className="voice-modal-close" onClick={onClose}><X size={19} /></button>
      <header><div className="voice-modal-art"><Mic2 size={29} /><AudioLines size={38} /></div><div><small>✦ GIỌNG MỚI</small><h2>Tạo hồ sơ giọng nói</h2><p>Hãy dùng bản ghi rõ ràng, chỉ có một người nói và ít tiếng ồn.</p></div></header>
      <div className="voice-modal-form"><label><span>Tên giọng</span><input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Ví dụ: Giọng kể chuyện ấm áp" /></label>
        <button className={`voice-audio-picker ${audioPath ? 'selected' : ''}`} onClick={chooseAudio}><UploadCloud size={25} /><strong>{fileName || 'Chọn audio tham chiếu'}</strong><small>{fileName ? audioPath : 'WAV, MP3, FLAC, M4A, OGG hoặc WebM · tối đa 50 MB'}</small></button>
        <div className="voice-form-grid"><label><span>Ngôn ngữ trong audio · {languageOptions.length} lựa chọn</span><select value={language} onChange={(e) => setLanguage(e.target.value)}>{languageOptions.map((item)=><option key={item.id} value={item.id}>{item.name}{item.id !== 'auto' ? ` (${item.id})` : ''}</option>)}</select></label><label><span>Bản chép lời tham chiếu <i>không bắt buộc</i></span><input value={refText} onChange={(e) => setRefText(cleanUnicode(e.target.value))} placeholder="Nội dung được nói trong audio?" /></label></div>
        <label><span>Ghi chú <i>không bắt buộc</i></span><input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Chất giọng, micro, bối cảnh thu âm..." /></label>
        <label className="voice-consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span><strong>Tôi có quyền sử dụng và clone giọng nói này.</strong><small>Chỉ clone giọng của bạn hoặc giọng mà bạn được chủ sở hữu cho phép.</small></span></label>
        {error && <div className="voice-modal-error">{error}</div>}
      </div><footer><button onClick={onClose}>Hủy</button><button className="create-voice" disabled={saving || !name.trim() || !audioPath || !consent} onClick={create}><Sparkles size={17} />{saving ? 'Đang tạo...' : 'Tạo giọng'}</button></footer>
    </section></div>;
}

function GenerationHistoryPanel({ history, refresh }: { history: StudioResult[]; refresh: () => void }) {
  const playAudio = async (item: StudioResult) => {
    if (!window.desktop) return;
    const player = new Audio(await window.desktop.readAudio(item.path));
    await player.play();
  };
  return <aside className="activity-panel generation-side-panel"><div className="generation-side-heading"><div><div className="eyebrow">↶ GẦN ĐÂY</div><h2>Lịch sử tạo giọng</h2></div><button className="icon-button"><MoreHorizontal size={17} /></button></div>
    <div className="generation-side-list">{history.length ? history.map((item) => <article className="generation-side-card" key={item.id}><div className="generation-card-top"><button className="history-play" onClick={() => playAudio(item)}><Play size={13} fill="currentColor" /></button><span><strong>{item.voiceName}</strong><small>{new Date(item.createdAt).toLocaleString('vi-VN')}</small></span><button title="Lưu audio" onClick={() => window.desktop?.saveAudio(item.path)}><Download size={13} /></button><button title="Xóa" onClick={async () => { await window.desktop?.request('studio.history.delete', { id: item.id }); refresh(); }}><Trash2 size={13} /></button></div><p>{item.text}</p><footer><span>{item.duration} giây</span><span>{item.format.toUpperCase()}</span><span>{item.language.toUpperCase()}</span><span>Seed {item.seed}</span></footer><div className="mini-wave">|||||||||||||||||||||||||||||</div></article>) : <div className="generation-side-empty"><AudioLines size={26} /><strong>Chưa có audio nào</strong><span>Kết quả mới sẽ được lưu tại đây.</span></div>}</div>
  </aside>;
}

function Studio({ voices, selectedVoice, setSelectedVoice, text, setText, onHistoryChange }: { voices: Voice[]; selectedVoice: string; setSelectedVoice: (v: string) => void; text: string; setText: (v: string) => void; onHistoryChange: () => void }) {
  const [speed, setSpeed] = useState(1);
  const [postprocess, setPostprocess] = useState(true);
  const [createSrt, setCreateSrt] = useState(false);
  const [language, setLanguage] = useState('vi');
  const [steps, setSteps] = useState(32);
  const [guidance, setGuidance] = useState(2);
  const [seed, setSeed] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [status, setStatus] = useState('Sẵn sàng khi bạn bắt đầu');
  const [audioUrl, setAudioUrl] = useState('');
  const [result, setResult] = useState<StudioResult | null>(null);
  const generate = async () => {
    if (!window.desktop) return setStatus('Chức năng tạo giọng chỉ hoạt động trong Electron.');
    if (!text.trim()) return setStatus('Vui lòng nhập nội dung cần tạo giọng.');
    setGenerating(true); setAudioUrl(''); setStatus('Đang nạp OmniVoice và tạo audio...');
    try {
      const generated = await window.desktop.request<StudioResult>('studio.generate', { text, voiceId: selectedVoice, language, speed, denoise: false, postprocess, createSrt, steps, guidance, seed });
      setResult(generated); setAudioUrl(await window.desktop.readAudio(generated.path));
      setStatus(`${generated.duration.toFixed(1)} giây · WAV · seed ${generated.seed} · tạo trong ${generated.generationTime.toFixed(1)} giây`);
      onHistoryChange();
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
    finally { setGenerating(false); }
  };
  return <div className="studio-page">
    <div className="hero-row"><div><div className="eyebrow"><Sparkles size={14} /> SÁNG TẠO BẰNG GIỌNG CỦA BẠN</div><h1>Biến câu chữ thành <span>âm thanh của bạn.</span></h1><p>Chọn giọng, nhập nội dung và điều chỉnh cách đọc.</p></div><label className="voice-select"><span className="voice-avatar">OV</span><span><small>ĐANG SỬ DỤNG GIỌNG</small><strong>{voices.find((v) => v.id === selectedVoice)?.name ?? 'Chọn giọng'}</strong></span><ChevronDown size={17} /><select value={selectedVoice} onChange={(e) => setSelectedVoice(e.target.value)}>{voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label></div>
    <section className="editor-card"><div className="editor-head"><strong>Văn bản</strong><span>{text.length} / 100,000</span></div><textarea value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.ctrlKey && e.key === 'Enter') generate(); }} /><div className="editor-foot"><label className="studio-language">Ngôn ngữ <select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="vi">Tiếng Việt</option><option value="en">English</option><option value="auto">Tự động</option></select></label><span>✦ Mẹo: dấu câu giúp tạo nhịp đọc tự nhiên.</span></div></section>
    <div className="controls studio-controls-compact"><div className="control-card speed"><div><span>Tốc độ đọc</span><strong>{speed.toFixed(2)}×</strong></div><input type="range" min="0.6" max="1.5" step="0.05" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /><div className="range-label"><span>Chậm rãi</span><span>Tự nhiên</span><span>Nhanh</span></div></div><button className="control-card" onClick={() => setCreateSrt(!createSrt)}><span className="control-icon purple"><Captions size={17} /></span><div><strong>Tạo phụ đề SRT</strong><small>Đồng bộ chữ và tiếng</small></div><i className={`toggle ${createSrt ? 'on' : ''}`} /></button><button className="control-card refine-button" onClick={() => setAdvanced(!advanced)}><Settings2 size={17} /><strong>Tinh chỉnh</strong><ChevronDown className={advanced ? 'rotated' : ''} size={16} /></button></div>
    {advanced && <div className="advanced-panel-hh"><label><span>Số bước suy luận <b>{steps}</b></span><input type="range" min="4" max="64" step="4" value={steps} onChange={(e) => setSteps(Number(e.target.value))} /></label><label><span>Độ bám giọng <b>{guidance.toFixed(1)}</b></span><input type="range" min="0.5" max="5" step="0.1" value={guidance} onChange={(e) => setGuidance(Number(e.target.value))} /></label><label className="seed-input"><span>Seed tái lập</span><input inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ''))} placeholder="Ngẫu nhiên" /></label><button className={`natural-toggle ${postprocess ? 'active' : ''}`} onClick={() => setPostprocess(!postprocess)}><Check size={15} /> Hoàn thiện tự nhiên</button></div>}
    <div className="action-row"><div className="hint"><span>◷</span><div><strong>Lần tạo đầu tiên sẽ lâu hơn</strong><small>Mô hình được nạp vào GPU/CPU trước khi tạo audio.</small></div></div><button className="primary" onClick={generate} disabled={generating}>{generating ? <><RefreshCw className="spin" size={18} /> Đang tạo giọng...</> : <><Sparkles size={18} /> Tạo giọng nói <kbd>Ctrl ↵</kbd></>}</button></div>
    <div className="audio-result"><span className="audio-symbol"><AudioLines /></span><div><small>{generating ? 'Đang tiến hành tạo giọng nói…' : result ? 'Kết quả mới nhất' : 'Audio OmniVoice'}</small><strong>{status}</strong>{generating ? <div className="indeterminate-progress"><i /></div> : audioUrl ? <audio className="studio-audio" src={audioUrl} controls /> : <div className="wave">|||||||||||||||||||||||||||||||||||||||||</div>}</div>{result && !generating && <div className="result-actions"><button title="Lưu audio" onClick={() => window.desktop?.saveAudio(result.path)}><Download size={17} /></button><button title="Mở thư mục" onClick={() => window.desktop?.showInFolder(result.path)}><FolderOpen size={17} /></button></div>}</div>
  </div>;
}

function TranslatePage({ onSendToSrt }: { onSendToSrt: (draft: SrtDraft) => void }) {
  type SubtitleRow = { id: number; start: string; end: string; source: string; translated: string };
  const [model, setModel] = useState(() => localStorage.getItem('hhvietsub.geminiModel') || '3.5 Flash-Lite');
  const [gemUrl, setGemUrl] = useState(() => localStorage.getItem('hhvietsub.gemUrl') || 'https://gemini.google.com/gem/1C0dbBamFcx7CUGXr5bTL48p1A6HX6sgw?usp=sharing');
  const [batchSize, setBatchSize] = useState(100);
  const [workers, setWorkers] = useState(1);
  const [savedGems, setSavedGems] = useState<{ name: string; url: string }[]>([]);
  const [selectedGem, setSelectedGem] = useState('');
  const [newGemName, setNewGemName] = useState('');
  const [characterBiblePath, setCharacterBiblePath] = useState('');
  const [characterBibleName, setCharacterBibleName] = useState('');
  const [characterBible, setCharacterBible] = useState('');
  const [profileReady, setProfileReady] = useState(false);
  const [glossary, setGlossary] = useState('');
  const [showOptions, setShowOptions] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [translationPaused, setTranslationPaused] = useState(false);
  const [translationProgress, setTranslationProgress] = useState({ done: 0, total: 0, chunk: 0, worker: 0 });
  const [filePath, setFilePath] = useState('');
  const [fileName, setFileName] = useState('');
  const [message, setMessage] = useState('Chọn một file SRT để bắt đầu.');
  const [rows, setRows] = useState<SubtitleRow[]>([]);
  useEffect(() => {
    window.desktop?.request<{ gemini?: { url: string; saved: { name: string; url: string }[]; selected: string; models: string[]; model: string; batch: number; workers: number; profileReady: boolean } }>('settings.get').then((settings) => {
      if (!settings.gemini) return;
      const localSaved = (() => { try { const value = JSON.parse(localStorage.getItem('hhvietsub.savedGems') || '[]'); return Array.isArray(value) ? value : []; } catch { return []; } })();
      const merged = [...settings.gemini.saved, ...localSaved].filter((item, index, all) => item?.name && item?.url && all.findIndex((candidate) => candidate.name === item.name) === index);
      setGemUrl(settings.gemini.url); setSavedGems(merged); setSelectedGem(settings.gemini.selected);
      const savedModelAliases: Record<string, string> = { '3.5 Flash': '3.6 Flash', '3.1 Flash-Lite': '3.5 Flash-Lite' };
      setModel(localStorage.getItem('hhvietsub.geminiModel') || savedModelAliases[settings.gemini.model] || settings.gemini.model || '3.5 Flash-Lite'); setBatchSize(settings.gemini.batch); setWorkers(1); setProfileReady(settings.gemini.profileReady);
    }).catch(() => undefined);
  }, []);
  const openSrt = async () => {
    if (translating) return setMessage('Hãy hủy hoặc chờ tác vụ dịch hiện tại trước khi đổi file.');
    if (!window.desktop) return setMessage('Hộp thoại chọn file chỉ hoạt động trong Electron.');
    const path = await window.desktop.selectFile({ filters: [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (!path) return;
    setMessage('Đang đọc phụ đề...');
    try {
      const result = await window.desktop.request<{ path: string; name: string; entries: typeof rows; warnings: string[] }>('subtitle.parse', { path });
      setFilePath(result.path); setFileName(result.name); setRows(result.entries);
      setMessage(result.warnings.length ? `Đã tải ${result.entries.length} câu · ${result.warnings.length} cảnh báo` : `Đã tải ${result.entries.length} câu phụ đề`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const openCharacterBible = async () => {
    if (translating) return setMessage('Hãy chờ hoặc hủy tác vụ dịch trước khi đổi Character Bible.');
    if (!window.desktop) return setMessage('Hộp thoại chọn file chỉ hoạt động trong Electron.');
    const path = await window.desktop.selectFile({ title: 'Chọn Character Bible', filters: [{ name: 'Character Bible', extensions: ['txt', 'md', 'json', 'csv'] }] });
    if (!path) return;
    try {
      const content = await window.desktop.readText(path);
      if (!content.trim()) throw new Error('Character Bible đang trống.');
      setCharacterBiblePath(path); setCharacterBibleName(path.split(/[\\/]/).pop() || 'Character Bible'); setCharacterBible(content);
      setMessage(`Đã tải Character Bible · ${content.length.toLocaleString()} ký tự.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const saveNewGem = () => {
    const name = newGemName.trim(); const url = gemUrl.trim();
    if (!name) return setMessage('Hãy nhập tên Gem muốn lưu.');
    if (!url.startsWith('https://gemini.google.com/')) return setMessage('Link Gem không hợp lệ.');
    const next = [...savedGems.filter((item) => item.name !== name), { name, url }];
    setSavedGems(next); setSelectedGem(name); setNewGemName('');
    localStorage.setItem('hhvietsub.savedGems', JSON.stringify(next));
    setMessage(`Đã lưu Gem “${name}”.`);
  };
  const saveSrt = async () => {
    if (!window.desktop || !filePath || !rows.length) return setMessage('Chưa có phụ đề để lưu.');
    try {
      const result = await window.desktop.request<{ path: string; entries: number }>('subtitle.save', { sourcePath: filePath, entries: rows });
      setMessage(`Đã lưu ${result.entries} câu: ${result.path}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const startTranslation = async (translateAll = false) => {
    if (!window.desktop || !rows.length || translating) return;
    if (!gemUrl.trim()) { setShowOptions(true); setMessage('Vui lòng nhập link Gem.'); return; }
    if (!characterBible.trim()) return setMessage('Vui lòng chọn file Character Bible trước khi dịch.');
    const selectedRows = translateAll ? rows : rows.filter((row) => !row.translated.trim());
    if (!selectedRows.length) return setMessage('Tất cả câu đã có bản dịch. Chọn “Dịch lại tất cả” nếu muốn làm mới toàn bộ.');
    localStorage.setItem('hhvietsub.gemUrl', gemUrl.trim());
    setTranslating(true); setTranslationPaused(false);
    setTranslationProgress({ done: 0, total: Math.ceil(selectedRows.length / batchSize), chunk: 0, worker: 0 });
    try {
      setMessage(`Đang mở Gem và gửi ${Math.ceil(selectedRows.length / batchSize)} chunk…`);
      const response = await window.desktop.translateWithGem<{ results: { id: number; translated: string }[]; chunks: number }>({
        gemUrl: gemUrl.trim(), modelName: model, batchSize, workers: 1, sourceLanguage: 'Auto', targetLanguage: 'Tiếng Việt', glossary, characterBible,
        entries: selectedRows.map((row) => ({ id: row.id, text: row.source })),
      });
      const translatedMap = new Map(response.results.map((item) => [item.id, item.translated]));
      setRows((current) => current.map((row) => translatedMap.has(row.id) ? { ...row, translated: translatedMap.get(row.id)! } : row));
      setMessage(`Hoàn tất ${response.results.length}/${selectedRows.length} câu trong ${response.chunks} chunk.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setTranslating(false); setTranslationPaused(false); }
  };
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => { if (event.ctrlKey && event.key === 'Enter') { event.preventDefault(); void startTranslation(false); } };
    window.addEventListener('keydown', shortcut); return () => window.removeEventListener('keydown', shortcut);
  });
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const event = raw as { event?: string; data?: { state?: string; model?: string; characters?: number; done?: number; total?: number; chunk?: number; worker?: number; attempt?: number; message?: string; results?: {id:number;translated:string}[] } };
    if (!event.data) return;
    if (event.event === 'translation.bible') {
      setMessage(event.data.state === 'ready' ? (event.data.message || 'Đã nạp Character Bible — sẵn sàng nhận chunk để dịch.') : `Đang gửi toàn bộ Character Bible (${event.data.characters || 0} ký tự)…`);
      return;
    }
    if (event.event === 'translation.model') {
      setMessage(`Đã chọn model ${event.data.model || model} trên Gemini; đang nạp Character Bible…`);
      return;
    }
    if (event.event === 'translation.result' && event.data.results) {
      const partial = new Map(event.data.results.map((item)=>[item.id,item.translated]));
      setRows((current)=>current.map((row)=>partial.has(row.id)?{...row,translated:partial.get(row.id)!}:row));
      return;
    }
    if (event.event === 'translation.retry') {
      setMessage(`Chunk ${event.data.chunk} gặp lỗi · đang thử lại lần ${event.data.attempt}${event.data.message ? ` · ${event.data.message}` : ''}`);
      return;
    }
    if (event.event !== 'translation.progress') return;
    setTranslationProgress({done:event.data.done || 0,total:event.data.total || 0,chunk:event.data.chunk || 0,worker:event.data.worker || 0});
    setMessage(`Đang dịch chunk ${event.data.chunk}/${event.data.total} · tab ${event.data.worker}${event.data.attempt ? ` · lần ${event.data.attempt}` : ''}`);
  }), []);
  const pauseTranslation = async () => { const paused = !translationPaused; await window.desktop?.pauseGem(paused); setTranslationPaused(paused); setMessage(paused ? 'Đã tạm dừng sau request hiện tại.' : 'Đang tiếp tục dịch…'); };
  const cancelTranslation = async () => { await window.desktop?.cancelGem(); setMessage('Đang hủy dịch; các câu đã hoàn thành vẫn được giữ lại.'); };
  const updateRow = (id: number, field: 'source' | 'translated', value: string) => setRows((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row));
  const characterCount = rows.reduce((sum, row) => sum + row.source.length, 0);
  const translatedCount = rows.filter((row) => row.translated.trim()).length;
  const missingCount = rows.length - translatedCount;
  return <div className="translate-page">
    <div className="translate-hero"><div><div className="eyebrow"><Languages size={14} /> DỊCH PHỤ ĐỀ THÔNG MINH</div><h1>Dịch SRT <span>nhanh và nhất quán.</span></h1><p>Giữ nguyên timestamp, cập nhật từng chunk và tiếp tục được từ phần còn thiếu.</p></div><div className="translate-hero-actions"><button className="secondary" onClick={() => onSendToSrt({ name: fileName || 'Bản dịch', path: filePath, rows: rows.map((row) => ({ id: row.id, start: row.start, end: row.end, text: row.translated.trim(), status: 'pending' })) })} disabled={!rows.length || missingCount > 0 || translating} title={missingCount ? `Còn ${missingCount} câu chưa dịch` : 'Chuyển sang tạo giọng'}><AudioLines size={16} /> Tạo giọng</button><button className="secondary" onClick={saveSrt} disabled={!rows.length || translating} title={missingCount ? `Lưu bản nháp; ${missingCount} câu chưa dịch sẽ giữ nội dung gốc` : 'Lưu bản dịch SRT'}><Download size={16} /> {missingCount ? 'Lưu bản nháp' : 'Lưu bản dịch'}</button>{translating ? <><button className="job-pause" onClick={pauseTranslation}>{translationPaused ? <Play size={16}/> : <Pause size={16}/>} {translationPaused ? 'Tiếp tục' : 'Tạm dừng'}</button><button className="job-cancel" onClick={cancelTranslation}><Square size={15}/> Hủy</button><button className="primary" disabled><RefreshCw className="spin" size={17}/> {translationPaused ? 'Đã tạm dừng' : `${translationProgress.done}/${translationProgress.total} chunk`}</button></> : <>{translatedCount > 0 && <button className="secondary" onClick={()=>startTranslation(true)}><RefreshCw size={16}/> Dịch lại tất cả</button>}<button className="primary" disabled={!rows.length || missingCount === 0} onClick={()=>startTranslation(false)}><Languages size={17}/> {translatedCount ? `Dịch ${missingCount} câu còn thiếu` : 'Mở Gem & dịch'}</button></>}</div></div>
    <div className="translate-toolbar">
      <button className="file-drop" onClick={openCharacterBible} disabled={translating}><UploadCloud size={20} /><span><strong>{characterBibleName || '1. Chọn Character Bible'}</strong><small>{characterBiblePath || 'TXT, MD, JSON hoặc CSV · tối đa 5 MB'}</small></span></button>
      <button className="file-drop" onClick={openSrt} disabled={translating}><UploadCloud size={20} /><span><strong>{fileName || '2. Chọn tệp phụ đề SRT'}</strong><small>{fileName ? 'Bấm để chọn tệp khác' : 'Kéo thả hoặc bấm để tải tệp'}</small></span></button>
      <label><small>GEM ĐÃ LƯU</small><select value={selectedGem} onChange={(e) => { const name = e.target.value; setSelectedGem(name); const gem = savedGems.find((item) => item.name === name); if (gem) setGemUrl(gem.url); }}><option value="">Chọn Gem</option>{savedGems.map((gem) => <option key={gem.name}>{gem.name}</option>)}</select></label>
      <label><small>MÔ HÌNH GEMINI</small><select value={model} onChange={(e) => { setModel(e.target.value); localStorage.setItem('hhvietsub.geminiModel', e.target.value); }}><option>3.5 Flash-Lite</option><option>3.6 Flash</option><option>3.1 Pro</option><option>Tư duy mở rộng</option></select></label>
      <label><small>BLOCK / CHUNK</small><input type="number" min="1" max="300" value={batchSize} onChange={(e) => setBatchSize(Math.max(1, Math.min(300, Number(e.target.value) || 1)))} /></label>
      <label><small>SỐ LUỒNG / TAB</small><select value={workers} disabled><option value="1">1 · Ưu tiên chính xác</option></select></label>
    </div>
    <div className="translation-stats"><span><strong>{rows.length}</strong> câu</span><span><strong>{Math.ceil(missingCount / batchSize)}</strong> chunk còn lại</span><span><strong>{translatedCount}</strong> đã dịch</span><span className={missingCount ? 'profile-warning' : 'success'}><Check size={13} /> {rows.length ? (missingCount ? `${missingCount} câu còn thiếu` : 'Bản dịch đã đầy đủ') : 'Chưa có dữ liệu'}</span><span className={profileReady ? 'success' : 'profile-warning'}><Check size={13} /> {profileReady ? 'Chrome đã đăng nhập' : 'Chưa có profile'}</span><button onClick={() => setShowOptions(!showOptions)}><Settings2 size={15} /> Kết nối & từ điển</button></div>
    {showOptions && <section className="translation-options browser-options"><label><span>Link Gemini Gem</span><input value={gemUrl} onChange={(e) => setGemUrl(e.target.value)} placeholder="https://gemini.google.com/gem/..." /><small>Electron điều khiển Chrome trực tiếp bằng CDP, không dùng Selenium.</small></label><label><span>Lưu Gem mới</span><input value={newGemName} onChange={(e) => setNewGemName(e.target.value)} placeholder="Tên gợi nhớ cho Gem" /><button type="button" onClick={saveNewGem}>Lưu Gem mới</button></label><div className="gem-browser-actions"><button onClick={() => window.desktop?.loginGem()}>Đăng nhập Google</button><button onClick={() => window.desktop?.openGem(gemUrl)}>Mở Gem kiểm tra</button></div><label><span>Thuật ngữ bổ sung</span><textarea value={glossary} onChange={(e) => setGlossary(e.target.value)} placeholder="Mỗi dòng một quy tắc thuật ngữ" /></label></section>}
    <section className={`subtitle-table ${translating ? 'is-translating' : ''}`}><div className="subtitle-head"><span># / THỜI GIAN</span><span>NỘI DUNG GỐC</span><span>BẢN DỊCH TIẾNG VIỆT</span></div>{rows.length ? rows.map((row) => <div className={`subtitle-row ${row.translated.trim() ? 'translated' : 'missing'}`} key={row.id}><div><b>{String(row.id).padStart(2, '0')}</b><small>{row.start} → {row.end}</small></div><textarea value={row.source} disabled={translating} onChange={(e) => updateRow(row.id, 'source', e.target.value)} /><textarea className={row.translated.length > row.source.length * 1.8 ? 'length-warning' : ''} value={row.translated} placeholder={translating ? 'Đang chờ kết quả…' : 'Chưa dịch'} onChange={(e) => updateRow(row.id, 'translated', e.target.value)} /></div>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>Chưa có phụ đề</strong><small>Chọn file SRT để hiển thị nội dung tại đây.</small></div>}</section>
    <div className="translation-footer"><div><strong>{message}</strong><small>Tool nạp toàn bộ Character Bible, chờ Gem xác nhận, rồi mới gửi tuần tự từng chunk dạng #id.</small></div><span className="shortcut-hint">Ctrl ↵ để dịch</span></div>
  </div>;
}

function SrtVoicePage({ voices, initialDraft }: { voices: Voice[]; initialDraft: SrtDraft | null }) {
  const [engine, setEngine] = useState<'omnivoice' | 'vieneu' | 'ai33' | 'aimax' | 'capcut'>('capcut');
  const [apiProvider, setApiProvider] = useState('minimax');
  const [apiModel, setApiModel] = useState('speech-2.8-hd');
  const [apiVoiceId, setApiVoiceId] = useState('');
  const [apiWorkers, setApiWorkers] = useState(8);
  const [apiRequestInterval, setApiRequestInterval] = useState(() => {
    const saved = Number(localStorage.getItem('hhvietsub.apiRequestInterval') || 10);
    return Number.isFinite(saved) ? Math.min(60, Math.max(0, saved)) : 10;
  });
  const [subtitleLanguage, setSubtitleLanguage] = useState('auto');
  const [omniLanguage, setOmniLanguage] = useState('auto');
  const [omniLanguages, setOmniLanguages] = useState<{id:string;name:string}[]>([{id:'auto',name:'Tự động nhận diện'},{id:'vi',name:'Vietnamese'},{id:'en',name:'English'},{id:'es',name:'Spanish'}]);
  const [apiVoices, setApiVoices] = useState<ApiVoice[]>([]);
  const [voiceLibraryOpen, setVoiceLibraryOpen] = useState(false);
  const [voiceLibraryLoading, setVoiceLibraryLoading] = useState(false);
  const [voiceQuery, setVoiceQuery] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [draft, setDraft] = useState<SrtDraft | null>(initialDraft);
  const [voiceId, setVoiceId] = useState(() => voices.find((voice) => voice.ready)?.id || '');
  const [outputDir, setOutputDir] = useState('');
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn file SRT ở panel bên trái để bắt đầu.');
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [speed, setSpeed] = useState(1);
  const [steps, setSteps] = useState(32);
  const [guidance, setGuidance] = useState(2);
  const [vieneuBatchSize, setVieneuBatchSize] = useState(8);
  const [vieneuVoice, setVieneuVoice] = useState('Ngọc Lan');
  const [audioUrl, setAudioUrl] = useState('');
  const [activeJobId, setActiveJobId] = useState('');
  const [jobState, setJobState] = useState<'idle'|'running'|'paused'|'cancelled'|'completed'>('idle');
  const [savedJobs, setSavedJobs] = useState<{jobId:string;state:string;engine:string;voiceId:string;outputDir:string;createdAt:string;total:number;completed:number;failed:number}[]>([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [jobPickerOpen, setJobPickerOpen] = useState(false);
  const [queue, setQueue] = useState<SrtQueueItem[]>([]);
  const [queueRunning, setQueueRunning] = useState(false);
  const [capcutBackend, setCapcutBackend] = useState<'direct'|'space'|'hybrid'>('hybrid');
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
  useEffect(() => { if (initialDraft) { setDraft(initialDraft); setMessage(`Đã nhận ${initialDraft.rows.length} câu từ tab Dịch.`); } }, [initialDraft]);
  useEffect(() => { if (!voiceId && voices.length) setVoiceId(voices.find((voice) => voice.ready)?.id || ''); }, [voices, voiceId]);
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
      const job = await window.desktop.request<{jobId:string;state:string;engine:'omnivoice'|'vieneu'|'ai33'|'aimax'|'capcut';provider:string;model:string;voiceId:string;subtitleLanguage?:string;workers:number;outputDir:string;entries:{id:number;start:string;end:string;text:string}[];items:SrtVoiceRow[]}>('srt.voice.get',{jobId:selectedJobId});
      setActiveJobId(job.jobId); setJobState(job.state === 'running' || job.state === 'failed' ? 'cancelled' : job.state as typeof jobState); setEngine(job.engine); setApiProvider(job.provider || 'minimax'); setApiModel(job.model || 'speech-2.8-hd');
      if (job.engine === 'omnivoice') setVoiceId(job.voiceId || ''); else setApiVoiceId(job.voiceId || '');
      setSubtitleLanguage(job.subtitleLanguage || 'auto'); if(job.engine==='omnivoice') setOmniLanguage(job.subtitleLanguage || 'auto');
      if (job.engine === 'vieneu') setVieneuBatchSize(job.workers || 8); else setApiWorkers(job.workers || 3);
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
    if (!window.desktop || engine === 'omnivoice') return;
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
  const [autoRetry, setAutoRetry] = useState(true);
  const [advancedVoiceOptions, setAdvancedVoiceOptions] = useState(false);
  const runQueue = async () => {
    if (!window.desktop || running || !queue.some((item) => item.status !== 'completed')) return;
    if (engine === 'omnivoice' && !voiceId) return setMessage('Hãy chọn một hồ sơ giọng OmniVoice hoàn chỉnh.');
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
            voiceId, outputDir: destination, jobId: `${jobId}-pass-${pass}`, engine, apiProvider, apiModel, apiVoiceId: apiVoiceId.trim(), apiWorkers, apiRequestInterval, capcutBackend,
            subtitleLanguage, vieneuBatchSize, vieneuVoice, language: engine === 'omnivoice' ? (omniLanguage === 'auto' ? '' : omniLanguage) : 'vi',
            speed, steps, guidance, postprocess: true, denoise: false, skipExisting: true,
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
    if (engine === 'omnivoice' && !voiceId) return setMessage('Hãy chọn một hồ sơ giọng OmniVoice hoàn chỉnh.');
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
    setDraft((current) => current ? { ...current, rows: current.rows.map((row) => entries.some((e) => e.id === row.id) ? { ...row, status: 'pending' as const, error: undefined } : row) } : current);
    try {
      const result = await window.desktop.request<{ state: 'cancelled'|'completed'; completed: number; failed: number; total: number; items: SrtVoiceRow[]; outputDir: string }>(only ? 'srt.voice.regenerate' : 'srt.voice.generate', {
        entries: entries.map((row) => ({ id: row.id, start: row.start, end: row.end, text: replacePronunciation(row.text) })), voiceId, outputDir: destination,
        jobId, engine, apiProvider, apiModel, apiVoiceId: apiVoiceId.trim(), apiWorkers, apiRequestInterval, capcutBackend, subtitleLanguage, vieneuBatchSize, vieneuVoice, language: engine === 'omnivoice' ? (omniLanguage === 'auto' ? '' : omniLanguage) : 'vi', speed, steps, guidance, postprocess: true, denoise: false, skipExisting: !only && !selectedRows,
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
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setMessage(detail); setJobState('cancelled');
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.status === 'generating' ? { ...row, status: 'failed' as const, error: detail } : row) } : current);
    }
    finally { setRunning(false); refreshSavedJobs(); }
  };
  const controlJob = async (action:'pause'|'resume'|'cancel') => { if(!activeJobId || !window.desktop) return; if(action==='cancel' && queueRunning) stopQueue.current=true; try { const r=await window.desktop.request<{state:typeof jobState}>('srt.voice.control',{jobId:activeJobId,action}); setJobState(r.state); setMessage(action==='pause'?'Đã tạm dừng gửi câu mới. Các request đang chạy vẫn hoàn tất an toàn.':action==='resume'?'Đang tiếp tục job…':'Đã yêu cầu huỷ job và dừng hàng chờ.'); } catch(error){ setMessage(error instanceof Error?error.message:String(error)); } };
  const play = async (row: SrtVoiceRow) => { if (!row.file) return; const url = await window.desktop?.readAudio(row.file); if (url) { setAudioUrl(url); setTimeout(() => document.querySelector<HTMLAudioElement>('.srt-voice-player')?.play(), 0); } };
  const completed = draft?.rows.filter((row) => row.status === 'completed').length || 0;
  const failed = draft?.rows.filter((row) => row.status === 'failed').length || 0;
  return <div className="srt-voice-page">
    <div className="srt-voice-hero"><div><h1>Tạo giọng từ <span>file hoặc thư mục SRT.</span></h1><p>Chọn nguồn, giọng đọc rồi theo dõi toàn bộ hàng chờ ở một màn hình.</p></div><button className="secondary folder-queue" disabled={running} onClick={chooseSrtFolder}><FolderOpen size={16} /> Chọn thư mục SRT</button></div>
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
      <button type="button" onClick={()=>{setApiSettingsOpen(true);void loadApiKeyStatus();}}>
        <Settings2 size={15}/> API key
        <b>{apiKeyStatus.ai33KeyCount + apiKeyStatus.aimaxKeyCount}</b>
      </button>
      </div>
    </section>
    <section className="srt-voice-config">
      <div className="srt-config-heading"><span>1</span><div><strong>Nguồn phụ đề</strong><small>Chọn một file SRT để chạy ngay.</small></div></div>
      <label className={`srt-input-card ${running?'disabled':''}`} role="button" tabIndex={running?-1:0} onClick={()=>{if(!running)void chooseSrt();}} onKeyDown={(event)=>{if(!running&&(event.key==='Enter'||event.key===' ')){event.preventDefault();void chooseSrt();}}}><small>FILE ĐẦU VÀO · BẤM ĐỂ CHỌN</small><strong>{draft?.name || 'Chưa chọn SRT'}</strong><span>{draft ? `${draft.rows.length} câu phụ đề · bấm để đổi file` : 'Chọn một file SRT từ máy'}</span></label>
      <div className="srt-config-heading voice-heading"><span>2</span><div><strong>Giọng đọc</strong><small>Chọn voice, ngôn ngữ và tốc độ.</small></div></div>
      {engine === 'omnivoice' ? <><label><small>GIỌNG OMNIVOICE</small><select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>{voices.filter((voice) => voice.ready).map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}</select></label><label><small>NGÔN NGỮ PHỤ ĐỀ</small><select value={omniLanguage} onChange={(e)=>setOmniLanguage(e.target.value)}>{omniLanguages.map((item)=><option key={item.id} value={item.id}>{item.name}{item.id !== 'auto' ? ` (${item.id})` : ''}</option>)}</select></label><label><small>STEP / GUIDANCE</small><div className="inline-numbers"><input type="number" min="4" max="64" value={steps} onChange={(e) => setSteps(Number(e.target.value))} /><input type="number" min="0.5" max="5" step="0.1" value={guidance} onChange={(e) => setGuidance(Number(e.target.value))} /></div></label></> : engine === 'vieneu' ? <><label><small>GIỌNG VIENEU v3 TURBO</small><select value={vieneuVoice} onChange={(e)=>setVieneuVoice(e.target.value)}>{['Ngọc Lan','Ngọc Linh','Trúc Ly','Mỹ Duyên','Xuân Vĩnh','Thái Sơn','Gia Bảo','Đức Trí','Trọng Hữu','Bình An'].map((name)=><option key={name}>{name}</option>)}</select><span>48 kHz · giọng tích hợp chính thức</span></label><label><small>BATCH GPU</small><input type="number" min="1" max="32" value={vieneuBatchSize} onChange={(e)=>setVieneuBatchSize(Math.min(32,Math.max(1,Number(e.target.value)||1)))}/><span>RTX 3060: khuyên dùng 8</span></label></> : engine === 'capcut' ? <><label className={!apiVoiceId?'voice-required':''}><small>GIỌNG CAPCUT SPACE</small><div className="voice-id-picker"><input value={apiVoices.find((voice)=>voice.id===apiVoiceId)?.name||''} readOnly placeholder={voiceLibraryLoading?'Đang tải thư viện giọng…':'Chưa chọn giọng'}/><button type="button" onClick={loadApiVoices}><Search size={14}/> Thư viện</button></div><span>{apiVoiceId?'Đã sẵn sàng tạo voice':'Bắt buộc chọn giọng trước khi chạy'}</span></label><label className="legacy-service-card"><small>DỊCH VỤ</small><strong>tony2k · AI Voice Studio</strong><span>CapCut TTS từ Hugging Face Space · không cần API key</span></label></> : <><label><small>VOICE ID</small><div className="voice-id-picker"><input value={apiVoiceId} onChange={(e) => setApiVoiceId(e.target.value)} placeholder="Chọn trong thư viện hoặc nhập ID"/><button type="button" onClick={loadApiVoices}><Search size={14}/> Thư viện</button></div></label><label><small>NHÀ CUNG CẤP {engine === 'aimax' ? '/ MODEL' : ''}</small><div className="inline-numbers"><select value={apiProvider} onChange={(e) => { const p=e.target.value; setApiProvider(p); setApiVoices([]); setApiModel(p === 'minimax' ? 'speech-2.8-hd' : 'eleven_multilingual_v2'); }}><option value="minimax">MiniMax</option><option value="elevenlabs">ElevenLabs</option>{engine === 'ai33' && <><option value="edge">Edge</option><option value="kokoro">Kokoro</option><option value="vbee">Vbee</option><option value="fishaudio">Fish Audio</option><option value="clone">Giọng clone</option></>}</select>{engine === 'aimax' && <select value={apiModel} onChange={(e) => setApiModel(e.target.value)}>{apiProvider === 'minimax' ? <><option value="speech-2.8-hd">2.8 HD</option><option value="speech-2.8-turbo">2.8 Turbo</option><option value="speech-2.6-hd">2.6 HD</option><option value="speech-2.6-turbo">2.6 Turbo</option><option value="speech-02-hd">02 HD</option><option value="speech-02-turbo">02 Turbo</option></> : <><option value="eleven_v3">Eleven v3</option><option value="eleven_multilingual_v2">Multilingual v2</option><option value="eleven_flash_v2_5">Flash v2.5</option><option value="eleven_turbo_v2_5">Turbo v2.5</option></>}</select>}</div></label></>}
      <label><small>TỐC ĐỘ · {speed.toFixed(2)}×</small><input type="range" min="0.6" max="1.5" step="0.05" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /></label>
      {(engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && <label><small>NGÔN NGỮ PHỤ ĐỀ</small><select value={subtitleLanguage} onChange={(e)=>{setSubtitleLanguage(e.target.value);setApiVoices([]);setApiVoiceId('');}}><option value="auto">Tự động nhận diện</option><option value="Vietnamese">Tiếng Việt</option><option value="English">Tiếng Anh</option><option value="Spanish">Tiếng Tây Ban Nha</option><option value="French">Tiếng Pháp</option><option value="German">Tiếng Đức</option><option value="Portuguese">Tiếng Bồ Đào Nha</option><option value="Italian">Tiếng Ý</option><option value="Japanese">Tiếng Nhật</option><option value="Korean">Tiếng Hàn</option><option value="Chinese">Tiếng Trung</option><option value="Thai">Tiếng Thái</option><option value="Indonesian">Tiếng Indonesia</option><option value="Russian">Tiếng Nga</option><option value="Arabic">Tiếng Ả Rập</option></select><span>Dùng để lọc giọng và tạo đúng phát âm</span></label>}
      <button className="srt-advanced-toggle" type="button" aria-expanded={advancedVoiceOptions} onClick={()=>setAdvancedVoiceOptions((current)=>!current)}><Settings2 size={15}/><span><strong>Tùy chọn nâng cao</strong><small>Luồng API, delay, retry và từ điển</small></span><ChevronDown size={16} className={advancedVoiceOptions?'rotated':''}/></button>
      {advancedVoiceOptions&&<>
      {(engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && <label><small>SỐ LUỒNG API</small><input type="number" min="1" max="32" value={apiWorkers} onChange={(e)=>setApiWorkers(Math.min(32,Math.max(1,Number(e.target.value)||1)))}/><span>Tối đa request đang xử lý song song</span></label>}
      {(engine === 'ai33' || engine === 'aimax' || engine === 'capcut') && <label><small>DELAY GỬI API · GIÂY</small><input type="number" min="0" max="60" step="0.5" value={apiRequestInterval} onChange={(e)=>{const value=Math.min(60,Math.max(0,Number(e.target.value)||0));setApiRequestInterval(value);localStorage.setItem('hhvietsub.apiRequestInterval',String(value));}}/><span>Khoảng cách giữa hai request: {apiRequestInterval}s{engine==='capcut'&&capcutBackend==='hybrid'?' trên mỗi nguồn':''}</span></label>}
      <label><small>TỰ ĐỘNG RETRY LỖI</small><button type="button" onClick={() => setAutoRetry(!autoRetry)} style={{ border: autoRetry ? '1px solid #7edab7' : '1px solid #dfe3f0', borderRadius: 8, padding: '7px 8px', fontSize: 10, fontWeight: 700, cursor: 'pointer', background: autoRetry ? '#ecfbf5' : '#f4f5fa', color: autoRetry ? '#178360' : '#778198', display: 'flex', alignItems: 'center', gap: 5 }}>{autoRetry ? <><RefreshCw size={12} /> Bật (Tối đa 3 lượt)</> : 'Tắt'}</button></label>
      {engine==='capcut'&&<label className="capcut-source-card"><small>NGUỒN CAPCUT TTS</small><select value={capcutBackend} onChange={(e)=>setCapcutBackend(e.target.value as typeof capcutBackend)}><option value="hybrid">Kết Hợp</option><option value="direct">Nội Bộ</option><option value="space">Space</option></select><span>{capcutBackend==='hybrid'?'Chia tải cho hai nguồn để tạo nhanh hơn.':capcutBackend==='direct'?'Gọi trực tiếp CapCut API nội bộ.':'Dùng tony2k/ai-voice-studio.'}</span></label>}
      {engine==='capcut'&&<label className="dictionary-config-card"><small>TỪ ĐIỂN PHÁT ÂM</small><button type="button" onClick={()=>setDictionaryOpen(true)}><FileText size={15}/><span>Mở từ điển</span><b>{pronunciationDictionary.length}</b></button><span>Tự động sửa cách đọc trước khi tạo MP3.</span></label>}
      </>}
    </section>
    <section className="srt-sticky-actions">
      {running && <>{engine!=='omnivoice' && (jobState==='paused'?<button className="job-resume" onClick={()=>controlJob('resume')}><Play size={16}/> Tiếp tục</button>:<button className="job-pause" onClick={()=>controlJob('pause')}><Pause size={16}/> Tạm dừng</button>)}<button className="job-cancel" onClick={()=>controlJob('cancel')}><Square size={15}/> Dừng / Huỷ</button></>}
      {!running && failed>0 && <button className="job-retry" onClick={()=>run(undefined,draft!.rows.filter((x)=>x.status==='failed'))}><RefreshCw size={15}/> Chạy lại {failed} lỗi</button>}
      {queue.length>0&&<button className="queue-run" disabled={running||!queue.some((item)=>item.status!=='completed')||(engine==='capcut'&&!apiVoiceId)} onClick={runQueue}><Play size={16}/> Hàng chờ ({queue.filter((item)=>item.status!=='completed').length})</button>}
      <button className="primary" disabled={!draft?.rows.length || running || (engine==='capcut'&&!apiVoiceId)} title={engine==='capcut'&&!apiVoiceId?'Đang chờ tải và chọn giọng CapCut':''} onClick={() => run()}>{running ? <><RefreshCw className="spin" size={17} /> {jobState==='paused'?'Đã tạm dừng':`Đang tạo ${progress.done}/${progress.total}`}</> : engine==='capcut'&&!apiVoiceId ? <><RefreshCw className={voiceLibraryLoading?'spin':''} size={17}/> {voiceLibraryLoading?'Đang tải giọng…':'Chọn giọng trước'}</> : <><Play size={17} /> {jobState==='cancelled'?'Tiếp tục phần còn lại':'Tạo voice'}</>}</button>
    </section>
    {voiceLibraryOpen && <section className="api-voice-library"><header><div><strong>Thư viện giọng {engine === 'ai33' ? 'AI33' : engine === 'aimax' ? 'AIMax' : 'CapCut Space'}</strong><small>{engine === 'capcut' ? 'tony2k/ai-voice-studio' : apiProvider} · {apiVoices.length} giọng</small></div><div className="api-voice-search"><Search size={14}/><input value={voiceQuery} onChange={(e)=>setVoiceQuery(e.target.value)} placeholder="Tìm tên hoặc Voice ID"/></div><button onClick={()=>setVoiceLibraryOpen(false)}><X size={16}/></button></header><div className="api-voice-list">{voiceLibraryLoading ? <div className="api-voice-empty"><RefreshCw className="spin"/> Đang tải thư viện…</div> : apiVoices.filter((v)=>`${v.name} ${v.id}`.toLowerCase().includes(voiceQuery.toLowerCase())).map((voice)=><article key={voice.id} className={apiVoiceId === voice.id ? 'selected' : ''}><div className="api-voice-avatar">{voice.name.slice(0,2).toUpperCase()}</div><div><strong>{voice.name}</strong><small>{voice.language || 'Không rõ ngôn ngữ'} · {voice.id}</small></div><button disabled={!voice.previewUrl} onClick={()=>playApiVoice(voice)} title="Nghe thử"><Play size={14}/></button><button className="choose" onClick={()=>chooseApiVoice(voice)}>Chọn</button></article>)}{!voiceLibraryLoading && !apiVoices.length && <div className="api-voice-empty">Không tìm thấy giọng phù hợp hoặc dịch vụ đang tạm ngủ. Hãy thử lại sau.</div>}</div></section>}
    <div className="srt-run-stats"><span>{draft?.rows.length || 0} câu</span><span className="ok">{completed} hoàn thành</span><span className={failed ? 'bad' : ''}>{failed} lỗi</span><div><i style={{ width: `${progress.total ? progress.done / progress.total * 100 : 0}%` }} /></div></div>
    <section className="srt-voice-table"><header><span># / THỜI GIAN</span><span>NỘI DUNG ĐỌC</span><span>TRẠNG THÁI</span><span>THAO TÁC</span></header>{draft?.rows.length ? draft.rows.map((row) => <article key={row.id}><div><b>{String(row.id).padStart(4, '0')}</b><small>{row.start} → {row.end}</small></div><textarea value={row.text} disabled={running} onChange={(e) => updateText(row.id, e.target.value)} /><div className={`voice-row-status ${row.status}`}><strong>{row.status === 'completed' ? 'Hoàn thành' : row.status === 'failed' ? 'Lỗi' : row.status === 'generating' ? 'Đang tạo' : 'Chờ'}</strong><small>{row.duration ? `${row.duration.toFixed(2)} giây` : row.error || `${String(row.id).padStart(4, '0')}.wav`}</small></div><div className="voice-row-actions"><button disabled={!row.file} onClick={() => play(row)} title="Nghe"><Play size={15} /></button><button disabled={running || !row.text.trim()} onClick={() => run(row)} title="Tạo lại"><RefreshCw size={15} /></button></div></article>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>Chưa có dữ liệu SRT</strong><small>Chọn file SRT ở panel bên trái hoặc quét cả thư mục để tạo hàng chờ.</small></div>}</section>
    {dictionaryOpen&&<div className="dictionary-backdrop" onMouseDown={(e)=>{if(e.target===e.currentTarget)setDictionaryOpen(false)}}><section className="dictionary-modal"><header><div><strong>Từ điển phát âm CapCut</strong><small>Thay từ sai hoặc tiếng Anh bằng cách viết để TTS đọc đúng trước khi tạo MP3.</small></div><button onClick={()=>setDictionaryOpen(false)}><X size={18}/></button></header><div className="dictionary-actions"><button onClick={()=>saveDictionary([...pronunciationDictionary,{id:`dict-${Date.now()}`,source:'',target:''}])}>+ Thêm từ</button><button onClick={()=>dictionaryImportRef.current?.click()}><UploadCloud size={14}/> Nhập JSON</button><button onClick={exportDictionary}><Download size={14}/> Xuất JSON</button><button className="apply" onClick={applyDictionaryToDraft}><Check size={14}/> Áp dụng vào SRT</button><input ref={dictionaryImportRef} type="file" accept=".json,application/json" hidden onChange={(e)=>{void importDictionary(e.target.files?.[0]);e.currentTarget.value=''}}/></div><div className="dictionary-head"><span>TỪ GỐC / TIẾNG ANH</span><span>CÁCH VIẾT ĐỂ ĐỌC</span><span/></div><div className="dictionary-list">{pronunciationDictionary.map((item)=><article key={item.id}><input value={item.source} onChange={(e)=>saveDictionary(pronunciationDictionary.map((row)=>row.id===item.id?{...row,source:e.target.value}:row))} placeholder="Ví dụ: Facebook"/><input value={item.target} onChange={(e)=>saveDictionary(pronunciationDictionary.map((row)=>row.id===item.id?{...row,target:e.target.value}:row))} placeholder="Ví dụ: phây búc"/><button title="Xóa" onClick={()=>saveDictionary(pronunciationDictionary.filter((row)=>row.id!==item.id))}><Trash2 size={15}/></button></article>)}{!pronunciationDictionary.length&&<div className="dictionary-empty">Chưa có quy tắc. Bấm “Thêm từ” hoặc nhập file JSON.</div>}</div><footer><span>{pronunciationDictionary.length} quy tắc · tự động áp dụng khi tạo voice</span><button onClick={()=>setDictionaryOpen(false)}>Đóng</button></footer></section></div>}
    {jobPickerOpen&&<div className="dictionary-backdrop" onMouseDown={(e)=>{if(e.target===e.currentTarget)setJobPickerOpen(false)}}><section className="saved-job-modal"><header><div><strong>Mở job tạo voice đã lưu</strong><small>Chỉ tải job khi bạn chủ động chọn.</small></div><button onClick={()=>setJobPickerOpen(false)}><X size={18}/></button></header><div className="saved-job-picker"><select value={selectedJobId} onChange={(e)=>setSelectedJobId(e.target.value)}><option value="">Chọn job muốn mở…</option>{savedJobs.map((job)=><option key={job.jobId} value={job.jobId}>{job.createdAt||job.jobId} · {job.engine} · {job.completed}/{job.total}{job.failed?` · ${job.failed} lỗi`:''}</option>)}</select>{!savedJobs.length&&<p>Chưa có job nào được lưu.</p>}</div><footer><button onClick={()=>{setSelectedJobId('');setDraft(null);setOutputDir('');setProgress({done:0,total:0});setJobState('idle');setJobPickerOpen(false);setMessage('Đã tạo phiên trống. Hãy chọn file SRT mới.');}}>Job mới</button><button className="primary" disabled={!selectedJobId} onClick={async()=>{await loadSavedJob();setJobPickerOpen(false)}}>Tải job đã chọn</button></footer></section></div>}
    <footer className="srt-voice-footer"><strong>{message}</strong><span>3 lượt tổng cộng · lượt đầu + tối đa 2 lượt chạy lại câu lỗi</span></footer>{audioUrl && <audio className="srt-voice-player" src={audioUrl} controls />}{previewUrl && <audio className="api-voice-preview-player" src={previewUrl} controls />}
    {apiSettingsOpen&&<div className="dictionary-backdrop" onMouseDown={(e)=>{if(e.target===e.currentTarget)setApiSettingsOpen(false)}}><section className="dictionary-modal api-key-modal"><header><div><strong>Cấu hình API tạo giọng</strong><small>Key được mã hóa bằng Windows Safe Storage và không ghi dạng rõ vào file cấu hình.</small></div><button onClick={()=>setApiSettingsOpen(false)}><X size={18}/></button></header><div className="lite-api-key-grid"><label><span>AI33 API key · {apiKeyStatus.ai33KeyCount} key đã lưu</span><textarea value={ai33Key} onChange={(e)=>setAi33Key(e.target.value)} placeholder="Mỗi key một dòng. Để trống nếu không thay đổi."/><button disabled={apiKeyBusy} onClick={()=>void testApiKey('ai33')}>Kiểm tra AI33</button></label><label><span>AIMax API key · {apiKeyStatus.aimaxKeyCount} key đã lưu</span><textarea value={aimaxKey} onChange={(e)=>setAimaxKey(e.target.value)} placeholder="Mỗi key một dòng. Để trống nếu không thay đổi."/><button disabled={apiKeyBusy} onClick={()=>void testApiKey('aimax')}>Kiểm tra AIMax</button></label></div><footer><button onClick={()=>setApiSettingsOpen(false)}>Đóng</button><button className="primary" disabled={apiKeyBusy||(!ai33Key.trim()&&!aimaxKey.trim())} onClick={()=>void saveApiKeys()}>{apiKeyBusy?'Đang xử lý…':'Lưu API key'}</button></footer></section></div>}
  </div>;
}

function FfmpegAndCapCutTab() {
  const [videoPath, setVideoPath] = useState('');
  const [srtPath, setSrtPath] = useState('');
  const [voiceDir, setVoiceDir] = useState('');
  const [outputDir, setOutputDir] = useState('');
  const [encoder, setEncoder] = useState('auto');
  const [renderProfile, setRenderProfile] = useState<'weak'|'balanced'|'fast'>('weak');
  const [voiceSpeed, setVoiceSpeed] = useState(1.0);
  const [changePitch, setChangePitch] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
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
    setAnalysis(null); setResult(null);
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
    setRunning(true);setLogs([]);setResult(null);setProgressPercent(0);setMessage('Đang lập kế hoạch đồng bộ…');
    const profileEncoder = renderProfile === 'weak' ? 'x264' : encoder;
    const chunkPieces = renderProfile === 'weak' ? 6 : renderProfile === 'balanced' ? 12 : 24;
    try { const value=await window.desktop.request<{projectName:string;projectPath:string;template:string}>('ffmpeg.sync.create',{videoPath,srtPath,voiceDir,outputDir,projectName:jobName,chunkPieces,encoder:profileEncoder,voiceSpeed,changePitch,videoVolumeDb:-35,mergeAudio:false,renderProfile}); setResult(value);setProgressPercent(100);setMessage(`Hoàn tất: ${value.projectName}`); }
    catch(error){setMessage(error instanceof Error?error.message:String(error));} finally{setRunning(false);}
  };
  return <div className="capcut-project-page" style={{ paddingTop: '10px' }}>
    <div className="capcut-project-hero"><div><h1>Co giãn video theo <span>voice nguyên bản.</span></h1><p>Xuất video đồng bộ độc lập; không ghép audio và không cần mở CapCut.</p></div></div>
    <section className="capcut-input-grid-4">
      <button className={videoPath?'complete':''} onClick={()=>pickFile('video')}><span className="capcut-step">{videoPath?<Check size={12}/>:1}</span><Clapperboard size={22}/><div><small>VIDEO GỐC</small><strong>{fileName(videoPath)||'Chọn video'}</strong><em>{videoPath||'MP4, MOV, MKV…'}</em></div></button>
      <button className={srtPath?'complete':''} onClick={()=>pickFile('srt')}><span className="capcut-step">{srtPath?<Check size={12}/>:2}</span><Captions size={22}/><div><small>PHỤ ĐỀ SRT</small><strong>{fileName(srtPath)||'Chọn file SRT'}</strong><em>{srtPath||'Timestamp bám video'}</em></div></button>
      <button className={voiceDir?'complete':''} onClick={()=>pickFolder('voice')}><span className="capcut-step">{voiceDir?<Check size={12}/>:3}</span><AudioLines size={22}/><div><small>THƯ MỤC VOICE</small><strong>{fileName(voiceDir)||'Chọn thư mục voice'}</strong><em>{voiceDir||'0001.wav, mp3, m4a…'}</em></div></button>
      <button className={outputDir ? 'selected-folder complete' : ''} onClick={()=>pickFolder('output')}><span className="capcut-step">{outputDir?<Check size={12}/>:4}</span><FolderOpen size={22}/><div><small>THƯ MỤC XUẤT</small><strong>{outputDir?fileName(outputDir):'Chọn thư mục xuất'}</strong><em>{outputDir||'Nơi lưu video MP4'}</em></div></button>
    </section>

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
              <strong>Thay đổi cao độ</strong>
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
          <label><small>BỘ MÃ HÓA VIDEO</small><select value={encoder} onChange={(e)=>setEncoder(e.target.value)}><option value="auto">Tự động (GPU tốt nhất)</option><option value="nvenc">NVIDIA NVENC</option><option value="amf">AMD AMF</option><option value="qsv">Intel QSV</option><option value="x264">CPU (libx264)</option></select></label>
        </div>
      </div>
    </div>
    <section className="capcut-progress-panel">
      <header><div><small>TIẾN TRÌNH</small><strong>{message}</strong></div><span>{running?`ĐANG XỬ LÝ (${progressPercent}%)`:result?'HOÀN TẤT':'SẴN SÀNG'}</span></header>
      {(running || progressPercent > 0) && <div className="ffmpeg-progress-bar-container"><div className="ffmpeg-progress-bar-fill" style={{ width: `${progressPercent}%` }} /></div>}
      <div className="capcut-log">{logs.length?logs.map((line,index)=><p key={`${index}-${line}`}>{line}</p>):<p>FFmpeg sẽ xử lý video độc lập mà không cần CapCut.</p>}</div>{result&&<footer><div><Check size={18}/><span><strong>{result.projectName}</strong><small>{result.template} · {result.projectPath}</small></span></div><button onClick={()=>window.desktop?.showInFolder(result.projectPath)}><FolderOpen size={15}/> Mở kết quả</button></footer>}
    </section>
    <section className="sync-sticky-cta"><div><strong>{analysis?.ready?'Đầu vào hợp lệ':message}</strong><small>{analysis?.ready?`${analysis.subtitles} phụ đề · ${analysis.voiceFiles} file voice`:'Hoàn tất 4 bước đầu vào để bắt đầu.'}</small></div><button className="primary" disabled={!analysis?.ready||!outputDir||!jobName.trim()||running} onClick={create}>{running?<><RefreshCw className="spin" size={17}/> Đang render ({progressPercent}%)…</>:<><Zap size={17}/> Đồng bộ & xuất MP4</>}</button></section>
  </div>;
}

function CapCutProjectPage() {
  const [subtab, setSubtab] = useState<'ffmpeg' | 'capcut'>('ffmpeg');
  const [mode, setMode] = useState<'new'|'existing'>('existing');
  const [projects, setProjects] = useState<{name:string;path:string}[]>([]);
  const [projectPath, setProjectPath] = useState('');
  const [videoPath, setVideoPath] = useState('');
  const [srtPath, setSrtPath] = useState('');
  const [voiceDir, setVoiceDir] = useState('');
  const [projectName, setProjectName] = useState(`HHVietSub ${new Date().toLocaleDateString('vi-VN').replaceAll('/', '-')}`);
  const [analysis, setAnalysis] = useState<{ subtitles: number; voiceFiles: number; missing: number[]; ready: boolean } | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn dự án CapCut, file SRT và thư mục voice để kiểm tra ánh xạ.');
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<{ projectName: string; projectPath: string; template: string } | null>(null);
  useEffect(() => { window.desktop?.request<{name:string;path:string}[]>('project.list').then((items)=>{setProjects(items || []);if(items?.length)setProjectPath((value)=>value || items[0].path);}).catch(()=>undefined); }, []);
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const event = raw as { event?: string; data?: { message?: string } };
    if (event.event === 'capcut.project.progress' && event.data?.message) {
      setLogs((current) => [...current.slice(-99), event.data!.message!]);
      setMessage(event.data.message);
    }
  }), []);
  useEffect(() => {
    setAnalysis(null); setResult(null);
    if ((mode === 'new' ? !videoPath : !projectPath) || !srtPath || !voiceDir || !window.desktop) return;
    window.desktop.request<typeof analysis>(mode === 'new' ? 'capcut.project.validate' : 'capcut.project.validate_existing', { videoPath, projectPath, srtPath, voiceDir })
      .then((value) => { setAnalysis(value); setMessage(value?.ready ? `Sẵn sàng: ${value.subtitles} phụ đề ↔ ${value.voiceFiles} voice.` : `Thiếu ${value?.missing.length || 0} file voice.`); })
      .catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [mode, videoPath, projectPath, srtPath, voiceDir]);
  const pick = async (kind: 'video' | 'srt' | 'voice') => {
    if (kind === 'voice') { const path = await window.desktop?.selectFolder(); if (path) setVoiceDir(path); return; }
    const path = await window.desktop?.selectFile({ filters: kind === 'video' ? [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'avi', 'm4v', 'webm'] }] : [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (path) kind === 'video' ? setVideoPath(path) : setSrtPath(path);
  };
  const create = async () => {
    if (!window.desktop || !analysis?.ready || running) return;
    setRunning(true); setLogs([]); setResult(null); setMessage(mode === 'new' ? 'Đang chuẩn bị project mới…' : 'Đang sao lưu và đồng bộ dự án có sẵn…');
    try {
      const created = await window.desktop.request<{ projectName: string; projectPath: string; template: string }>(mode === 'new' ? 'capcut.project.create' : 'capcut.project.sync', { videoPath, projectPath, srtPath, voiceDir, projectName });
      setResult(created); setMessage(`Hoàn tất project: ${created.projectName}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
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
      <section className="capcut-mode-switch"><button className={mode === 'existing' ? 'selected' : ''} onClick={()=>setMode('existing')}><Clapperboard size={18}/><span><strong>Dự án có sẵn</strong><small>Giữ media, effect và chỉnh sửa hiện tại</small></span></button><button className={mode === 'new' ? 'selected' : ''} onClick={()=>setMode('new')}><Sparkles size={18}/><span><strong>Tạo dự án mới</strong><small>Bắt đầu từ video gốc và SRT</small></span></button></section>
      <section className="capcut-input-grid">
        {mode === 'new' ? <button onClick={() => pick('video')}><span className="capcut-step">1</span><Clapperboard size={23} /><div><small>VIDEO GỐC</small><strong>{fileName(videoPath) || 'Chọn video'}</strong><em>{videoPath || 'MP4, MOV, MKV…'}</em></div></button> : <label className="capcut-project-picker"><span className="capcut-step">1</span><Clapperboard size={23}/><div><small>DỰ ÁN CAPCUT CÓ SẴN</small><select value={projectPath} onChange={(e)=>setProjectPath(e.target.value)}><option value="">Chọn dự án…</option>{projects.map((project)=><option key={project.path} value={project.path}>{project.name}</option>)}</select><em>{projectPath || 'Không tìm thấy dự án CapCut'}</em></div></label>}
        <button onClick={() => pick('srt')}><span className="capcut-step">2</span><Captions size={23} /><div><small>PHỤ ĐỀ SRT</small><strong>{fileName(srtPath) || 'Chọn file SRT'}</strong><em>{srtPath || 'Timestamp dùng để chia video'}</em></div></button>
        <button onClick={() => pick('voice')}><span className="capcut-step">3</span><AudioLines size={23} /><div><small>THƯ MỤC VOICE</small><strong>{fileName(voiceDir) || 'Chọn thư mục voice'}</strong><em>{voiceDir || '0001.wav, 0002.wav…'}</em></div></button>
      </section>
      <section className={`capcut-project-settings ${mode === 'existing' ? 'existing' : ''}`}>{mode === 'new' && <label><small>TÊN DỰ ÁN MỚI</small><input value={projectName} onChange={(e) => setProjectName(e.target.value)} /></label>}<div className={`capcut-readiness ${analysis?.ready ? 'ready' : analysis ? 'warning' : ''}`}><Check size={18} /><span><strong>{analysis ? `${analysis.voiceFiles}/${analysis.subtitles} voice đã khớp` : 'Chưa kiểm tra đầu vào'}</strong><small>{analysis?.missing.length ? `Thiếu: ${analysis.missing.slice(0, 12).map((id) => String(id).padStart(4, '0')).join(', ')}` : mode === 'existing' ? 'JSON dự án sẽ được sao lưu trước khi đồng bộ.' : 'Dự án mới sẽ được lưu vào thư mục CapCut mặc định.'}</small></span></div></section>
      <section className="capcut-flow"><div><span>1</span><strong>{mode === 'existing' ? 'Sao lưu dự án' : 'Tạo project mới'}</strong><small>{mode === 'existing' ? 'Snapshot JSON an toàn' : 'Sinh schema CapCut sạch'}</small></div><i>→</i><div><span>2</span><strong>Ghép SRT + voice</strong><small>0001.wav ↔ câu 0001</small></div><i>→</i><div><span>3</span><strong>Cắt video</strong><small>Theo từng block phụ đề</small></div><i>→</i><div><span>4</span><strong>Đồng bộ</strong><small>Voice quyết định timeline</small></div></section>
      <section className="capcut-progress-panel"><header><div><small>TIẾN TRÌNH</small><strong>{message}</strong></div><span>{running ? 'ĐANG XỬ LÝ' : result ? 'HOÀN TẤT' : 'SẴN SÀNG'}</span></header><div className="capcut-log">{logs.length ? logs.map((line, index) => <p key={`${index}-${line}`}>{line}</p>) : <p>Chưa có tác vụ. Tool sẽ yêu cầu đóng CapCut trước khi ghi project.</p>}</div>{result && <footer><div><Check size={18} /><span><strong>{result.projectName}</strong><small>{result.template} · {result.projectPath}</small></span></div><button onClick={() => window.desktop?.showInFolder(result.projectPath)}><FolderOpen size={15} /> Mở thư mục</button><button className="open-capcut" onClick={() => window.desktop?.request('capcut.open')}><Clapperboard size={15} /> Mở CapCut</button></footer>}</section>
      <section className="sync-sticky-cta"><div><strong>{analysis?.ready?'Dự án đã sẵn sàng':message}</strong><small>CapCut sẽ được yêu cầu đóng trước khi cập nhật project.</small></div><button className="primary" disabled={!analysis?.ready || running} onClick={create}>{running ? <><RefreshCw className="spin" size={17} /> Đang đồng bộ…</> : <><Sparkles size={17} /> Thêm voice & đồng bộ</>}</button></section>
    </>}
  </div>;
}

type ApiSavedState = {
  ai33Configured: boolean;
  aimaxConfigured: boolean;
  ai33KeyCount?: number;
  aimaxKeyCount?: number;
};

type LocalModelItem = {
  id: string;
  repo: string;
  name: string;
  size: string;
  description: string;
  required: boolean;
  ready: boolean;
  status: 'not_downloaded' | 'downloading' | 'ready' | 'error';
  sizeOnDisk: string;
  localPath?: string;
};

function VoiceBackendSettings() {
  const [mode, setMode] = useState<'local' | 'colab'>('local');
  const [url, setUrl] = useState(''); const [token, setToken] = useState('');
  const [tokenConfigured, setTokenConfigured] = useState(false);
  const [message, setMessage] = useState('Chọn nơi thực hiện suy luận OmniVoice.'); const [testing, setTesting] = useState(false);
  const [ai33Key, setAi33Key] = useState(''); const [aimaxKey, setAimaxKey] = useState('');
  const [apiSaved, setApiSaved] = useState<ApiSavedState>({ ai33Configured: false, aimaxConfigured: false, ai33KeyCount: 0, aimaxKeyCount: 0 });
  const [models, setModels] = useState<LocalModelItem[]>([]);
  const [modelMsg, setModelMsg] = useState('');

  const loadModels = () => {
    window.desktop?.request<LocalModelItem[]>('models.list').then((res) => {
      if (Array.isArray(res)) setModels(res);
    });
  };

  useEffect(() => { window.desktop?.request<{ voiceBackend?: { mode: 'local' | 'colab'; url: string; token: string; tokenConfigured?: boolean } }>('settings.get').then((v) => {
    if (v.voiceBackend) { setMode(v.voiceBackend.mode); setUrl(v.voiceBackend.url); setTokenConfigured(Boolean(v.voiceBackend.tokenConfigured)); }
  }); }, []);
  useEffect(() => {
    window.desktop?.request<ApiSavedState>('settings.tts.get').then((res) => {
      if (res) {
        setApiSaved(res);
      }
    });
    loadModels();
    const unsub = window.desktop?.onBackendEvent((evt: any) => {
      if (evt?.event === 'model.progress' && evt?.data) {
        const { modelId, status, message: msg } = evt.data;
        if (msg) setModelMsg(msg);
        setModels((prev) =>
          prev.map((m) => (m.id === modelId ? { ...m, status, ready: status === 'ready' } : m))
        );
        if (status === 'ready' || status === 'error') {
          setTimeout(loadModels, 1000);
        }
      }
    });
    return () => { unsub?.(); };
  }, []);

  const downloadModel = async (modelId: string) => {
    try {
      setModelMsg('Đang gửi lệnh tải model...');
      setModels((prev) => prev.map((m) => (m.id === modelId ? { ...m, status: 'downloading' } : m)));
      await window.desktop?.request('models.download', { modelId });
    } catch (e) {
      setModelMsg(e instanceof Error ? e.message : String(e));
      loadModels();
    }
  };

  const deleteModel = async (modelId: string) => {
    try {
      await window.desktop?.request('models.delete', { modelId });
      setModelMsg('Đã xóa cache model.');
      loadModels();
    } catch (e) {
      setModelMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const save = async () => { try { await window.desktop?.request('settings.voice.save', { mode, url, token }); if (token.trim()) { setTokenConfigured(true); setToken(''); } setMessage('Đã lưu cấu hình backend giọng nói.'); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } };
  const test = async () => { setTesting(true); try { const r = await window.desktop?.request<{ device?: string | null; status?: string | null; detail?: string | null }>('settings.voice.test', { mode, url, token }); if (!r) throw new Error('Backend Electron chưa sẵn sàng.'); const device = (r.device || 'GPU').toUpperCase(); setMessage(`Kết nối thành công · ${device} · ${r.status || 'sẵn sàng'}${r.detail ? ` · ${r.detail}` : ''}`); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } finally { setTesting(false); } };
  const saveApi = async () => {
    try {
      const saved = await window.desktop?.request<ApiSavedState>('settings.tts.save', { ai33Key, aimaxKey });
      if (saved) setApiSaved(saved);
      setMessage(`Đã lưu danh sách API key (AI33: ${saved?.ai33KeyCount || 0} keys, AIMax: ${saved?.aimaxKeyCount || 0} keys).`);
    } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); }
  };
  const testApi = async (provider: 'ai33'|'aimax') => {
    try {
      const res = await window.desktop?.request<{ ok: boolean; validKeys?: number; totalKeys?: number }>('settings.tts.test', { provider, key: provider === 'ai33' ? ai33Key : aimaxKey });
      const updated = await window.desktop?.request<ApiSavedState>('settings.tts.get');
      if (updated) setApiSaved(updated);
      setMessage(`Kiểm tra ${provider === 'ai33' ? 'AI33' : 'AIMax'} thành công: ${res?.validKeys ?? 1}/${res?.totalKeys ?? 1} key hợp lệ.`);
    } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); }
  };

  return <div className="voice-backend-page"><div className="settings-hero"><div className="eyebrow"><Settings2 size={15}/> CẤU HÌNH ỨNG DỤNG</div><h1>Thiết lập cấu hình</h1><p>Chọn bộ xử lý OmniVoice cho Phòng thu và Tạo từ SRT.</p></div>
    <section className="voice-backend-card"><header><AudioLines size={23}/><div><h2>Cấu hình Bộ xử lý (Backend)</h2><p>Chạy trên máy hoặc dùng GPU Google Colab cho máy cấu hình yếu.</p></div></header>
      <div className="backend-options"><button className={mode === 'local' ? 'selected' : ''} onClick={() => setMode('local')}><b>○</b><strong>Chạy cục bộ (Local GPU/CPU)</strong><small>Riêng tư, offline; sử dụng phần cứng của máy.</small></button><button className={mode === 'colab' ? 'selected' : ''} onClick={() => setMode('colab')}><b>○</b><strong>Google Colab (Remote GPU)</strong><small>Tạo giọng trên GPU Colab, kết quả vẫn lưu về máy.</small></button></div>
      {mode === 'colab' && <div className="colab-config"><div><strong>Đường dẫn API Google Colab</strong><a href="https://colab.research.google.com/github/nguyenduchung98/HHVietSub-Colab/blob/main/HHVietSub_Colab.ipynb" target="_blank" rel="noreferrer">Mở Colab Notebook ↗</a></div><ol><li>Chọn Runtime → Change runtime type → GPU.</li><li>Run all và chờ hiện cả URL lẫn TOKEN.</li><li>Dán đầy đủ URL và TOKEN, kiểm tra kết nối rồi lưu.</li></ol><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://xxx.trycloudflare.com"/><input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={tokenConfigured ? 'Token đã lưu an toàn · nhập để thay đổi' : 'Token bảo mật (bắt buộc)'}/><button onClick={test} disabled={testing || !url.trim() || (!token.trim() && !tokenConfigured)}>{testing ? 'Đang kiểm tra…' : 'Kiểm tra kết nối'}</button></div>}
      <footer><span>{message}</span><button className="primary" onClick={save}>Lưu cấu hình</button></footer></section>

    <section className="voice-backend-card model-manager-card">
      <header>
        <DownloadCloud size={23} />
        <div>
          <h2>Quản lý & Tải Model Giọng nói (Local Models)</h2>
          <p>Tải các mô hình AI cần thiết khi sử dụng chế độ Cục bộ (Local offline).</p>
        </div>
      </header>
      <div className="model-grid">
        {models.map((m) => (
          <div key={m.id} className={`model-item-card ${m.ready ? 'ready' : ''}`}>
            <div className="model-info">
              <div className="model-header">
                <strong>{m.name}</strong>
                {m.required && <span className="badge-required">BẮT BỤC</span>}
                <span className={`badge-status ${m.status}`}>
                  {m.status === 'ready' ? `🟢 Đã sẵn sàng (${m.sizeOnDisk})` : m.status === 'downloading' ? '⏳ Đang tải...' : '⚪ Chưa tải'}
                </span>
              </div>
              <p>{m.description}</p>
              <small className="model-repo">Repo: {m.repo} · Kích thước: ~{m.size}</small>
            </div>
            <div className="model-actions">
              {m.status === 'downloading' ? (
                <button disabled className="btn-downloading"><Loader2 className="spin" size={15} /> Đang tải...</button>
              ) : m.ready ? (
                <button onClick={() => deleteModel(m.id)} className="btn-delete"><Trash2 size={14} /> Xóa cache ({m.sizeOnDisk})</button>
              ) : (
                <button onClick={() => downloadModel(m.id)} className="btn-download primary"><DownloadCloud size={15} /> Tải về ({m.size})</button>
              )}
            </div>
          </div>
        ))}
      </div>
      {modelMsg && <footer><span className="model-msg">{modelMsg}</span></footer>}
    </section>

    <section className="voice-backend-card api-key-card"><header><AudioLines size={23}/><div><h2>API tạo giọng từ phụ đề (Phân tải Đa Key)</h2><p>Có thể nhập nhiều API key (mỗi key 1 dòng). Hệ thống tự động xoay vòng chia đều luồng gửi API để tăng tốc và tránh 429 Rate Limit.</p></div></header><div className="api-key-grid"><label><div className="api-key-header"><strong>AI33 API Keys</strong>{apiSaved.ai33KeyCount ? <span className="api-key-badge">{apiSaved.ai33KeyCount} Keys</span> : null}</div><textarea value={ai33Key} onChange={(e)=>setAi33Key(e.target.value)} placeholder="Nhập 1 hoặc nhiều xi-api-key (mỗi key 1 dòng)..."/><button onClick={()=>testApi('ai33')}>Kiểm tra AI33 ({apiSaved.ai33KeyCount || 0} Key)</button></label><label><div className="api-key-header"><strong>AIMax API Keys</strong>{apiSaved.aimaxKeyCount ? <span className="api-key-badge">{apiSaved.aimaxKeyCount} Keys</span> : null}</div><textarea value={aimaxKey} onChange={(e)=>setAimaxKey(e.target.value)} placeholder="Nhập 1 hoặc nhiều X-API-Key (mỗi key 1 dòng)..."/><button onClick={()=>testApi('aimax')}>Kiểm tra AIMax ({apiSaved.aimaxKeyCount || 0} Key)</button></label></div><footer><span>{message}</span><button className="primary" onClick={saveApi}>Lưu danh sách API Key</button></footer></section></div>;
}

function Placeholder({ page, label }: { page: Page; label: string }) {
  const descriptions: Record<Page, string> = { studio: '', translate: '', srt: 'Tải file SRT và tạo giọng nói khớp theo từng mốc thời gian.', capcut: '', settings: 'Quản lý backend, model OmniVoice, định dạng audio và thư mục đầu ra.' };
  return <div className="placeholder"><div className="upload-icon">{page === 'srt' ? <UploadCloud size={32} /> : <Settings2 size={32} />}</div><div className="eyebrow">{page === 'srt' ? 'KHỚP THỜI GIAN CHÍNH XÁC' : 'CẤU HÌNH ỨNG DỤNG'}</div><h1>{label}</h1><p>{descriptions[page]}</p>{page === 'srt' && <button className="primary"><Captions size={17} /> Chọn tệp SRT</button>}</div>;
}
