import { useEffect, useMemo, useState } from 'react';
import './studio-v2.css';
import './voice-modal.css';
import './studio-layout.css';
import './generation-side.css';
import './focused-workspace.css';
import './translate-complete.css';
import './translate-toolbar-v2.css';
import './srt-voice-v1.css';
import './capcut-project-v1.css';
import './voice-backend-settings.css';
import { AudioLines, Captions, Check, ChevronDown, CircleHelp, Clapperboard, Download, FileText, FolderOpen, Languages, Mic2, MoreHorizontal, Play, RefreshCw, Search, Settings2, Sparkles, Trash2, UploadCloud, Volume2, X } from 'lucide-react';

type Page = 'studio' | 'translate' | 'srt' | 'capcut' | 'settings';
type Voice = { id: string; name: string; language: string; ready: boolean; source: string };
type StudioResult = { id: string; path: string; name: string; bytes: number; duration: number; generationTime: number; seed: number; format: string; voiceId: string; voiceName: string; language: string; text: string; createdAt: string; srtPath?: string };
type SrtVoiceRow = { id: number; start: string; end: string; text: string; status: 'pending' | 'generating' | 'completed' | 'failed'; duration?: number; file?: string; error?: string };
type SrtDraft = { name: string; path: string; rows: SrtVoiceRow[] };
type ApiVoice = { id: string; name: string; previewUrl?: string; language?: string; provider?: string; personal?: boolean };

const cleanUnicode = (value: string) => new TextDecoder().decode(new TextEncoder().encode(value));

const nav: { id: Page; label: string; icon: typeof Sparkles }[] = [
  { id: 'studio', label: 'Phòng thu', icon: AudioLines },
  { id: 'translate', label: 'Dịch phụ đề', icon: Languages },
  { id: 'srt', label: 'Tạo từ SRT', icon: FileText },
  { id: 'capcut', label: 'Dự án CapCut', icon: Clapperboard },
  { id: 'settings', label: 'Cấu hình', icon: Settings2 },
];

const sampleVoices: Voice[] = [
  { id: 'ban-mai', name: 'Ban Mai', language: 'Tiếng Việt', ready: true, source: 'OmniVoice' },
  { id: 'lan-trinh', name: 'Lan Trinh', language: 'Tiếng Việt', ready: true, source: 'OmniVoice' },
  { id: 'story', name: 'Story', language: 'English', ready: true, source: 'OmniVoice' },
];

