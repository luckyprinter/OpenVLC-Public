import React, {useEffect, useMemo, useState} from 'react';
import {ArrowUpRight, Code2, Search} from 'lucide-react';
import repoIndex from './data/repo-index.json';
import './deep-dive.css';

const REPO='https://github.com/luckyprinter/OpenVLC-Public';
const SOURCE_PIN='411f183a8592d8285118f613bb4909c5bbd9d3cc';

async function fetchSource(file, signal) {
 const path=file.path.split('/').map(encodeURIComponent).join('/');
 const response=await fetch(`https://raw.githubusercontent.com/luckyprinter/OpenVLC-Public/${SOURCE_PIN}/${path}`,{signal});
 if(!response.ok) throw new Error(`Source returned HTTP ${response.status}`);
 const bytes=new Uint8Array(await response.arrayBuffer());
 if(bytes.length!==file.bytes) throw new Error('Source size does not match the index');
 if(globalThis.crypto?.subtle) {
  const header=new TextEncoder().encode(`blob ${bytes.length}\0`);
  const blob=new Uint8Array(header.length+bytes.length);
  blob.set(header);
  blob.set(bytes,header.length);
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-1',blob));
  const hash=Array.from(digest,byte=>byte.toString(16).padStart(2,'0')).join('');
  if(hash!==file.blob) throw new Error('Source blob does not match the index');
 }
 return new TextDecoder().decode(bytes);
}
const link=(path,ref,lines='')=>{const firstRange=lines?lines.split(',')[0].trim():'';return REPO+'/blob/'+ref+'/'+path+(firstRange?'#L'+firstRange.replace('-','-L'):'');};
const formatLines=(lines='')=>lines.split(',').map(part=>'L'+part.trim().replace('-','–L')).join(', ');

