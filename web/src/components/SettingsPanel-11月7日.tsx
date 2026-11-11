import { useEffect, useRef, useState } from 'react';
import { RotateCcw, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { defaultPreferences } from '../lib/preferences-11月7日';
import type { EditorPreferences, StyleSettings } from '../lib/preferences-11月7日';
import type { EditorScene } from '../types';

interface Props {
  scene?: EditorScene;
  preferences: EditorPreferences;
  initialTab: 'editor' | 'subtitle';
  onPreview: (scene: EditorScene | null) => void;
  onSave: (preferences: EditorPreferences, style: StyleSettings) => Promise<boolean>;
  onClose: () => void;
}

export function SettingsPanel({scene, preferences, initialTab, onPreview, onSave, onClose}: Props) {
  const [tab, setTab] = useState(initialTab);
  const [prefs, setPrefs] = useState(preferences);
  const [style, setStyle] = useState<StyleSettings>({});
  const [resolved, setResolved] = useState(scene);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const panel = useRef<HTMLElement>(null);
  const initial = useRef(scene);
  const onPreviewRef = useRef(onPreview);
  onPreviewRef.current = onPreview;

  useEffect(() => {
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => onPreviewRef.current(null);
  }, []);

  useEffect(() => {
    if (!Object.keys(style).length) { setResolved(initial.current); onPreviewRef.current(null); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void apiFetch<EditorScene>('/api/editor/settings/preview', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(style), signal: controller.signal,
      }).then(value => {
        setResolved(value); onPreviewRef.current(value); setError('');
      }).catch(reason => { if (!controller.signal.aborted) setError(String(reason)); });
    }, 140);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [style]);

  function change<K extends keyof EditorPreferences>(key: K, value: EditorPreferences[K]) {
    setPrefs(current => ({...current, [key]:value}));
  }
  function layout(key: 'margin_x' | 'top_y' | 'bottom_y', value: number) {
    setStyle(current => ({...current, layout:{...current.layout, [key]:value}}));
  }
  function reset() {
    if (tab === 'editor') setPrefs({...defaultPreferences});
    else setStyle(current => ({...current, theme:initial.current?.theme??'nogizaka46', colors:{},
      layout:{margin_x:110,top_y:750,bottom_y:950},countdown:false,katakana_ruby:false,
      media:{blackout:[]}}));
  }
  async function save() {
    setBusy(true); setError('');
    try {
      if (await onSave(prefs, style)) onClose();
      else setError('保存失败，请重试');
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }
  function trap(event: React.KeyboardEvent) {
    event.stopPropagation();
    if (event.key === 'Escape' && !busy) { event.preventDefault(); onClose(); }
    if (event.key !== 'Tab') return;
    const controls = [...(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input,select') ?? [])]
      .filter(element => element.getClientRects().length > 0);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  const current = resolved ?? scene;
  const masks = style.media?.blackout ?? current?.blackout ?? [];
  const bottomMask = masks.length === 1 && masks[0].x === 0 && masks[0].width === 1920
    && masks[0].start === 0 && masks[0].end == null;
  const percent = bottomMask ? Math.round(masks[0].height/1080*100) : 0;
  return <div className="settings-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget && !busy) onClose();
  }}><section ref={panel} className="settings-panel" role="dialog" aria-modal="true" aria-label="设置" onKeyDown={trap}>
    <div className="settings-heading"><strong>设置</strong><button aria-label="关闭设置" onClick={onClose} disabled={busy}><X size={17}/></button></div>
    <div className="settings-tabs" role="tablist" aria-label="设置分类">
      <button role="tab" aria-selected={tab==='editor'} onClick={() => setTab('editor')}>播放与编辑</button>
      <button role="tab" aria-selected={tab==='subtitle'} onClick={() => setTab('subtitle')}>字幕样式</button>
    </div>
    <div className="settings-body">
      {tab==='editor' ? <>
        <div className="settings-section-title">播放</div>
        <label className="preference-row">默认速度<select aria-label="默认速度" value={prefs.playback_speed} onChange={e=>change('playback_speed',Number(e.target.value))}>{[.5,.75,1,1.25,1.5,2].map(v=><option key={v} value={v}>{v}×</option>)}</select></label>
        <label className="preference-row">倍速保调<input type="checkbox" checked={prefs.preserve_pitch} onChange={e=>change('preserve_pitch',e.target.checked)}/></label>
        <label className="preference-row">默认循环<select aria-label="默认循环" value={prefs.loop} onChange={e=>change('loop',e.target.value as EditorPreferences['loop'])}><option value="line">循环此句</option><option value="off">连续播放</option></select></label>
        <label className="settings-slider">句前预听 <span className="setting-value">{(prefs.lead_ms/1000).toFixed(2)}s</span><input aria-label="句前预听" type="range" min="0" max="2000" step="50" value={prefs.lead_ms} onChange={e=>change('lead_ms',Number(e.target.value))}/></label>
        <div className="settings-section-title">时间轴</div>
        <label className="preference-row">拖动吸附<input type="checkbox" checked={prefs.snap} onChange={e=>change('snap',e.target.checked)}/></label>
        <label className="preference-row">吸附间隔<select aria-label="吸附间隔" value={prefs.snap_ms} onChange={e=>change('snap_ms',Number(e.target.value))}>{[1,5,10,20,50,100].map(v=><option key={v} value={v}>{v} ms</option>)}</select></label>
        <label className="preference-row">方向键步长<select aria-label="方向键步长" value={prefs.key_step_ms} onChange={e=>change('key_step_ms',Number(e.target.value))}>{[1,5,10,20,50,100].map(v=><option key={v} value={v}>{v} ms</option>)}</select></label>
        <label className="preference-row">Shift 定位步长<select aria-label="Shift 定位步长" value={prefs.seek_large_ms} onChange={e=>change('seek_large_ms',Number(e.target.value))}>{[100,250,500,1000].map(v=><option key={v} value={v}>{v/1000}s</option>)}</select></label>
        <div className="settings-section-title">轨道显示</div>
        <label className="preference-row">音频波形<input type="checkbox" checked={prefs.show_waveform} onChange={e=>change('show_waveform',e.target.checked)}/></label>
        <label className="preference-row">正文单字<input type="checkbox" checked={prefs.show_characters} onChange={e=>change('show_characters',e.target.checked)}/></label>
        <label className="preference-row">假名读音<input type="checkbox" checked={prefs.show_readings} onChange={e=>change('show_readings',e.target.checked)}/></label>
      </> : <>
        <label className="settings-field">右上标题<input aria-label="右上标题" value={style.title_text??current?.title_text??''} onChange={e=>setStyle(s=>({...s,title_text:e.target.value}))}/></label>
        <label className="preference-row">团体<select aria-label="团体" value={style.theme??current?.theme??'nogizaka46'} onChange={e=>setStyle(s=>({...s,theme:e.target.value,colors:{}}))}>{[['nogizaka46','乃木坂46'],['hinatazaka46','日向坂46'],['keyakizaka46','欅坂46'],['sakurazaka46','櫻坂46'],['not_equal_me','≠ME']].map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label className="preference-row">已唱颜色<input type="color" aria-label="已唱颜色" value={style.colors?.sung??current?.colors.sung??'#8B4FD8'} onChange={e=>setStyle(s=>({...s,colors:{...s.colors,sung:e.target.value}}))}/></label>
        <label className="preference-row">段落倒数<input type="checkbox" checked={style.countdown??current?.countdown??false} onChange={e=>setStyle(s=>({...s,countdown:e.target.checked}))}/></label>
        <label className="preference-row">片假名注音<input type="checkbox" checked={style.katakana_ruby??current?.katakana_ruby??false} onChange={e=>setStyle(s=>({...s,katakana_ruby:e.target.checked}))}/></label>
        <div className="settings-section-title">画面位置</div>
        {([['top_y','上行高度',750,400,900],['bottom_y','下行高度',950,600,1040],['margin_x','左右留白',110,20,300]] as const).map(([key,label,fallback,min,max])=><label className="settings-slider" key={key}>{label}<span className="setting-value">{style.layout?.[key]??current?.layout[key]??fallback} px</span><input aria-label={label} type="range" min={min} max={max} step="5" value={style.layout?.[key]??current?.layout[key]??fallback} onChange={e=>layout(key,Number(e.target.value))}/></label>)}
        <div className="settings-section-title">底部遮黑</div>
        {masks.length>0&&!bottomMask ? <div className="settings-mask-note">当前项目使用坐标或时段遮黑<button onClick={()=>setStyle(s=>({...s,media:{blackout:[]}}))}>关闭遮黑</button></div> : <label className="settings-slider">遮黑比例<span className="setting-value">{percent}%</span><input aria-label="遮黑比例" type="range" min="0" max="40" step="1" value={percent} onChange={e=>{const ratio=Number(e.target.value)/100;setStyle(s=>({...s,media:{blackout:ratio?[{x:0,y:1080*(1-ratio),width:1920,height:1080*ratio,start:0}]:[]}}))}}/></label>}
      </>}
    </div>
    {error&&<div className="settings-error" role="alert">{error}</div>}
    <div className="settings-footer"><button onClick={reset} disabled={busy}><RotateCcw size={14}/>恢复默认</button><span className="spacer"/><button onClick={onClose} disabled={busy}>取消</button><button className="primary" onClick={()=>void save()} disabled={busy}>{busy?'保存中':'应用'}</button></div>
  </section></div>;
}
