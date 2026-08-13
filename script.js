const API_BASE_URL = "/.netlify/functions";

const timeframes=["S3","S5","S10","S15","S20","S30","S40","S50","M1","M2","M3","M5","M10","M15","M30","M60","H1","H4","H12","H24","D1","D7","D30"];
let selectedTF="S3",total=0,calls=0,puts=0,waits=0;

function getHorizon(tf){
 const n=parseInt(tf.substring(1),10);
 if(tf.startsWith("S")) return n+" seconde"+(n>1?"s":"");
 if(tf.startsWith("M")) return n+" minute"+(n>1?"s":"");
 if(tf.startsWith("H")) return n+" heure"+(n>1?"s":"");
 return n+" jour"+(n>1?"s":"");
}

function createTimeframes(){
 const box=document.getElementById("tfbox");
 timeframes.forEach((tf,i)=>{
  const b=document.createElement("button"); b.className="tf"+(i===0?" active":""); b.textContent=tf;
  b.onclick=()=>{document.querySelectorAll(".tf").forEach(x=>x.classList.remove("active"));b.classList.add("active");selectedTF=tf;document.getElementById("horizon").textContent="HORIZON : "+getHorizon(tf)};
  box.appendChild(b);
 });
}

function renderResult(r){
 if(r.price!=null) document.getElementById("price").textContent=Number(r.price).toFixed(5);
 if(r.trend) document.getElementById("trend").textContent=r.trend;
 if(r.rsi!=null) document.getElementById("rsi").textContent=Number(r.rsi).toFixed(1);
 if(r.macd) document.getElementById("macd").textContent=r.macd;
 if(r.ema_fast!=null&&r.ema_slow!=null) document.getElementById("ema").textContent=Number(r.ema_fast).toFixed(5)+" / "+Number(r.ema_slow).toFixed(5);
 if(r.momentum!=null) document.getElementById("momentum").textContent=Number(r.momentum).toFixed(5);
 if(r.support!=null) document.getElementById("support").textContent=Number(r.support).toFixed(5);
 if(r.resistance!=null) document.getElementById("resistance").textContent=Number(r.resistance).toFixed(5);
 if(r.score!=null) document.getElementById("raw").textContent=r.score;

 const signal=r.signal||"WAIT", score=Math.max(0,Math.min(99,Number(r.score)||0));
 const s=document.getElementById("signal"); s.textContent=signal; s.className="signal "+signal.toLowerCase();
 document.getElementById("confidence").textContent=score; document.getElementById("fill").style.width=score+"%";
 document.getElementById("reason").textContent=r.reason||"Analyse reçue depuis le backend.";

 const row=document.createElement("tr");
 row.innerHTML="<td>"+new Date().toLocaleTimeString("fr-FR")+"</td><td>"+document.getElementById("asset").value+"</td><td>"+selectedTF+"</td><td>"+signal+"</td><td>"+score+"%</td>";
 document.getElementById("history").prepend(row);

 total++; if(signal==="CALL")calls++; else if(signal==="PUT")puts++; else waits++;
 document.getElementById("total").textContent=total;document.getElementById("calls").textContent=calls;document.getElementById("puts").textContent=puts;document.getElementById("waits").textContent=waits;
}

async function analyze(){
 const reason=document.getElementById("reason");
 if(!API_BASE_URL){reason.textContent="Ajoute l'URL de ton backend dans API_BASE_URL.";return}
 reason.textContent="Connexion au moteur…";
 try{
  const res=await fetch(API_BASE_URL+"/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset:document.getElementById("asset").value,timeframe:selectedTF})});
  const data=await res.json(); if(!res.ok) throw new Error(data.detail||data.error||"Erreur API"); renderResult(data);
 }catch(e){reason.textContent="Erreur backend : "+e.message}
}

async function analyzeCandles(candles){
 if(!API_BASE_URL) throw new Error("API_BASE_URL n'est pas configurée.");
 const res=await fetch(API_BASE_URL+"/analyze-candles",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset:document.getElementById("asset").value,timeframe:selectedTF,candles})});
 const data=await res.json(); if(!res.ok) throw new Error(data.detail||data.error||"Erreur API"); return data;
}

function runBacktest(){document.getElementById("reason").textContent="Le backtest sera connecté aux données historiques du backend.";document.getElementById("bestTf").textContent="En attente des données";}
function autoTimeframe(){document.getElementById("reason").textContent="La sélection automatique utilisera les performances historiques disponibles."}

document.addEventListener("DOMContentLoaded",()=>{
 createTimeframes();
 document.getElementById("analyze").onclick=analyze;
 document.getElementById("backtest").onclick=runBacktest;
 document.getElementById("auto").onclick=autoTimeframe;
 if("serviceWorker" in navigator) navigator.serviceWorker.register("./service-worker.js").catch(()=>{});
});
