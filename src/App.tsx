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

const cleanUnicode = (value: string) => new TextDecoder().decode(new TextEncoder().encode(value));

const nav: { id: Page; label: string; icon: typeof Sparkles }[] = [
  { id: 'studio', label: 'PhÃ²ng thu', icon: AudioLines },
  { id: 'translate', label: 'Dá»‹ch phá»¥ Ä‘á»', icon: Languages },
  { id: 'srt', label: 'Táº¡o tá»« SRT', icon: FileText },
  { id: 'capcut', label: 'Dá»± Ã¡n CapCut', icon: Clapperboard },
  { id: 'settings', label: 'Cáº¥u hÃ¬nh', icon: Settings2 },
];

const sampleVoices: Voice[] = [
  { id: 'ban-mai', name: 'Ban Mai', language: 'Tiáº¿ng Viá»‡t', ready: true, source: 'OmniVoice' },
  { id: 'lan-trinh', name: 'Lan Trinh', language: 'Tiáº¿ng Viá»‡t', ready: true, source: 'OmniVoice' },
  { id: 'story', name: 'Story', language: 'English', ready: true, source: 'OmniVoice' },
];

export function App() {
  const [page, setPage] = useState<Page>('studio');
  const [online, setOnline] = useState(false);
  const [voices, setVoices] = useState<Voice[]>(sampleVoices);
  const [query, setQuery] = useState('');
  const [selectedVoice, setSelectedVoice] = useState('ban-mai');
  const [text, setText] = useState('Dich CapCut Studio giÃºp báº¡n biáº¿n phá»¥ Ä‘á» thÃ nh giá»ng nÃ³i vÃ  Ä‘á»“ng bá»™ trá»±c tiáº¿p vá»›i dá»± Ã¡n CapCut.');
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
  const pageLabel = nav.find((item) => item.id === page)?.label ?? 'PhÃ²ng thu';

  const focusedWorkspace = page === 'translate' || page === 'srt' || page === 'capcut';
  return <div className={`app-shell ${focusedWorkspace ? 'focused-workspace' : ''}`}>
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><AudioLines size={23} /></div><div><strong>Dich CapCut</strong><span>AI LOCAL STUDIO</span></div></div>
      <nav className="nav-pills">{nav.map((item) => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => setPage(item.id)}><item.icon size={15} />{item.label}</button>)}</nav>
      <div className="top-actions"><span className={`backend-state ${online ? 'online' : ''}`}><i />{online ? 'Backend sáºµn sÃ ng' : 'Cháº¿ Ä‘á»™ xem trÆ°á»›c'}</span><button className="icon-button"><RefreshCw size={17} /></button><button className="icon-button"><CircleHelp size={18} /></button><div className="avatar">DC</div></div>
    </header>

    {!focusedWorkspace && <aside className="sidebar">
      <div className="eyebrow">THÆ¯ VIá»†N GIá»ŒNG</div><div className="side-title"><h2>Giá»ng cá»§a báº¡n</h2><button title="ThÃªm giá»ng" onClick={() => setVoiceModal(true)}>+</button></div>
      <label className="search"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="TÃ¬m kiáº¿m giá»ng" /></label>
      <div className="section-caption">GIá»ŒNG OMNIVOICE</div>
      <div className="project-list">{filteredVoices.length ? filteredVoices.map((voice, i) => <button className={`project-card ${voice.id === selectedVoice ? 'selected' : ''}`} key={voice.id} onClick={() => setSelectedVoice(voice.id)}><span className={`project-icon tone-${i % 4}`}>{voice.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase()}</span><span><strong>{voice.name}</strong><small>{voice.language}</small></span><Volume2 size={15} /></button>) : <div className="empty-small"><AudioLines size={25} /><span>ChÆ°a tÃ¬m tháº¥y giá»ng</span><small>ThÃªm audio máº«u Ä‘á»ƒ táº¡o há»“ sÆ¡ giá»ng má»›i.</small></div>}</div>
      <div className="privacy"><span>âœ“</span><div><strong>RiÃªng tÆ° ngay tá»« thiáº¿t káº¿</strong><small>Audio vÃ  dá»± Ã¡n chá»‰ lÆ°u trÃªn thiáº¿t bá»‹ nÃ y.</small></div></div>
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
    const path = await window.desktop?.selectFile({ filters: [{ name: 'Audio tham chiáº¿u', extensions: ['wav', 'mp3', 'flac', 'm4a', 'ogg', 'webm'] }] });
    if (path) setAudioPath(path);
  };
  const create = async () => {
    if (!window.desktop || !name.trim() || !audioPath || !consent) return setError('HÃ£y nháº­p tÃªn, chá»n audio vÃ  xÃ¡c nháº­n quyá»n sá»­ dá»¥ng.');
    setSaving(true); setError('');
    try { await onCreated(await window.desktop.request<Voice>('voice.create', { name, audioPath, language, refText, notes, consentConfirmed: consent })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  };
  const fileName = audioPath.split(/[\\/]/).pop();
  return <div className="voice-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <section className="voice-modal"><button className="voice-modal-close" onClick={onClose}><X size={19} /></button>
      <header><div className="voice-modal-art"><Mic2 size={29} /><AudioLines size={38} /></div><div><small>âœ¦ GIá»ŒNG Má»šI</small><h2>Táº¡o há»“ sÆ¡ giá»ng nÃ³i</h2><p>HÃ£y dÃ¹ng báº£n ghi rÃµ rÃ ng, chá»‰ cÃ³ má»™t ngÆ°á»i nÃ³i vÃ  Ã­t tiáº¿ng á»“n.</p></div></header>
      <div className="voice-modal-form"><label><span>TÃªn giá»ng</span><input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="VÃ­ dá»¥: Giá»ng ká»ƒ chuyá»‡n áº¥m Ã¡p" /></label>
        <button className={`voice-audio-picker ${audioPath ? 'selected' : ''}`} onClick={chooseAudio}><UploadCloud size={25} /><strong>{fileName || 'Chá»n audio tham chiáº¿u'}</strong><small>{fileName ? audioPath : 'WAV, MP3, FLAC, M4A, OGG hoáº·c WebM Â· tá»‘i Ä‘a 50 MB'}</small></button>
        <div className="voice-form-grid"><label><span>NgÃ´n ngá»¯ trong audio</span><select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="auto">Tá»± Ä‘á»™ng</option><option value="vi">Tiáº¿ng Viá»‡t</option><option value="en">English</option></select></label><label><span>Báº£n chÃ©p lá»i tham chiáº¿u <i>khÃ´ng báº¯t buá»™c</i></span><input value={refText} onChange={(e) => setRefText(cleanUnicode(e.target.value))} placeholder="Ná»™i dung Ä‘Æ°á»£c nÃ³i trong audio?" /></label></div>
        <label><span>Ghi chÃº <i>khÃ´ng báº¯t buá»™c</i></span><input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Cháº¥t giá»ng, micro, bá»‘i cáº£nh thu Ã¢m..." /></label>
        <label className="voice-consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span><strong>TÃ´i cÃ³ quyá»n sá»­ dá»¥ng vÃ  clone giá»ng nÃ³i nÃ y.</strong><small>Chá»‰ clone giá»ng cá»§a báº¡n hoáº·c giá»ng mÃ  báº¡n Ä‘Æ°á»£c chá»§ sá»Ÿ há»¯u cho phÃ©p.</small></span></label>
        {error && <div className="voice-modal-error">{error}</div>}
      </div><footer><button onClick={onClose}>Há»§y</button><button className="create-voice" disabled={saving || !name.trim() || !audioPath || !consent} onClick={create}><Sparkles size={17} />{saving ? 'Äang táº¡o...' : 'Táº¡o giá»ng'}</button></footer>
    </section></div>;
}

function GenerationHistoryPanel({ history, refresh }: { history: StudioResult[]; refresh: () => void }) {
  const playAudio = async (item: StudioResult) => {
    if (!window.desktop) return;
    const player = new Audio(await window.desktop.readAudio(item.path));
    await player.play();
  };
  return <aside className="activity-panel generation-side-panel"><div className="generation-side-heading"><div><div className="eyebrow">â†¶ Gáº¦N ÄÃ‚Y</div><h2>Lá»‹ch sá»­ táº¡o giá»ng</h2></div><button className="icon-button"><MoreHorizontal size={17} /></button></div>
    <div className="generation-side-list">{history.length ? history.map((item) => <article className="generation-side-card" key={item.id}><div className="generation-card-top"><button className="history-play" onClick={() => playAudio(item)}><Play size={13} fill="currentColor" /></button><span><strong>{item.voiceName}</strong><small>{new Date(item.createdAt).toLocaleString('vi-VN')}</small></span><button title="LÆ°u audio" onClick={() => window.desktop?.saveAudio(item.path)}><Download size={13} /></button><button title="XÃ³a" onClick={async () => { await window.desktop?.request('studio.history.delete', { id: item.id }); refresh(); }}><Trash2 size={13} /></button></div><p>{item.text}</p><footer><span>{item.duration} giÃ¢y</span><span>{item.format.toUpperCase()}</span><span>{item.language.toUpperCase()}</span><span>Seed {item.seed}</span></footer><div className="mini-wave">|||||||||||||||||||||||||||||</div></article>) : <div className="generation-side-empty"><AudioLines size={26} /><strong>ChÆ°a cÃ³ audio nÃ o</strong><span>Káº¿t quáº£ má»›i sáº½ Ä‘Æ°á»£c lÆ°u táº¡i Ä‘Ã¢y.</span></div>}</div>
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
  const [status, setStatus] = useState('Sáºµn sÃ ng khi báº¡n báº¯t Ä‘áº§u');
  const [audioUrl, setAudioUrl] = useState('');
  const [result, setResult] = useState<StudioResult | null>(null);
  const generate = async () => {
    if (!window.desktop) return setStatus('Chá»©c nÄƒng táº¡o giá»ng chá»‰ hoáº¡t Ä‘á»™ng trong Electron.');
    if (!text.trim()) return setStatus('Vui lÃ²ng nháº­p ná»™i dung cáº§n táº¡o giá»ng.');
    setGenerating(true); setAudioUrl(''); setStatus('Äang náº¡p OmniVoice vÃ  táº¡o audio...');
    try {
      const generated = await window.desktop.request<StudioResult>('studio.generate', { text, voiceId: selectedVoice, language, speed, denoise: false, postprocess, createSrt, steps, guidance, seed });
      setResult(generated); setAudioUrl(await window.desktop.readAudio(generated.path));
      setStatus(`${generated.duration.toFixed(1)} giÃ¢y Â· WAV Â· seed ${generated.seed} Â· táº¡o trong ${generated.generationTime.toFixed(1)} giÃ¢y`);
      onHistoryChange();
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
    finally { setGenerating(false); }
  };
  return <div className="studio-page">
    <div className="hero-row"><div><div className="eyebrow"><Sparkles size={14} /> SÃNG Táº O Báº°NG GIá»ŒNG Cá»¦A Báº N</div><h1>Biáº¿n cÃ¢u chá»¯ thÃ nh <span>Ã¢m thanh cá»§a báº¡n.</span></h1><p>Chá»n giá»ng, nháº­p ná»™i dung vÃ  Ä‘iá»u chá»‰nh cÃ¡ch Ä‘á»c.</p></div><label className="voice-select"><span className="voice-avatar">OV</span><span><small>ÄANG Sá»¬ Dá»¤NG GIá»ŒNG</small><strong>{voices.find((v) => v.id === selectedVoice)?.name ?? 'Chá»n giá»ng'}</strong></span><ChevronDown size={17} /><select value={selectedVoice} onChange={(e) => setSelectedVoice(e.target.value)}>{voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label></div>
    <section className="editor-card"><div className="editor-head"><strong>VÄƒn báº£n</strong><span>{text.length} / 100,000</span></div><textarea value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.ctrlKey && e.key === 'Enter') generate(); }} /><div className="editor-foot"><label className="studio-language">NgÃ´n ngá»¯ <select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="vi">Tiáº¿ng Viá»‡t</option><option value="en">English</option><option value="auto">Tá»± Ä‘á»™ng</option></select></label><span>âœ¦ Máº¹o: dáº¥u cÃ¢u giÃºp táº¡o nhá»‹p Ä‘á»c tá»± nhiÃªn.</span></div></section>
    <div className="controls studio-controls-compact"><div className="control-card speed"><div><span>Tá»‘c Ä‘á»™ Ä‘á»c</span><strong>{speed.toFixed(2)}Ã—</strong></div><input type="range" min="0.6" max="1.5" step="0.05" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /><div className="range-label"><span>Cháº­m rÃ£i</span><span>Tá»± nhiÃªn</span><span>Nhanh</span></div></div><button className="control-card" onClick={() => setCreateSrt(!createSrt)}><span className="control-icon purple"><Captions size={17} /></span><div><strong>Táº¡o phá»¥ Ä‘á» SRT</strong><small>Äá»“ng bá»™ chá»¯ vÃ  tiáº¿ng</small></div><i className={`toggle ${createSrt ? 'on' : ''}`} /></button><button className="control-card refine-button" onClick={() => setAdvanced(!advanced)}><Settings2 size={17} /><strong>Tinh chá»‰nh</strong><ChevronDown className={advanced ? 'rotated' : ''} size={16} /></button></div>
    {advanced && <div className="advanced-panel-hh"><label><span>Sá»‘ bÆ°á»›c suy luáº­n <b>{steps}</b></span><input type="range" min="4" max="64" step="4" value={steps} onChange={(e) => setSteps(Number(e.target.value))} /></label><label><span>Äá»™ bÃ¡m giá»ng <b>{guidance.toFixed(1)}</b></span><input type="range" min="0.5" max="5" step="0.1" value={guidance} onChange={(e) => setGuidance(Number(e.target.value))} /></label><label className="seed-input"><span>Seed tÃ¡i láº­p</span><input inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ''))} placeholder="Ngáº«u nhiÃªn" /></label><button className={`natural-toggle ${postprocess ? 'active' : ''}`} onClick={() => setPostprocess(!postprocess)}><Check size={15} /> HoÃ n thiá»‡n tá»± nhiÃªn</button></div>}
    <div className="action-row"><div className="hint"><span>â—·</span><div><strong>Láº§n táº¡o Ä‘áº§u tiÃªn sáº½ lÃ¢u hÆ¡n</strong><small>MÃ´ hÃ¬nh Ä‘Æ°á»£c náº¡p vÃ o GPU/CPU trÆ°á»›c khi táº¡o audio.</small></div></div><button className="primary" onClick={generate} disabled={generating}>{generating ? <><RefreshCw className="spin" size={18} /> Äang táº¡o giá»ng...</> : <><Sparkles size={18} /> Táº¡o giá»ng nÃ³i <kbd>Ctrl â†µ</kbd></>}</button></div>
    <div className="audio-result"><span className="audio-symbol"><AudioLines /></span><div><small>{generating ? 'Äang tiáº¿n hÃ nh táº¡o giá»ng nÃ³iâ€¦' : result ? 'Káº¿t quáº£ má»›i nháº¥t' : 'Audio OmniVoice'}</small><strong>{status}</strong>{generating ? <div className="indeterminate-progress"><i /></div> : audioUrl ? <audio className="studio-audio" src={audioUrl} controls /> : <div className="wave">|||||||||||||||||||||||||||||||||||||||||</div>}</div>{result && !generating && <div className="result-actions"><button title="LÆ°u audio" onClick={() => window.desktop?.saveAudio(result.path)}><Download size={17} /></button><button title="Má»Ÿ thÆ° má»¥c" onClick={() => window.desktop?.showInFolder(result.path)}><FolderOpen size={17} /></button></div>}</div>
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
  const [message, setMessage] = useState('Chá»n má»™t file SRT Ä‘á»ƒ báº¯t Ä‘áº§u.');
  const [rows, setRows] = useState<SubtitleRow[]>([]);
  useEffect(() => {
    window.desktop?.request<{ gemini?: { url: string; saved: { name: string; url: string }[]; selected: string; models: string[]; model: string; batch: number; workers: number; profileReady: boolean } }>('settings.get').then((settings) => {
      if (!settings.gemini) return;
      setGemUrl(settings.gemini.url); setSavedGems(settings.gemini.saved); setSelectedGem(settings.gemini.selected);
      setModel(settings.gemini.model); setBatchSize(settings.gemini.batch); setWorkers(settings.gemini.workers); setProfileReady(settings.gemini.profileReady);
    }).catch(() => undefined);
  }, []);
  const openSrt = async () => {
    if (!window.desktop) return setMessage('Há»™p thoáº¡i chá»n file chá»‰ hoáº¡t Ä‘á»™ng trong Electron.');
    const path = await window.desktop.selectFile({ filters: [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (!path) return;
    setMessage('Äang Ä‘á»c phá»¥ Ä‘á»...');
    try {
      const result = await window.desktop.request<{ path: string; name: string; entries: typeof rows; warnings: string[] }>('subtitle.parse', { path });
      setFilePath(result.path); setFileName(result.name); setRows(result.entries);
      setMessage(result.warnings.length ? `ÄÃ£ táº£i ${result.entries.length} cÃ¢u Â· ${result.warnings.length} cáº£nh bÃ¡o` : `ÄÃ£ táº£i ${result.entries.length} cÃ¢u phá»¥ Ä‘á»`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const saveSrt = async () => {
    if (!window.desktop || !filePath || !rows.length) return setMessage('ChÆ°a cÃ³ phá»¥ Ä‘á» Ä‘á»ƒ lÆ°u.');
    try {
      const result = await window.desktop.request<{ path: string; entries: number }>('subtitle.save', { sourcePath: filePath, entries: rows });
      setMessage(`ÄÃ£ lÆ°u ${result.entries} cÃ¢u: ${result.path}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const startTranslation = async () => {
    if (!window.desktop || !rows.length || translating) return;
    if (!gemUrl.trim()) { setShowOptions(true); setMessage('Vui lÃ²ng nháº­p link Gem.'); return; }
    localStorage.setItem('hhvietsub.gemUrl', gemUrl.trim());
    setTranslating(true);
    try {
      setMessage(`Äang má»Ÿ Gem vÃ  gá»­i ${Math.ceil(rows.length / batchSize)} chunkâ€¦`);
      const response = await window.desktop.translateWithGem<{ results: { id: number; translated: string }[]; chunks: number }>({
        gemUrl: gemUrl.trim(), modelName: model, batchSize, workers, sourceLanguage: 'Auto', targetLanguage: 'Tiáº¿ng Viá»‡t', glossary,
        entries: rows.map((row) => ({ id: row.id, text: row.source })),
      });
      const translatedMap = new Map(response.results.map((item) => [item.id, item.translated]));
      setRows((current) => current.map((row) => translatedMap.has(row.id) ? { ...row, translated: translatedMap.get(row.id)! } : row));
      setMessage(`HoÃ n táº¥t ${response.results.length}/${rows.length} cÃ¢u trong ${response.chunks} chunk.`);
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
    setMessage(`Äang dá»‹ch chunk ${event.data.chunk}/${event.data.total} Â· tab ${event.data.worker}${event.data.attempt ? ` Â· láº§n ${event.data.attempt}` : ''}`);
  }), []);
  const updateRow = (id: number, field: 'source' | 'translated', value: string) => setRows((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row));
  const characterCount = rows.reduce((sum, row) => sum + row.source.length, 0);
  const translatedCount = rows.filter((row) => row.translated.trim()).length;
  return <div className="translate-page">
    <div className="translate-hero"><div><div className="eyebrow"><Languages size={14} /> Dá»ŠCH PHá»¤ Äá»€ THÃ”NG MINH</div><h1>Dá»‹ch SRT <span>nhanh vÃ  nháº¥t quÃ¡n.</span></h1><p>Giá»¯ nguyÃªn timestamp, gá»­i chunk qua Gemini Gem vÃ  kiá»ƒm tra tá»«ng cÃ¢u trÆ°á»›c khi lÆ°u.</p></div><div className="translate-hero-actions"><button className="secondary" onClick={() => onSendToSrt({ name: fileName || 'Báº£n dá»‹ch', path: filePath, rows: rows.map((row) => ({ id: row.id, start: row.start, end: row.end, text: row.translated.trim() || row.source, status: 'pending' })) })} disabled={!rows.length}><AudioLines size={16} /> Táº¡o giá»ng</button><button className="secondary" onClick={saveSrt} disabled={!rows.length}><Download size={16} /> LÆ°u báº£n dá»‹ch</button><button className="primary" disabled={!rows.length || translating} onClick={startTranslation}>{translating ? <><RefreshCw className="spin" size={17} /> Gem Ä‘ang dá»‹châ€¦</> : <><Languages size={17} /> Má»Ÿ Gem & dá»‹ch</>}</button></div></div>
    <div className="translate-toolbar">
      <button className="file-drop" onClick={openSrt}><UploadCloud size={20} /><span><strong>{fileName || 'Chá»n tá»‡p phá»¥ Ä‘á» SRT'}</strong><small>{fileName ? 'Báº¥m Ä‘á»ƒ chá»n tá»‡p khÃ¡c' : 'KÃ©o tháº£ hoáº·c báº¥m Ä‘á»ƒ táº£i tá»‡p'}</small></span></button>
      <label><small>GEM ÄÃƒ LÆ¯U</small><select value={selectedGem} onChange={(e) => { const name = e.target.value; setSelectedGem(name); const gem = savedGems.find((item) => item.name === name); if (gem) setGemUrl(gem.url); }}><option value="">Chá»n Gem</option>{savedGems.map((gem) => <option key={gem.name}>{gem.name}</option>)}</select></label>
      <label><small>MÃ” HÃŒNH GEMINI</small><select value={model} onChange={(e) => setModel(e.target.value)}><option>3.1 Pro</option><option>3.5 Flash</option><option>3.1 Flash-Lite</option></select></label>
      <label><small>BLOCK / CHUNK</small><input type="number" min="1" max="300" value={batchSize} onChange={(e) => setBatchSize(Math.max(1, Math.min(300, Number(e.target.value) || 1)))} /></label>
      <label><small>Sá» LUá»’NG / TAB</small><select value={workers} onChange={(e) => setWorkers(Number(e.target.value))}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></select></label>
    </div>
    <div className="translation-stats"><span><strong>{rows.length}</strong> cÃ¢u</span><span><strong>{Math.ceil(rows.length / batchSize)}</strong> chunk</span><span><strong>{translatedCount}</strong> Ä‘Ã£ dá»‹ch</span><span className={profileReady ? 'success' : 'profile-warning'}><Check size={13} /> {profileReady ? 'Chrome Ä‘Ã£ Ä‘Äƒng nháº­p' : 'ChÆ°a cÃ³ profile'}</span><button onClick={() => setShowOptions(!showOptions)}><Settings2 size={15} /> Káº¿t ná»‘i & tá»« Ä‘iá»ƒn</button></div>
    {showOptions && <section className="translation-options browser-options"><label><span>Link Gemini Gem</span><input value={gemUrl} onChange={(e) => setGemUrl(e.target.value)} placeholder="https://gemini.google.com/gem/..." /><small>Electron Ä‘iá»u khiá»ƒn Chrome trá»±c tiáº¿p báº±ng CDP, khÃ´ng dÃ¹ng Selenium.</small></label><div className="gem-browser-actions"><button onClick={() => window.desktop?.loginGem()}>ÄÄƒng nháº­p Google</button><button onClick={() => window.desktop?.openGem(gemUrl)}>Má»Ÿ Gem kiá»ƒm tra</button></div><label><span>Thuáº­t ngá»¯ bá»• sung</span><textarea value={glossary} onChange={(e) => setGlossary(e.target.value)} placeholder="Má»—i dÃ²ng má»™t quy táº¯c thuáº­t ngá»¯" /></label></section>}
    <section className={`subtitle-table ${translating ? 'is-translating' : ''}`}><div className="subtitle-head"><span># / THá»œI GIAN</span><span>Ná»˜I DUNG Gá»C</span><span>Báº¢N Dá»ŠCH TIáº¾NG VIá»†T</span></div>{rows.length ? rows.map((row) => <div className="subtitle-row" key={row.id}><div><b>{String(row.id).padStart(2, '0')}</b><small>{row.start} â†’ {row.end}</small></div><textarea value={row.source} onChange={(e) => updateRow(row.id, 'source', e.target.value)} /><textarea className={row.translated.length > row.source.length * 1.8 ? 'length-warning' : ''} value={row.translated} placeholder={translating ? 'Äang dá»‹châ€¦' : 'ChÆ°a dá»‹ch'} onChange={(e) => updateRow(row.id, 'translated', e.target.value)} /></div>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>ChÆ°a cÃ³ phá»¥ Ä‘á»</strong><small>Chá»n file SRT Ä‘á»ƒ hiá»ƒn thá»‹ ná»™i dung táº¡i Ä‘Ã¢y.</small></div>}</section>
    <div className="translation-footer"><div><strong>{message}</strong><small>Gem nháº­n tá»«ng chunk dáº¡ng #id, kiá»ƒm tra Ã¡nh xáº¡ 1:1 vÃ  tá»± retry cÃ¢u thiáº¿u.</small></div><span className="shortcut-hint">Ctrl â†µ Ä‘á»ƒ dá»‹ch</span></div>
  </div>;
}

function SrtVoicePage({ voices, initialDraft }: { voices: Voice[]; initialDraft: SrtDraft | null }) {
  const [draft, setDraft] = useState<SrtDraft | null>(initialDraft);
  const [voiceId, setVoiceId] = useState(() => voices.find((voice) => voice.ready)?.id || '');
  const [outputDir, setOutputDir] = useState('');
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chá»n file SRT hoáº·c láº¥y báº£n dá»‹ch tá»« tab Dá»‹ch.');
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [speed, setSpeed] = useState(1);
  const [steps, setSteps] = useState(32);
  const [guidance, setGuidance] = useState(2);
  const [audioUrl, setAudioUrl] = useState('');
  useEffect(() => { if (initialDraft) { setDraft(initialDraft); setMessage(`ÄÃ£ nháº­n ${initialDraft.rows.length} cÃ¢u tá»« tab Dá»‹ch.`); } }, [initialDraft]);
  useEffect(() => { if (!voiceId && voices.length) setVoiceId(voices.find((voice) => voice.ready)?.id || ''); }, [voices, voiceId]);
  useEffect(() => window.desktop?.onBackendEvent((raw) => {
    const packet = raw as { event?: string; data?: { event?: string; done?: number; total?: number; id?: number; attempt?: number; item?: SrtVoiceRow } };
    if (packet.event !== 'srt.voice.progress' || !packet.data) return;
    const data = packet.data;
    if (data.event === 'model') setMessage('Äang náº¡p mÃ´ hÃ¬nh OmniVoiceâ€¦');
    if (data.event === 'attempt' && data.id) {
      setMessage(`Äang táº¡o cÃ¢u ${String(data.id).padStart(4, '0')} Â· láº§n ${data.attempt}/3`);
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
      setMessage(`ÄÃ£ táº£i ${result.entries.length} cÃ¢u${result.warnings.length ? ` Â· ${result.warnings.length} cáº£nh bÃ¡o` : ''}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
  };
  const chooseOutput = async () => {
    const folder = await window.desktop?.selectFolder();
    if (!folder || !draft) return;
    const stem = draft.name.replace(/\.srt$/i, '').replace(/[<>:"/\\|?*]+/g, '-').trim() || 'subtitle';
    setOutputDir(`${folder}\\${stem}_voice`);
  };
  const updateText = (id: number, text: string) => setDraft((current) => current ? { ...current, rows: current.rows.map((row) => row.id === id ? { ...row, text, status: row.status === 'completed' ? 'pending' : row.status } : row) } : current);
  const run = async (only?: SrtVoiceRow) => {
    if (!window.desktop || !draft || running) return;
    if (!voiceId) return setMessage('HÃ£y chá»n má»™t há»“ sÆ¡ giá»ng OmniVoice hoÃ n chá»‰nh.');
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
        language: 'vi', speed, steps, guidance, postprocess: true, denoise: false, skipExisting: !only,
      });
      setDraft((current) => current ? { ...current, rows: current.rows.map((row) => result.items.find((item) => item.id === row.id) ? { ...row, ...result.items.find((item) => item.id === row.id)! } : row) } : current);
      setMessage(`HoÃ n táº¥t ${result.completed}/${result.total} cÃ¢u${result.failed ? ` Â· ${result.failed} cÃ¢u lá»—i` : ''}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setRunning(false); }
  };
  const play = async (row: SrtVoiceRow) => { if (!row.file) return; const url = await window.desktop?.readAudio(row.file); if (url) { setAudioUrl(url); setTimeout(() => document.querySelector<HTMLAudioElement>('.srt-voice-player')?.play(), 0); } };
  const completed = draft?.rows.filter((row) => row.status === 'completed').length || 0;
  const failed = draft?.rows.filter((row) => row.status === 'failed').length || 0;
  return <div className="srt-voice-page">
    <div className="srt-voice-hero"><div><div className="eyebrow"><Captions size={14} /> OMNIVOICE BATCH</div><h1>Táº¡o giá»ng tá»« <span>phá»¥ Ä‘á» SRT.</span></h1><p>Táº¡o tá»«ng cÃ¢u thÃ nh 0001.wav, 0002.wav vÃ  tá»± thá»­ láº¡i hai láº§n khi gáº·p lá»—i.</p></div><div className="srt-voice-actions"><button className="secondary" onClick={chooseSrt}><UploadCloud size={16} /> Chá»n file SRT</button><button className="primary" disabled={!draft?.rows.length || running} onClick={() => run()}>{running ? <><RefreshCw className="spin" size={17} /> Äang táº¡o {progress.done}/{progress.total}</> : <><AudioLines size={17} /> Táº¡o táº¥t cáº£</>}</button></div></div>
    <section className="srt-voice-config"><label><small>FILE Äáº¦U VÃ€O</small><strong>{draft?.name || 'ChÆ°a chá»n SRT'}</strong><span>{draft ? `${draft.rows.length} cÃ¢u phá»¥ Ä‘á»` : 'CÃ³ thá»ƒ nháº­n trá»±c tiáº¿p tá»« tab Dá»‹ch'}</span></label><label><small>GIá»ŒNG OMNIVOICE</small><select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>{voices.filter((voice) => voice.ready).map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}</select></label><label><small>Tá»C Äá»˜ Â· {speed.toFixed(2)}Ã—</small><input type="range" min="0.6" max="1.5" step="0.05" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /></label><label><small>STEP / GUIDANCE</small><div className="inline-numbers"><input type="number" min="4" max="64" value={steps} onChange={(e) => setSteps(Number(e.target.value))} /><input type="number" min="0.5" max="5" step="0.1" value={guidance} onChange={(e) => setGuidance(Number(e.target.value))} /></div></label></section>
    <div className="srt-output-bar"><div><FolderOpen size={17} /><span><small>THÆ¯ Má»¤C Káº¾T QUáº¢</small><strong>{outputDir || 'Chá»n khi báº¯t Ä‘áº§u táº¡o'}</strong></span></div><button onClick={chooseOutput}>Chá»n thÆ° má»¥c</button>{outputDir && <button onClick={() => window.desktop?.showInFolder(outputDir)}>Má»Ÿ káº¿t quáº£</button>}</div>
    <div className="srt-run-stats"><span>{draft?.rows.length || 0} cÃ¢u</span><span className="ok">{completed} hoÃ n thÃ nh</span><span className={failed ? 'bad' : ''}>{failed} lá»—i</span><div><i style={{ width: `${progress.total ? progress.done / progress.total * 100 : 0}%` }} /></div></div>
    <section className="srt-voice-table"><header><span># / THá»œI GIAN</span><span>Ná»˜I DUNG Äá»ŒC</span><span>TRáº NG THÃI</span><span>THAO TÃC</span></header>{draft?.rows.length ? draft.rows.map((row) => <article key={row.id}><div><b>{String(row.id).padStart(4, '0')}</b><small>{row.start} â†’ {row.end}</small></div><textarea value={row.text} disabled={running} onChange={(e) => updateText(row.id, e.target.value)} /><div className={`voice-row-status ${row.status}`}><strong>{row.status === 'completed' ? 'HoÃ n thÃ nh' : row.status === 'failed' ? 'Lá»—i' : row.status === 'generating' ? 'Äang táº¡o' : 'Chá»'}</strong><small>{row.duration ? `${row.duration.toFixed(2)} giÃ¢y` : row.error || `${String(row.id).padStart(4, '0')}.wav`}</small></div><div className="voice-row-actions"><button disabled={!row.file} onClick={() => play(row)} title="Nghe"><Play size={15} /></button><button disabled={running || !row.text.trim()} onClick={() => run(row)} title="Táº¡o láº¡i"><RefreshCw size={15} /></button></div></article>) : <div className="subtitle-empty"><UploadCloud size={30} /><strong>ChÆ°a cÃ³ dá»¯ liá»‡u SRT</strong><small>Chá»n file ngoÃ i hoáº·c chuyá»ƒn báº£n dá»‹ch tá»« tab Dá»‹ch.</small></div>}</section>
    <footer className="srt-voice-footer"><strong>{message}</strong><span>Retry lá»—i: tá»‘i Ä‘a 2 láº§n</span></footer>{audioUrl && <audio className="srt-voice-player" src={audioUrl} controls />}
  </div>;
}

function CapCutProjectPage() {
  const [videoPath, setVideoPath] = useState('');
  const [srtPath, setSrtPath] = useState('');
  const [voiceDir, setVoiceDir] = useState('');
  const [projectName, setProjectName] = useState(`HHVietSub ${new Date().toLocaleDateString('vi-VN').replaceAll('/', '-')}`);
  const [analysis, setAnalysis] = useState<{ subtitles: number; voiceFiles: number; missing: number[]; ready: boolean } | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('Chá»n video, SRT vÃ  thÆ° má»¥c voice Ä‘á»ƒ kiá»ƒm tra Ã¡nh xáº¡.');
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
      .then((value) => { setAnalysis(value); setMessage(value?.ready ? `Sáºµn sÃ ng: ${value.subtitles} phá»¥ Ä‘á» â†” ${value.voiceFiles} voice.` : `Thiáº¿u ${value?.missing.length || 0} file voice.`); })
      .catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [videoPath, srtPath, voiceDir]);
  const pick = async (kind: 'video' | 'srt' | 'voice') => {
    if (kind === 'voice') { const path = await window.desktop?.selectFolder(); if (path) setVoiceDir(path); return; }
    const path = await window.desktop?.selectFile({ filters: kind === 'video' ? [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'avi', 'm4v', 'webm'] }] : [{ name: 'SubRip Subtitle', extensions: ['srt'] }] });
    if (path) kind === 'video' ? setVideoPath(path) : setSrtPath(path);
  };
  const create = async () => {
    if (!window.desktop || !analysis?.ready || running) return;
    setRunning(true); setLogs([]); setResult(null); setMessage('Äang chuáº©n bá»‹ project má»›iâ€¦');
    try {
      const created = await window.desktop.request<{ projectName: string; projectPath: string; template: string }>('capcut.project.create', { videoPath, srtPath, voiceDir, projectName });
      setResult(created); setMessage(`HoÃ n táº¥t project: ${created.projectName}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setRunning(false); }
  };
  const fileName = (value: string) => value.split(/[\\/]/).at(-1) || '';
  return <div className="capcut-project-page">
    <div className="capcut-project-hero"><div><div className="eyebrow"><Clapperboard size={14} /> Tá»° Äá»˜NG HÃ“A CAPCUT</div><h1>Táº¡o vÃ  Ä‘á»“ng bá»™ <span>dá»± Ã¡n CapCut.</span></h1><p>Tá»± thÃªm video gá»‘c, phá»¥ Ä‘á», voice vÃ  co giÃ£n video theo thá»i lÆ°á»£ng lá»i Ä‘á»c.</p></div><button className="primary" disabled={!analysis?.ready || !projectName.trim() || running} onClick={create}>{running ? <><RefreshCw className="spin" size={17} /> Äang táº¡o dá»± Ã¡nâ€¦</> : <><Sparkles size={17} /> Táº¡o dá»± Ã¡n & Ä‘á»“ng bá»™</>}</button></div>
    <section className="capcut-input-grid">
      <button onClick={() => pick('video')}><span className="capcut-step">1</span><Clapperboard size={23} /><div><small>VIDEO Gá»C</small><strong>{fileName(videoPath) || 'Chá»n video'}</strong><em>{videoPath || 'MP4, MOV, MKVâ€¦'}</em></div></button>
      <button onClick={() => pick('srt')}><span className="capcut-step">2</span><Captions size={23} /><div><small>PHá»¤ Äá»€ SRT</small><strong>{fileName(srtPath) || 'Chá»n file SRT'}</strong><em>{srtPath || 'Timestamp dÃ¹ng Ä‘á»ƒ chia video'}</em></div></button>
      <button onClick={() => pick('voice')}><span className="capcut-step">3</span><AudioLines size={23} /><div><small>THÆ¯ Má»¤C VOICE</small><strong>{fileName(voiceDir) || 'Chá»n thÆ° má»¥c voice'}</strong><em>{voiceDir || '0001.wav, 0002.wavâ€¦'}</em></div></button>
    </section>
    <section className="capcut-project-settings"><label><small>TÃŠN Dá»° ÃN Má»šI</small><input value={projectName} onChange={(e) => setProjectName(e.target.value)} /></label><div className={`capcut-readiness ${analysis?.ready ? 'ready' : analysis ? 'warning' : ''}`}><Check size={18} /><span><strong>{analysis ? `${analysis.voiceFiles}/${analysis.subtitles} voice Ä‘Ã£ khá»›p` : 'ChÆ°a kiá»ƒm tra Ä‘áº§u vÃ o'}</strong><small>{analysis?.missing.length ? `Thiáº¿u: ${analysis.missing.slice(0, 12).map((id) => String(id).padStart(4, '0')).join(', ')}` : 'Project má»›i sáº½ Ä‘Æ°á»£c lÆ°u vÃ o thÆ° má»¥c dá»± Ã¡n CapCut máº·c Ä‘á»‹nh.'}</small></span></div></section>
    <section className="capcut-flow"><div><span>1</span><strong>Táº¡o project má»›i</strong><small>Sinh schema CapCut sáº¡ch</small></div><i>â†’</i><div><span>2</span><strong>ThÃªm ná»™i dung</strong><small>Video + SRT + voice</small></div><i>â†’</i><div><span>3</span><strong>Cáº¯t video</strong><small>Theo tá»«ng block SRT</small></div><i>â†’</i><div><span>4</span><strong>Äá»“ng bá»™</strong><small>Voice quyáº¿t Ä‘á»‹nh timeline</small></div></section>
    <section className="capcut-progress-panel"><header><div><small>TIáº¾N TRÃŒNH</small><strong>{message}</strong></div><span>{running ? 'ÄANG Xá»¬ LÃ' : result ? 'HOÃ€N Táº¤T' : 'Sáº´N SÃ€NG'}</span></header><div className="capcut-log">{logs.length ? logs.map((line, index) => <p key={`${index}-${line}`}>{line}</p>) : <p>ChÆ°a cÃ³ tÃ¡c vá»¥. Tool sáº½ yÃªu cáº§u Ä‘Ã³ng CapCut trÆ°á»›c khi ghi project.</p>}</div>{result && <footer><div><Check size={18} /><span><strong>{result.projectName}</strong><small>{result.template} Â· {result.projectPath}</small></span></div><button onClick={() => window.desktop?.showInFolder(result.projectPath)}><FolderOpen size={15} /> Má»Ÿ thÆ° má»¥c</button><button className="open-capcut" onClick={() => window.desktop?.request('capcut.open')}><Clapperboard size={15} /> Má»Ÿ CapCut</button></footer>}</section>
  </div>;
}

function VoiceBackendSettings() {
  const [mode, setMode] = useState<'local' | 'colab'>('local');
  const [url, setUrl] = useState(''); const [token, setToken] = useState('');
  const [message, setMessage] = useState('Chá»n nÆ¡i thá»±c hiá»‡n suy luáº­n OmniVoice.'); const [testing, setTesting] = useState(false);
  useEffect(() => { window.desktop?.request<{ voiceBackend?: { mode: 'local' | 'colab'; url: string; token: string } }>('settings.get').then((v) => {
    if (v.voiceBackend) { setMode(v.voiceBackend.mode); setUrl(v.voiceBackend.url); setToken(v.voiceBackend.token || ''); }
  }); }, []);
  const save = async () => { try { await window.desktop?.request('settings.voice.save', { mode, url, token }); setMessage('ÄÃ£ lÆ°u cáº¥u hÃ¬nh backend giá»ng nÃ³i.'); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } };
  const test = async () => { setTesting(true); try { const r = await window.desktop?.request<{ device?: string | null; status?: string | null; detail?: string | null }>('settings.voice.test', { mode, url, token }); if (!r) throw new Error('Backend Electron chÆ°a sáºµn sÃ ng.'); const device = (r.device || 'GPU').toUpperCase(); setMessage(`Káº¿t ná»‘i thÃ nh cÃ´ng Â· ${device} Â· ${r.status || 'sáºµn sÃ ng'}${r.detail ? ` Â· ${r.detail}` : ''}`); } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); } finally { setTesting(false); } };
  return <div className="voice-backend-page"><div className="settings-hero"><div className="eyebrow"><Settings2 size={15}/> Cáº¤U HÃŒNH á»¨NG Dá»¤NG</div><h1>Thiáº¿t láº­p cáº¥u hÃ¬nh</h1><p>Chá»n bá»™ xá»­ lÃ½ OmniVoice cho PhÃ²ng thu vÃ  Táº¡o tá»« SRT.</p></div>
    <section className="voice-backend-card"><header><AudioLines size={23}/><div><h2>Cáº¥u hÃ¬nh Bá»™ xá»­ lÃ½ (Backend)</h2><p>Cháº¡y trÃªn mÃ¡y hoáº·c dÃ¹ng GPU Google Colab cho mÃ¡y cáº¥u hÃ¬nh yáº¿u.</p></div></header>
      <div className="backend-options"><button className={mode === 'local' ? 'selected' : ''} onClick={() => setMode('local')}><b>â—‹</b><strong>Cháº¡y cá»¥c bá»™ (Local GPU/CPU)</strong><small>RiÃªng tÆ°, offline; sá»­ dá»¥ng pháº§n cá»©ng cá»§a mÃ¡y.</small></button><button className={mode === 'colab' ? 'selected' : ''} onClick={() => setMode('colab')}><b>â—‹</b><strong>Google Colab (Remote GPU)</strong><small>Táº¡o giá»ng trÃªn GPU Colab, káº¿t quáº£ váº«n lÆ°u vá» mÃ¡y.</small></button></div>
      {mode === 'colab' && <div className="colab-config"><div><strong>ÄÆ°á»ng dáº«n API Google Colab</strong><a href="https://colab.research.google.com/github/nguyenduchung98/HHVietSub-Colab/blob/main/HHVietSub_Colab.ipynb" target="_blank" rel="noreferrer">Má»Ÿ Colab Notebook â†—</a></div><ol><li>Chá»n Runtime â†’ Change runtime type â†’ GPU.</li><li>Run all vÃ  chá» URL dáº¡ng https://xxx.trycloudflare.com.</li><li>DÃ¡n URL, kiá»ƒm tra káº¿t ná»‘i rá»“i lÆ°u.</li></ol><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://xxx.trycloudflare.com"/><input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Token báº£o máº­t (notebook má»›i, tÃ¹y chá»n)"/><button onClick={test} disabled={testing}>{testing ? 'Äang kiá»ƒm traâ€¦' : 'Kiá»ƒm tra káº¿t ná»‘i'}</button></div>}
      <footer><span>{message}</span><button className="primary" onClick={save}>LÆ°u cáº¥u hÃ¬nh</button></footer></section></div>;
}

function Placeholder({ page, label }: { page: Page; label: string }) {
  const descriptions: Record<Page, string> = { studio: '', translate: '', srt: 'Táº£i file SRT vÃ  táº¡o giá»ng nÃ³i khá»›p theo tá»«ng má»‘c thá»i gian.', capcut: '', settings: 'Quáº£n lÃ½ backend, model OmniVoice, Ä‘á»‹nh dáº¡ng audio vÃ  thÆ° má»¥c Ä‘áº§u ra.' };
  return <div className="placeholder"><div className="upload-icon">{page === 'srt' ? <UploadCloud size={32} /> : <Settings2 size={32} />}</div><div className="eyebrow">{page === 'srt' ? 'KHá»šP THá»œI GIAN CHÃNH XÃC' : 'Cáº¤U HÃŒNH á»¨NG Dá»¤NG'}</div><h1>{label}</h1><p>{descriptions[page]}</p>{page === 'srt' && <button className="primary"><Captions size={17} /> Chá»n tá»‡p SRT</button>}</div>;
}

