export async function api<T>(path:string,options?:RequestInit):Promise<T>{
  const response=await fetch('/api'+path,options);
  if(!response.ok){const data=await response.json().catch(()=>({detail:'Request failed'}));throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return response.json();
}
export const money=(n:number)=>'$'+n.toLocaleString('en-US');
export const percent=(n:number|undefined|null)=>n==null?'—':(n*100).toFixed(1)+'%';