export function App() {
  const [page, setPage] = useState<Page>('studio');
  const [online, setOnline] = useState(false);
  const [voices, setVoices] = useState<Voice[]>(sampleVoices);
  const [query, setQuery] = useState('');
  const [selectedVoice, setSelectedVoice] = useState('ban-mai');
  const [text, setText] = useState('Dich CapCut Studio giúp bạn biến phụ đề thành giọng nói và đồng bộ trực tiếp với dự án CapCut.');
  const [voiceModal, setVoiceModal] = useState(false);
  const [studioHistory, setStudioHistory] = useState<StudioResult[]>([]);
  const [srtDraft, setSrtDraft] = useState<SrtDraft | null>(null);
  const loadVoices = () => window.desktop?.request<Voice[]>('voice.list').then(setVoices).catch(() => undefined);
  const loadStudioHistory = () => window.desktop?.request<StudioResult[]>('studio.history').then(setStudioHistory).catch(() => undefined);

  useEffect(() => {
    if (!window.desktop) return;
    window.desktop.request<{ online: boolean }>('system.ping').then((v) => setOnline(v.online)).catch(() => setOnline(false));
    loadVoices();
    loadStudioHistory();
    return window.desktop.onBackendEvent((raw) => {
      const event = raw as { event?: string; data?: { online?: boolean } };
      if (event.event === 'backend.state') setOnline(Boolean(event.data?.online));
    });
  }, []);

  const filteredVoices = useMemo(() => voices.filter((voice) => voice.name.toLowerCase().includes(query.toLowerCase())), [voices, query]);
  const pageLabel = nav.find((item) => item.id === page)?.label ?? 'Phòng thu';

  const focusedWorkspace = page === 'translate' || page === 'srt' || page === 'capcut';
  return <div className={`app-shell ${focusedWorkspace ? 'focused-workspace' : ''}`}>
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><AudioLines size={23} /></div><div><strong>Dich CapCut</strong><span>AI LOCAL STUDIO</span></div></div>
      <nav className="nav-pills">{nav.map((item) => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => setPage(item.id)}><item.icon size={15} />{item.label}</button>)}</nav>
      <div className="top-actions"><span className={`backend-state ${online ? 'online' : ''}`}><i />{online ? 'Backend sẵn sàng' : 'Chế độ xem trước'}</span><button className="icon-button"><RefreshCw size={17} /></button><button className="icon-button"><CircleHelp size={18} /></button><div className="avatar">DC</div></div>
    </header>

    {!focusedWorkspace && <aside className="sidebar">
      <div className="eyebrow">THƯ VIỆN GIỌNG</div><div className="side-title"><h2>Giọng của bạn</h2><button title="Thêm giọng" onClick={() => setVoiceModal(true)}>+</button></div>
      <label className="search"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm kiếm giọng" /></label>
      <div className="section-caption">GIỌNG OMNIVOICE</div>
      <div className="project-list">{filteredVoices.length ? filteredVoices.map((voice, i) => <button className={`project-card ${voice.id === selectedVoice ? 'selected' : ''}`} key={voice.id} onClick={() => setSelectedVoice(voice.id)}><span className={`project-icon tone-${i % 4}`}>{voice.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase()}</span><span><strong>{voice.name}</strong><small>{voice.language}</small></span><Volume2 size={15} /></button>) : <div className="empty-small"><AudioLines size={25} /><span>Chưa tìm thấy giọng</span><small>Thêm audio mẫu để tạo hồ sơ giọng mới.</small></div>}</div>
      <div className="privacy"><span>✓</span><div><strong>Riêng tư ngay từ thiết kế</strong><small>Audio và dự án chỉ lưu trên thiết bị này.</small></div></div>
    </aside>}

    <main className="workspace">{page === 'studio' ? <Studio voices={voices} selectedVoice={selectedVoice} setSelectedVoice={setSelectedVoice} text={text} setText={setText} onHistoryChange={loadStudioHistory} /> : page === 'translate' ? <TranslatePage onSendToSrt={(draft) => { setSrtDraft(draft); setPage('srt'); }} /> : page === 'srt' ? <SrtVoicePage voices={voices} initialDraft={srtDraft} /> : page === 'capcut' ? <CapCutProjectPage /> : <VoiceBackendSettings />}</main>

    {!focusedWorkspace && <GenerationHistoryPanel history={studioHistory} refresh={loadStudioHistory} />}
    {voiceModal && <VoiceModal onClose={() => setVoiceModal(false)} onCreated={async (voice) => { await loadVoices(); setSelectedVoice(voice.id); setPage('studio'); setVoiceModal(false); }} />}
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
        <div className="voice-form-grid"><label><span>Ngôn ngữ trong audio</span><select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="auto">Tự động</option><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label><label><span>Bản chép lời tham chiếu <i>không bắt buộc</i></span><input value={refText} onChange={(e) => setRefText(cleanUnicode(e.target.value))} placeholder="Nội dung được nói trong audio?" /></label></div>
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
  const [model, setModel] = useState('3.1 Pro');
  const [gemUrl, setGemUrl] = useState(() => localStorage.getItem('hhvietsub.gemUrl') || 'https://gemini.google.com/gem/1C0dbBamFcx7CUGXr5bTL48p1A6HX6sgw?usp=sharing');
  const [batchSize, setBatchSize] = useState(200);
  const [workers, setWorkers] = useState(1);
  const [savedGems, setSavedGems] = useState<{ name: string; url: string }[]>([]);
  const [selectedGem, setSelectedGem] = useState('');
  const [profileReady, setProfileReady] = useState(false);
  const [glossary, setGlossary] = useState('');
  const [showOptions, setShowOptions] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [filePath, setFilePath] = useState('');
  const [fileName, setFileName] = useState('');
  const [message, setMessage] = useState('Chọn một file SRT để bắt đầu.');
  const [rows, setRows] = useState<SubtitleRow[]>([]);
  useEffect(() => {
    window.desktop?.request<{ gemini?: { url: string; saved: { name: string; url: string }[]; selected: string; models: string[]; model: string; batch: number; workers: number; profileReady: boolean } }>('settings.get').then((settings) => {
      if (!settings.gemini) return;
      setGemUrl(settings.gemini.url); setSavedGems(settings.gemini.saved); setSelectedGem(settings.gemini.selected);
      setModel(settings.gemini.model); setBatchSize(settings.gemini.batch); setWorkers(settings.gemini.workers); setProfileReady(settings.gemini.profileReady);
    }).catch(() => undefined);
  }, []);
  const openSrt = async () => {
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
  const saveSrt = async () => {
    if (!window.desktop || !filePath || !rows.length) return setMessage('Chưa có phụ đề để lưu.');
    try {
      const result = await window.desktop.request<{ path: string; entries: number }>('subtitle.save', { sourcePath: filePath, entries: rows });
      setMessage(`Đã lưu ${result.entries} câu: ${result.path}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const startTranslation = async () => {
    if (!window.desktop || !rows.length || translating) return;
    if (!gemUrl.trim()) { setShowOptions(true); setMessage('Vui lòng nhập link Gem.'); return; }
    localStorage.setItem('hhvietsub.gemUrl', gemUrl.trim());
    setTranslating(true);
    try {
      setMessage(`Đang mở Gem và gửi ${Math.ceil(rows.length / batchSize)} chunk…`);
      const response = await window.desktop.translateWithGem<{ results: { id: number; translated: string }[]; chunks: number }>({
        gemUrl: gemUrl.trim(), modelName: model, batchSize, workers, sourceLanguage: 'Auto', targetLanguage: 'Tiếng Việt', glossary,
        entries: rows.map((row) => ({ id: row.id, text: row.source })),
      });
      const translatedMap = new Map(response.results.map((item) => [item.id, item.translated]));
      setRows((current) => current.map((row) => translatedMap.has(row.id) ? { ...row, translated: translatedMap.get(row.id)! } : row));
      setMessage(`Hoàn tất ${response.results.length}/${rows.length} câu trong ${response.chunks} chunk.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setTranslating(false); }
  };
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => { if (event.ctrlKey && event.key === 'Enter') { event.preventDefault(); void startTranslation(); } };
    window.addEventListener('keydown', shortcut); return () => window.removeEventListener('keydown', shortcut);
  });
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const event = raw as { event?: string; data?: { done?: number; total?: number; chunk?: number; worker?: number; attempt?: number } };
    if (event.event !== 'translation.progress' || !event.data) return;
    setMessage(`Đang dịch chunk ${event.data.chunk}/${event.data.total} · tab ${event.data.worker}${event.data.attempt ? ` · lần ${event.data.attempt}` : ''}`);
  }), []);
  const updateRow = (id: number, field: 'source' | 'translated', value: string) => setRows((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row));
  const characterCount = rows.reduce((sum, row) => sum + row.source.length, 0);
  const translatedCount = rows.filter((row) => row.translated.trim()).length;
  return <div className="translate-page">
    <div className="translate-hero"><div><div className="eyebrow"><Languages size={14} /> DỊCH PHỤ ĐỀ THÔNG MINH</div><h1>Dịch SRT <span>nhanh và nhất quán.</span></h1><p>Giữ nguyên timestamp, gửi chunk qua Gemini Gem và kiểm tra từng câu trước khi lưu.</p></div><div className="translate-hero-actions"><button className="secondary" onClick={() => onSendToSrt({ name: fileName || 'Bản dịch', path: filePath, rows: rows.map((row) => ({ id: row.id, start: row.start, end: row.end, text: row.translated.trim() || row.source, status: 'pending' })) })} disabled={!rows.length}><AudioLines size={16} /> Tạo giọng</button><button className="secondary" onClick={saveSrt} disabled={!rows.length}><Download size={16} /> Lưu bản dịch</button><button className="primary" disabled={!rows.length || translating} onClick={startTranslation}>{translating ? <><RefreshCw className="spin" size={17} /> Gem đang dịch…</> : <><Languages size={17} /> Mở Gem & dịch</>}</button></div></div>
    <div className="translate-toolbar">
      <button className="file-drop" onClick={openSrt}><UploadCloud size={20} /><span><strong>{fileName || 'Chọn tệp phụ đề SRT'}</strong><small>{fileName ? 'Bấm để chọn tệp khác' : 'Kéo thả hoặc bấm để tải tệp'}</small></span></button>
      <label><small>GEM ĐÃ LƯU</small><select value={selectedGem} onChange={(e) => { const name = e.target.value; setSelectedGem(name); const gem = savedGems.find((item) => item.name === name); if (gem) setGemUrl(gem.url); }}><option value="">Chọn Gem</option>{savedGems.map((gem) => <option key={gem.name}>{gem.name}</option>)}</select></label>
      <label><small>MÔ HÌNH GEMINI</small><select value={model} onChange={(e) => setModel(e.target.value)}><option>3.1 Pro</option><option>3.5 Flash</option><option>3.1 Flash-Lite</option></select></label>
      <label><small>BLOCK / CHUNK</small><input type="number" min="1" max="300" value={batchSize} onChange={(e) => setBatchSize(Math.max(1, Math.min(300, Number(e.target.value) || 1)))} /></label>
      <label><small>SỐ LUỒNG / TAB</small><select value={workers} onChange={(e) => setWorkers(Number(e.target.value))}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></select></label>
    </div>
    <div className="translation-stats"><span><strong>{rows.length}</strong> câu</span><span><strong>{Math.ceil(rows.length / batchSize)}</strong> chunk</span><span><strong>{translatedCount}</strong> đã dịch</span><span className={profileReady ? 'success' : 'profile-warning'}><Check size={13} /> {profileReady ? 'Chrome đã đăng nhập' : 'Chưa có profile'}</span><button onClick={() => setShowOptions(!showOptions)}><Settings2 size={15} /> Kết nối & từ điển</button></div>
    {showOptions && <section className="translation-options browser-options"><label><span>Link Gemini Gem</span><input value={gemUrl} onChange={(e) => setGemUrl(e.target.value)} placeholder="https://gemini.google.com/gem/..." /><small>Electron điều khiển Chrome trực tiếp bằng CDP, không dùng Selenium.</small></label><div className="gem-browser-actions"><button onClick={() => window.desktop?.loginGem()}>Đăng nhập Google</button><button onClick={() => window.desktop?.openGem(gemUrl)}>Mở Gem kiểm tra</button></div><label><span>Thuật ngữ bổ sung</span><textarea value={glossary} onChange={(e) => setGlossary(e.target.value)} placeholder="Mỗi dòng một quy tắc thuật ngữ" /></label></section>}
    <section className={`subtitle-table ${translating ? 'is-translating' : ''}`}><div className="subtitle-head"><span># / THỜI GIAN</span><span>NỘI DUNG GỐC</span><span>BẢN DỊCH TIẾNG VIỆT</span></div>{rows.length ? rows.map((row) => <div className="subtitle-row" key={row.id}><div><b>{String(row.id).padStart(2, '0')}</b><small>{row.start} → {row.end}</small></div><textarea value={row.source} onChange={(e) => updateRow(row.id, 'source', e.target.value)} /><textarea className={row.translated.length > row.source.length * 1.8 ? 'length-warning' : ''} value={row.translated} placeholder={translating ? 'Đang dịch…' : 'Chưa dịch'} onChange={(e) => updateRow(row.id, 'translated', e.target.value)} /></div>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>Chưa có phụ đề</strong><small>Chọn file SRT để hiển thị nội dung tại đây.</small></div>}</section>
    <div className="translation-footer"><div><strong>{message}</strong><small>Gem nhận từng chunk dạng #id, kiểm tra ánh xạ 1:1 và tự retry câu thiếu.</small></div><span className="shortcut-hint">Ctrl ↵ để dịch</span></div>
  </div>;
}

