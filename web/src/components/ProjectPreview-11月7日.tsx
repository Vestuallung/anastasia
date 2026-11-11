import { useEffect, useRef, useState } from 'react';
import { apiUrl } from '../lib/api';
import type { EditorScene, SceneGlyph } from '../types';

interface Props {
  scene?: EditorScene; mediaRef: React.RefObject<HTMLAudioElement | null>;
  selectedId: string; boundaries: number[]; currentMs: number; hasVideo: boolean;
}
const clamp=(v:number)=>Math.max(0,Math.min(1,v));
const font='"Studio Japanese", "Noto Sans JP", sans-serif';
const chineseFont='"Studio Chinese", "Noto Sans JP", sans-serif';
const defaultType:NonNullable<EditorScene["typography"]>={width:1920,height:1080,main:96,reading:48,title:48,chinese:48,title_y:96,outline:3,title_outline:3.2,bold:true};
let fontsReady:Promise<unknown>|undefined;
function loadStudioFonts(){
  return fontsReady??=Promise.allSettled([
    new FontFace('Studio Japanese','url(/font/japanese)').load().then(face=>document.fonts.add(face)),
    new FontFace('Studio Chinese','url(/font/chinese)').load().then(face=>document.fonts.add(face)),
  ]);
}
export function ProjectPreview({scene,mediaRef,selectedId,boundaries,currentMs,hasVideo}:Props){
  const video=useRef<HTMLVideoElement>(null), canvas=useRef<HTMLCanvasElement>(null);
  const container=useRef<HTMLElement>(null);
  const [fontVersion,setFontVersion]=useState(0);
  useEffect(()=>{let active=true;if(typeof FontFace!=='undefined')void loadStudioFonts().then(()=>{if(active)setFontVersion(1)});return()=>{active=false}},[]);
  const [box,setBox]=useState({width:0,height:0});
  useEffect(()=>{if(!container.current)return;const element=container.current;const ratio=(scene?.canvas.width||1920)/(scene?.canvas.height||1080);const update=()=>{const r=element.getBoundingClientRect();const h=r.height||r.width/ratio;const width=Math.min(r.width,h*ratio);setBox(old=>Math.abs(old.width-width)<.5?old:{width,height:width/ratio})};const observer=new ResizeObserver(update);observer.observe(element);update();return()=>observer.disconnect()},[scene?.canvas.width,scene?.canvas.height]);
  useEffect(()=>{
    let frame=0;
    function sync(){
      const a=mediaRef.current,v=video.current;
      if(a&&v&&hasVideo&&scene){
        const target=a.currentTime-(scene.audio_offset_ms||0)/1000+scene.video_offset_ms/1000;
        v.playbackRate=a.playbackRate;
        if(Math.abs(v.currentTime-target)>.1)v.currentTime=Math.max(0,target);
        if(a.paused){if(!v.paused)v.pause()}else if(v.paused)void v.play().catch(()=>{});
      }
      frame=requestAnimationFrame(sync);
    }
    sync();return()=>cancelAnimationFrame(frame);
  },[hasVideo,scene?.video_offset_ms,scene?.audio_offset_ms,mediaRef]);
  useEffect(()=>{
    const el=canvas.current;if(!el||!scene)return;
    function draw(){
      const el=canvas.current;if(!el||!scene)return;const rect=el.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
      el.width=Math.round(rect.width*dpr);el.height=Math.round(rect.height*dpr);
      const context=el.getContext('2d');if(!context)return;const c:CanvasRenderingContext2D=context;
      const type=scene.typography??defaultType;
      const time=currentMs;
      c.scale(dpr,dpr);
      for(const region of scene.blackout??[]){
        if(time>=region.start*1000&&(region.end==null||time<=region.end*1000)){
          c.fillStyle='black';
          c.fillRect(rect.width*region.x/1920,rect.height*region.y/1080,
                     rect.width*region.width/1920,rect.height*region.height/1080);
        }
      }
      const scale=Math.min(rect.width/type.width,rect.height/type.height);
      c.translate((rect.width-type.width*scale)/2,(rect.height-type.height*scale)/2);
      c.scale(scale,scale);
      c.lineJoin='round';c.textAlign='center';c.textBaseline='middle';
      function paint(text:string,left:number,right:number,y:number,size:number,start:number,end:number,progress?:number){
        c.font=`${type.bold?700:400} ${size}px ${font}`;const x=(left+right)/2;c.lineWidth=2*type.outline;c.strokeStyle=scene!.colors.unsung_outline;c.fillStyle=scene!.colors.unsung_fill;c.strokeText(text,x,y);c.fillText(text,x,y);
        const fraction=progress??clamp((time-start)/Math.max(1,end-start));if(fraction>0){c.save();c.beginPath();c.rect(left-6,y-size,right-left+12>0?(right-left+12)*fraction:0,size*2);c.clip();c.strokeStyle=scene!.colors.sung_outline;c.fillStyle=scene!.colors.sung;c.strokeText(text,x,y);c.fillText(text,x,y);c.restore()}
      }
      for(const line of scene.lines){
        if(time<line.display_start_ms||time>=line.display_end_ms)continue;
        const remaining = line.countdown ? line.start_ms - time : 0;
        const countingDown = remaining > 0 && remaining <= 3000;
        for(const g of line.glyphs){
          const indices=g.mora_indices;const draft=line.id===selectedId&&indices.length&&boundaries.length;
          const start=draft?boundaries[indices[0]]+scene.subtitle_offset_ms:g.start_ms;
          const end=draft?boundaries[indices[indices.length-1]+1]+scene.subtitle_offset_ms:g.end_ms;
          let progress=clamp((time-start)/Math.max(1,end-start));
          if(g.kana.filter(k=>k.text).length>1&&indices.length>1){
            progress=indices.reduce((sum,i,j)=>{const a=draft?boundaries[i]+scene.subtitle_offset_ms:g.kana[j]?.start_ms??start;const b=draft?boundaries[i+1]+scene.subtitle_offset_ms:g.kana[j]?.end_ms??end;return sum+clamp((time-a)/Math.max(1,b-a))},0)/indices.length;
          }
          paint(g.text,g.left,g.right,g.y,type.main,start,end,countingDown ? 0 : progress);
          for(const k of g.kana){const i=k.mora_index??k.mora_indices?.[0];const last=k.mora_indices?.at(-1)??i;const a=draft&&i!=null?boundaries[i]+scene.subtitle_offset_ms:k.start_ms;const b=draft&&last!=null?boundaries[last+1]+scene.subtitle_offset_ms:k.end_ms;paint(k.text,k.left,k.right,k.y,type.reading,a,b,countingDown ? 0 : undefined)}
        }
        const cue = line.countdown_position;
        if (countingDown && cue) {
          const count = Math.ceil(remaining / 1000);
          c.fillStyle = scene.colors.sung;
          c.strokeStyle = scene.colors.sung_outline;
          c.lineWidth = 4;
          for (let i = 0; i < count; i++) {
            c.beginPath();
            c.arc(cue.left + cue.radius + i * cue.spacing, cue.y, cue.radius, 0, Math.PI * 2);
            c.fill();
            c.stroke();
          }
        }
      }
      c.textBaseline='top';
      const first=scene.lines[0],last=scene.lines.at(-1);
      if(scene.title_text&&first&&last&&time>=first.display_start_ms&&time<last.display_end_ms){c.font=`${type.title}px ${font}`;c.textAlign='right';c.fillStyle=scene.colors.title_fill;c.strokeStyle=scene.colors.title_outline||'white';c.lineWidth=2*type.title_outline;c.strokeText(scene.title_text,type.width-(scene.layout.margin_x??110),type.title_y);c.fillText(scene.title_text,type.width-(scene.layout.margin_x??110),type.title_y)}
      for(const event of scene.translation_events||[]){
        if(time<event.start_ms||time>=event.end_ms)continue;
        c.font=`${type.chinese}px ${chineseFont}`;c.strokeStyle=scene.colors.title_outline??"white";c.lineWidth=2*(type.chinese_outline??type.title_outline);c.fillStyle=scene.colors.title_fill;
        const column=(event.alignment-1)%3,row=Math.floor((event.alignment-1)/3);
        c.textAlign=column===0?'left':column===1?'center':'right';
        const lines=event.text.split('\n'),lineHeight=type.chinese*1.2,height=lines.length*lineHeight;
        const y=event.y-(row===0?height:row===1?height/2:0);
        lines.forEach((text,i)=>{c.strokeText(text,event.x,y+i*lineHeight);c.fillText(text,event.x,y+i*lineHeight)});
      }
    }
    draw();const resize=new ResizeObserver(draw);resize.observe(el);return()=>resize.disconnect();
  },[scene,boundaries,selectedId,currentMs,fontVersion]);
  return <section ref={container} className="preview-panel" aria-label="实时字幕预览"><div className="preview-stage" style={{aspectRatio:`${scene?.canvas.width||1920}/${scene?.canvas.height||1080}`,width:box.width||undefined,height:box.height||undefined}}>
    {hasVideo?<video ref={video} src={apiUrl('/api/video')} muted playsInline preload="auto" aria-label="项目视频"/>:<div className="audio-only">音频项目</div>}
    <audio ref={mediaRef} src={apiUrl('/api/audio')} preload="auto"/>
    <canvas ref={canvas} className="subtitle-canvas" aria-label="结构化字幕画布"/>
  </div></section>
}
