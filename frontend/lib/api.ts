// Establish one browser workspace before parallel API calls can set competing cookies.
let workspaceReady:Promise<void>|undefined;
function establishWorkspace():Promise<void>{
  if(!workspaceReady)workspaceReady=fetch('/api/health',{cache:'no-store'}).then(async response=>{
    if(!response.ok){const data=await response.json().catch(()=>({detail:'Backend service unavailable.'}));throw new Error(data.detail||'Backend service unavailable.');}
  }).catch(error=>{workspaceReady=undefined;throw error;});
  return workspaceReady;
}
export async function api<T>(path:string,options?:RequestInit):Promise<T>{
  await establishWorkspace();
  const response=await fetch('/api'+path,options);
  if(!response.ok){const data=await response.json().catch(()=>({detail:'Request failed'}));throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return response.json();
}
export const money=(n:number)=>'$'+n.toLocaleString('en-US');
export const percent=(n:number|undefined|null)=>n==null?'—':(n*100).toFixed(1)+'%';
