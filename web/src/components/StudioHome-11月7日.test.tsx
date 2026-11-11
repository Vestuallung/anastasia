import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StudioRoot } from './StudioHome-11月7日';

const initial={mode:'workspace',path:'/projects',projects:[],jobs:[]};
describe('新手制作入口',()=>{
  beforeEach(()=>{
    Object.defineProperty(window,'webkit',{configurable:true,value:{messageHandlers:{desktop:{postMessage:(message:{id:string;kind:string})=>{
      window.dispatchEvent(new CustomEvent('studio-file',{detail:{id:message.id,path:message.kind==='video'?'/media/video.mp4':'/media/lyrics.txt'}}));
    }}}}});
    vi.stubGlobal('fetch',vi.fn(async (input:RequestInfo|URL,init?:RequestInit)=>{
      const path=String(input);
      if(path.endsWith('/lyrics-info'))return new Response(JSON.stringify({bilingual:true,line_count:2}),{headers:{'Content-Type':'application/json'}});
      if(path.endsWith('/produce'))return new Response(JSON.stringify({id:'job1',title:'Song',project_url:'/p/1234567890abcdef/',status:'queued',stage:'准备',message:'等待制作',progress:0,files:{}}),{headers:{'Content-Type':'application/json'}});
      return new Response(JSON.stringify(initial),{headers:{'Content-Type':'application/json'}});
    }));
  });
  afterEach(()=>{Object.defineProperty(window,'webkit',{configurable:true,value:undefined})});

  it('opens a project library without requiring an existing project',async()=>{
    render(<StudioRoot/>);
    expect(await screen.findByText('第一首歌，从这里开始')).toBeVisible();
    expect(screen.getByRole('button',{name:'打开项目'})).toBeVisible();
    expect(vi.mocked(fetch).mock.calls.some(([path])=>String(path).includes('/produce'))).toBe(false);
  });

  it('sends bilingual input and default full rerun through the prepare workflow',async()=>{
    render(<StudioRoot/>);await screen.findByText('第一首歌，从这里开始');
    await userEvent.click(screen.getAllByRole('button',{name:'新建制作'})[0]);
    await userEvent.click(screen.getByRole('button',{name:'选择视频'}));
    await userEvent.click(screen.getByRole('button',{name:'选择歌词'}));
    await screen.findByText('已识别中日对照歌词');
    await userEvent.clear(screen.getByLabelText('歌曲名'));await userEvent.type(screen.getByLabelText('歌曲名'),'Song');
    await userEvent.type(screen.getByLabelText('截取结束'),'00:08');
    await userEvent.click(screen.getByRole('button',{name:'对齐并进入编辑'}));
    await waitFor(()=>expect(vi.mocked(fetch).mock.calls.some(([path])=>String(path).endsWith('/produce'))).toBe(true));
    const call=vi.mocked(fetch).mock.calls.find(([path])=>String(path).endsWith('/produce'))!;
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({mode:'prepare',fresh:true,video:'/media/video.mp4',lyrics:'/media/lyrics.txt',trim_end:'00:08',outputs:['on_vocal_karaoke','on_vocal_karaoke_zh']});
  });
});
