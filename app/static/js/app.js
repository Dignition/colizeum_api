// COLIZEUM front logic
(function () {
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }
  function toNum(v){ if(v===undefined||v===null)return 0; const s=String(v).replace(/\s+/g,'').replace(',', '.'); const n=parseFloat(s); return isNaN(n)?0:n; }
  function fmt(n){ return (Math.round(n*100)/100).toLocaleString('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2}); }

  // ===== LIST =====
  document.addEventListener('change', e => {
    if (e.target && e.target.matches('input[type="month"]')) {
      const form = e.target.form;
      // РµСЃР»Рё РµСЃС‚СЊ С„РѕСЂРјР° СЃ GET вЂ” РѕС‚РїСЂР°РІР»СЏРµРј; РёРЅР°С‡Рµ вЂ” РјРµРЅСЏРµРј URL-РїР°СЂР°РјРµС‚СЂ month
      if (form && (form.method || 'get').toLowerCase() === 'get') { form.submit(); return; }
      const url = new URL(window.location.href);
      url.searchParams.set('month', e.target.value);
      url.searchParams.delete('page');
      window.location.href = url.toString();
    }
  });
  document.addEventListener('click', e => {
    const el = e.target.closest('.cz-expense'); if(!el) return;
    const t = el.getAttribute('data-tip') || el.getAttribute('title') || '';
    if (t && navigator.clipboard) navigator.clipboard.writeText(t).catch(()=>{});
  });

  // ===== FORM =====
  function inCashierForm(){ return !!$('#cr-form'); }

  // Expenses
  function buildExpenseRow(amount, note){
    const wrap=document.createElement('div');
    wrap.className='row g-2 expense-row';
    wrap.innerHTML=[
      '<div class="col-sm-3"><input class="form-control cz-input expense-amount" inputmode="decimal" step="0.01" placeholder="РЎСѓРјРјР°" value="'+(amount??'')+'"></div>',
      '<div class="col-sm-8"><input class="form-control cz-input expense-note" placeholder="РќР° С‡С‚Рѕ РїРѕС‚СЂР°С‡РµРЅРѕ" value="'+(note?String(note).replace(/"/g,'&quot;'):'')+'"></div>',
      '<div class="col-sm-1 d-grid"><button type="button" class="btn btn-outline-secondary remove-expense" title="РЈРґР°Р»РёС‚СЊ">Г—</button></div>'
    ].join('');
    const amountInput=wrap.querySelector('.expense-amount');
    const noteInput=wrap.querySelector('.expense-note');
    function syncReq(){
      const amt=toNum(amountInput.value);
      if(amt>0){
        noteInput.required=true;
        if((noteInput.value||'').trim().length===0) noteInput.classList.add('is-invalid');
        else noteInput.classList.remove('is-invalid');
      }else{
        noteInput.required=false;
        noteInput.classList.remove('is-invalid');
      }
    }
    [amountInput,noteInput].forEach(i=>i.addEventListener('input',()=>{ recalcExpenses(); recalcEnvelope(); syncReq(); }));
    wrap.querySelector('.remove-expense').addEventListener('click',()=>{ wrap.remove(); recalcExpenses(); recalcEnvelope(); });
    setTimeout(syncReq,0);
    return wrap;
  }
  function readInitialExpenses(){ let raw=$('#expenses_json')?.value||'[]'; try{ return JSON.parse(raw);}catch{ return[]; } }
  function recalcExpenses(){
    const rows=$all('#expenses_list .expense-row');
    const items=rows.map(r=>({
      amount:toNum($('.expense-amount',r)?.value),
      note:($('.expense-note',r)?.value||'').trim()
    })).filter(x=>x.amount||x.note);
    const total=items.reduce((s,i)=>s+(i.amount||0),0);
    const totalInput=$('#expense_total'); if(totalInput) totalInput.value= total ? (Math.round(total*100)/100).toFixed(2) : '';
    const totalView=$('#expense_sum_view'); if(totalView) totalView.textContent=fmt(total);
    const holder=$('#expenses_json'); if(holder) holder.value=JSON.stringify(items);
  }

  // KPI
  function recalcKPIs(){
    const cash=toNum($('[name="cash"]')?.value);
    const ext=toNum($('[name="extended"]')?.value);
    const sbpA=toNum($('[name="sbp_acq"]')?.value);
    const sbpC=toNum($('[name="sbp_cls"]')?.value);
    const acq=toNum($('[name="acquiring"]')?.value);
    const z=cash+ext; const diff=ext-(sbpA+sbpC+acq);
    const zbox=$('#kpi_z'); if(zbox) zbox.textContent=fmt(z);
    const eq=$('#kpi_equal');
    if(eq){
      if(Math.abs(diff)<0.01){ eq.textContent='Р”Рђ'; eq.classList.remove('kpi-bad'); eq.classList.add('kpi-ok'); }
      else{ eq.textContent=fmt(diff); eq.classList.remove('kpi-ok'); eq.classList.add('kpi-bad'); }
    }
  }

  // Envelope
  function getExpenseTotal(){ const hidden=$('#expense_total'); if(hidden){ const v=toNum(hidden.value); if(v) return v; }
    let sum=0; $all('.expense-amount').forEach(el=>{ sum+=toNum(el.value); }); return sum; }
  function recalcEnvelope(){
    const box=$('#env_amount'); if(!box) return;
    const cash=toNum($('[name="cash"]')?.value);
    const refund=toNum($('[name="refund_cash"]')?.value);
    const expenses=getExpenseTotal();
    const env=cash-refund-expenses;
    box.textContent=fmt(env);
  }

  // Validate + Modal
  function gatherValues(){
    const vals={
      shift_date:$('[name="shift_date"]')?.value||'',
      shift_type:$('[name="shift_type"]')?.value||'day',
      admin:$('#cr-form input[disabled]')?.value||'',
      bar:toNum($('[name="bar"]')?.value),
      cash:toNum($('[name="cash"]')?.value),
      extended:toNum($('[name="extended"]')?.value),
      sbp_acq:toNum($('[name="sbp_acq"]')?.value),
      sbp_cls:toNum($('[name="sbp_cls"]')?.value),
      acquiring:toNum($('[name="acquiring"]')?.value),
      refund_cash:toNum($('[name="refund_cash"]')?.value),
      refund_noncash:toNum($('[name="refund_noncash"]')?.value),
      encashment:toNum($('[name="encashment"]')?.value),
      expenses:(()=>{ try{return JSON.parse($('#expenses_json')?.value||'[]');}catch{return[];} })()
    };
    vals.z=vals.cash+vals.extended;
    vals.nonCashSum=vals.sbp_acq+vals.sbp_cls+vals.acquiring;
    vals.expenseTotal=vals.expenses.reduce((s,i)=>s+toNum(i.amount),0)||toNum($('#expense_total')?.value);
    vals.envelope=vals.cash-vals.refund_cash-vals.expenseTotal;
    return vals;
  }
  function validate(vals){
    const errors=[], warnings=[];
    [['Р‘Р°СЂ',vals.bar],['РќР°Р»',vals.cash],['Р Р°СЃС€РёСЂРµРЅРЅР°СЏ РѕРїР»Р°С‚Р°',vals.extended],
     ['РЎР‘Рџ СЌРєРІР°Р№СЂРёРЅРі',vals.sbp_acq],['CLS',vals.sbp_cls],['Р­РєРІР°Р№СЂРёРЅРі!',vals.acquiring],
     ['Р’РѕР·РІСЂР°С‚ РЅР°Р»',vals.refund_cash],['Р’РѕР·РІСЂР°С‚ Р±РµР·РЅР°Р»',vals.refund_noncash],
     ['РРЅРєР°СЃСЃР°С†РёСЏ',vals.encashment],['РС‚РѕРіРѕ СЂР°СЃС…РѕРґРѕРІ',vals.expenseTotal]
    ].forEach(([label,num])=>{ if(num<0) errors.push(`${label}: Р·РЅР°С‡РµРЅРёРµ РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РѕС‚СЂРёС†Р°С‚РµР»СЊРЅС‹Рј`); });

    const diff=vals.extended-vals.nonCashSum;
    if(Math.abs(diff)>=0.01) warnings.push(`Р Р°СЃС€РёСЂРµРЅРЅР°СЏ РѕРїР»Р°С‚Р° РЅРµ СЃС…РѕРґРёС‚СЃСЏ РЅР° ${fmt(diff)} (РѕР¶РёРґР°Р»РѕСЃСЊ = РЎР‘Рџ + CLS + Р­РєРІР°Р№СЂРёРЅРі!)`);
    if(vals.envelope<0) warnings.push(`РџРѕР»РѕР¶РёС‚СЊ РІ РєРѕРЅРІРµСЂС‚ РїРѕР»СѓС‡РёР»РѕСЃСЊ РѕС‚СЂРёС†Р°С‚РµР»СЊРЅРѕ: ${fmt(vals.envelope)}. РџСЂРѕРІРµСЂСЊ В«РќР°Р»В», В«Р’РѕР·РІСЂР°С‚ РЅР°Р»В» Рё В«Р Р°СЃС…РѕРґС‹В».`);

    // РѕРїРёСЃР°РЅРёРµ СЂР°СЃС…РѕРґР° РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ, РµСЃР»Рё СЃСѓРјРјР° > 0
    vals.expenses.forEach((x,i)=>{ const a=toNum(x.amount); const note=(x.note||'').trim();
      if(a>0 && note.length===0) errors.push(`Р Р°СЃС…РѕРґ в„–${i+1}: Р·Р°РїРѕР»РЅРёС‚Рµ В«РќР° С‡С‚Рѕ РїРѕС‚СЂР°С‡РµРЅРѕВ».`); });

    // РќСѓР»РµРІР°СЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ СЃС‡РёС‚Р°РµС‚СЃСЏ Р±РµР· СѓС‡С‘С‚Р° СЂР°СЃС…РѕРґРѕРІ
    const coreSum = vals.bar + vals.cash + vals.extended + vals.refund_cash + vals.refund_noncash + vals.encashment;
    const isZeroShift = Math.abs(coreSum) < 0.01;
    if(vals.expenseTotal>0 && isZeroShift) warnings.push('РўРѕР»СЊРєРѕ СЂР°СЃС…РѕРґС‹ Р±РµР· РїСЂРѕРґР°Р¶. РџРѕРґС‚РІРµСЂРґРёС‚Рµ РЅСѓР»РµРІСѓСЋ СЃРјРµРЅСѓ.');

    return { errors, warnings, isZeroShift };
  }
  function buildPreviewHTML(vals, checks){
    const rows=[
      ['Р”Р°С‚Р°',vals.shift_date],['РЎРјРµРЅР°',vals.shift_type==='day'?'Р”РµРЅСЊ':'РќРѕС‡СЊ'],['РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ',vals.admin],
      ['Р‘Р°СЂ',fmt(vals.bar)],['РќР°Р»',fmt(vals.cash)],['Р Р°СЃС€РёСЂРµРЅРЅР°СЏ РѕРїР»Р°С‚Р°',fmt(vals.extended)],
      ['РЎР‘Рџ СЌРєРІР°Р№СЂРёРЅРі',fmt(vals.sbp_acq)],['CLS (РћРЅР»Р°Р№РЅ РїР»Р°С‚РµР¶Рё)',fmt(vals.sbp_cls)],['Р­РєРІР°Р№СЂРёРЅРі!',fmt(vals.acquiring)],
      ['Р’РѕР·РІСЂР°С‚ РЅР°Р»',fmt(vals.refund_cash)],['Р’РѕР·РІСЂР°С‚ Р±РµР·РЅР°Р»',fmt(vals.refund_noncash)],['РС‚РѕРіРѕ СЂР°СЃС…РѕРґРѕРІ',fmt(vals.expenseTotal)],
      ['Z-РѕС‚С‡С‘С‚',fmt(vals.z)],['Р Р°РІРЅРѕ?',Math.abs(vals.extended-vals.nonCashSum)<0.01?'<b class="kpi-ok">Р”Рђ</b>':`<b class="kpi-bad">${fmt(vals.extended-vals.nonCashSum)}</b>`],
      ['РџРѕР»РѕР¶РёС‚СЊ РІ РєРѕРЅРІРµСЂС‚',fmt(vals.envelope)]
    ].map(([k,v])=>`<tr><td>${k}</td><td class="num">${v}</td></tr>`).join('');
    const exRows=(vals.expenses||[]).length
      ? vals.expenses.map((x,i)=>`<tr><td>${i+1}</td><td>${(x.note||'').replace(/</g,'&lt;')}</td><td class="num">${fmt(toNum(x.amount))}</td></tr>`).join('')
      : '<tr><td colspan="3" class="muted">РќРµС‚ СЂР°СЃС…РѕРґРѕРІ</td></tr>';
    const warnList=checks.warnings.map(w=>`<li class="cz-warn">${w}</li>`).join('');
    const errList=checks.errors.map(w=>`<li class="cz-err">${w}</li>`).join('');
    const zeroBlock=checks.isZeroShift?`
      <div class="mt-2"><label class="form-check">
        <input type="checkbox" id="cz-zero-confirm" class="form-check-input">
        <span>РџРѕРґС‚РІРµСЂР¶РґР°СЋ РЅСѓР»РµРІСѓСЋ СЃРјРµРЅСѓ</span>
      </label></div>`:'';
    return `
      <div class="cz-fieldset"><div class="cz-legend">РџСЂРѕРІРµСЂРєР° РїРµСЂРµРґ СЃРѕС…СЂР°РЅРµРЅРёРµРј</div>
        ${(warnList||errList)?`<ul>${errList}${warnList}</ul>`:'<div class="muted">РћС€РёР±РѕРє РЅРµ РЅР°Р№РґРµРЅРѕ</div>'}
        ${zeroBlock}
      </div>
      <div class="row g-3 mt-2">
        <div class="col-lg-6"><div class="cz-fieldset"><div class="cz-legend">РЎРІРѕРґРЅС‹Рµ РґР°РЅРЅС‹Рµ</div>
          <div class="table-responsive"><table class="cz-table"><tbody>${rows}</tbody></table></div></div></div>
        <div class="col-lg-6"><div class="cz-fieldset"><div class="cz-legend">Р Р°СЃС…РѕРґС‹</div>
          <div class="table-responsive"><table class="cz-table"><thead><tr><th>#</th><th>РќР° С‡С‚Рѕ</th><th class="num">РЎСѓРјРјР°</th></tr></thead><tbody>${exRows}</tbody></table></div></div></div>
      </div>`;
  }
  function openModal(html, checks){
    const modal=$('#cz-modal'); if(!modal) return;
    $('#cz-modal-body').innerHTML=html; modal.hidden=false;
    const btn=$('#cz-modal-confirm'), cancel=$('#cz-modal-cancel'), zero=$('#cz-zero-confirm'), hiddenZero=$('#confirm_zero');
    function syncBtn(){ const allow=(checks.errors.length===0)&&(!checks.isZeroShift || (zero&&zero.checked)); btn.disabled=!allow; hiddenZero&&(hiddenZero.value=(zero&&zero.checked)?'1':'0'); }
    zero&&zero.addEventListener('change',syncBtn); syncBtn();
    cancel.onclick=()=>closeModal();
    btn.onclick=()=>{ closeModal(); $('#cr-form').dataset.confirmed='1'; $('#cr-form').submit(); };
  }
  function closeModal(){ const m=$('#cz-modal'); if(m) m.hidden=true; }

  document.addEventListener('DOMContentLoaded', function(){
    if(!inCashierForm()) return;

    // СЃС‚Р°СЂС‚РѕРІС‹С… СЃС‚СЂРѕРє СЂР°СЃС…РѕРґРѕРІ РЅРµС‚; РїРѕРєР°Р·С‹РІР°РµРј С‚РѕР»СЊРєРѕ СЃРѕС…СЂР°РЅС‘РЅРЅС‹Рµ
    const list=$('#expenses_list'); if(list){ const init=readInitialExpenses(); if(init.length){ init.forEach(x=>list.appendChild(buildExpenseRow(
      (Math.abs(toNum(x.amount)-Math.round(toNum(x.amount)))<0.005)?String(Math.round(toNum(x.amount))):String(toNum(x.amount)),
      x.note||'' ))); } }

    $('#add_expense')?.addEventListener('click',()=>{ const list=$('#expenses_list'); if(!list) return; const row=buildExpenseRow('',''); list.appendChild(row); row.querySelector('.expense-amount')?.focus(); recalcExpenses(); recalcEnvelope(); });

    recalcExpenses(); recalcKPIs(); recalcEnvelope();

    const form=$('#cr-form');
    form.addEventListener('submit', function(e){
      if(form.dataset.confirmed==='1') return;
      e.preventDefault();
      const vals=gatherValues();
      const checks=validate(vals);
      // Р±С‹СЃС‚СЂС‹Р№ РїСЂРѕС…РѕРґ С‚РѕР»СЊРєРѕ РµСЃР»Рё РќР•Рў РѕС€РёР±РѕРє, РќР•Рў РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёР№, РќР• РЅСѓР»РµРІР°СЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ Рё СЃС…РѕРґРёС‚СЃСЏ В«Р Р°СЃС€РёСЂРµРЅРЅР°СЏВ»
      if(checks.errors.length===0 && checks.warnings.length===0 && !checks.isZeroShift && Math.abs(vals.extended-vals.nonCashSum)<0.01){
        form.dataset.confirmed='1'; form.submit(); return;
      }
      openModal(buildPreviewHTML(vals,checks),checks);
    });
  });

  document.addEventListener('input', e=>{
    const n=e.target?.name||'';
    if(['cash','extended','sbp_acq','sbp_cls','acquiring'].includes(n)) recalcKPIs();
    if(n==='cash'||n==='refund_cash') recalcEnvelope();
    if(e.target.classList?.contains('expense-amount')) recalcEnvelope();
  });
  document.addEventListener('keydown', e=>{ if(e.key==='Escape'){ const m=$('#cz-modal'); if(m && !m.hidden){ e.preventDefault(); m.hidden=true; } }});
})();

// ===== SCHEDULE (Р“СЂР°С„РёРє) =====
(function(){
  function $(s,ctx){return (ctx||document).querySelector(s)}
  function $all(s,ctx){return Array.from((ctx||document).querySelectorAll(s))}

  // РјСЏРіРєРёР№ РїР°СЂСЃРµСЂ: РЅРµ РјРµС€Р°РµС‚ РЅР°Р±РѕСЂСѓ, РЅРѕСЂРјР°Р»РёР·СѓРµС‚ РїРѕ blur/Enter
  function parseTime(v){
    if(v===undefined||v===null) return null;
    const s=String(v).trim().toUpperCase();
    if( !s) return null; 
    if(s === 'OFF' || s[0] === 'B' || s.charCodeAt(0) === 1042) return 'OFF';
    const m=s.match(/^(\d{1,2})(?::?([0-5]?\d))?$/); // 9, 09, 900, 9:5, 09:05
    if(!m) return null;
    let hh=parseInt(m[1],10);
    let mm=(m[2]!==undefined)? parseInt(m[2],10) : (s.length===3? parseInt(s.slice(-2),10) : 0);
    if(isNaN(mm)) mm=0;
    if(hh<0||hh>24) return null;
    if(hh===24 && mm!==0) return null;
    if(hh===24 && mm===0) return 24*60;
    return hh*60+mm;
  }
  function fmtHM(mins){
    if(mins==null) return '';
    mins=Math.max(0, Math.round(mins));
    const h=Math.floor(mins/60), m=mins%60;
    return String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0');
  }
  function normalize(el){
    let s=(el.value||'').trim();
    if(!s){ el.value=''; return; }
    if(/^([vVРІР’])$/.test(s)){ el.value='Р’'; return; }
    // РґРѕРїСѓСЃС‚РёС‚СЊ 2,3,4 С†РёС„СЂС‹ Р±РµР· РґРІРѕРµС‚РѕС‡РёСЏ
    if(/^\d{2}$/.test(s)) s=s+':00';
    else if(/^\d{3}$/.test(s)) s=('0'+s[0])+':'+s.slice(1);
    else if(/^\d{4}$/.test(s)) s=s.slice(0,2)+':'+s.slice(2);
    const m=s.match(/^(\d{1,2}):([0-5]?\d)$/);
    if(m){
      const hh=String(parseInt(m[1],10)).padStart(2,'0');
      const mm=String(parseInt(m[2],10) || 0).padStart(2,'0');
      el.value = `${hh}:${mm}`;
    }
  }

  // span: РѕР±С‹С‡РЅС‹Р№ РґРµРЅСЊ/РЅРѕС‡СЊ РёР»Рё В«РґРІРѕР№РЅР°СЏ СЃРјРµРЅР°В» both
  // override parseTime: handle OFF markers ('В', 'B', 'OFF', 'ВЫХ...')
  function parseTime(v){
    if(v===undefined||v===null) return null;
    const s=String(v).trim().toUpperCase();
    // Support Cyrillic 'В', Latin 'B', 'OFF', and 'ВЫХ...'
    if(s==='В' || s==='B' || s==='OFF' || s.startsWith('ВЫХ')) return 'OFF';
    if(!s) return null;
    if(s==='В' || s==='B' || s==='OFF' || s.startsWith('ВЫХ')) return 'OFF';
    const m=s.match(/^(\d{1,2})(?::?([0-5]?\d))?$/); // 9, 09, 900, 9:5, 09:05
    if(!m) return null;
    let hh=parseInt(m[1],10);
    let mm=(m[2]!==undefined)? parseInt(m[2],10) : (s.length===3? parseInt(s.slice(-2),10) : 0);
    if(isNaN(mm)) mm=0;
    if(hh<0||hh>24) return null;
    if(hh===24 && mm!==0) return null;
    if(hh===24 && mm===0) return 24*60;
    return hh*60+mm;
  }
  function calcSpan(aStr, bStr, both){
    const a = parseTime(aStr), b = parseTime(bStr);
    if(a==='OFF' || b==='OFF') return null;
    if(a===null || b===null) return null;

    // Унифицированный расчёт с учётом "both" (день+ночь):
    // - обычный случай: разница по кругу суток
    // - если both=true и конец >= начало: прибавляем к 24:00 дельту (поддержка 24:34, 25:00 и т.п.)
    // - если времена равны: трактуем как 24:00
    if (a === b) return 24*60;
    if (both && b >= a) return 24*60 + (b - a);
    let minutes = b - a;
    if (minutes < 0) minutes += 24*60; // пересечение полуночи
    return minutes;
}function recalcRow(row){
    let total=0, shifts=0;
    const cells = $all('.cell', row);
    for(let i=0;i<cells.length;i+=3){
      const cIn  = $('input.in-time',  cells[i]);
      const cOut = $('input.out-time', cells[i+1]);
      const cHrs = $('input.hours',    cells[i+2]);
      const both = (cIn.dataset.both === '1' || cOut.dataset.both === '1');
      const span = calcSpan(cIn.value, cOut.value, both);
      cHrs.value = fmtHM(span);
      if(span != null){
        if(span>0){
          total += span;
          // РЎСѓС‚РѕС‡РЅР°СЏ СЃРјРµРЅР° (24:00) СЃС‡РёС‚Р°РµС‚СЃСЏ РєР°Рє 2 СЃРјРµРЅС‹
          shifts += (span >= 24*60 ? 2 : 1);
        } else if(span===0){
          shifts += 1;
        }
      }
    }
    $('.row-hours', row).textContent  = fmtHM(total);
    $('.row-shifts', row).textContent = String(shifts);
  }

  function initSchedule(){
    const tables = $all('.sched-table');
    if(!tables.length) return;
    const _saveBtn = document.getElementById('sched-save');
    if(_saveBtn) _saveBtn.remove();
    try{ const st=document.createElement('style'); st.textContent='#sched-save{display:none!important;}'; document.head.appendChild(st);}catch{}

    // Visual lock for rows without permission
    (function lockByRights(){
      const root = document.getElementById('sched-root');
      if(!root) return;
      const editAll = (root.dataset.editAll === '1');
      const editSelf= (root.dataset.editSelf === '1');
      const me = parseInt(root.dataset.my||'0',10)||0;
      if(editAll) return; // can edit everyone
      $all('.row-person').forEach(row=>{
        const uid = parseInt(row.getAttribute('data-user')||'0',10)||0;
        const can = editSelf && (uid===me);
        if(!can){
          $all('input.in-time, input.out-time', row).forEach(inp=>{ inp.disabled=true; });
        }
      });
    })();

    // Inject Save button if not present and bind handler
    const toolbar = document.getElementById('sched-toolbar') || document.querySelector('.toolbar');
    if(toolbar && !document.getElementById('sched-save')){
      const btn = document.createElement('button');
      btn.type='button'; btn.id='sched-save'; btn.className='btn sec'; btn.textContent='Сохранить';
      toolbar.appendChild(btn);
    }
    document.getElementById('sched-save')?.addEventListener('click', async ()=>{
      const payload = (function collect(){
        const monthInput = document.querySelector('input[type="month"][name="m"]');
        const ym = (monthInput?.value||'').trim();
        const rows=[];
        $all('.row-person').forEach(row=>{
          const uid=parseInt(row.getAttribute('data-user')||'0',10)||0; if(!uid) return;
          const cells=$all('.cell',row); const days={};
          for(let i=0,d=1;i<cells.length;i+=3,d++){
            const cIn=$('input.in-time',cells[i]); const cOut=$('input.out-time',cells[i+1]);
            if(!cIn||!cOut) continue; const start=(cIn.value||'').trim(); const end=(cOut.value||'').trim();
            const both=(cIn.dataset.both==='1'||cOut.dataset.both==='1')?1:0; if(!start&&!end) continue;
            const iso = ym? (ym+'-'+String(d).padStart(2,'0')) : (new Date(new Date().getFullYear(), new Date().getMonth(), d).toISOString().slice(0,10));
            days[iso]={start,end,both};
          }
          if(Object.keys(days).length) rows.push({user_id:uid, days});
        });
        return {month: ym, rows};
      })();
      try{
        const res = await fetch('/schedule/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
        const data = await res.json();
        if(data?.ok) alert(`Сохранено смен: ${data.saved}`); else alert('Не удалось сохранить');
      }catch{ alert('Сеть: не удалось сохранить'); }
    });

    async function autosaveFromInput(el, row){
      try{
        const uid = parseInt(row.getAttribute('data-user')||'0',10)||0; if(!uid) return;
        const cells = $all('.cell', row);
        const td = el.closest('td.cell'); if(!td) return;
        const idx = cells.indexOf(td); if(idx<0) return;
        const group = Math.floor(idx/3);
        const cIn = $('input.in-time', cells[group*3]);
        const cOut= $('input.out-time',cells[group*3+1]);
        const both = (cIn?.dataset.both==='1' || cOut?.dataset.both==='1') ? 1 : 0;
        function toHHMM(v){
          let s=(v||'').trim(); if(!s) return '';
          if(/^\d$/.test(s)) return ('0'+s+':00');
          if(/^\d{2}$/.test(s)) return (s+':00');
          if(/^\d{3}$/.test(s)) return ('0'+s[0]+':'+s.slice(1));
          if(/^\d{4}$/.test(s)) return (s.slice(0,2)+':'+s.slice(2));
          const m=s.match(/^(\d{1,2}):([0-5]?\d)$/); if(m){
            const hh=String(parseInt(m[1],10)).padStart(2,'0');
            const mm=String(parseInt(m[2],10)||0).padStart(2,'0');
            return `${hh}:${mm}`;
          }
          if(/^off$/i.test(s) || /^[vb]$/i.test(s)) return 'OFF';
          return s;
        }
        const start = toHHMM(cIn?.value);
        const end   = toHHMM(cOut?.value);
        const ym = (document.querySelector('input[type="month"][name="m"]')?.value||'').trim();
        if(!ym) return; const day = String(group+1).padStart(2,'0');
        const iso = `${ym}-${day}`;
        // tiny delay to coalesce quick edits
        await new Promise(r=>setTimeout(r,100));
        const res = await fetch('/schedule/save-one', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user_id: uid, date: iso, start, end, both})});
        const data = await res.json().catch(()=>({ok:false}));
        const hoursCell = cells[group*3+2];
        const target = $('input.hours', hoursCell) || hoursCell;
        const prev = target.style.boxShadow;
        if(data?.ok){
          target.style.boxShadow = '0 0 0 3px rgba(105,211,107,.85) inset';
          setTimeout(()=>{ target.style.boxShadow = prev; }, 900);
        } else {
          target.style.boxShadow = '0 0 0 3px rgba(255,110,110,.85) inset';
          setTimeout(()=>{ target.style.boxShadow = prev; }, 1200);
          console.warn('autosave failed', data);
        }
      }catch(err){ console.warn('autosave error', err); }
    }

    $all('.row-person').forEach(row=>{
      // РїРµСЂРµСЃС‡С‘С‚ РїСЂРё Р·Р°РіСЂСѓР·РєРµ
      recalcRow(row);

      // UX: Enter/Tab/blur -> РЅРѕСЂРјР°Р»РёР·Р°С†РёСЏ Рё РїРµСЂРµСЃС‡С‘С‚
      row.addEventListener('keydown', e=>{
        const el=e.target;
        if(!(el.classList && (el.classList.contains('in-time')||el.classList.contains('out-time')))) return;
        if(e.key==='Enter'){
          e.preventDefault();
          normalize(el);
          recalcRow(row);
          autosaveFromInput(el, row);
          // РїРµСЂРµРІРµСЃС‚Рё С„РѕРєСѓСЃ РЅР° СЃР»РµРґСѓСЋС‰РёР№ РёРЅРїСѓС‚
          const inputs=$all('input.in-time, input.out-time', row);
          const idx=inputs.indexOf(el);
          const next=inputs[idx+1]||inputs[0];
          next.focus(); next.select?.();
        }
      });
      row.addEventListener('blur', e=>{
        const el=e.target;
        if(!(el.classList && (el.classList.contains('in-time')||el.classList.contains('out-time')))) return;
        normalize(el);
        recalcRow(row);
        autosaveFromInput(el, row);
      }, true);

      // Р°РІС‚Рѕ-РІС‹РґРµР»РµРЅРёРµ С‚РµРєСЃС‚Р° РїСЂРё С„РѕРєСѓСЃРµ
      row.addEventListener('focusin', e=>{
        const el=e.target;
        if(el.tagName==='INPUT') el.select?.();
      });
    });
  }

  document.addEventListener('DOMContentLoaded', initSchedule);
  document.addEventListener('change', e=>{
    if(e.target && e.target.matches('input[type="month"]')) {
      const form = e.target.form;
      if (form && (form.method || 'get').toLowerCase() === 'get') { form.submit(); return; }
      const url = new URL(window.location.href);
      url.searchParams.set('month', e.target.value);
      url.searchParams.delete('page');
      window.location.href = url.toString();
    }
  });
})();