function SrtVoicePage({ voices, initialDraft }: { voices: Voice[]; initialDraft: SrtDraft | null }) {
  const [engine, setEngine] = useState<'omnivoice' | 'ai33' | 'aimax'>('omnivoice');
  const [apiProvider, setApiProvider] = useState('minimax');
  const [apiModel, setApiModel] = useState('speech-2.8-hd');
  const [apiVoiceId, setApiVoiceId] = useState('');
  const [apiWorkers, setApiWorkers] = useState(3);
  const [apiVoices, setApiVoices] = useState<ApiVoice[]>([]);
  const [voiceLibraryOpen, setVoiceLibraryOpen] = useState(false);
  const [voiceLibraryLoading, setVoiceLibraryLoading] = useState(false);
  const [voiceQuery, setVoiceQuery] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [draft, setDraft] = useState<SrtDraft | null>(initialDraft);
  const [voiceId, setVoiceId] = useState(() => voices.find((voice) => voice.ready)?.id || '');
  const [outputDir, setOutputDir] = useState('');
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn file SRT hoặc lấy bản dịch từ tab Dịch.');
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [speed, setSpeed] = useState(1);
  const [steps, setSteps] = useState(32);
  const [guidance, setGuidance] = useState(2);
  const [audioUrl, setAudioUrl] = useState('');
  useEffect(() => { if (initialDraft) { setDraft(initialDraft); setMessage(`Đã nhận ${initialDraft.rows.length} câu từ tab Dịch.`); } }, [initialDraft]);
  useEffect(() => { if (!voiceId && voices.length) setVoiceId(voices.find((voice) => voice.ready)?.id || ''); }, [voices, voiceId]);
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const packet = raw as { event?: string; data?: { event?: string; done?: number; total?: number; id?: number; attempt?: number; item?: SrtVoiceRow } };
    if (packet.event !== 'srt.voice.progress' || !packet.data) return;
    const data = packet.data;
    if (data.event === 'model') setMessage('Đang nạp mô hình OmniVoice…');
    if (data.event === 'attempt' && data.id) {
      setMessage(`Đang tạo câu ${String(data.id).padStart(4, '0')} · lần ${data.attempt}/3`);
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === data.id ? { ...row, status: 'generating' } : row) } : current);
    }
    if (data.event === 'progress' && data.item) {
      setProgress({ done: data.done || 0, total: data.total || 0 });
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === data.item!.id ? { ...row, ...data.item } : row) } : current);
    }
  }), []);
  const chooseSrt = async () => {
    const path = await window.desktop?.selectFile({ filters: [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (!path || !window.desktop) return;
    try {
      const result = await window.desktop.request<{ path: string; name: string; entries: { id: number; start: string; end: string; source: string }[]; warnings: string[] }>('subtitle.parse', { path });
      setDraft({ name: result.name, path: result.path, rows: result.entries.map((row) => ({ id: row.id, start: row.start, end: row.end, text: row.source, status: 'pending' })) });
      setOutputDir(''); setProgress({ done: 0, total: result.entries.length });
      setMessage(`Đã tải ${result.entries.length} câu${result.warnings.length ? ` · ${result.warnings.length} cảnh báo` : ''}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const chooseOutput = async () => {
    const folder = await window.desktop?.selectFolder();
    if (!folder || !draft) return;
    const stem = draft.name.replace(/\.srt$/i, '').replace(/[<>:"/\\|?*]+/g, '-').trim() || 'subtitle';
    setOutputDir(`${folder}\\${stem}_voice`);
  };
  const updateText = (id: number, text: string) => setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === id ? { ...row, text, status: row.status === 'completed' ? 'pending' : row.status } : row) } : current);
  const loadApiVoices = async () => {
    if (!window.desktop || engine === 'omnivoice') return;
    setVoiceLibraryOpen(true); setVoiceLibraryLoading(true); setApiVoices([]);
    try {
      const result = await window.desktop.request<{ voices: ApiVoice[]; total: number }>('tts.voices.list', { engine, provider: apiProvider });
      setApiVoices(result.voices); setMessage(`Đã tải ${result.total} giọng từ ${engine === 'ai33' ? 'AI33' : 'AIMax'}.`);
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
  const run = async (only?: SrtVoiceRow) => {
    if (!window.desktop || !draft || running) return;
    if (engine === 'omnivoice' && !voiceId) return setMessage('Hãy chọn một hồ sơ giọng OmniVoice hoàn chỉnh.');
    if (engine !== 'omnivoice' && !apiVoiceId.trim()) return setMessage('Hãy nhập Voice ID của dịch vụ API.');
    let destination = outputDir;
    if (!destination) {
      const folder = await window.desktop.selectFolder();
      if (!folder) return;
      const stem = draft.name.replace(/\.srt$/i, '').replace(/[<>:"/\\|?*]+/g, '-').trim() || 'subtitle';
      destination = `${folder}\\${stem}_voice`; setOutputDir(destination);
    }
    const entries = only ? [only] : draft.rows.filter((row) => row.text.trim());
    setRunning(true); setProgress({ done: 0, total: entries.length });
    try {
      const result = await window.desktop.request<{ completed: number; failed: number; total: number; items: SrtVoiceRow[]; outputDir: string }>(only ? 'srt.voice.regenerate' : 'srt.voice.generate', {
        entries: entries.map((row) => ({ id: row.id, start: row.start, end: row.end, text: row.text })), voiceId, outputDir: destination,
        engine, apiProvider, apiModel, apiVoiceId: apiVoiceId.trim(), apiWorkers, language: 'vi', speed, steps, guidance, postprocess: true, denoise: false, skipExisting: !only,
      });
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => result.items.find((item) => item.id === row.id) ? { ...row, ...result.items.find((item) => item.id === row.id)! } : row) } : current);
      setMessage(`Hoàn tất ${result.completed}/${result.total} câu${result.failed ? ` · ${result.failed} câu lỗi` : ''}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setRunning(false); }
  };
  const play = async (row: SrtVoiceRow) => { if (!row.file) return; const url = await window.desktop?.readAudio(row.file); if (url) { setAudioUrl(url); setTimeout(() => document.querySelector<HTMLAudioElement>('.srt-voice-player')?.play(), 0); } };
  const completed = draft?.rows.filter((row) => row.status === 'completed').length || 0;
  const failed = draft?.rows.filter((row) => row.status === 'failed').length || 0;
  return <div className="srt-voice-page">
    <div className="srt-voice-hero"><div><div className="eyebrow"><Captions size={14} /> OMNIVOICE BATCH</div><h1>Tạo giọng từ <span>phụ đề SRT.</span></h1><p>Tạo từng câu thành 0001.wav, 0002.wav và tự thử lại hai lần khi gặp lỗi.</p></div><div className="srt-voice-actions"><button className="secondary" onClick={chooseSrt}><UploadCloud size={16} /> Chọn file SRT</button><button className="primary" disabled={!draft?.rows.length || running} onClick={() => run()}>{running ? <><RefreshCw className="spin" size={17} /> Đang tạo {progress.done}/{progress.total}</> : <><AudioLines size={17} /> Tạo tất cả</>}</button></div></div>
    <section className="srt-voice-config">
      <label><small>FILE ĐẦU VÀO</small><strong>{draft?.name || 'Chưa chọn SRT'}</strong><span>{draft ? `${draft.rows.length} câu phụ đề` : 'Có thể nhận trực tiếp từ tab Dịch'}</span></label>
      <label><small>MÔ HÌNH TẠO GIỌNG</small><select value={engine} onChange={(e) => setEngine(e.target.value as typeof engine)}><option value="omnivoice">OmniVoice · Local</option><option value="ai33">AI33 API</option><option value="aimax">AIMax API</option></select></label>
      {engine === 'omnivoice' ? <><label><small>GIỌNG OMNIVOICE</small><select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>{voices.filter((voice) => voice.ready).map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}</select></label><label><small>STEP / GUIDANCE</small><div className="inline-numbers"><input type="number" min="4" max="64" value={steps} onChange={(e) => setSteps(Number(e.target.value))} /><input type="number" min="0.5" max="5" step="0.1" value={guidance} onChange={(e) => setGuidance(Number(e.target.value))} /></div></label></> : <><label><small>VOICE ID</small><div className="voice-id-picker"><input value={apiVoiceId} onChange={(e) => setApiVoiceId(e.target.value)} placeholder="Chọn trong thư viện hoặc nhập ID"/><button type="button" onClick={loadApiVoices}><Search size={14}/> Thư viện</button></div></label><label><small>NHÀ CUNG CẤP {engine === 'aimax' ? '/ MODEL' : ''}</small><div className="inline-numbers"><select value={apiProvider} onChange={(e) => { const p=e.target.value; setApiProvider(p); setApiVoices([]); setApiModel(p === 'minimax' ? 'speech-2.8-hd' : 'eleven_multilingual_v2'); }}><option value="minimax">MiniMax</option><option value="elevenlabs">ElevenLabs</option>{engine === 'ai33' && <><option value="edge">Edge</option><option value="kokoro">Kokoro</option><option value="vbee">Vbee</option><option value="fishaudio">Fish Audio</option><option value="clone">Giọng clone</option></>}</select>{engine === 'aimax' && <select value={apiModel} onChange={(e) => setApiModel(e.target.value)}>{apiProvider === 'minimax' ? <><option value="speech-2.8-hd">2.8 HD</option><option value="speech-2.8-turbo">2.8 Turbo</option><option value="speech-2.6-hd">2.6 HD</option><option value="speech-2.6-turbo">2.6 Turbo</option><option value="speech-02-hd">02 HD</option><option value="speech-02-turbo">02 Turbo</option></> : <><option value="eleven_v3">Eleven v3</option><option value="eleven_multilingual_v2">Multilingual v2</option><option value="eleven_flash_v2_5">Flash v2.5</option><option value="eleven_turbo_v2_5">Turbo v2.5</option></>}</select>}</div></label></>}
      <label><small>TỐC ĐỘ · {speed.toFixed(2)}×</small><input type="range" min="0.6" max="1.5" step="0.05" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /></label>
      {engine !== 'omnivoice' && <label><small>SỐ LUỒNG API</small><input type="number" min="1" max="8" value={apiWorkers} onChange={(e)=>setApiWorkers(Math.min(8,Math.max(1,Number(e.target.value)||1)))}/><span>Khuyên dùng 3–4 luồng</span></label>}
    </section>
    {voiceLibraryOpen && <section className="api-voice-library"><header><div><strong>Thư viện giọng {engine === 'ai33' ? 'AI33' : 'AIMax'}</strong><small>{apiProvider} · {apiVoices.length} giọng</small></div><div className="api-voice-search"><Search size={14}/><input value={voiceQuery} onChange={(e)=>setVoiceQuery(e.target.value)} placeholder="Tìm tên hoặc Voice ID"/></div><button onClick={()=>setVoiceLibraryOpen(false)}><X size={16}/></button></header><div className="api-voice-list">{voiceLibraryLoading ? <div className="api-voice-empty"><RefreshCw className="spin"/> Đang tải thư viện…</div> : apiVoices.filter((v)=>`${v.name} ${v.id}`.toLowerCase().includes(voiceQuery.toLowerCase())).map((voice)=><article key={voice.id} className={apiVoiceId === voice.id ? 'selected' : ''}><div className="api-voice-avatar">{voice.name.slice(0,2).toUpperCase()}</div><div><strong>{voice.name}</strong><small>{voice.language || 'Không rõ ngôn ngữ'} · {voice.id}</small></div><button disabled={!voice.previewUrl} onClick={()=>playApiVoice(voice)} title="Nghe thử"><Play size={14}/></button><button className="choose" onClick={()=>chooseApiVoice(voice)}>Chọn</button></article>)}{!voiceLibraryLoading && !apiVoices.length && <div className="api-voice-empty">Không tìm thấy giọng. Hãy kiểm tra API key và bộ lọc nhà cung cấp.</div>}</div></section>}
    <div className="srt-output-bar"><div><FolderOpen size={17} /><span><small>THƯ MỤC KẾT QUẢ</small><strong>{outputDir || 'Chọn khi bắt đầu tạo'}</strong></span></div><button onClick={chooseOutput}>Chọn thư mục</button>{outputDir && <button onClick={() => window.desktop?.showInFolder(outputDir)}>Mở kết quả</button>}</div>
    <div className="srt-run-stats"><span>{draft?.rows.length || 0} câu</span><span className="ok">{completed} hoàn thành</span><span className={failed ? 'bad' : ''}>{failed} lỗi</span><div><i style={{ width: `${progress.total ? progress.done / progress.total * 100 : 0}%` }} /></div></div>
    <section className="srt-voice-table"><header><span># / THỜI GIAN</span><span>NỘI DUNG ĐỌC</span><span>TRẠNG THÁI</span><span>THAO TÁC</span></header>{draft?.rows.length ? draft.rows.map((row) => <article key={row.id}><div><b>{String(row.id).padStart(4, '0')}</b><small>{row.start} → {row.end}</small></div><textarea value={row.text} disabled={running} onChange={(e) => updateText(row.id, e.target.value)} /><div className={`voice-row-status ${row.status}`}><strong>{row.status === 'completed' ? 'Hoàn thành' : row.status === 'failed' ? 'Lỗi' : row.status === 'generating' ? 'Đang tạo' : 'Chờ'}</strong><small>{row.duration ? `${row.duration.toFixed(2)} giây` : row.error || `${String(row.id).padStart(4, '0')}.wav`}</small></div><div className="voice-row-actions"><button disabled={!row.file} onClick={() => play(row)} title="Nghe"><Play size={15} /></button><button disabled={running || !row.text.trim()} onClick={() => run(row)} title="Tạo lại"><RefreshCw size={15} /></button></div></article>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>Chưa có dữ liệu SRT</strong><small>Chọn file ngoài hoặc chuyển bản dịch từ tab Dịch.</small></div>}</section>
    <footer className="srt-voice-footer"><strong>{message}</strong><span>Retry lỗi: tối đa 2 lần</span></footer>{audioUrl && <audio className="srt-voice-player" src={audioUrl} controls />}{previewUrl && <audio className="api-voice-preview-player" src={previewUrl} controls />}
  </div>;
}

function CapCutProjectPage() {
  const [videoPath, setVideoPath] = useState('');
  const [srtPath, setSrtPath] = useState('');
  const [voiceDir, setVoiceDir] = useState('');
  const [projectName, setProjectName] = useState(`HHVietSub ${new Date().toLocaleDateString('vi-VN').replaceAll('/', '-')}`);
  const [analysis, setAnalysis] = useState<{ subtitles: number; voiceFiles: number; missing: number[]; ready: boolean } | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chọn video, SRT và thư mục voice để kiểm tra ánh xạ.');
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<{ projectName: string; projectPath: string; template: string } | null>(null);
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const event = raw as { event?: string; data?: { message?: string } };
    if (event.event === 'capcut.project.progress' && event.data?.message) {
      setLogs((current) => [...current.slice(-99), event.data!.message!]);
      setMessage(event.data.message);
    }
  }), []);
  useEffect(() => {
    setAnalysis(null); setResult(null);
    if (!videoPath || !srtPath || !voiceDir || !window.desktop) return;
    window.desktop.request<typeof analysis>('capcut.project.validate', { videoPath, srtPath, voiceDir })
      .then((value) => { setAnalysis(value); setMessage(value?.ready ? `Sẵn sàng: ${value.subtitles} phụ đề ↔ ${value.voiceFiles} voice.` : `Thiếu ${value?.missing.length || 0} file voice.`); })
      .catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [videoPath, srtPath, voiceDir]);
  const pick = async (kind: 'video' | 'srt' | 'voice') => {
    if (kind === 'voice') { const path = await window.desktop?.selectFolder(); if (path) setVoiceDir(path); return; }
    const path = await window.desktop?.selectFile({ filters: kind === 'video' ? [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'avi', 'm4v', 'webm'] }] : [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (path) kind === 'video' ? setVideoPath(path) : setSrtPath(path);
  };
  const create = async () => {
    if (!window.desktop || !analysis?.ready || running) return;
    setRunning(true); setLogs([]); setResult(null); setMessage('Đang chuẩn bị project mới…');
    try {
      const created = await window.desktop.request<{ projectName: string; projectPath: string; template: string }>('capcut.project.create', { videoPath, srtPath, voiceDir, projectName });
      setResult(created); setMessage(`Hoàn tất project: ${created.projectName}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setRunning(false); }
  };
  const fileName = (value: string) => value.split(/[\\/]/).at(-1) || '';
  return <div className="capcut-project-page">
    <div className="capcut-project-hero"><div><div className="eyebrow"><Clapperboard size={14} /> TỰ ĐỘNG HÓA CAPCUT</div><h1>Tạo và đồng bộ <span>dự án CapCut.</span></h1><p>Tự thêm video gốc, phụ đề, voice và co giãn video theo thời lượng lời đọc.</p></div><button className="primary" disabled={!analysis?.ready || !projectName.trim() || running} onClick={create}>{running ? <><RefreshCw className="spin" size={17} /> Đang tạo dự án…</> : <><Sparkles size={17} /> Tạo dự án & đồng bộ</>}</button></div>
    <section className="capcut-input-grid">
      <button onClick={() => pick('video')}><span className="capcut-step">1</span><Clapperboard size={23} /><div><small>VIDEO GỐC</small><strong>{fileName(videoPath) || 'Chọn video'}</strong><em>{videoPath || 'MP4, MOV, MKV…'}</em></div></button>
      <button onClick={() => pick('srt')}><span className="capcut-step">2</span><Captions size={23} /><div><small>PHỤ ĐỀ SRT</small><strong>{fileName(srtPath) || 'Chọn file SRT'}</strong><em>{srtPath || 'Timestamp dùng để chia video'}</em></div></button>
      <button onClick={() => pick('voice')}><span className="capcut-step">3</span><AudioLines size={23} /><div><small>THƯ MỤC VOICE</small><strong>{fileName(voiceDir) || 'Chọn thư mục voice'}</strong><em>{voiceDir || '0001.wav, 0002.wav…'}</em></div></button>
    </section>
    <section className="capcut-project-settings"><label><small>TÊN DỰ ÁN MỚI</small><input value={projectName} onChange={(e) => setProjectName(e.target.value)} /></label><div className={`capcut-readiness ${analysis?.ready ? 'ready' : analysis ? 'warning' : ''}`}><Check size={18} /><span><strong>{analysis ? `${analysis.voiceFiles}/${analysis.subtitles} voice đã khớp` : 'Chưa kiểm tra đầu vào'}</strong><small>{analysis?.missing.length ? `Thiếu: ${analysis.missing.slice(0, 12).map((id) => String(id).padStart(4, '0')).join(', ')}` : 'Project mới sẽ được lưu vào thư mục dự án CapCut mặc định.'}</small></span></div></section>
    <section className="capcut-flow"><div><span>1</span><strong>Tạo project mới</strong><small>Sinh schema CapCut sạch</small></div><i>→</i><div><span>2</span><strong>Thêm nội dung</strong><small>Video + SRT + voice</small></div><i>→</i><div><span>3</span><strong>Cắt video</strong><small>Theo từng block SRT</small></div><i>→</i><div><span>4</span><strong>Đồng bộ</strong><small>Voice quyết định timeline</small></div></section>
    <section className="capcut-progress-panel"><header><div><small>TIẾN TRÌNH</small><strong>{message}</strong></div><span>{running ? 'ĐANG XỬ LÝ' : result ? 'HOÀN TẤT' : 'SẴN SÀNG'}</span></header><div className="capcut-log">{logs.length ? logs.map((line, index) => <p key={`${index}-${line}`}>{line}</p>) : <p>Chưa có tác vụ. Tool sẽ yêu cầu đóng CapCut trước khi ghi project.</p>}</div>{result && <footer><div><Check size={18} /><span><strong>{result.projectName}</strong><small>{result.template} · {result.projectPath}</small></span></div><button onClick={() => window.desktop?.showInFolder(result.projectPath)}><FolderOpen size={15} /> Mở thư mục</button><button className="open-capcut" onClick={() => window.desktop?.request('capcut.open')}><Clapperboard size={15} /> Mở CapCut</button></footer>}</section>
  </div>;
}

function VoiceBackendSettings() {
  const [mode, setMode] = useState<'local' | 'colab'>('local');
  const [url, setUrl] = useState(''); const [token, setToken] = useState('');
  const [message, setMessage] = useState('Chọn nơi thực hiện suy luận OmniVoice.'); const [testing, setTesting] = useState(false);
  const [ai33Key, setAi33Key] = useState(''); const [aimaxKey, setAimaxKey] = useState('');
  const [apiSaved, setApiSaved] = useState({ ai33Configured: false, aimaxConfigured: false });
  useEffect(() => { window.desktop?.request<{ voiceBackend?: { mode: 'local' | 'colab'; url: string; token: string } }>('settings.get').then((v) => {
    if (v.voiceBackend) { setMode(v.voiceBackend.mode); setUrl(v.voiceBackend.url); setToken(v.voiceBackend.token || ''); }
  }); }, []);
  useEffect(() => { window.desktop?.request<typeof apiSaved>('settings.tts.get').then(setApiSaved); }, []);
  const save = async () => { try { await window.desktop?.request('settings.voice.save', { mode, url, token }); setMessage('Đã lưu cấu hình backend giọng nói.'); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } };
  const test = async () => { setTesting(true); try { const r = await window.desktop?.request<{ device?: string | null; status?: string | null; detail?: string | null }>('settings.voice.test', { mode, url, token }); if (!r) throw new Error('Backend Electron chưa sẵn sàng.'); const device = (r.device || 'GPU').toUpperCase(); setMessage(`Kết nối thành công · ${device} · ${r.status || 'sẵn sàng'}${r.detail ? ` · ${r.detail}` : ''}`); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } finally { setTesting(false); } };
  const saveApi = async () => { try { const saved = await window.desktop?.request<typeof apiSaved>('settings.tts.save', { ai33Key, aimaxKey }); if (saved) setApiSaved(saved); setAi33Key(''); setAimaxKey(''); setMessage('Đã lưu khóa API tạo giọng an toàn trên máy.'); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } };
  const testApi = async (provider: 'ai33'|'aimax') => { try { await window.desktop?.request('settings.tts.test', { provider, key: provider === 'ai33' ? ai33Key : aimaxKey }); setApiSaved((v) => ({...v, [provider === 'ai33' ? 'ai33Configured' : 'aimaxConfigured']: true})); setMessage(`Kết nối ${provider === 'ai33' ? 'AI33' : 'AIMax'} thành công.`); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } };
  return <div className="voice-backend-page"><div className="settings-hero"><div className="eyebrow"><Settings2 size={15}/> CẤU HÌNH ỨNG DỤNG</div><h1>Thiết lập cấu hình</h1><p>Chọn bộ xử lý OmniVoice cho Phòng thu và Tạo từ SRT.</p></div>
    <section className="voice-backend-card"><header><AudioLines size={23}/><div><h2>Cấu hình Bộ xử lý (Backend)</h2><p>Chạy trên máy hoặc dùng GPU Google Colab cho máy cấu hình yếu.</p></div></header>
      <div className="backend-options"><button className={mode === 'local' ? 'selected' : ''} onClick={() => setMode('local')}><b>○</b><strong>Chạy cục bộ (Local GPU/CPU)</strong><small>Riêng tư, offline; sử dụng phần cứng của máy.</small></button><button className={mode === 'colab' ? 'selected' : ''} onClick={() => setMode('colab')}><b>○</b><strong>Google Colab (Remote GPU)</strong><small>Tạo giọng trên GPU Colab, kết quả vẫn lưu về máy.</small></button></div>
      {mode === 'colab' && <div className="colab-config"><div><strong>Đường dẫn API Google Colab</strong><a href="https://colab.research.google.com/github/nguyenduchung98/HHVietSub-Colab/blob/main/HHVietSub_Colab.ipynb" target="_blank" rel="noreferrer">Mở Colab Notebook ↗</a></div><ol><li>Chọn Runtime → Change runtime type → GPU.</li><li>Run all và chờ hiện cả URL lẫn TOKEN.</li><li>Dán đầy đủ URL và TOKEN, kiểm tra kết nối rồi lưu.</li></ol><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://xxx.trycloudflare.com"/><input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Token bảo mật (bắt buộc)"/><button onClick={test} disabled={testing || !url.trim() || !token.trim()}>{testing ? 'Đang kiểm tra…' : 'Kiểm tra kết nối'}</button></div>}
      <footer><span>{message}</span><button className="primary" onClick={save}>Lưu cấu hình</button></footer></section>
    <section className="voice-backend-card api-key-card"><header><AudioLines size={23}/><div><h2>API tạo giọng từ phụ đề</h2><p>Khóa chỉ lưu trong dữ liệu ứng dụng trên máy, không đưa vào mã nguồn hoặc log.</p></div></header><div className="api-key-grid"><label><strong>AI33 API Key</strong><input type="password" value={ai33Key} onChange={(e)=>setAi33Key(e.target.value)} placeholder={apiSaved.ai33Configured ? 'Đã lưu · nhập khóa mới để thay đổi' : 'Nhập xi-api-key'}/><button onClick={()=>testApi('ai33')}>Kiểm tra AI33</button></label><label><strong>AIMax API Key</strong><input type="password" value={aimaxKey} onChange={(e)=>setAimaxKey(e.target.value)} placeholder={apiSaved.aimaxConfigured ? 'Đã lưu · nhập khóa mới để thay đổi' : 'Nhập X-API-Key'}/><button onClick={()=>testApi('aimax')}>Kiểm tra AIMax</button></label></div><footer><span>{message}</span><button className="primary" onClick={saveApi}>Lưu khóa API</button></footer></section></div>;
}

function Placeholder({ page, label }: { page: Page; label: string }) {
  const descriptions: Record<Page, string> = { studio: '', translate: '', srt: 'Tải file SRT và tạo giọng nói khớp theo từng mốc thời gian.', capcut: '', settings: 'Quản lý backend, model OmniVoice, định dạng audio và thư mục đầu ra.' };
  return <div className="placeholder"><div className="upload-icon">{page === 'srt' ? <UploadCloud size={32} /> : <Settings2 size={32} />}</div><div className="eyebrow">{page === 'srt' ? 'KHỚP THỜI GIAN CHÍNH XÁC' : 'CẤU HÌNH ỨNG DỤNG'}</div><h1>{label}</h1><p>{descriptions[page]}</p>{page === 'srt' && <button className="primary"><Captions size={17} /> Chọn tệp SRT</button>}</div>;
}
