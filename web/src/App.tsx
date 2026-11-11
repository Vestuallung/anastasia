import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Download, FolderOpen, HelpCircle, Pause, Play, Redo2, RefreshCw, Settings2, Undo2, X } from 'lucide-react';
import { ProjectPreview } from './components/ProjectPreview-11月7日';
import { BitrateInput, validVideoBitrate } from './components/BitrateInput-11月11日';
import { Timeline } from './components/Timeline';
import { Inspector } from './components/Inspector';
import { SettingsPanel } from './components/SettingsPanel-11月7日';
import { defaultPreferences } from './lib/preferences-11月7日';
import type { EditorPreferences, StyleSettings } from './lib/preferences-11月7日';
import { ImportPanel } from './components/ImportPanel';
import { apiFetch, apiUrl, getProject, getWaveform, saveTiming } from './lib/api';
import type { EditorScene, ProjectPayload, RubyGroup, WaveformPayload } from './types';
interface History {lineId:string;before:number[];after:number[]}
type JobKind = 'align' | 'render';
interface EditorJob {
  id:string;
  mode:JobKind;
  upload?:boolean;
  video_bitrate_mbps?:number|null;
  status:string;
  message:string;
  files?:Record<string,string>;
  details?:{overwide?:Array<{index:number;text:string;width_px:number}>};
}
const finished = (status:string) => ['completed','failed','cancelled','interrupted'].includes(status);
const outputLabels:Record<string,string> = {
  on_vocal_karaoke:'日文卡拉 OK',
  on_vocal_karaoke_zh:'中日双语',
  off_vocal_karaoke:'伴奏卡拉 OK',
};
const fmt=(ms:number)=>`${Math.floor(ms/60000).toString().padStart(2,'0')}:${((ms%60000)/1000).toFixed(2).padStart(5,'0')}`;
function App(){
 const [project,setProject]=useState<ProjectPayload|null>(null),[waveform,setWaveform]=useState<WaveformPayload>({peaks:[],duration_ms:0});
 const [selectedId,setSelectedId]=useState(''),[range,setRange]=useState<[number,number]|null>(null),[currentMs,setCurrentMs]=useState(0),[playing,setPlaying]=useState(false),[loop,setLoop]=useState<'line'|'selection'|'off'>('line'),[speed,setSpeed]=useState(.75);
 const [previewBounds,setPreviewBounds]=useState<number[]|null>(null),[draftScene,setDraftScene]=useState<EditorScene|null>(null),[text,setText]=useState(''),[saveState,setSaveState]=useState<'saved'|'saving'|'error'>('saved');
 const [error,setError]=useState(''),[help,setHelp]=useState(false),[settingsOpen,setSettingsOpen]=useState(false),[settingsTab,setSettingsTab]=useState<'editor'|'subtitle'>('editor'),[styleScene,setStyleScene]=useState<EditorScene|null>(null),[taskOpen,setTaskOpen]=useState(false),[taskMessage,setTaskMessage]=useState(''),[taskBusy,setTaskBusy]=useState(false),[files,setFiles]=useState<Record<string,string>>({});
 const [currentJob,setCurrentJob]=useState<EditorJob|null>(null);
 const [uploadCopy,setUploadCopy]=useState(false);
 const [exportBitrate,setExportBitrate]=useState<string|null>(null);
 const [undoStack,setUndoStack]=useState<History[]>([]),[redoStack,setRedoStack]=useState<History[]>([]),[preferenceVersion,setPreferenceVersion]=useState(0);
 const mediaRef=useRef<HTMLAudioElement>(null),queue=useRef<Promise<unknown>>(Promise.resolve()),events=useRef<EventSource|null>(null),loadedId=useRef('');
 const load=useCallback(async()=>{try{const [p,w]=await Promise.all([getProject(),getWaveform().catch(()=>null)]);setProject(p);setWaveform(w??{peaks:[],duration_ms:p.audio.duration_ms||0});setSelectedId(id=>p.lines.some(l=>l.id===id)?id:p.lines[0]?.id||'')}catch(e){setError(String(e))}},[]);
 const watchJob=useCallback((initial:EditorJob)=>{
   events.current?.close();
   setCurrentJob(initial);setTaskMessage(initial.message);setTaskBusy(!finished(initial.status));
   setFiles(initial.files??{});
   if(finished(initial.status))return;
   const source=new EventSource(apiUrl(`/api/jobs/${initial.id}/events`));
   events.current=source;
   source.onmessage=event=>{
     const value={...initial,...JSON.parse(event.data)} as EditorJob;
     setCurrentJob(value);setTaskMessage(value.message);
     if(!finished(value.status))return;
     source.close();setTaskBusy(false);
     if(value.status==='completed'){
       void load();
       if(value.mode==='render')void apiFetch<{files:Record<string,string>}>(`/api/jobs/${initial.id}/result`)
         .then(result=>setFiles(result.files)).catch(reason=>setTaskMessage(String(reason)));
     }
   };
   source.onerror=()=>setTaskMessage('连接中断，正在尝试重新连接');
 },[load]);
 useEffect(()=>{
   let live=true;
   void load();
   if(/^\/p\/[a-f0-9]{16}/.test(window.location.pathname)){
     void apiFetch<{job:EditorJob|null}>('/api/editor/job').then(({job})=>{if(live&&job)watchJob(job)}).catch(()=>{});
   }
   return()=>{live=false;events.current?.close()};
 },[load,watchJob]);
 const selected=project?.lines.find(l=>l.id===selectedId),index=project?.lines.findIndex(l=>l.id===selectedId)??-1;
 const savedBounds=project?.effective_boundaries[selectedId]??[],bounds=previewBounds??savedBounds,scene=styleScene??draftScene??project?.editor;
 const preferences=project?.editor_preferences??defaultPreferences;
 const duration=waveform.duration_ms||project?.audio.duration_ms||1;
 const segment=scene?.lines.find(l=>l.id===selectedId),dirty=text!==(selected?.original??'');
 useEffect(()=>{if(savedBounds.length<2)return;const controller=new AbortController();void getWaveform(Math.max(0,savedBounds[0]-450),Math.min(duration,savedBounds.at(-1)!+450),controller.signal).then(setWaveform).catch(()=>{});return()=>controller.abort()},[selectedId,savedBounds[0],savedBounds.at(-1),duration]);
 const a=loop==='selection'&&range?bounds[range[0]]:bounds[0],b=loop==='selection'&&range?bounds[range[1]]:bounds.at(-1);
 const clock=useRef({a,b,loop,duration,lead:preferences.lead_ms,offset:scene?.audio_offset_ms??0});clock.current={a,b,loop,duration,lead:preferences.lead_ms,offset:scene?.audio_offset_ms??0};
 useEffect(()=>{setText(selected?.original??'');setDraftScene(null);setPreviewBounds(null);setRange(null)},[selectedId,selected?.original]);
 const seek=useCallback((ms:number)=>{const m=mediaRef.current;if(m)m.currentTime=Math.max(0,ms+(clock.current.offset||0))/1000;setCurrentMs(Math.max(0,ms))},[]);
 useEffect(()=>{const m=mediaRef.current;if(!m)return;m.playbackRate=speed;m.preservesPitch=preferences.preserve_pitch},[speed,project?.project_id,preferences.preserve_pitch]);
 useEffect(()=>{setSpeed(preferences.playback_speed);setLoop(preferences.loop)},[project?.project_id,preferences.playback_speed,preferences.loop]);
 useEffect(()=>{let frame=0;let last=0;function update(t:number){const m=mediaRef.current;if(m&&t-last>25){const c=clock.current;let value=m.currentTime*1000-c.offset;if(!m.paused&&c.loop!=='off'&&c.a!=null&&c.b!=null&&value>=c.b+100){m.currentTime=Math.max(0,c.a-c.lead+c.offset)/1000;value=c.a-c.lead}setCurrentMs(Math.max(0,value));setPlaying(!m.paused&&!m.ended);last=t}frame=requestAnimationFrame(update)}frame=requestAnimationFrame(update);return()=>cancelAnimationFrame(frame)},[Boolean(project)]);
 useEffect(()=>{if(!dirty){setDraftScene(null);return}if(!selected)return;const controller=new AbortController();const timer=setTimeout(()=>{void apiFetch<EditorScene>(`/api/lines/${selected.id}/text`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,commit:false}),signal:controller.signal}).then(setDraftScene).catch(()=>{})},180);return()=>{clearTimeout(timer);controller.abort()}},[text,selectedId,dirty]);
 useEffect(()=>{const initial=project?.effective_boundaries[selectedId]?.[0];if(initial!=null)seek(Math.max(0,initial-preferences.lead_ms))},[selectedId,project?.project_id]);
 async function select(id:string){if(saveState==='saving'||id===selectedId)return;if(dirty&&!await saveText())return;setSelectedId(id);const start=project?.effective_boundaries[id]?.[0];if(start!=null)seek(Math.max(0,start-preferences.lead_ms))}
 function toggle(){const m=mediaRef.current;if(!m)return;if(!m.paused){m.pause();setPlaying(false)}else{if(a!=null&&b!=null&&(currentMs<a||currentMs>=b))seek(Math.max(0,a-preferences.lead_ms));void m.play().then(()=>setPlaying(true)).catch(e=>setError(String(e)))}}
 function enqueue(action:()=>Promise<ProjectPayload>):Promise<boolean>{
   setSaveState('saving');
   const next=queue.current.catch(()=>{}).then(async()=>{
     try{const p=await action();setProject(p);setSaveState('saved');setDraftScene(null);setError('');return true}
     catch(e){setSaveState('error');setError(e instanceof Error?e.message:String(e));setUndoStack([]);setRedoStack([]);try{setProject(await getProject())}catch{}return false}
   });queue.current=next;return next;
 }
 function commit(before:number[],after:number[],kind:'line_shift'|'boundary'|'line_start'|'line_end',boundaryIndex?:number){if(!selected)return;const id=selected.id;setProject(p=>p?{...p,effective_boundaries:{...p.effective_boundaries,[id]:after}}:p);setUndoStack(s=>[...s,{lineId:id,before,after}]);setRedoStack([]);enqueue(()=>saveTiming(id,after,kind,boundaryIndex))}
 function history(direction:'undo'|'redo'){if(saveState==='saving')return;const stack=direction==='undo'?undoStack:redoStack,item=stack.at(-1);if(!item)return;const next=direction==='undo'?item.before:item.after;if(direction==='undo'){setUndoStack(s=>s.slice(0,-1));setRedoStack(s=>[...s,item])}else{setRedoStack(s=>s.slice(0,-1));setUndoStack(s=>[...s,item])}enqueue(()=>saveTiming(item.lineId,next,'line_shift'))}
 async function applySettings(value:EditorPreferences,style:StyleSettings){const success=await enqueue(async()=>{
   if(Object.keys(style).length)await apiFetch('/api/editor/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(style)});
   return apiFetch('/api/editor/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
 });if(success){setSpeed(value.playback_speed);setLoop(value.loop);setPreferenceVersion(v=>v+1)}return success}
 function closeSettings(){setSettingsOpen(false);setStyleScene(null);document.querySelector<HTMLButtonElement>('button[aria-label="设置"]')?.focus()}
 async function openSettings(tab:'editor'|'subtitle'){
   if(saveState==='saving')return;if(dirty&&!await saveText())return;
   mediaRef.current?.pause();setPlaying(false);setSettingsTab(tab);setSettingsOpen(true);
 }
 function saveText(value=text):Promise<boolean>{if(!selected)return Promise.resolve(false);const id=selected.id;return enqueue(()=>apiFetch(`/api/lines/${id}/text`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:value,commit:true})}))}
 function reading(group:RubyGroup,value:string,_romaji:string){if(selected)saveText(selected.original.slice(0,group.span.start)+group.display+'《'+value+'》'+selected.original.slice(group.span.end))}
 async function task(
   kind:JobKind,fresh=true,upload=kind==='render'&&uploadCopy,
   bitrate=exportBitrate===null?null:Number(exportBitrate),
 ){
   setTaskOpen(true);setTaskBusy(true);setFiles({});
   const message=kind==='render'?'正在导出成片':'正在对齐';
   setTaskMessage(message);
   try{
     const query = new URLSearchParams({fresh:String(fresh)});
     if(kind==='render'){
       if(upload)query.set('upload','true');
       if(bitrate!==null)query.set('video_bitrate_mbps',String(bitrate));
     }
     const result=await apiFetch<{job_id:string}>(`/api/jobs/${kind}?${query}`,{method:'POST'});
     watchJob({id:result.job_id,mode:kind,status:'queued',message,upload,video_bitrate_mbps:bitrate});
   }catch(e){setTaskMessage(String(e));setTaskBusy(false)}
 }
 async function stopTask(){
   if(!currentJob)return;
   try{await apiFetch(`/api/jobs/${currentJob.id}/cancel`,{method:'POST'})}
   catch(e){setTaskMessage(String(e))}
 }

 useEffect(()=>{function key(e:KeyboardEvent){if((e.metaKey||e.ctrlKey)&&e.key===','){e.preventDefault();void openSettings('editor');return}if(settingsOpen||help||taskOpen)return;const target=e.target as HTMLElement;if(['INPUT','TEXTAREA','SELECT'].includes(target.tagName))return;if(e.code==='Space'){e.preventDefault();toggle()}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();history(e.shiftKey?'redo':'undo')}if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();seek(Math.max(0,Math.min(duration,currentMs+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?preferences.seek_large_ms:preferences.key_step_ms))))}}window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[currentMs,duration,undoStack,redoStack,a,b,preferences.seek_large_ms,preferences.key_step_ms,settingsOpen,help,taskOpen,saveState,dirty]);
 useEffect(()=>{if(project&&loadedId.current!==project.project_id){loadedId.current=project.project_id;setUndoStack([]);setRedoStack([])}},[project?.project_id]);
 if(!project)return <div className="boot-screen"><RefreshCw size={18} className="spin"/>{error||'正在打开项目'}</div>;
 if(!project.lines.length)return <ImportPanel onImported={p=>{setProject(p);setSelectedId(p.lines[0]?.id||'');void getWaveform().then(setWaveform)}}/>;
 const subtitle=selected?.display_tokens.map(t=>t.text).join('');
 const bitrateValue=exportBitrate??String(project.editor?.video_bitrate_mbps??'');
 return <div className={`app-shell ${settingsOpen?'settings-visible':''}`}><header className="app-header"><div className="brand-mark">♪</div><strong>Karaoke Studio</strong><span className="header-slash">/</span><span className="project-title">{project.title}</span><div className="spacer"/><span className="save-state">{saveState==='saving'?'保存中':saveState==='error'?'保存失败':<><Check size={13}/>已保存</>}</span><button onClick={()=>history('undo')} disabled={!undoStack.length||saveState==='saving'} aria-label="撤销"><Undo2 size={16}/></button><button onClick={()=>history('redo')} disabled={!redoStack.length||saveState==='saving'} aria-label="重做"><Redo2 size={16}/></button><button onClick={()=>void openSettings('editor')} disabled={saveState==='saving'} aria-label="设置"><Settings2 size={16}/></button><button onClick={()=>setHelp(true)} aria-label="帮助"><HelpCircle size={16}/></button><button className="primary" onClick={()=>void task('render')} disabled={saveState==='saving'||dirty||taskBusy||project.alignment_stale||!validVideoBitrate(bitrateValue)}><Download size={15}/>导出成片</button></header>
 <nav className="workspace-tabs"><button onClick={()=>{if(/^\/p\/[a-f0-9]{16}/.test(window.location.pathname)){window.location.assign('/');return}const w=window as unknown as {webkit?:{messageHandlers?:{desktop?:{postMessage:(s:string)=>void}}}};if(w.webkit?.messageHandlers?.desktop)w.webkit.messageHandlers.desktop.postMessage('open');else void apiFetch('/api/editor/open-folder')}}>项目</button><button className="active" onClick={()=>{if(settingsOpen)closeSettings()}}>打轴工作台</button><button onClick={()=>void openSettings('subtitle')}>字幕样式</button><button onClick={()=>setTaskOpen(true)}>导出任务</button><BitrateInput value={bitrateValue} onChange={setExportBitrate} disabled={taskBusy}/><label className="version-choice upload-option"><input type="checkbox" checked={uploadCopy} disabled={taskBusy} onChange={event=>setUploadCopy(event.target.checked)}/>同时生成上传版（500 MB 以内）</label><span className="spacer"/><span className="muted small">{scene?.canvas.width} × {scene?.canvas.height}</span></nav>
 {error&&<div className="error-banner" role="alert"><span>{error}</span><button onClick={()=>setError('')} aria-label="关闭错误"><X size={14}/></button></div>}
 {project.alignment_stale&&<div className="attention-banner"><span>读音已修改</span><button onClick={()=>void task('align')} disabled={taskBusy}>重新对齐</button></div>}
 <div className="workspace"><aside className="lyrics-panel"><div className="section-heading">歌词与段落 <span className="muted">{project.lines.length} 句</span></div><div className="lyrics-list">{project.lines.map((line,i)=>{const timing=project.effective_boundaries[line.id];return <div key={line.id}>{(i===0||line.paragraph_before>0)&&<div className="paragraph-label">段落 {1+project.lines.slice(0,i).filter(l=>l.paragraph_before>0).length+(i>0&&line.paragraph_before>0?1:0)}</div>}<button className={`lyric-row ${line.id===selectedId?'active':''}`} onClick={()=>select(line.id)}><span>{line.display_tokens.map(t=>t.text).join('')}</span><small>{timing?.length?`${fmt(timing[0])} — ${fmt(timing.at(-1)!)}`:'待对齐'}</small></button></div>})}</div></aside>
 <main className="editor-main"><div className="preview-toolbar"><span>画面预览</span><span>{segment&&segment.width>1700?'当前句超宽':''}</span></div><ProjectPreview scene={scene} mediaRef={mediaRef} selectedId={selectedId} boundaries={bounds} currentMs={currentMs} hasVideo={Boolean(project.source.video_path)}/><div className="transport"><span className="time-readout">{fmt(currentMs)}</span><button onClick={()=>project.lines[index-1]&&select(project.lines[index-1].id)} aria-label="上一句"><ChevronLeft size={17}/></button><button className="primary play-button" onClick={toggle} aria-label={playing?'暂停':'播放'}>{playing?<Pause size={17}/>:<Play size={17}/>}</button><button onClick={()=>project.lines[index+1]&&select(project.lines[index+1].id)} aria-label="下一句"><ChevronRight size={17}/></button><select aria-label="循环范围" value={loop} onChange={e=>setLoop(e.target.value as typeof loop)}><option value="line">循环此句</option><option value="selection" disabled={!range}>循环选中</option><option value="off">连续播放</option></select><select aria-label="播放速度" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.5,.75,1,1.25,1.5,2].map(v=><option value={v} key={v}>{v}×</option>)}</select></div></main>
 <Inspector line={selected} range={range} bounds={bounds} scene={scene} saving={saveState==='saving'} onReading={reading}/></div>
 <section className="editing-area"><div className="line-editor"><span>日文</span><input aria-label="当前句歌词" disabled={saveState==='saving'} value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&dirty)saveText();if(e.key==='Escape')setText(selected?.original??'')}}/><button disabled={!dirty||saveState==='saving'} onClick={()=>saveText()}>保存</button></div><Timeline preferenceVersion={preferenceVersion} preferences={preferences} line={selected} boundaries={savedBounds} glyphs={segment?.glyphs} selectedRange={range??undefined} onSelect={setRange} peaks={waveform.peaks} waveformStart={waveform.start_ms} waveformEnd={waveform.end_ms} durationMs={duration} currentMs={currentMs} onSeek={seek} onPreview={setPreviewBounds} onCommit={commit} disabled={saveState==='saving'||dirty} onRestore={()=>selected&&enqueue(()=>apiFetch(`/api/lines/${selected.id}/restore-timing`,{method:'POST'}))}/></section>
 <footer className="status-bar"><span>{range?selected?.moras.slice(range[0],range[1]).map(m=>m.kana).join(''):subtitle}</span><span>{project.alignment_stale?'需要对齐':'时间轴已同步'}</span></footer>
 {settingsOpen&&<SettingsPanel scene={project.editor} preferences={preferences} initialTab={settingsTab} onPreview={setStyleScene} onSave={applySettings} onClose={closeSettings}/>}
 {help&&<div className="modal-backdrop" onMouseDown={()=>setHelp(false)}><section className="dialog" role="dialog" aria-label="帮助" onMouseDown={e=>e.stopPropagation()}><div className="dialog-heading"><strong>操作</strong><button onClick={()=>setHelp(false)} aria-label="关闭帮助"><X size={16}/></button></div><p>拖动色块移动字音，拖动两侧调整起止。</p><p>空格播放；方向键定位；⌘Z / Ctrl+Z 撤销。</p><p>修改读音后可重新自动对齐。</p><button onClick={()=>{setHelp(false);void task('align')}}><RefreshCw size={14}/>自动对齐</button><button onClick={()=>void apiFetch('/api/editor/open-folder')}><FolderOpen size={14}/>项目文件夹</button></section></div>}
 {taskOpen&&<div className="modal-backdrop" onMouseDown={()=>setTaskOpen(false)}><section className="dialog" role="dialog" aria-label="任务" onMouseDown={e=>e.stopPropagation()}><div className="dialog-heading"><strong>任务</strong><button onClick={()=>setTaskOpen(false)} aria-label="关闭任务"><X size={16}/></button></div><p>{taskMessage||'暂无任务'}</p>{taskBusy&&<><RefreshCw size={18} className="spin"/>{currentJob&&/^\/p\//.test(window.location.pathname)&&<button onClick={()=>void stopTask()}>停止任务</button>}</>}
 {currentJob?.mode==='render'&&!taskBusy&&['failed','interrupted','cancelled'].includes(currentJob.status)&&
   <button onClick={()=>void task('render',false,currentJob.upload??false,currentJob.video_bitrate_mbps??null)}>从断点继续导出</button>}
 {currentJob?.details?.overwide?.map(line=><p key={line.index}>第 {line.index+1} 句 · {Math.round(line.width_px)} px · {line.text}</p>)}
 {Object.entries(files).map(([name,path])=><p key={name} className="output-path" title={path}>
   <a href={apiUrl(`/api/jobs/${currentJob?.id}/files/${name}`)} download>{name.endsWith('_upload')?`${outputLabels[name.slice(0,-7)]??name.slice(0,-7)} · 上传版`:outputLabels[name]??name}</a> · {path.split(/[\\/]/).at(-1)}
 </p>)}{Object.keys(files).length>0&&<button onClick={()=>void apiFetch('/api/editor/open-folder')}><FolderOpen size={14}/>打开文件夹</button>}</section></div>}
 </div>
}
export default App;
