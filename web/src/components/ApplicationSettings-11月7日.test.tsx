import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ApplicationSettings } from "./ApplicationSettings-11月7日";
const settings={ffmpeg:"ffmpeg",ffprobe:"ffprobe",alignment_python:"",device:"cpu",model_id:"NextFire/model",model_revision:"fixed",model_cache:"",japanese_font:"Noto Sans CJK JP",japanese_font_path:"bundle:jp.otf",chinese_font:"Noto Sans CJK JP",chinese_font_path:"bundle:cn.otf",groups:{nogizaka46:{label:"乃木坂46",sung:"#9465D9"}},default_theme:"nogizaka46"};
const status={tools:{ffmpeg:{ready:true},ffprobe:{ready:true}},alignment:{runtime_ready:true,model_ready:false},fonts:{japanese:{ready:true},chinese:{ready:true}},model_url:"https://huggingface.co/NextFire/model",model_license:"CC-BY-NC-SA-4.0"};
let requests:{url:string;init?:RequestInit}[]=[];
beforeEach(()=>{
 requests=[];
 vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);requests.push({url,init});
  let value:unknown={};
  if(url.endsWith("/settings"))value={settings};
  if(url.endsWith("/status"))value=status;
  if(url.endsWith("/tasks"))value=[];
  if(url.endsWith("/setup"))value={id:"task",status:"running",action:"model",message:"正在下载模型"};
  return new Response(JSON.stringify(value),{headers:{"content-type":"application/json"}});
 }));
});
it("requires deliberate model download and preserves group color edits",async()=>{
 render(<ApplicationSettings onClose={()=>{}}/>);
 await screen.findByText("NextFire/model");
 expect(screen.getByRole("button",{name:"下载模型"})).toBeDisabled();
 expect(requests.some(r=>r.url.endsWith("/setup"))).toBe(false);
 await userEvent.click(screen.getByRole("checkbox"));
 await userEvent.click(screen.getByRole("button",{name:"下载模型"}));
 expect(await screen.findByText("正在下载模型")).toBeVisible();
 const request=requests.find(r=>r.url.endsWith("/setup"));
 expect(JSON.parse(String(request?.init?.body))).toEqual({action:"model",license_accepted:true});
});
it("saves the selected font and a new group",async()=>{
 render(<ApplicationSettings onClose={()=>{}}/>);
 await screen.findByText("NextFire/model");
 await userEvent.click(screen.getByRole("button",{name:"字体"}));
 const names=screen.getAllByLabelText("字体名称");
 await userEvent.clear(names[1]);await userEvent.type(names[1],"楷体");
 await userEvent.click(screen.getByRole("button",{name:"团体与颜色"}));
 await userEvent.click(screen.getByRole("button",{name:"添加团体"}));
 await userEvent.click(screen.getByRole("button",{name:"保存设置"}));
 expect(await screen.findByText("已保存，下次启动时生效")).toBeVisible();
 const request=requests.find(r=>r.url.endsWith("/settings")&&r.init?.method==="POST");
 const body=JSON.parse(String(request?.init?.body));
 expect(body.chinese_font).toBe("楷体");expect(body.groups.group_2.label).toBe("新团体");
});
it("dismisses with Escape and does not save",async()=>{
 const close=vi.fn();render(<ApplicationSettings onClose={close}/>);
 await screen.findByText("NextFire/model");await userEvent.keyboard("{Escape}");
 expect(close).toHaveBeenCalledOnce();
 await waitFor(()=>expect(requests.some(r=>r.init?.method==="POST")).toBe(false));
});
