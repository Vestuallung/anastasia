type FileKind='video'|'audio'|'lyrics'|'project';
interface DesktopBridge {postMessage:(message:unknown)=>void}
function bridge():DesktopBridge|undefined {
  return (window as unknown as {webkit?:{messageHandlers?:{desktop?:DesktopBridge}}}).webkit?.messageHandlers?.desktop;
}
export function hasDesktopPicker(){return Boolean(bridge());}
export function pickLocalFile(kind:FileKind):Promise<string|null>{
  const host=bridge();if(!host)return Promise.resolve(null);
  const id=crypto.randomUUID();
  return new Promise(resolve=>{
    const listener=(event:Event)=>{
      const detail=(event as CustomEvent<{id:string;path:string|null}>).detail;
      if(detail?.id!==id)return;
      window.removeEventListener('studio-file',listener);resolve(detail.path);
    };
    window.addEventListener('studio-file',listener);
    host.postMessage({action:'pick',kind,id});
  });
}
