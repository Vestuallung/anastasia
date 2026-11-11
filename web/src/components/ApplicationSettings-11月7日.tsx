import { useEffect, useRef, useState } from "react";
import { Check, Download, LoaderCircle, Settings, X } from "lucide-react";
import { apiFetch } from "../lib/api";
import "./ApplicationSettings-11月7日.css";

type Group = {label:string; sung:string; [key:string]:string};
type Edit = {ffmpeg:string;ffprobe:string;alignment_python:string;device:string;model_id:string;model_revision:string;model_cache:string;japanese_font:string;japanese_font_path:string;chinese_font:string;chinese_font_path:string;groups:Record<string,Group>;default_theme:string};
type Task = {id:string;status:string;action:string;message:string};
type Status = {tools:Record<string,{ready:boolean;message:string}>;alignment:{runtime_ready:boolean;model_ready:boolean;message?:string};fonts:Record<string,{ready:boolean;family:string}>;model_url:string;model_license:string};
const running = (task:Task) => ["queued","running"].includes(task.status);
const label: Record<string,string> = {completed:"已完成",failed:"未完成",interrupted:"已中断",cancelled:"已停止",queued:"准备中",running:"进行中"};

export function ApplicationSettings({onClose}:{onClose:()=>void}) {
  const [edit,setEdit]=useState<Edit|null>(null);
  const [tab,setTab]=useState("environment");
  const [status,setStatus]=useState<Status|null>(null);
  const [tasks,setTasks]=useState<Task[]>([]);
  const [accepted,setAccepted]=useState(false);
  const [busy,setBusy]=useState(false);
  const [checking,setChecking]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const panel=useRef<HTMLDivElement>(null);
  const closeRef=useRef(onClose);
  closeRef.current=onClose;
  const active=tasks.some(running);
  const change=<K extends keyof Edit>(key:K,value:Edit[K])=>setEdit(old=>old?{...old,[key]:value}:old);
  async function check() {
    setChecking(true);
    try {setStatus(await apiFetch<Status>("/api/application/status"));}
    catch(e){setError(String(e instanceof Error?e.message:e));}
    finally{setChecking(false);}
  }
  useEffect(()=>{
    let mounted=true;
    void apiFetch<{settings:Edit}>("/api/application/settings").then(v=>{if(mounted)setEdit(v.settings);}).catch(e=>{if(mounted)setError(e.message);});
    void check();
    async function poll(){
      try{const next=await apiFetch<Task[]>("/api/application/tasks");if(mounted)setTasks(next);}
      catch(e){if(mounted)setError(e instanceof Error?e.message:String(e));}
    }
    void poll(); const timer=window.setInterval(()=>void poll(),1500);
    const previous=document.activeElement as HTMLElement|null;
    panel.current?.focus();
    const key=(event:KeyboardEvent)=>{
      if(event.key==="Escape"){event.stopPropagation();closeRef.current();}
      if(event.key!=="Tab")return;
      const items=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href],summary')??[]).filter(el=>el.getClientRects().length>0);
      if(!items.length)return;
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    document.addEventListener("keydown",key,true);
    return()=>{mounted=false;window.clearInterval(timer);document.removeEventListener("keydown",key,true);previous?.focus();};
  },[]);
  const priorStatus=useRef("");
  useEffect(()=>{
    const state=tasks.map(t=>t.id+":"+t.status).join(",");
    if(priorStatus.current&&state!==priorStatus.current&&!tasks.some(running))void check();
    priorStatus.current=state;
  },[tasks]);
  async function save(){
    setBusy(true);setError("");setMessage("");
    try{
      const result=await apiFetch<{settings:Edit}>("/api/application/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(edit)});
      setEdit(result.settings);setMessage("已保存，下次启动时生效");
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function setup(action:string){
    setBusy(true);setError("");
    try{
      const task=await apiFetch<Task>("/api/application/setup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,license_accepted:accepted})});
      setTasks(old=>[task,...old]);
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function cancel(id:string){
    try{const next=await apiFetch<Task>(`/api/application/tasks/${id}/cancel`,{method:"POST"});setTasks(old=>old.map(t=>t.id===id?next:t));}
    catch(e){setError(e instanceof Error?e.message:String(e));}
  }
  const field=(name:keyof Edit,text:string)=><label>{text}<input value={String(edit?.[name]??"")} onChange={event=>change(name,event.target.value as never)}/></label>;
  const badge=(ready?:boolean)=><span className={`setup-badge ${ready?"ready":""}`}>{ready?<><Check size={12}/>就绪</>:"待配置"}</span>;
  return <div className="application-settings-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <div className="application-settings" ref={panel} role="dialog" aria-modal="true" aria-label="应用设置" tabIndex={-1}>
      <header><div><Settings size={20}/><h2>应用设置</h2></div><button aria-label="关闭设置" onClick={onClose}><X size={18}/></button></header>
      <nav aria-label="设置分类">{[["environment","环境与模型"],["appearance","字体"],["groups","团体与颜色"]].map(([id,text])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{text}</button>)}</nav>
      <div className="application-settings-content">
        {error&&<div className="setup-error" role="alert">{error}</div>}
        {message&&<div className="setup-success" role="status">{message}</div>}
        {!edit?<p>正在读取设置…</p>:<>
        {tab==="environment"&&<>
          <section><h3>运行环境<button disabled={checking} onClick={()=>void check()}>{checking?<LoaderCircle size={14} className="spin"/>:"重新检查"}</button></h3>
          <div className="setup-status-row"><span>视频处理</span>{badge(status?.tools.ffmpeg?.ready&&status?.tools.ffprobe?.ready)}</div>
          <div className="setup-status-row"><span>歌词对齐</span>{badge(status?.alignment.runtime_ready)}</div>
          <button className="setup-primary" disabled={busy||active} onClick={()=>void setup("environment")}>配置对齐环境</button>
          </section>
          <section><h3>对齐模型{badge(status?.alignment.model_ready)}</h3><p className="setup-model-name">{edit.model_id}</p>
          <label className="setup-check"><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/><span>我已阅读<a href={status?.model_url??`https://huggingface.co/${edit.model_id}`} target="_blank" rel="noreferrer">模型许可</a>，同意其使用条件</span></label>
          <button disabled={busy||active||!accepted||!status?.alignment.runtime_ready} onClick={()=>void setup("model")}><Download size={15}/> 下载模型</button>
          </section>
          <details><summary>自定义模型与工具</summary><div className="setup-fields">{field("model_id","模型 ID")}{field("model_revision","模型版本")}{field("model_cache","模型存放目录")}{field("alignment_python","对齐环境 Python")}{field("ffmpeg","FFmpeg")}{field("ffprobe","FFprobe")}<label>计算设备<select value={edit.device} onChange={e=>change("device",e.target.value)}><option value="cpu">CPU</option><option value="cuda">NVIDIA CUDA</option><option value="mps">Apple MPS</option></select></label></div></details>
          {tasks.slice(0,3).map(task=><article className="setup-task" key={task.id}><div><strong>{task.action==="model"?"模型下载":"环境配置"}</strong><span>{label[task.status]??task.status}</span></div><p>{task.message}</p>{running(task)&&<button onClick={()=>void cancel(task.id)}>停止</button>}</article>)}
        </>}
        {tab==="appearance"&&<><section><h3>日文字体{badge(status?.fonts.japanese?.ready)}</h3>{field("japanese_font","字体名称")}{field("japanese_font_path","字体文件")}</section><section><h3>中文字幕字体{badge(status?.fonts.chinese?.ready)}</h3>{field("chinese_font","字体名称")}{field("chinese_font_path","字体文件")}</section><p className="setup-hint">内置 Noto CJK 字体，可直接制作中日字幕。</p></>}
        {tab==="groups"&&<section><label>默认团体<select value={edit.default_theme} onChange={e=>change("default_theme",e.target.value)}>{Object.entries(edit.groups).map(([key,group])=><option key={key} value={key}>{group.label}</option>)}</select></label><div className="setup-groups">{Object.entries(edit.groups).map(([key,group])=><div className="setup-group" key={key}><input aria-label={`${key} 团体名`} value={group.label} onChange={e=>change("groups",{...edit.groups,[key]:{...group,label:e.target.value}})}/><input type="color" aria-label={`${key} 颜色`} value={group.sung} onChange={e=>change("groups",{...edit.groups,[key]:{...group,sung:e.target.value}})}/><code>{group.sung.toUpperCase()}</code></div>)}</div><button onClick={()=>{const key="group_"+(Object.keys(edit.groups).length+1);change("groups",{...edit.groups,[key]:{label:"新团体",sung:"#9465D9"}});}}>添加团体</button></section>}
        </>}
      </div>
      <footer><button onClick={onClose}>关闭</button><button className="setup-primary" disabled={!edit||busy||active} onClick={()=>void save()}>保存设置</button></footer>
    </div>
  </div>;
}
