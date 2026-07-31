import os
import json
import uuid
import base64
from datetime import datetime
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
DATA_FILE = "inventory.json"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>黑膠庫存管理</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #F5F5F5; max-width: 480px; margin: 0 auto; min-height: 100vh; }
.header { background: #1a1a2e; color: #fff; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
.header h1 { font-size: 17px; font-weight: 700; }
.icon-btn { background: rgba(255,255,255,0.15); border: none; color: #fff; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 15px; }
.filter-bar { background: #fff; padding: 10px 12px; border-bottom: 1px solid #eee; }
.search-input { width: 100%; padding: 8px 12px; border: 1.5px solid #E5E7EB; border-radius: 10px; font-size: 14px; outline: none; }
.grade-filters { display: flex; gap: 6px; margin-top: 8px; }
.grade-filter-btn { padding: 4px 14px; border-radius: 20px; border: none; font-size: 13px; font-weight: 600; cursor: pointer; background: #F3F4F6; color: #374151; }
.grade-filter-btn.active { background: #1a1a2e; color: #fff; }
.count-bar { padding: 6px 16px; font-size: 13px; color: #6B7280; }
.record-list { padding-bottom: 100px; }
.record-row { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #fff; border-bottom: 1px solid #F3F4F6; cursor: pointer; }
.thumb { width: 56px; height: 56px; border-radius: 8px; flex-shrink: 0; background: #F3F4F6; display: flex; align-items: center; justify-content: center; font-size: 24px; overflow: hidden; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.record-info { flex: 1; min-width: 0; }
.record-artist { font-weight: 700; font-size: 15px; color: #1F2937; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.record-album { font-size: 13px; color: #6B7280; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.record-tags { display: flex; gap: 5px; margin-top: 5px; flex-wrap: wrap; }
.tag { padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.tag-A { background: #FEF3C7; color: #D97706; }
.tag-B { background: #DBEAFE; color: #1D4ED8; }
.tag-C { background: #F3F4F6; color: #6B7280; }
.tag-fmt { background: #F3F4F6; color: #6B7280; }
.chevron { color: #D1D5DB; font-size: 18px; }
.empty { text-align: center; padding: 60px 20px; color: #9CA3AF; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.fab { position: fixed; bottom: 24px; right: 24px; width: 56px; height: 56px; border-radius: 50%; background: #1a1a2e; color: #fff; font-size: 28px; border: none; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 200; }
.panel { position: fixed; inset: 0; background: #F5F5F5; z-index: 300; overflow-y: auto; display: none; }
.panel.open { display: block; }
.panel-header { background: #1a1a2e; color: #fff; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; }
.panel-header h2 { font-size: 17px; font-weight: 700; }
.back-btn { background: none; border: none; color: #60A5FA; font-size: 15px; cursor: pointer; }
.danger-btn { background: none; border: none; color: #F87171; font-size: 15px; cursor: pointer; }
.form-body { padding: 16px; }
.photo-zone { width: 100%; height: 180px; background: #fff; border: 2px dashed #D1D5DB; border-radius: 16px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px; overflow: hidden; }
.photo-placeholder { text-align: center; color: #9CA3AF; }
.upload-btn-label { display: block; width: 100%; padding: 12px; background: #F3F4F6; color: #374151; border: 1.5px solid #D1D5DB; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; text-align: center; margin-bottom: 10px; }
.batch-btn-label { display: block; width: 100%; padding: 12px; background: #EDE9FE; color: #7C3AED; border: 1.5px solid #7C3AED; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; text-align: center; margin-bottom: 14px; }
.ai-bar { padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 12px; text-align: center; font-weight: 600; display: none; }
.ai-bar.loading { background: #FEF3C7; color: #92400E; display: block; }
.ai-bar.done { background: #D1FAE5; color: #065F46; display: block; }
.ai-bar.error { background: #FEE2E2; color: #991B1B; display: block; }
.progress-bar-wrap { background: #E5E7EB; border-radius: 10px; height: 8px; margin: 8px 0 4px; }
.progress-bar { background: #7C3AED; height: 8px; border-radius: 10px; transition: width 0.3s; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.field { margin-bottom: 10px; }
.field label { display: block; font-size: 12px; font-weight: 700; color: #374151; margin-bottom: 4px; }
.field input, .field select, .field textarea { width: 100%; padding: 9px 11px; border: 1.5px solid #E5E7EB; border-radius: 8px; font-size: 14px; outline: none; background: #fff; font-family: inherit; }
.field textarea { resize: vertical; }
.grade-btns { display: flex; gap: 8px; }
.grade-btn { flex: 1; padding: 10px 4px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 700; text-align: center; border: 2px solid transparent; }
.grade-btn.A { border-color: #F59E0B; background: #FEF3C7; color: #D97706; }
.grade-btn.A.active { background: #F59E0B; color: #fff; }
.grade-btn.B { border-color: #3B82F6; background: #DBEAFE; color: #1D4ED8; }
.grade-btn.B.active { background: #3B82F6; color: #fff; }
.grade-btn.C { border-color: #9CA3AF; background: #F3F4F6; color: #6B7280; }
.grade-btn.C.active { background: #9CA3AF; color: #fff; }
.save-btn { width: 100%; padding: 14px; background: #1a1a2e; color: #fff; border: none; border-radius: 12px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 8px; }
.save-btn:disabled { opacity: 0.5; }
.detail-body { padding: 16px 16px 40px; }
.detail-img { width: 100%; border-radius: 12px; margin-bottom: 14px; max-height: 240px; object-fit: cover; }
.detail-card { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 10px; }
.detail-artist { font-size: 22px; font-weight: 800; color: #1F2937; }
.detail-album { font-size: 16px; color: #6B7280; margin-top: 4px; }
.detail-tags { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.section-label { font-size: 11px; font-weight: 700; color: #9CA3AF; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.detail-text { font-size: 14px; color: #374151; line-height: 1.6; }
.stats-body { padding: 16px; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.stat-card { border-radius: 12px; padding: 16px; text-align: center; }
.stat-num { font-size: 32px; font-weight: 800; }
.stat-label { font-size: 13px; margin-top: 4px; }
.export-btn { width: 100%; padding: 14px; background: #065F46; color: #fff; border: none; border-radius: 12px; font-size: 15px; font-weight: 700; cursor: pointer; margin-bottom: 16px; display: block; text-decoration: none; text-align: center; }
.toast { position: fixed; bottom: 90px; left: 50%; transform: translateX(-50%); padding: 10px 20px; border-radius: 20px; font-size: 14px; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999; display: none; }
.toast.success { background: #D1FAE5; color: #065F46; }
.toast.error { background: #FEE2E2; color: #991B1B; }
.batch-queue { background: #fff; border-radius: 12px; padding: 12px; margin-bottom: 12px; }
.batch-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #F3F4F6; font-size: 13px; }
.batch-item:last-child { border-bottom: none; }
</style>
</head>
<body>
<div id="main-view">
  <div class="header">
    <h1>&#127925; 黑膠庫存管理</h1>
    <button class="icon-btn" onclick="showStats()">&#128202;</button>
  </div>
  <div class="filter-bar">
    <input class="search-input" id="search-input" placeholder="搜尋藝人 / 專輯 / 廠牌..." oninput="renderList()">
    <div class="grade-filters">
      <button class="grade-filter-btn active" onclick="setGradeFilter(this,'all')">全部</button>
      <button class="grade-filter-btn" onclick="setGradeFilter(this,'A')">A級</button>
      <button class="grade-filter-btn" onclick="setGradeFilter(this,'B')">B級</button>
      <button class="grade-filter-btn" onclick="setGradeFilter(this,'C')">C級</button>
    </div>
  </div>
  <div class="count-bar" id="count-bar">共 0 張</div>
  <div class="record-list" id="record-list">
    <div class="empty"><div class="empty-icon">&#128230;</div><div>還沒有任何庫存<br>點擊下方「＋」開始新增</div></div>
  </div>
  <button class="fab" onclick="showAdd()">＋</button>
</div>
<div class="panel" id="add-panel">
  <div class="panel-header">
    <button class="back-btn" onclick="closeAdd()">← 返回</button>
    <h2>新增唱片</h2>
    <div style="width:48px"></div>
  </div>
  <div class="form-body">
    <div class="photo-zone" id="photo-zone">
      <div class="photo-placeholder" id="photo-placeholder">
        <div style="font-size:40px">&#128191;</div>
        <div style="margin-top:8px;font-size:14px">單張拍照辨識</div>
      </div>
      <img id="preview-img" style="display:none;width:100%;height:100%;object-fit:cover;" alt="preview">
    </div>
    <label class="upload-btn-label" for="file-input">&#128247; 單張拍照 / 選取（AI辨識）</label>
    <input type="file" id="file-input" accept="image/*" style="display:none" onchange="handleFileChange(this)">
    <label class="batch-btn-label" for="batch-input">&#128230; 批量上傳多張（自動排隊辨識）</label>
    <input type="file" id="batch-input" accept="image/*" multiple style="display:none" onchange="handleBatchChange(this)">
    <div class="ai-bar" id="ai-bar"></div>
    <div id="batch-queue-wrap" style="display:none"><div class="batch-queue" id="batch-queue"></div></div>
    <div class="form-grid">
      <div class="field"><label>藝人 / 樂團</label><input id="f-artist" placeholder="藝人名稱"></div>
      <div class="field"><label>專輯名稱</label><input id="f-album" placeholder="專輯名稱"></div>
      <div class="field"><label>年份</label><input id="f-year" placeholder="例：1976"></div>
      <div class="field"><label>唱片公司</label><input id="f-label" placeholder="廠牌"></div>
      <div class="field"><label>音樂類型</label><input id="f-genre" placeholder="例：Jazz"></div>
      <div class="field"><label>估計市場價值</label><input id="f-value" placeholder="例：NT$300-500"></div>
    </div>
    <div class="field">
      <label>格式</label>
      <select id="f-format">
        <option>LP (33轉)</option><option>SP/78轉蟲膠</option><option>EP (45轉)</option><option>其他</option>
      </select>
    </div>
    <div class="field">
      <label>等級分類</label>
      <div class="grade-btns">
        <button class="grade-btn A" onclick="setGrade('A')">A級</button>
        <button class="grade-btn B active" onclick="setGrade('B')">B級</button>
        <button class="grade-btn C" onclick="setGrade('C')">C級</button>
      </div>
    </div>
    <div class="field"><label>品相說明</label><input id="f-condition" placeholder="例：封面八成新，黑膠無刮傷"></div>
    <div class="field"><label>曲目</label><textarea id="f-tracks" rows="3" placeholder="歌曲名稱（AI可自動辨識）"></textarea></div>
    <div class="field"><label>備註</label><textarea id="f-notes" rows="2" placeholder="收藏價值、特殊說明..."></textarea></div>
    <button class="save-btn" id="save-btn" onclick="saveRecord()">&#128190; 儲存到庫存</button>
  </div>
</div>
<div class="panel" id="detail-panel">
  <div class="panel-header">
    <button class="back-btn" onclick="closeDetail()">← 返回</button>
    <h2>唱片詳情</h2>
    <button class="danger-btn" onclick="deleteRecord()">刪除</button>
  </div>
  <div class="detail-body" id="detail-body"></div>
</div>
<div class="panel" id="stats-panel">
  <div class="panel-header">
    <button class="back-btn" onclick="document.getElementById('stats-panel').classList.remove('open')">← 返回</button>
    <h2>庫存統計</h2>
    <div style="width:48px"></div>
  </div>
  <div class="stats-body" id="stats-body"></div>
</div>
<div class="toast" id="toast"></div>
<script>
var records=[],currentGrade='all',currentRecord=null,currentGradeSelected='B',uploadedImageUrl='',batchQueue=[],batchProcessing=false;
function fetchRecords(){fetch('/api/records').then(function(r){return r.json();}).then(function(d){records=d;renderList();}).catch(function(){records=[];renderList();});}
function getFiltered(){var q=document.getElementById('search-input').value.toLowerCase();return records.filter(function(r){if(currentGrade!=='all'&&r.grade!==currentGrade)return false;if(q&&(r.artist+' '+r.album+' '+r.label).toLowerCase().indexOf(q)===-1)return false;return true;});}
function renderList(){var f=getFiltered();document.getElementById('count-bar').textContent='共 '+f.length+' 張'+(currentGrade!=='all'||document.getElementById('search-input').value?'（已篩選）':'');var el=document.getElementById('record-list');var gl={A:'A級',B:'B級',C:'C級'};if(!f.length){el.innerHTML='<div class="empty"><div class="empty-icon">'+(records.length===0?'&#128230;':'&#128269;')+'</div><div>'+(records.length===0?'還沒有任何庫存<br>點擊下方「＋」開始新增':'找不到符合的唱片')+'</div></div>';return;}el.innerHTML=f.map(function(r){return'<div class="record-row" onclick="showDetail(\''+r.id+'\')">'+'<div class="thumb">'+(r.image_url?'<img src="'+r.image_url+'" onerror="this.parentElement.textContent=\'&#127925;\'">':'&#127925;')+'</div>'+'<div class="record-info"><div class="record-artist">'+(r.artist||'未知藝人')+'</div><div class="record-album">'+(r.album||'未知專輯')+'</div>'+'<div class="record-tags"><span class="tag tag-'+r.grade+'">'+(gl[r.grade]||r.grade)+'</span>'+'<span class="tag tag-fmt">'+(r.format||'').replace(' (33轉)','').replace('/78轉蟲膠','')+'</span>'+(r.year?'<span class="tag tag-fmt">'+r.year+'</span>':'')+'</div></div><div class="chevron">›</div></div>';}).join('');}
function setGradeFilter(btn,grade){document.querySelectorAll('.grade-filter-btn').forEach(function(b){b.classList.remove('active');});btn.classList.add('active');currentGrade=grade;renderList();}
function showAdd(){resetForm();document.getElementById('add-panel').classList.add('open');}
function closeAdd(){document.getElementById('add-panel').classList.remove('open');}
function resetForm(){['artist','album','year','label','genre','value','condition','tracks','notes'].forEach(function(k){var e=document.getElementById('f-'+k);if(e)e.value='';});document.getElementById('f-format').value='LP (33轉)';document.getElementById('preview-img').style.display='none';document.getElementById('photo-placeholder').style.display='block';document.getElementById('ai-bar').className='ai-bar';document.getElementById('file-input').value='';document.getElementById('batch-input').value='';document.getElementById('batch-queue-wrap').style.display='none';document.getElementById('batch-queue').innerHTML='';uploadedImageUrl='';batchQueue=[];setGrade('B');}
function setGrade(g){currentGradeSelected=g;document.querySelectorAll('.grade-btn').forEach(function(b){b.classList.remove('active');});var b=document.querySelector('.grade-btn.'+g);if(b)b.classList.add('active');}
function handleFileChange(input){var file=input.files[0];if(!file)return;var reader=new FileReader();reader.onload=function(e){document.getElementById('preview-img').src=e.target.result;document.getElementById('preview-img').style.display='block';document.getElementById('photo-placeholder').style.display='none';};reader.readAsDataURL(file);showAiBar('loading','上傳圖片中...');var fd=new FormData();fd.append('file',file);fetch('/api/upload',{method:'POST',body:fd}).then(function(r){return r.json();}).then(function(d){uploadedImageUrl=d.url;showAiBar('loading','AI 辨識中...');return fetch('/api/ai-recognize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_url:uploadedImageUrl});}).then(function(r){return r.json();});}).then(function(info){fillForm(info);showAiBar('done','AI辨識完成，請確認並補充資料');}).catch(function(){showAiBar('error','辨識失敗，請手動輸入');});}
function fillForm(info){if(info.artist)document.getElementById('f-artist').value=info.artist;if(info.album)document.getElementById('f-album').value=info.album;if(info.year)document.getElementById('f-year').value=info.year;if(info.label)document.getElementById('f-label').value=info.label;if(info.genre)document.getElementById('f-genre').value=info.genre;if(info.condition)document.getElementById('f-condition').value=info.condition;if(info.tracks)document.getElementById('f-tracks').value=info.tracks;if(info.notes)document.getElementById('f-notes').value=info.notes;if(info.estimated_value)document.getElementById('f-value').value=info.estimated_value;if(info.suggested_grade)setGrade(info.suggested_grade);if(info.format){if(info.format.indexOf('SP')!==-1||info.format.indexOf('78')!==-1)document.getElementById('f-format').value='SP/78轉蟲膠';else if(info.format.indexOf('EP')!==-1)document.getElementById('f-format').value='EP (45轉)';}}
function handleBatchChange(input){var files=Array.from(input.files);if(!files.length)return;batchQueue=files.map(function(f,i){return{file:f,status:'待處理',name:f.name,index:i};});document.getElementById('batch-queue-wrap').style.display='block';renderBatchQueue();processBatchQueue();}
function renderBatchQueue(){var el=document.getElementById('batch-queue');var icons={'待處理':'⏳','處理中':'🔄','完成':'✅','失敗':'❌'};var done=batchQueue.filter(function(i){return i.status==='完成';}).length;var pct=batchQueue.length?Math.round(done/batchQueue.length*100):0;el.innerHTML='<div style="font-size:12px;font-weight:700;color:#6B7280;margin-bottom:8px">批量進度 '+done+'/'+batchQueue.length+'</div>'+batchQueue.map(function(item){return'<div class="batch-item"><span style="width:20px;text-align:center">'+(icons[item.status]||'⏳')+'</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+item.name+'</span><span style="color:#9CA3AF;font-size:11px">'+item.status+'</span></div>';}).join('')+'<div class="progress-bar-wrap"><div class="progress-bar" style="width:'+pct+'%"></div></div><div style="text-align:right;font-size:12px;color:#6B7280">'+pct+'%</div>';}
function processBatchQueue(){if(batchProcessing)return;batchProcessing=true;var i=0;function next(){if(i>=batchQueue.length){batchProcessing=false;fetchRecords();var done=batchQueue.filter(function(x){return x.status==='完成';}).length;showToast('批量完成！共 '+done+' 張已存入庫存');return;}batchQueue[i].status='處理中';renderBatchQueue();var fd=new FormData();fd.append('file',batchQueue[i].file);var idx=i;fetch('/api/upload',{method:'POST',body:fd}).then(function(r){return r.json();}).then(function(up){return fetch('/api/ai-recognize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_url:up.url})}).then(function(r){return r.json();}).then(function(info){var fmt='LP (33轉)';if(info.format&&(info.format.indexOf('SP')!==-1||info.format.indexOf('78')!==-1))fmt='SP/78轉蟲膠';else if(info.format&&info.format.indexOf('EP')!==-1)fmt='EP (45轉)';return fetch('/api/records',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({artist:info.artist||'',album:info.album||'',year:info.year||'',label:info.label||'',genre:info.genre||'',format:fmt,grade:info.suggested_grade||'B',condition:info.condition||'',tracks:info.tracks||'',notes:info.notes||'',estimated_value:info.estimated_value||'',image_url:up.url})});});}).then(function(){batchQueue[idx].status='完成';}).catch(function(){batchQueue[idx].status='失敗';}).then(function(){renderBatchQueue();i++;next();});}next();}
function showAiBar(type,msg){var el=document.getElementById('ai-bar');el.className='ai-bar '+type;el.textContent=msg;}
function saveRecord(){var artist=document.getElementById('f-artist').value;var album=document.getElementById('f-album').value;if(!artist&&!album){showToast('請至少填寫藝人或專輯名稱','error');return;}document.getElementById('save-btn').disabled=true;fetch('/api/records',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({artist:artist,album:album,year:document.getElementById('f-year').value,label:document.getElementById('f-label').value,genre:document.getElementById('f-genre').value,format:document.getElementById('f-format').value,grade:currentGradeSelected,condition:document.getElementById('f-condition').value,tracks:document.getElementById('f-tracks').value,notes:document.getElementById('f-notes').value,estimated_value:document.getElementById('f-value').value,image_url:uploadedImageUrl})}).then(function(){fetchRecords();showToast('已新增 '+(artist||album));closeAdd();}).catch(function(){showToast('儲存失敗','error');}).then(function(){document.getElementById('save-btn').disabled=false;});}
function showDetail(id){currentRecord=null;for(var i=0;i<records.length;i++){if(records[i].id===id){currentRecord=records[i];break;}}if(!currentRecord)return;var r=currentRecord;var gc={A:'#D97706',B:'#1D4ED8',C:'#6B7280'};var gb={A:'#FEF3C7',B:'#DBEAFE',C:'#F3F4F6'};var gl={A:'A級精品',B:'B級流通',C:'C級散貨'};var html=(r.image_url?'<img class="detail-img" src="'+r.image_url+'">';':'')+' <div class="detail-card"><div class="detail-artist">'+(r.artist||'未知藝人')+'</div><div class="detail-album">'+(r.album||'未知專輯')+'</div><div class="detail-tags"><span class="tag" style="background:'+(gb[r.grade]||'#F3F4F6')+';color:'+(gc[r.grade]||'#6B7280')+';font-size:13px;padding:3px 10px">'+(gl[r.grade]||r.grade)+'</span><span class="tag tag-fmt" style="font-size:13px;padding:3px 10px">'+(r.format||'')+'</span>'+(r.year?'<span class="tag tag-fmt" style="font-size:13px;padding:3px 10px">'+r.year+'</span>':'')+(r.label?'<span class="tag tag-fmt" style="font-size:13px;padding:3px 10px">'+r.label+'</span>':'')+'</div></div><div class="detail-card"><div class="section-label">快速改等級</div><div class="grade-btns" style="margin-top:8px"><button class="grade-btn A '+(r.grade==='A'?'active':'')+'" onclick="quickUpdateGrade(\'A\')">A級</button><button class="grade-btn B '+(r.grade==='B'?'active':'')+'" onclick="quickUpdateGrade(\'B\')">B級</button><button class="grade-btn C '+(r.grade==='C'?'active':'')+'" onclick="quickUpdateGrade(\'C\')">C級</button></div></div>';[['音樂類型',r.genre],['品相',r.condition],['估計市場價值',r.estimated_value],['曲目',r.tracks],['備註',r.notes]].forEach(function(f){if(f[1])html+='<div class="detail-card"><div class="section-label">'+f[0]+'</div><div class="detail-text" style="margin-top:4px">'+f[1]+'</div></div>';});html+='<div style="text-align:center;color:#9CA3AF;font-size:12px;margin-top:8px">建立：'+(r.created_at||'').slice(0,10)+'</div>';document.getElementById('detail-body').innerHTML=html;document.getElementById('detail-panel').classList.add('open');}
function closeDetail(){document.getElementById('detail-panel').classList.remove('open');currentRecord=null;}
function quickUpdateGrade(grade){if(!currentRecord)return;var id=currentRecord.id;fetch('/api/records/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({grade:grade})}).then(function(){fetchRecords();showToast('等級已更新');showDetail(id);}).catch(function(){showToast('更新失敗','error');});}
function deleteRecord(){if(!currentRecord||!confirm('確定刪除？'))return;var id=currentRecord.id;fetch('/api/records/'+id,{method:'DELETE'}).then(function(){fetchRecords();closeDetail();showToast('已刪除');}).catch(function(){showToast('刪除失敗','error');});}
function showStats(){var total=records.length;var A=records.filter(function(r){return r.grade==='A';}).length;var B=records.filter(function(r){return r.grade==='B';}).length;var C=records.filter(function(r){return r.grade==='C';}).length;var SP=records.filter(function(r){return r.format==='SP/78轉蟲膠';}).length;var sd=[['總計',total,'#1F2937','#F9FAFB'],['A級精品',A,'#D97706','#FEF3C7'],['B級流通',B,'#1D4ED8','#DBEAFE'],['C級散貨',C,'#6B7280','#F3F4F6'],['78轉蟲膠',SP,'#7C3AED','#EDE9FE']];var html='<div class="stats-grid">'+sd.map(function(s){return'<div class="stat-card" style="background:'+s[3]+'"><div class="stat-num" style="color:'+s[2]+'">'+s[1]+'</div><div class="stat-label" style="color:'+s[2]+'">'+s[0]+'</div></div>';}).join('')+'</div><a href="/api/export-csv" class="export-btn">匯出 CSV</a><div class="detail-card"><div class="section-label">各格式分佈</div>';['LP (33轉)','SP/78轉蟲膠','EP (45轉)','其他'].forEach(function(f){var cnt=records.filter(function(r){return r.format===f;}).length;if(cnt)html+='<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #F3F4F6"><span style="font-size:14px;color:#374151">'+f+'</span><span style="font-weight:700;color:#1F2937">'+cnt+' 張</span></div>';});html+='</div>';document.getElementById('stats-body').innerHTML=html;document.getElementById('stats-panel').classList.add('open');}
function showToast(msg,type){var el=document.getElementById('toast');el.className='toast '+(type||'success');el.textContent=msg;el.style.display='block';setTimeout(function(){el.style.display='none';},3000);}
fetchRecords();
</script>
</body>
</html>"""


def load_inventory():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_inventory(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/")
def index():
    return HTML


@app.route("/api/records", methods=["GET"])
def get_records():
    return jsonify(load_inventory())


@app.route("/api/records", methods=["POST"])
def add_record():
    data = request.json
    inventory = load_inventory()
    record = {
        "id": str(uuid.uuid4()),
        "artist": data.get("artist", ""),
        "album": data.get("album", ""),
        "year": data.get("year", ""),
        "label": data.get("label", ""),
        "format": data.get("format", "LP (33轉)"),
        "genre": data.get("genre", ""),
        "grade": data.get("grade", "B"),
        "condition": data.get("condition", ""),
        "tracks": data.get("tracks", ""),
        "notes": data.get("notes", ""),
        "estimated_value": data.get("estimated_value", ""),
        "image_url": data.get("image_url", ""),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    inventory.insert(0, record)
    save_inventory(inventory)
    return jsonify(record), 201


@app.route("/api/records/<record_id>", methods=["PUT"])
def update_record(record_id):
    data = request.json
    inventory = load_inventory()
    for i, r in enumerate(inventory):
        if r["id"] == record_id:
            inventory[i].update(data)
            inventory[i]["updated_at"] = datetime.now().isoformat()
            save_inventory(inventory)
            return jsonify(inventory[i])
    return jsonify({"error": "Not found"}), 404


@app.route("/api/records/<record_id>", methods=["DELETE"])
def delete_record(record_id):
    inventory = load_inventory()
    inventory = [r for r in inventory if r["id"] != record_id]
    save_inventory(inventory)
    return jsonify({"ok": True})


@app.route("/api/upload", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["file"]
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    filename = str(uuid.uuid4()) + "." + ext
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    return jsonify({"url": "/uploads/" + filename})


@app.route("/uploads/<filename>")
def serve_upload(filename):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/ai-recognize", methods=["POST"])
def ai_recognize():
    data = request.json
    image_url = data.get("image_url", "")
    filename = image_url.replace("/uploads/", "")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Image not found"}), 404
    with open(filepath, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    ext = filepath.rsplit(".", 1)[-1].lower()
    media_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/" + ext
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": '你是黑膠唱片專家。分析圖片，只回傳JSON：{"artist":"","album":"","year":"","label":"","format":"","genre":"","tracks":"","condition":"","suggested_grade":"A或B或C","estimated_value":"台幣範圍","notes":""}'}
        ]}]
    )
    text = message.content[0].text
    try:
        clean = text.replace("```json", "").replace("```", "").strip()
        return jsonify(json.loads(clean))
    except:
        return jsonify({})


@app.route("/api/export-csv")
def export_csv():
    import csv, io
    inventory = load_inventory()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["藝人","專輯","年份","廠牌","格式","類型","等級","品相","曲目","估計價值","備註","建立時間"])
    for r in inventory:
        writer.writerow([r.get("artist",""),r.get("album",""),r.get("year",""),r.get("label",""),r.get("format",""),r.get("genre",""),r.get("grade",""),r.get("condition",""),r.get("tracks",""),r.get("estimated_value",""),r.get("notes",""),r.get("created_at","")[:10]])
    return Response("\ufeff"+output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=vinyl_inventory.csv"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
