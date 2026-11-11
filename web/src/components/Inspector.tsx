import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import type { EditorScene, LyricLine, RubyGroup } from '../types';
interface Props {
  line?:LyricLine; range:[number,number]|null; bounds:number[]; scene?:EditorScene;
  saving:boolean; onReading:(group:RubyGroup,reading:string,romaji:string)=>void;
}
export function Inspector({line,range,bounds,saving,onReading}:Props){
  const chosen=line?.moras[range?.[0]??0];
  const group=line?.ruby_groups.find(g=>g.id===chosen?.group_id)??line?.ruby_groups[0];
  const [reading,setReading]=useState('');
  useEffect(()=>{setReading(group?.reading??'')},[group?.id,line?.id,group?.reading]);
  const romaji=line?.moras.filter(m=>m.group_id===group?.id).map(m=>m.romaji).join(' ')??'';
  return <aside className="inspector">
    <div className="section-heading">当前字音</div>
    <div className="selected-word"><span>{group?.display||'—'}</span><small>{group?.reading}</small></div>
    <div className="reading-chips">{line?.moras.filter(m=>m.group_id===group?.id).map(m=><span key={m.id}>{m.kana}</span>)}</div>
    <label>假名读音<input value={reading} disabled={saving} onChange={e=>setReading(e.target.value)} aria-label="假名读音"/></label>
    <details><summary>罗马音</summary><input value={romaji} readOnly aria-label="罗马音"/></details>
    <button className="primary full" disabled={!group||saving||reading===group.reading} onClick={()=>group&&onReading(group,reading,romaji)}><Save size={14}/>保存读音</button>
    <div className="inspector-divider"/><div className="section-heading">选中范围</div>
    <div className="range-duration">{range&&bounds[range[1]]!=null?`${((bounds[range[1]]-bounds[range[0]])/1000).toFixed(2)}s`:'—'}</div>
  </aside>;
}
