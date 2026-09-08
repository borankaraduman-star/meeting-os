"""Explicit user-supplied plain text; never an audio transcription or identity claim."""
import json,re,uuid
from datetime import datetime,timezone
MAX_BYTES=1048576
STAMP=re.compile(r'^\[(\d{1,3}:\d{2}(?::\d{2})?)\]\s*(.*)$')
NAME=re.compile(r"^([\wÇĞİÖŞÜçğıöşü .’'\-]{1,60}):\s+(.+)$")
def preview(text):
    if not isinstance(text,str) or not text.strip():raise ValueError('Aktarılacak metin boş olamaz.')
    try:size=len(text.encode('utf-8'))
    except UnicodeError:raise ValueError('Metin UTF-8 olarak okunamadı.')
    if size>MAX_BYTES:raise ValueError('Metin en fazla 1 MB olabilir.')
    if any(ord(c)<32 and c not in '\n\r\t' for c in text):raise ValueError('Dosya düz metin değil veya bozuk karakter içeriyor. UTF-8 .txt kullanın.')
    rows=[]
    for line in text.splitlines():
        content=line.strip()
        if not content:continue
        start=None;name=None
        match=STAMP.match(content)
        if match:
            parts=[int(x) for x in match[1].split(':')]
            if parts[-1]>=60 or (len(parts)==3 and parts[1]>=60):raise ValueError('Geçersiz zaman damgası; [MM:SS] veya [HH:MM:SS] kullanın.')
            start=parts[-1]+60*parts[-2]+(3600*parts[0] if len(parts)==3 else 0);content=match[2]
        bracket=re.match(r'^\[([^\]\d:]{1,60})\]\s+(.+)$',content)
        labeled=NAME.match(content)
        if bracket or labeled:
            m=bracket or labeled;name=m[1].strip();content=m[2]
        if not content.strip():raise ValueError('Zaman damgasından sonra metin bulunamadı.')
        rows.append({'start':start,'end':None,'text':content,'source':'chatgpt_manual','speaker':'unknown','speaker_name':name,'flags':['imported_text']+(['untimed'] if start is None else [])+(['speaker_unverified'] if name else []),'metrics':{},'words':[],'embedding':None,'embedding_model':None})
        if len(rows)>1000:raise ValueError('En fazla 1000 metin satırı aktarılabilir.')
    return {'rows':rows,'source':'chatgpt_manual'}
def save(store,title,text):
    data=preview(text)
    if not isinstance(title,str) or not title.strip() or len(title)>200:raise ValueError('1–200 karakterlik bir toplantı adı girin.')
    mid=uuid.uuid4().hex[:12]
    meta={'text_only':True,'imported_from':'chatgpt_manual','raw_source_text':text,'import_format':'plain-text-v1','audio_available':False}
    with store.db:
        store.db.execute('INSERT INTO meetings VALUES(?,?,?,?,?)',(mid,title.strip(),datetime.now(timezone.utc).isoformat(),'complete',json.dumps(meta,ensure_ascii=False)))
        for row in data['rows']:
            store.db.execute('INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES(?,?,?,?,?,?,?)',(mid,row['start'],row['end'],row['source'],row['speaker'],row['speaker_name'],json.dumps(row,ensure_ascii=False)))
    return {'meeting':mid}
