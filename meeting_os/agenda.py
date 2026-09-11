"""Next-meeting preparation: open tasks, unanswered questions and decisions from recent meetings, with sources.
Draft only — nothing is sent anywhere."""
from .insights import prepared_header, source_line
from .memory import Memory


def build_agenda(store, limit=5):
    memory=Memory(store)
    meetings=[m for m in store.meetings() if m['status']=='complete'][:limit]
    titles={m['id']:m['title'] for m in meetings}
    open_tasks=[t for t in memory.actions() if t.get('state') in ('open','in_progress') and t.get('meeting') in titles]
    questions=[];decisions=[]
    for m in meetings:
        latest=memory.latest(m['id'])
        if not latest: continue
        payload=latest.get('payload') or {}
        # `visible` and the text itself are the user's layer: a question they removed is not on their agenda,
        # and a decision they reworded goes out in their words. `Memory.latest` already applied the layer.
        from .insight_layer import visible
        for q in visible(payload.get('questions',[])): questions.append({'meeting':m['id'],'title':m['title'],'text':q.get('text'),'evidence':q.get('evidence',[])})
        for d in visible(payload.get('decisions',[])): decisions.append({'meeting':m['id'],'title':m['title'],'text':d.get('text'),'evidence':d.get('evidence',[])})
    return {'meetings':[{'id':m['id'],'title':m['title'],'created':m['created']} for m in meetings],'open_tasks':open_tasks,'questions':questions,'decisions':decisions}


def render_agenda(agenda):
    lines=prepared_header('Sonraki toplantı gündemi (taslak)','Kaynak toplantılar: '+', '.join(m['title'] for m in agenda['meetings']),
                          'Bu taslak yalnız kayıtlı toplantılardan çıkarılmıştır; dışarı otomatik gönderilmez. Her maddeyi kaynağıyla doğrulayın.')
    lines+=['## Açık görevler']
    if not agenda['open_tasks']: lines.append('- Açık görev yok.')
    for t in agenda['open_tasks']:
        lines.append(f"- {t['title']} · {t.get('owner') or 'sahibi belirsiz'} · {t.get('due_text') or 'tarih yok'} · {t.get('state')}"+(' · GÜNCEL DEĞİL' if t.get('stale') else ''))
    lines+=['','## Cevapsız sorular']
    if not agenda['questions']: lines.append('- Kayıtlı açık soru yok.')
    for q in agenda['questions']:
        lines.append(f"- {q['text']}  ({q['title']})")
        for e in q['evidence'][:1]: lines.append(source_line(e))
    lines+=['','## Alınan kararlar (hatırlatma)']
    if not agenda['decisions']: lines.append('- Kayıtlı karar yok.')
    for d in agenda['decisions']:
        lines.append(f"- {d['text']}  ({d['title']})")
        for e in d['evidence'][:1]: lines.append(source_line(e))
    lines+=['','## Bu toplantıda konuşulacaklar','- (buraya yaz)','']
    return '\n'.join(lines)
