import { useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { defaultPreferences } from '../lib/preferences-11月7日';
import type { EditorPreferences } from '../lib/preferences-11月7日';
import type { LyricLine, SceneGlyph } from '../types';
interface Props {
  preferences?:EditorPreferences; preferenceVersion?:number;
  line?: LyricLine; boundaries:number[]; peaks:number[]; durationMs:number; currentMs:number;
  waveformStart?:number; waveformEnd?:number; glyphs?:SceneGlyph[]; selectedRange?:[number,number]; onSelect?:(range:[number,number])=>void;
  onSeek:(ms:number)=>void; onPreview:(value:number[]|null)=>void;
  onCommit:(before:number[],after:number[],kind:'line_shift'|'boundary'|'line_start'|'line_end',index?:number)=>void;
  onRestore:()=>void; disabled?:boolean;
}
type Drag={kind:'move'|'boundary';range:[number,number];index:number;x:number;before:number[];width:number};
const fmt=(ms:number)=>`${Math.floor(ms/60000).toString().padStart(2,'0')}:${((ms%60000)/1000).toFixed(2).padStart(5,'0')}`;
export function Timeline({preferences=defaultPreferences,preferenceVersion=0,line,boundaries,peaks,durationMs,currentMs,glyphs=[],waveformStart=0,waveformEnd=durationMs,selectedRange,onSelect,onSeek,onPreview,onCommit,onRestore,disabled=false}:Props){
 const root=useRef<HTMLDivElement>(null),scroll=useRef<HTMLDivElement>(null),drag=useRef<Drag|null>(null),draftRef=useRef(boundaries);
 const [draft,setDraft]=useState(boundaries),[zoom,setZoom]=useState(1),[width,setWidth]=useState(900),[mode,setMode]=useState<'sound'|'char'>('sound'),[snap,setSnap]=useState(preferences.snap);
 useEffect(()=>{drag.current=null;draftRef.current=boundaries;setDraft(boundaries);onPreview(null)},[line?.id]);
 useEffect(()=>{if(!scroll.current)return;const o=new ResizeObserver(e=>setWidth(e[0].contentRect.width));o.observe(scroll.current);return()=>o.disconnect()},[]);
 useEffect(()=>setSnap(preferences.snap),[preferences.snap,preferenceVersion]);
 useEffect(()=>{if(!preferences.show_readings&&preferences.show_characters)setMode('char');else if(!preferences.show_characters&&preferences.show_readings)setMode('sound')},[preferences.show_readings,preferences.show_characters]);
 const source=drag.current?draft:boundaries;
 const from=Math.max(0,(boundaries[0]??0)-450),to=Math.min(durationMs||1,(boundaries.at(-1)??1000)+450),span=Math.max(200,to-from);
 const trackWidth=Math.max(width,Math.min(2200,(line?.moras.length??0)*38))*zoom;
 const percent=(v:number)=>(v-from)/span*100;
 const waveform=useMemo(()=>{if(!peaks.length||!durationMs)return [];const waveDuration=Math.max(1,waveformEnd-waveformStart);const a=Math.max(0,Math.floor((from-waveformStart)/waveDuration*peaks.length)),b=Math.ceil((to-waveformStart)/waveDuration*peaks.length);return peaks.slice(a,b)},[peaks,durationMs,from,to,waveformStart,waveformEnd]);
 function begin(e:React.PointerEvent,kind:Drag['kind'],range:[number,number],index=range[0]){if(disabled||source.length<2)return;e.stopPropagation();e.preventDefault();onSelect?.(range);const before=[...source];drag.current={kind,range,index,x:e.clientX,before,width:root.current!.getBoundingClientRect().width};draftRef.current=before;setDraft(before);root.current!.setPointerCapture(e.pointerId)}
 function move(e:React.PointerEvent){const d=drag.current;if(!d)return;let next=[...d.before];let delta=(e.clientX-d.x)/d.width*span;
 if(d.kind==='boundary'){let v=d.before[d.index]+delta;if(snap&&!e.altKey)v=Math.round(v/preferences.snap_ms)*preferences.snap_ms;const low=d.index?next[d.index-1]:0,high=d.index<next.length-1?next[d.index+1]:durationMs;next[d.index]=Math.round(Math.max(low,Math.min(high,v)))}
 else{const [a,b]=d.range;delta=Math.round(delta);delta=Math.max((a?next[a-1]:0)-next[a],Math.min((b<next.length-1?next[b+1]:durationMs)-next[b],delta));for(let i=a;i<=b;i++)next[i]+=delta}
 draftRef.current=next;setDraft(next);onPreview(next)}
 function finish(cancel=false){const d=drag.current;if(!d)return;drag.current=null;onPreview(null);if(cancel){setDraft(d.before);return}const next=draftRef.current;if(next.some((v,i)=>v!==d.before[i]))onCommit(d.before,next,d.kind==='move'?'line_shift':d.index===0?'line_start':d.index===next.length-1?'line_end':'boundary',d.kind==='boundary'?d.index:undefined)}
 function segment(label:string,a:number,b:number,kind:string,key:string){if(a<0||b>=source.length)return null;const selected=selectedRange?.[0]===a&&selectedRange?.[1]===b;return <div key={key} className={`time-block ${kind} ${selected?'selected':''} ${currentMs>=source[a]&&currentMs<source[b]?'active':''}`} style={{left:`${percent(source[a])}%`,width:`${Math.max(.15,percent(source[b])-percent(source[a]))}%`}} onPointerDown={e=>begin(e,'move',[a,b])} onClick={()=>onSelect?.([a,b])}><span>{label}</span>{[a,b].map((index,i)=><button key={i} className={`time-handle ${i?'right':'left'}`} aria-label={`边界 ${index+1}，${source[index]} 毫秒，${label}`} onPointerDown={e=>begin(e,'boundary',[a,b],index)} onKeyDown={e=>{if(!disabled&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();e.stopPropagation();const next=[...source];next[index]=Math.max(index?next[index-1]:0,Math.min(index<next.length-1?next[index+1]:durationMs,next[index]+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?preferences.seek_large_ms:preferences.key_step_ms)));onCommit(source,next,'boundary',index)}}}/>)}</div>}
 return <section className="timeline-panel" aria-label="单句时间轴编辑器"><div className="timeline-toolbar"><strong>精细打轴</strong><span className="muted small">{line?`第 ${line.source_index+1} 句`:''}</span><div className="spacer"/><label className="compact-check"><input type="checkbox" checked={snap} onChange={e=>setSnap(e.target.checked)}/>吸附</label><button aria-label="缩小时间轴" onClick={()=>setZoom(z=>Math.max(1,z/1.4))}><Minus size={15}/></button><button aria-label="放大时间轴" onClick={()=>setZoom(z=>Math.min(6,z*1.4))}><Plus size={15}/></button><button aria-pressed={mode==='char'} disabled={!preferences.show_characters} onClick={()=>setMode('char')}>正文单字</button><button aria-pressed={mode==='sound'} disabled={!preferences.show_readings} onClick={()=>setMode('sound')}>读音</button><button aria-label="恢复原始时间" onClick={onRestore} disabled={disabled}><RotateCcw size={15}/></button></div><div className="timeline-content"><div className="lane-labels" style={{gridTemplateRows:`28px ${preferences.show_waveform?'80px ':''}44px ${preferences.show_characters?'44px ':''}${preferences.show_readings?'44px':''}`}}><span/>{preferences.show_waveform&&<span>波形</span>}<span>句子</span>{preferences.show_characters&&<span>正文</span>}{preferences.show_readings&&<span>读音</span>}</div><div className="timeline-scroll" ref={scroll}><div className="timeline-track" ref={root} style={{width:trackWidth}} onPointerMove={move} onPointerUp={()=>finish()} onPointerCancel={()=>finish(true)}>
 <div className="ruler">{[0,.25,.5,.75,1].map(r=><span key={r} style={{left:`${r*100}%`}}>{fmt(from+span*r)}</span>)}</div>
 {preferences.show_waveform&&<svg className="waveform" viewBox={`0 0 ${Math.max(1,waveform.length)} 80`} preserveAspectRatio="none" role="img" aria-label="音频波形" onPointerDown={e=>{const r=e.currentTarget.getBoundingClientRect();onSeek(Math.round(from+(e.clientX-r.left)/r.width*span))}}>{waveform.map((v,i)=><line key={i} x1={i} x2={i} y1={40-v*34} y2={40+v*34}/>)}</svg>}
 <div className="time-lane">{source.length>1&&segment(line?.display_tokens.map(t=>t.text).join('')||'',0,source.length-1,'phrase','phrase')}</div>
 {preferences.show_characters&&<div className={`time-lane ${mode==='char'?'focused':''}`}>{glyphs.map((g,i)=>g.mora_indices.length?segment(g.text,g.mora_indices[0],g.mora_indices.at(-1)!+1,'character',String(i)):null)}</div>}
 {preferences.show_readings&&<div className={`time-lane ${mode==='sound'?'focused':''}`}>{source.slice(0,-1).map((_,i)=>segment(line?.moras[i]?.kana||'·',i,i+1,'sound',String(i)))}</div>}
 <div className="playhead" style={{left:`${percent(currentMs)}%`}}/>
 </div></div></div><div className="timeline-footer"><span className="muted">{selectedRange&&source[selectedRange[1]]!=null?`${fmt(source[selectedRange[0]])} — ${fmt(source[selectedRange[1]])} · ${source[selectedRange[1]]-source[selectedRange[0]]} ms`:''}</span></div></section>
}
