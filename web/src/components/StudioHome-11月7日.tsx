import { BitrateInput, validVideoBitrate } from "./BitrateInput-11月11日";
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, FileAudio, FileText, FolderOpen, Plus, RefreshCw, Settings2, Video, X } from 'lucide-react';
import App from '../App';
import { ApplicationSettings } from './ApplicationSettings-11月7日';
import { apiFetch } from '../lib/api';
import { hasDesktopPicker, pickLocalFile } from '../lib/desktop-11月7日';

interface ProjectRecord {key:string;title:string;path:string;updated_at:string;line_count:number;url:string;unavailable?:boolean}
interface ProductionJob {id:string;title:string;project_url:string;project_path:string;mode:string;status:string;stage:string;progress:number;message:string;editable?:boolean;fresh:boolean;files:Record<string,string>;details?:{overwide?:Array<{index:number;text:string;width_px:number}>}}
interface WorkspaceInfo {mode:string;path:string;projects:ProjectRecord[];jobs:ProductionJob[];groups?:Record<string,{label:string}>;default_theme?:string;model?:{url:string;license:string}}
const fallbackGroups=[['nogizaka46','乃木坂46'],['hinatazaka46','日向坂46'],['keyakizaka46','欅坂46'],['sakurazaka46','櫻坂46'],['not_equal_me','≠ME']];
const active=(job:ProductionJob)=>['queued','running'].includes(job.status);

export function StudioRoot(){
  const [mode,setMode]=useState<'loading'|'editor'|'home'>('loading');
  const [initial,setInitial]=useState<WorkspaceInfo>();
  useEffect(()=>{let live=true;void apiFetch<WorkspaceInfo>('/api/workspace').then(info=>{
    if(!live)return;if(info.mode==='workspace'){setInitial(info);setMode('home')}else setMode('editor');
  }).catch(()=>{if(live)setMode('editor')});return()=>{live=false}},[]);
  if(mode==='loading')return <div className="boot-screen"><RefreshCw size={18} className="spin"/>正在打开工作室</div>;
  return mode==='home'&&initial?<StudioHome initial={initial}/>:<App/>;
}

function FileField({label,kind,value,onChange,optional=false,onBusy}:{label:string;kind:'video'|'audio'|'lyrics';value:string;onChange:(path:string)=>void;optional?:boolean;onBusy?:(busy:boolean)=>void}){
  const input=useRef<HTMLInputElement>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function choose(){
    if(hasDesktopPicker()){const path=await pickLocalFile(kind);if(path)onChange(path)}else input.current?.click();
  }
  async function upload(file?:File){
    if(!file)return;setBusy(true);onBusy?.(true);onChange('');setError('');
    try{const form=new FormData();form.append('file',file);form.append('kind',kind);const result=await apiFetch<{path:string}>('/api/workspace/assets',{method:'POST',body:form});onChange(result.path)}catch(e){setError(String(e))}finally{setBusy(false);onBusy?.(false)}
  }
  const Icon=kind==='video'?Video:kind==='lyrics'?FileText:FileAudio;
  return <div className="production-file"><div className="production-field-label">{label}{optional&&<small>可选</small>}</div><button type="button" aria-label={`选择${label}`} className={`file-choice ${value?'chosen':''}`} onClick={()=>void choose()} disabled={busy}><Icon size={21}/><span>{busy?'正在导入素材':value.split(/[\\/]/).at(-1)||'选择文件'}</span>{value?<Check size={15}/>:<Plus size={16}/>}</button><input ref={input} hidden type="file" accept={kind==='lyrics'?'.txt,.lrc,.ass,.json':kind==='video'?'video/*':'audio/*,video/*'} onChange={e=>void upload(e.target.files?.[0])}/><details className="path-entry"><summary>本机路径</summary><input aria-label={`${label}路径`} value={value} placeholder="粘贴文件路径" onChange={e=>onChange(e.target.value)}/></details>{error&&<p className="home-error" role="alert">{error}</p>}</div>;
}