const deepRelations = {
 'application-source/gui_dev_v3/app.py':[
  {label:'Launches the TX shell from the unified app window',path:'application-source/gui_dev_v3/app.py',lines:'321-330'},
  {label:'Launches the RX shell from the unified app window',path:'application-source/gui_dev_v3/app.py',lines:'331-338'}
 ],
 'application-source/gui_dev_v3/tx/dashboard.py':[
  {label:'Delegates the selected path to TXAppState',path:'application-source/gui_dev_v3/tx_app_state.py',lines:'225-238'},
  {label:'TX state calls the physical backend',path:'application-source/gui_dev_v3/tx/backends/physical.py',lines:'194-207'},
  {label:'Physical backend calls the serial controller',path:'application-source/gui_dev_v3/serial/controllers.py',lines:'145-165'},
  {label:'TX firmware receives STREAM commands',path:'firmware/tx/tx.ino',lines:'306-332'}
 ],
 'application-source/gui_dev_v3/tx_app_state.py':[
  {label:'TX Dashboard calls state methods',path:'application-source/gui_dev_v3/tx/dashboard.py',lines:'719-766'},
  {label:'TX physical backend',path:'application-source/gui_dev_v3/tx/backends/physical.py',lines:'194-250'},
  {label:'TX serial controller',path:'application-source/gui_dev_v3/serial/controllers.py',lines:'145-210'}
 ],
 'application-source/gui_dev_v3/serial/controllers.py':[
  {label:'Uses shared serial session',path:'application-source/gui_dev_v3/serial/session.py',lines:'90-150'},
  {label:'Receives firmware command responses',path:'firmware/tx/tx.ino',lines:'306-332'},
  {label:'TX physical backend owns the controller',path:'application-source/gui_dev_v3/tx/backends/physical.py',lines:'1-80'}
 ],
 'firmware/tx/tx.ino':[
  {label:'TX desktop serial controller sends preload commands',path:'application-source/gui_dev_v3/serial/controllers.py',lines:'145-210'},
  {label:'TX output pin and LED driver',path:'firmware/README.md',lines:'60-95'},
  {label:'Protocol fields and framing',path:'firmware/specs/protocol_spec.md',lines:'1-46'}
 ],
 'firmware/rx/rx.ino':[
  {label:'RX physical backend parses firmware output',path:'application-source/gui_dev_v3/rx/backends/physical.py',lines:'909-950'},
  {label:'RX backend parses firmware transfer notices and received-file records',path:'application-source/gui_dev_v3/rx/backends/physical.py',lines:'299-370'},
  {label:'Protocol field definitions',path:'firmware/specs/protocol_spec.md',lines:'1-46'}
 ],
 'application-source/gui_dev_v3/rx/backends/physical.py':[
  {label:'Updates RX application state',path:'application-source/gui_dev_v3/app_state.py',lines:'130-245'},
  {label:'Feeds the RX Dashboard',path:'application-source/gui_dev_v3/rx/dashboard.py',lines:'309-405'},
  {label:'Feeds Inspect and transfer records',path:'application-source/gui_dev_v3/rx/inspect_page.py',lines:'329-430'}
 ],
 'application-source/gui_dev_v3/rx/signal_page.py':[
  {label:'Reads live signal state',path:'application-source/gui_dev_v3/app_state.py',lines:'130-245'},
  {label:'Physical backend maps LQ telemetry',path:'application-source/gui_dev_v3/rx/backends/physical.py',lines:'909-950'},
  {label:'Uses reusable signal plot widgets',path:'application-source/gui_dev_v3/rx/signal_widgets.py',lines:'330-480'}
 ],
 'application-source/gui_dev_v3/rx/inspect_page.py':[
  {label:'Reads transfer/chunk state',path:'application-source/gui_dev_v3/app_state.py',lines:'130-245'},
  {label:'Loads reference bytes for comparison',path:'application-source/gui_dev_v3/rx/ber_analyzer_page.py',lines:'97-180'},
  {label:'BER comparison helper',path:'application-source/gui_dev_v3/logic/ber_bridge.py',lines:'1-125'}
 ],
 'application-source/gui_dev_v3/rx/ber_analyzer_page.py':[
  {label:'Uses shared BER comparison logic',path:'application-source/gui_dev_v3/logic/ber_bridge.py',lines:'1-125'},
  {label:'Receives expected bytes from Inspect',path:'application-source/gui_dev_v3/rx/inspect_page.py',lines:'430-490'}
 ],
 'application-source/gui_dev_v3/rx/settings.py':[
  {label:'Persists values through SettingsManager',path:'application-source/gui_dev_v3/settings.py',lines:'1-110'},
  {label:'Sends settings to RX physical backend',path:'application-source/gui_dev_v3/rx/backends/physical.py',lines:'568-592'},
  {label:'Firmware command parser',path:'firmware/rx/rx.ino',lines:'1014-1048'}
 ],
 'application-source/gui_dev_v3/rx/export_page.py':[
  {label:'Loads saved SessionCapture data',path:'application-source/gui_dev_v3/data/session.py',lines:'1-160'},
  {label:'Uses transfer records',path:'application-source/gui_dev_v3/data/records.py',lines:'1-180'}
 ],
 'application-source/gui_dev_v3/tx/settings.py':[
  {label:'Persists values through SettingsManager',path:'application-source/gui_dev_v3/settings.py',lines:'1-110'},
  {label:'Applies supported link commands',path:'application-source/gui_dev_v3/serial/controllers.py',lines:'90-135'},
  {label:'TX firmware command parser',path:'firmware/tx/tx.ino',lines:'306-332'}
 ]
};
const deepLessons = {
 'application-source/gui_dev_v3/app.py':['app-launch','console-launch'],
 'application-source/gui_dev_v3/tx/dashboard.py':['tx-select','tx-start'],
 'application-source/gui_dev_v3/tx_app_state.py':['tx-state'],
 'application-source/gui_dev_v3/tx/settings.py':['tx-settings-apply'],
 'application-source/gui_dev_v3/serial/controllers.py':['serial-start','tx-chunk-size'],
 'application-source/gui_dev_v3/rx/settings.py':['rx-settings-apply'],
 'application-source/gui_dev_v3/rx/backends/physical.py':['rx-app','rx-vref-stepper'],
 'application-source/gui_dev_v3/rx/signal_page.py':['rx-signal-sampler','rx-quality-estimates'],
 'application-source/gui_dev_v3/rx/ber_analyzer_page.py':['rx-ber'],
 'application-source/gui_dev_v3/rx/export_page.py':['rx-export-fallback'],
 'application-source/gui_dev_v3/rx/table_builder_page.py':['rx-table-mock'],
 'firmware/tx/tx.ino':['tx-frame','tx-encode','tx-bit'],
 'firmware/rx/rx.ino':['rx-majority','rx-decode','rx-crc']
};

