import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsPanel } from './SettingsPanel-11月7日';
import { defaultPreferences } from '../lib/preferences-11月7日';
import type { EditorScene } from '../types';

const scene: EditorScene = {
  lines: [], canvas: {width:1920,height:1080}, theme:'hinatazaka46', title_text:'曲名/日向坂46',
  colors:{sung:'#3399FF',unsung_fill:'#FFFFFF',unsung_outline:'#000000',sung_outline:'#FFFFFF',title_fill:'#3399FF'},
  layout:{top_y:750,bottom_y:950,margin_x:110}, blackout:[], countdown:false,katakana_ruby:false,
  translations:{},subtitle_offset_ms:0,video_offset_ms:0,audio_offset_ms:0,
};

describe('设置', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch',vi.fn(async (_input:RequestInfo|URL,init?:RequestInit) => {
      const changes=JSON.parse(String(init?.body??'{}'));
      return new Response(JSON.stringify({...scene,...changes}),{headers:{'Content-Type':'application/json'}});
    }));
  });

  it('applies playback and timeline defaults together',async () => {
    const onSave=vi.fn().mockResolvedValue(true),onClose=vi.fn();
    render(<SettingsPanel scene={scene} preferences={defaultPreferences} initialTab="editor" onSave={onSave} onClose={onClose} onPreview={vi.fn()}/>);
    await userEvent.selectOptions(screen.getByLabelText('默认速度'),'1.25');
    await userEvent.click(screen.getByLabelText('倍速保调'));
    await userEvent.selectOptions(screen.getByLabelText('吸附间隔'),'50');
    await userEvent.click(screen.getByLabelText('假名读音'));
    expect(onSave).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button',{name:'应用'}));
    expect(onSave).toHaveBeenCalledWith({...defaultPreferences,playback_speed:1.25,preserve_pitch:false,snap_ms:50,show_readings:false},{});
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('previews subtitle changes without saving and supports cancellation',async () => {
    const onSave=vi.fn(),onClose=vi.fn(),onPreview=vi.fn();
    render(<SettingsPanel scene={scene} preferences={defaultPreferences} initialTab="subtitle" onSave={onSave} onClose={onClose} onPreview={onPreview}/>);
    const title=screen.getByLabelText('右上标题');
    await userEvent.clear(title); await userEvent.type(title,'草稿标题');
    await waitFor(()=>expect(onPreview).toHaveBeenCalledWith(expect.objectContaining({title_text:'草稿标题'})));
    expect(vi.mocked(fetch).mock.calls.every(([url])=>String(url)==='/api/editor/settings/preview')).toBe(true);
    await userEvent.click(screen.getByRole('button',{name:'取消'}));
    expect(onSave).not.toHaveBeenCalled();expect(onClose).toHaveBeenCalledOnce();
  });

  it('keeps timed masks until the user chooses to remove them',async () => {
    const onSave=vi.fn().mockResolvedValue(true);
    render(<SettingsPanel scene={{...scene,blackout:[{x:30,y:900,width:1000,height:120,start:10,end:20}]}} preferences={defaultPreferences} initialTab="subtitle" onSave={onSave} onClose={vi.fn()} onPreview={vi.fn()}/>);
    expect(screen.queryByLabelText('遮黑比例')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'应用'}));
    expect(onSave).toHaveBeenCalledWith(defaultPreferences,{});
  });
});