function StudioHome({initial}:{initial:WorkspaceInfo}){
  const [info,setInfo]=useState(initial),[create,setCreate]=useState(new URLSearchParams(window.location.search).has('new')),[open,setOpen]=useState(false),[folder,setFolder]=useState(''),[error,setError]=useState('');
  const [settingsOpen,setSettingsOpen]=useState(false);
  const [bitrate,setBitrate]=useState('');
  const groups=info.groups?Object.entries(info.groups).map(([key,value])=>[key,value.label]):fallbackGroups;
  const defaultTheme=info.default_theme??groups[0][0];
  const defaultArtist=groups.find(([key])=>key===defaultTheme)?.[1]??'';
  const [video,setVideo]=useState(''),[audio,setAudio]=useState(''),[lyrics,setLyrics]=useState(''),[offVocal,setOffVocal]=useState(''),[translation,setTranslation]=useState('');
  const [title,setTitle]=useState(''),[artist,setArtist]=useState(defaultArtist),[theme,setTheme]=useState(defaultTheme),[start,setStart]=useState('00:00'),[end,setEnd]=useState('');
  const [japanese,setJapanese]=useState(true),[chinese,setChinese]=useState(false),[offVersion,setOffVersion]=useState(false),[bilingual,setBilingual]=useState(false);
  const [countdown,setCountdown]=useState(true),[katakana,setKatakana]=useState(true),[mask,setMask]=useState(0),[download,setDownload]=useState(false),[license,setLicense]=useState(false),[busy,setBusy]=useState(false),[uploadCount,setUploadCount]=useState(0);
  const fileBusy=(busy:boolean)=>setUploadCount(count=>Math.max(0,count+(busy?1:-1)));
  function newProduction(){setBitrate('');setVideo('');setAudio('');setLyrics('');setOffVocal('');setTranslation('');setTitle('');setArtist(defaultArtist);setTheme(defaultTheme);setStart('00:00');setEnd('');setJapanese(true);setChinese(false);setOffVersion(false);setMask(0);setCountdown(true);setKatakana(true);setError('');setCreate(true)}
  useEffect(()=>{if(!bilingual&&!translation)setChinese(false)},[bilingual,translation]);
  useEffect(()=>{if(!offVocal)setOffVersion(false)},[offVocal]);
  const refresh=useCallback(async()=>{try{setInfo(await apiFetch('/api/workspace'));setError('')}catch(e){setError(String(e))}},[]);
  useEffect(()=>{if(!info.jobs.some(active))return;const timer=setInterval(()=>void refresh(),1200);return()=>clearInterval(timer)},[info.jobs.some(active),refresh]);
  useEffect(()=>{if(!lyrics){setBilingual(false);return}let live=true;const timer=setTimeout(()=>{void apiFetch<{bilingual:boolean}>('/api/workspace/lyrics-info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:lyrics})}).then(value=>{if(live){setBilingual(value.bilingual);if(value.bilingual)setChinese(true)}}).catch(()=>{if(live)setBilingual(false)})},250);return()=>{live=false;clearTimeout(timer)}},[lyrics]);
  async function openProject(path=folder){
    if(!path.trim())return;setBusy(true);setError('');try{const record=await apiFetch<ProjectRecord>('/api/workspace/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});window.location.assign(record.url)}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  async function chooseProject(){if(hasDesktopPicker()){const path=await pickLocalFile('project');if(path)await openProject(path)}else setOpen(true)}
  async function startJob(mode:'prepare'|'produce'){
    setBusy(true);setError('');try{
      const outputs=[...(japanese?['on_vocal_karaoke']:[]),...(chinese?['on_vocal_karaoke_zh']:[]),...(offVersion?['off_vocal_karaoke']:[])];
      const job=await apiFetch<ProductionJob>('/api/workspace/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,artist,theme,video,audio:audio||null,lyrics,off_vocal:offVocal||null,translation:translation||null,trim_start:start||'0',trim_end:end||null,outputs,mode,fresh:true,countdown,katakana_ruby:katakana,blackout_bottom:mask/100,video_bitrate_mbps:bitrate===""?null:Number(bitrate),allow_download:download,license_accepted:license})});
      setInfo(current=>({...current,jobs:[job,...current.jobs]}));setCreate(false);void refresh();
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }
  async function action(job:ProductionJob,name:'cancel'|'retry',fresh=true){try{await apiFetch(`/api/workspace/jobs/${job.id}/${name}`,{method:'POST',headers:{'Content-Type':'application/json'},...(name==='retry'?{body:JSON.stringify({fresh})}:{})});await refresh()}catch(e){setError(String(e))}}
  const ready=Boolean(title.trim()&&video&&lyrics&&(japanese||chinese||offVersion)&&(!download||license)&&uploadCount===0&&validVideoBitrate(bitrate));
  return <div className="home-shell"><header className="home-header"><div className="brand-mark">♪</div><strong>Karaoke Studio</strong><span className="spacer"/><button aria-label="应用设置" onClick={()=>setSettingsOpen(true)}><Settings2 size={16}/></button><button onClick={()=>void chooseProject()}><FolderOpen size={15}/>打开项目</button><button className="primary" onClick={newProduction}><Plus size={15}/>新建制作</button></header>
    {settingsOpen&&<ApplicationSettings onClose={()=>{setSettingsOpen(false);void refresh()}}/>}
    <main className="home-main">
      {error&&<div className="error-banner" role="alert"><span>{error}</span><button aria-label="关闭错误" onClick={()=>setError('')}><X size={15}/></button></div>}
      {create?<section className="production-form"><div className="home-section-heading"><button onClick={()=>setCreate(false)} aria-label="返回项目库"><ArrowLeft size={17}/></button><div><h1>新建制作</h1><p>选择素材，准备你的卡拉 OK</p></div></div>
        <div className="production-columns"><section><h2>素材</h2><FileField onBusy={fileBusy} label="视频" kind="video" value={video} onChange={setVideo}/><FileField onBusy={fileBusy} label="歌词" kind="lyrics" value={lyrics} onChange={path=>{setLyrics(path);if(!title)setTitle(path.split(/[\\/]/).at(-1)?.replace(/\.[^.]+$/,'').replace(/_lyrics$/,'')||'')}}/><FileField onBusy={fileBusy} label="独立音轨" kind="audio" value={audio} onChange={setAudio} optional/>{bilingual&&<div className="bilingual-badge"><Check size={13}/>已识别中日对照歌词</div>}</section>
        <section><h2>歌曲</h2><label className="production-label">歌曲名<input aria-label="歌曲名" value={title} onChange={e=>setTitle(e.target.value)}/></label><label className="production-label">演唱者<input aria-label="演唱者" value={artist} onChange={e=>setArtist(e.target.value)}/></label><label className="production-label">团体配色<select aria-label="团体配色" value={theme} onChange={e=>{const before=groups.find(([key])=>key===theme)?.[1];const next=groups.find(([key])=>key===e.target.value)?.[1]||'';setTheme(e.target.value);if(!artist||artist===before)setArtist(next)}}>{groups.map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label><div className="production-range"><label className="production-label">开始<input aria-label="截取开始" value={start} placeholder="00:00" onChange={e=>setStart(e.target.value)}/></label><span>—</span><label className="production-label">结束<input aria-label="截取结束" value={end} placeholder="视频结尾" onChange={e=>setEnd(e.target.value)}/></label></div>
        <h2>成片版本</h2><BitrateInput value={bitrate} onChange={setBitrate} disabled={busy}/><label className="version-choice"><input type="checkbox" checked={japanese} onChange={e=>setJapanese(e.target.checked)}/>日文卡拉 OK</label><label className="version-choice"><input type="checkbox" checked={chinese} onChange={e=>setChinese(e.target.checked)} disabled={!bilingual&&!translation}/>中日双语</label>{offVocal&&<label className="version-choice"><input type="checkbox" checked={offVersion} onChange={e=>setOffVersion(e.target.checked)}/>伴奏卡拉 OK</label>}
        </section></div>
        <details className="production-advanced"><summary>制作选项</summary><div className="production-columns"><div><FileField onBusy={fileBusy} label="伴奏音轨" kind="audio" value={offVocal} onChange={setOffVocal} optional/><FileField onBusy={fileBusy} label="独立翻译" kind="lyrics" value={translation} onChange={setTranslation} optional/></div><div><label className="preference-row">段落倒数<input type="checkbox" checked={countdown} onChange={e=>setCountdown(e.target.checked)}/></label><label className="preference-row">片假名注音<input type="checkbox" checked={katakana} onChange={e=>setKatakana(e.target.checked)}/></label><label className="settings-slider">底部遮黑<span className="setting-value">{mask}%</span><input type="range" min="0" max="40" value={mask} onChange={e=>setMask(Number(e.target.value))}/></label><label className="version-choice"><input type="checkbox" checked={download} onChange={e=>setDownload(e.target.checked)}/>首次使用时下载对齐模型</label>{download&&<label className="model-license"><input type="checkbox" checked={license} onChange={e=>setLicense(e.target.checked)}/><span>同意模型的 <a href={info.model?.url??"https://huggingface.co/NextFire/mms-300m-ForcedAligner-karaoke-ja-Latn"} target="_blank" rel="noreferrer">{info.model?.license??"CC-BY-NC-SA-4.0"} 许可</a></span></label>}</div></div></details>
        <div className="production-actions"><span>右上角：{title||'歌曲名'}{artist?`/${artist}`:''}</span><span className="spacer"/><button disabled={!ready||busy} onClick={()=>void startJob('produce')}>{busy?'正在创建':'直接生成成片'}</button><button className="primary" disabled={!ready||busy} onClick={()=>void startJob('prepare')}>对齐并进入编辑<ArrowRight size={15}/></button></div>
      </section>:<>
        <div className="home-intro"><h1>你的卡拉 OK 工作室</h1><p>从歌曲素材开始，也可以继续编辑已有项目。</p></div>
        {info.jobs.length>0&&<section className="home-jobs"><div className="home-section-heading"><h2>制作任务</h2><span className="spacer"/><button className="quiet" onClick={()=>void refresh()} aria-label="刷新任务"><RefreshCw size={14}/></button></div>{info.jobs.map(job=><article className={`production-job ${job.status}`} key={job.id}><div className="job-heading"><strong>{job.title}</strong><span>{active(job)?job.stage:job.status==='completed'?'完成':job.status==='cancelled'?'已停止':job.status==='interrupted'?'已中断':'制作遇到问题'}</span></div><p>{job.message}</p>{active(job)&&<progress max="1" value={job.progress}/>}<div className="job-actions">{job.editable&&!active(job)&&<button className="primary" onClick={()=>window.location.assign(job.project_url)}>进入编辑<ArrowRight size={14}/></button>}{active(job)?<button onClick={()=>void action(job,'cancel')}>停止任务</button>:<><button onClick={()=>void action(job,'retry',true)}>{job.mode==='render'?'重新导出':'从头重做'}</button>{job.status!=='completed'&&<button onClick={()=>void action(job,'retry',false)}>从断点继续</button>}</>}{Object.entries(job.files).map(([name,path])=><span className="job-output" key={name} title={path}>{path.split(/[\\/]/).at(-1)}</span>)}</div>{job.details?.overwide?.map(line=><div className="job-width-error" key={line.index}>第 {line.index+1} 句 · {Math.round(line.width_px)} px · {line.text}</div>)}</article>)}</section>}
        <section><div className="home-section-heading"><h2>项目</h2><span>{info.projects.length}</span></div>{!info.projects.length?<div className="home-empty"><FileText size={30}/><h3>第一首歌，从这里开始</h3><button className="primary" onClick={newProduction}><Plus size={15}/>新建制作</button></div>:<div className="project-grid">{info.projects.map(project=><button className="project-card" key={project.key} disabled={project.unavailable||info.jobs.some(job=>job.project_url===project.url&&active(job))} onClick={()=>window.location.assign(project.url)}><div className="project-icon">♪</div><strong>{project.title}</strong><span>{project.line_count} 句 · {new Date(project.updated_at).toLocaleDateString()}</span><small title={project.path}>{project.path}</small></button>)}</div>}</section>
      </>}
    </main><footer className="home-footer">Karaoke Studio<span>{info.path}</span></footer>
    {open&&<div className="modal-backdrop"><section className="dialog" role="dialog" aria-label="打开项目"><div className="dialog-heading"><strong>打开项目</strong><button aria-label="关闭打开项目" onClick={()=>setOpen(false)}><X size={16}/></button></div><label className="production-label">项目文件夹<input aria-label="项目文件夹" value={folder} onChange={e=>setFolder(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void openProject()}} placeholder="粘贴项目文件夹路径"/></label><button className="primary" disabled={!folder.trim()||busy} onClick={()=>void openProject()}>打开</button></section></div>}
  </div>;
}