export default function DeepDive({onOpenCode,codeLessons}) {
 const [query,setQuery]=useState('');
 const [category,setCategory]=useState('ALL');
 const [status,setStatus]=useState('ALL');
 const [selected,setSelected]=useState('application-source/gui_dev_v3/tx/dashboard.py');
 const [symbolQuery,setSymbolQuery]=useState('');
 const [activeSymbolLine,setActiveSymbolLine]=useState(null);
 const [source,setSource]=useState(null);
 const fileSearch=React.useRef(null);
 const fileHeading=React.useRef(null);
 const symbolHeading=React.useRef(null);
 const symbolSearch=React.useRef(null);
 function focusMobile(ref){
  if(window.matchMedia('(max-width: 720px)').matches){
   requestAnimationFrame(()=>ref.current?.focus());
  }
 }
 const files=repoIndex;
 const categories=useMemo(()=>['ALL',...Array.from(new Set(files.map(f=>f.category))).sort()],[files]);
 const filtered=useMemo(()=>files.filter(f=>{
  const text=(f.path+' '+f.summary+' '+f.symbols.map(s=>s.name).join(' ')+' '+f.headings.map(h=>h.title).join(' ')).toLowerCase();
  return (category==='ALL'||f.category===category)&&(status==='ALL'||f.status===status)&&text.includes(query.trim().toLowerCase());
 }),[files,category,status,query]);
 const current=filtered.find(f=>f.path===selected)||filtered[0];
 const symbolFilter=current?.path===selected?symbolQuery:'';
 const visibleSymbols=useMemo(()=>current?.symbols.filter(s=>(s.name+' '+s.kind).toLowerCase().includes(symbolFilter.trim().toLowerCase()))??[],[current,symbolFilter]);
 const activeSymbol=current?.path===selected?visibleSymbols.find(s=>s.line===activeSymbolLine):null;
 const sourceFile=activeSymbol?current:null;
 useEffect(()=>{
  if(!sourceFile) return;
  const request=new AbortController();
  fetchSource(sourceFile,request.signal).then(value=>{
   if(!request.signal.aborted) setSource({path:sourceFile.path,value,status:'ready'});
  }).catch(()=>{
   if(!request.signal.aborted) setSource({path:sourceFile.path,status:'error'});
  });
  return ()=>request.abort();
 },[sourceFile]);
 const sourceStatus=source?.path===current?.path?source?.status??'loading':'loading';
 const activeSourceLines=activeSymbol&&sourceStatus==='ready'
  ?source.value.split('\n').slice(activeSymbol.line-1,activeSymbol.endLine||activeSymbol.line)
  :[];
 const relations=deepRelations[current?.path]||[];
 const lessons=deepLessons[current?.path]||[];
 const codeCount=files.filter(f=>f.kind==='python'||f.kind==='arduino-cpp').length;
 const symbolCount=files.reduce((sum,f)=>sum+f.symbols.length,0);
 const docCount=files.filter(f=>f.headings.length>0).length;
 const statusLabel={active:'ACTIVE SOURCE','alternate/test':'ALTERNATE / TEST',supporting:'SUPPORTING',documentation:'DOCUMENTATION',build:'BUILD / CI',asset:'ASSET',data:'DATA'};
 const choose=(f)=>{setSelected(f.path);setSymbolQuery('');setActiveSymbolLine(null)};
 return <section className="deep-dive-section">
  <div className="section-kicker">COMPLETE REPOSITORY DEEP DIVE <span>OPTIONAL · ADVANCED READING</span></div>
  <div className="section-title-row"><div><p className="eyebrow">GO BEYOND THE GUIDED CURRICULUM</p><h2>Explore the whole<br/><i>source repository.</i></h2></div><p className="section-intro">This is the optional reference layer. Search every tracked file, inspect indexed classes and functions, follow verified cross-file relationships, and open the exact source revision. You do not need this page to complete the beginner learning paths.</p></div>
  <div className="deep-dive-stats"><div><b>{files.length}</b><span>TRACKED FILES</span></div><div><b>{codeCount}</b><span>CODE FILES</span></div><div><b>{symbolCount.toLocaleString()}</b><span>INDEXED SYMBOLS</span></div><div><b>{docCount}</b><span>DOCUMENTS WITH HEADINGS</span></div></div>
  <div className="deep-dive-pin"><span>PINNED SOURCE SNAPSHOT</span><code>OpenVLC-Public · {SOURCE_PIN}</code><a href={'https://github.com/luckyprinter/OpenVLC-Public/tree/'+SOURCE_PIN} target="_blank" rel="noreferrer">VIEW REPOSITORY <ArrowUpRight size={13}/></a></div>
  <div className="deep-dive-layout">
   <aside className="deep-dive-browser">
    <label className="deep-search"><Search size={15}/><input ref={fileSearch} aria-label="Search repository files" type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search files, classes, functions…"/></label>
    <div className="deep-filter-row"><select aria-label="File category" value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(c=><option key={c} value={c}>{c==='ALL'?'ALL CATEGORIES':c}</option>)}</select><select aria-label="File status" value={status} onChange={e=>setStatus(e.target.value)}>{[['ALL','ALL STATUS'],['active','ACTIVE SOURCE'],['alternate/test','ALTERNATE / TEST'],['supporting','SUPPORTING'],['documentation','DOCUMENTATION'],['build','BUILD / CI'],['asset','ASSET'],['data','DATA']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
    <div className="deep-result-count" role="status">{filtered.length} FILES MATCH YOUR FILTERS</div>
    <div className="deep-file-list">{filtered.map(f=><button key={f.path} data-path={f.path} aria-pressed={current?.path===f.path} className={current?.path===f.path?'active':''} onClick={()=>{choose(f);focusMobile(fileHeading)}}><span className="deep-file-top"><i>{f.kind.toUpperCase()}</i><small>{statusLabel[f.status]||f.status}</small></span><b>{f.path.split('/').pop()}</b><code>{f.path}</code><span className="deep-file-meta">{f.lineCount?f.lineCount+' lines · ':''}{f.symbols.length?f.symbols.length+' symbols · ':''}{Math.round(f.bytes/1024*10)/10} KiB</span></button>)}</div>
   </aside>
   {current?<article className="deep-file-detail">
    <button className="reference-nav-control" onClick={()=>focusMobile(fileSearch)}>Back to file search</button>
    <div className="deep-file-head"><div><span className="eyebrow">{current.category} · {statusLabel[current.status]||current.status}</span><h3 ref={fileHeading} tabIndex={-1}>{current.path.split('/').pop()}</h3><code>{current.path}</code></div><a href={link(current.path,SOURCE_PIN)} target="_blank" rel="noreferrer">OPEN FULL SOURCE <ArrowUpRight size={14}/></a></div>
    <p className="deep-file-summary">{current.summary}</p>
    <div className="deep-file-stats"><span>{current.lineCount??'—'} LINES</span><span>{current.symbols.length} SYMBOLS</span><span>{(current.bytes/1024).toFixed(1)} KiB</span><span>BLOB {current.blob.slice(0,9)}</span></div>
    {relations.length>0&&<div className="deep-relations"><div className="deep-section-label">VERIFIED CONNECTIONS · CROSS-FILE TRACE</div>{relations.map((r,i)=><a key={i} href={link(r.path,SOURCE_PIN,r.lines)} target="_blank" rel="noreferrer"><span>{r.label}</span><code>{r.path.split('/').pop()} · {formatLines(r.lines)}</code><ArrowUpRight size={13}/></a>)}</div>}
    {lessons.length>0&&<div className="deep-lessons"><div className="deep-section-label">GUIDED LESSONS RELATED TO THIS FILE</div>{lessons.map(id=>{const lesson=codeLessons.find(x=>x.id===id);return lesson?<button key={id} onClick={()=>onOpenCode(id)}><Code2 size={13}/>{lesson.name}<ArrowUpRight size={12}/></button>:null})}</div>}
    {current.symbols.length>0&&(
      <div className="deep-symbols">
       <div className="deep-symbol-heading">
        <div><div className="deep-section-label">CLASS / FUNCTION / CONSTANT INDEX</div><p>Select a symbol to inspect its outline and implementation.</p></div>
        <label><Search size={13}/><input ref={symbolSearch} aria-label="Filter file symbols" type="search" value={symbolFilter} onChange={e=>{if(current.path!==selected) choose(current);setSymbolQuery(e.target.value)}} placeholder="Filter symbols"/></label>
       </div>
       <div className="deep-symbol-list">
        {visibleSymbols.map((s,i)=>(
         <button type="button" key={s.name+'-'+s.line+'-'+i} aria-pressed={activeSymbol===s} className={activeSymbol===s?'active':''} onClick={()=>{if(current.path!==selected) choose(current);setActiveSymbolLine(s.line);focusMobile(symbolHeading)}}>
          <span className={'deep-symbol-kind kind-'+s.kind}>{s.kind}</span><b>{s.name}</b><code>L{s.line}–{s.endLine||s.line}</code><ArrowUpRight size={12}/>
         </button>
        ))}
        {visibleSymbols.length===0&&<p className="deep-empty">No symbols match this filter.</p>}
       </div>
       {activeSymbol&&(
        <div className="deep-symbol-detail">
         <div className="deep-section-label">SELECTED {activeSymbol.kind.toUpperCase()} · SOURCE OUTLINE</div>
         <h4 ref={symbolHeading} tabIndex={-1}>{activeSymbol.name}</h4>
         <button className="reference-nav-control" onClick={()=>focusMobile(symbolSearch)}>Back to symbol search</button>
         <code className="deep-symbol-range">SOURCE LINES {activeSymbol.line}–{activeSymbol.endLine||activeSymbol.line}</code>
         <pre>{activeSymbol.signature||activeSymbol.name}</pre>
         {activeSymbol.doc&&<p>{activeSymbol.doc}</p>}
         <a href={link(current.path,SOURCE_PIN,String(activeSymbol.line)+'-'+String(activeSymbol.endLine||activeSymbol.line))} target="_blank" rel="noreferrer">OPEN THIS SOURCE SPAN ON GITHUB <ArrowUpRight size={13}/></a>
         <small>Line range is an indexed outline from the pinned source snapshot.</small>
         <div className="deep-source-viewer">
          <div className="deep-source-head" role="status"><span>PINNED SOURCE EXCERPT</span><span>{sourceStatus==='ready'?activeSourceLines.length+' LINES LOADED':sourceStatus==='loading'?'LOADING SOURCE…':'SOURCE FETCH UNAVAILABLE'}</span></div>
          {sourceStatus==='ready'?(
           <pre tabIndex={0} aria-label={'Source excerpt for '+activeSymbol.name}>{activeSourceLines.map((line,i)=><span key={i} className={i===0?'source-focus':''}><i>{activeSymbol.line+i}</i>{line||' '}</span>)}</pre>
          ):(
           <p>{sourceStatus==='loading'?'Loading the selected function from the pinned public repository…':'The source excerpt could not be loaded. Use the immutable GitHub link above to inspect it.'}</p>
          )}
         </div>
        </div>
       )}
      </div>
    )}
    {current.headings.length>0&&<div className="deep-symbols"><div className="deep-section-label">DOCUMENT SECTION INDEX</div><div className="deep-symbol-list">{current.headings.map((h,i)=><a key={h.line+'-'+i} href={link(current.path,SOURCE_PIN,String(h.line)+'-'+String(h.line+2))} target="_blank" rel="noreferrer"><span className="deep-symbol-kind kind-doc">HEADING</span><b>{h.title}</b><code>LINE {h.line}</code><ArrowUpRight size={12}/></a>)}</div></div>}
    {current.symbols.length===0&&current.headings.length===0&&<div className="deep-file-note">This tracked item is an asset, data file, workflow, or configuration file rather than a symbol-indexed source module. Open the immutable source link to inspect its full contents.</div>}
    <div className="deep-file-footnote">The Deep Dive indexes all tracked files at this pinned revision. Full source text remains in the source repository and opens at immutable commit links; the guided Code Studio provides curated, explained excerpts for the most important execution paths.</div>
   </article>:<div className="deep-file-detail"><p>No files match these filters.</p></div>}
  </div>
 </section>
}
