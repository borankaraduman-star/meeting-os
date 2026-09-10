"""Generation-time JSON constraints; semantic/source verification remains mandatory."""
def analysis_schema(ids,summary_only=False,summary_max=12):
    evidence={'type':'array','minItems':1,'maxItems':4,'items':{'type':'object','properties':{'segment_id':{'type':'integer','enum':sorted(set(ids))},'quote':{'type':'string','minLength':1}},'required':['segment_id','quote'],'additionalProperties':False}}
    item={'type':'object','properties':{'text':{'type':'string','minLength':1},'evidence':evidence},'required':['text','evidence'],'additionalProperties':False}
    action={'type':'object','properties':{'title':{'type':'string','minLength':1},'owner':{'type':['string','null']},'due_text':{'type':['string','null']},'evidence':evidence},'required':['title','owner','due_text','evidence'],'additionalProperties':False}
    keys=['summary'] if summary_only else ['summary','decisions','risks','questions','actions']
    # summary: one bullet per topic (Boran, 11 Sep 2026: "özetler çok çok özet, bir şeyleri kaçırıyor"); the other lists keep 8.
    return {'type':'object','properties':{key:{'type':'array','maxItems':summary_max if key=='summary' else 8,'items':action if key=='actions' else item} for key in keys},'required':keys,'additionalProperties':False}
